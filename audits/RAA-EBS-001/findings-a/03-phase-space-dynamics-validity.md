## Claim
Phase space dynamics (velocity, curvature, stability) are computed from a valid 3D trajectory manifold with coordinates (entrainment, breath_rate_norm, amplitude_norm).

## Files Examined
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/src/processing/phase.py` — lines 1–481 (full file)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/src/processing/hrv.py` — lines 1–296 (HRVMetrics, coordinate sources)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/src/processing/movement.py` — lines 1–704 (soft mode, hysteresis)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/tests/test_phase.py` — lines 1–185 (test coverage)

## Evidence

### 1. Is a 3D manifold actually used?

`PhaseState.position` is typed as `tuple[float, float, float]` and annotated `(entrainment, breath, amplitude)` (phase.py:41–42). The `_metrics_to_position()` method (phase.py:160–175) maps:

- **Axis 0 — entrainment**: taken directly from `HRVMetrics.entrainment` (0–1, already normalised via autocorrelation in hrv.py:65–106)
- **Axis 1 — breath_rate_norm**: `(breath_rate - 4) / 16` clamped to [0,1]; defaults to 0.5 if `breath_rate is None`
- **Axis 2 — amplitude_norm**: `min(1.0, amplitude / 200)`

All three coordinates are populated on every call. The 3D coordinate space is genuinely used in all downstream computations.

### 2. Are velocity, curvature, and stability computed with mathematically correct formulas?

**Velocity** (phase.py:224–229): First-order forward finite difference over `dt1` (time from previous stored state to new state). Formula is `(pos_new - pos_prev) / dt1` per axis, with `dt1 = max(dt1, 0.001)` to prevent division by zero. Mathematically correct for a first derivative approximation.

**"Curvature"** (phase.py:237–244): Computes the magnitude of the acceleration vector — the second finite difference divided by average `dt`:

```
acceleration[i] = (velocity[i] - prev_velocity[i]) / dt_avg
curvature = |acceleration|
```

This is **not** geometric curvature. The standard formula for 3D curve curvature is κ = |r'(t) × r''(t)| / |r'(t)|³ (cross product of velocity and acceleration divided by speed cubed). The code computes only `|acceleration|`, which equals κ × speed² — they are equivalent only when speed is 1.0. The code comment acknowledges "magnitude of acceleration (second derivative)" but the field is named `curvature` and the docstring uses the curvature framing. At low speeds (near-stationary trajectory), acceleration magnitude and geometric curvature diverge substantially: a slow bend and a fast bend register the same acceleration but very different curvature.

**Stability** (phase.py:249–253): Heuristic proxy — `1 / (1 + (velocity_magnitude + curvature * 0.5) * 2)` clamped to [0,1]. The 0.5 and 2 coefficients are implicit tuning parameters with no documented empirical basis. This is a reasonable engineering proxy mapping "high movement intensity → low stability," but it is not formal dynamical-systems stability (e.g., Lyapunov stability, eigenvalue analysis, basin depth). The docstring comment only says "low curvature & low velocity → high stability," which matches the formula but does not constitute a definition.

### 3. Is trajectory tracking stateful across time steps?

Yes, genuinely stateful. `PhaseTrajectory` maintains:
- `self.states: deque[PhaseState]` — rolling 30-state buffer (phase.py:121)
- `self.cumulative_path_length: float` — path integral, updated on every append (phase.py:151–154)
- `self.mode_history: ModeHistory` — full mode transition history (phase.py:126)
- `self._last_soft_inference`, `self._last_mode_score`, `self._mode_score_velocity` — used for movement annotation continuity

One dead-state issue: `self._last_velocity` is assigned at phase.py:247 but never read in subsequent calls. `prev_velocity` is recomputed from `self.states[-1]` and `self.states[-2]` on every call (phase.py:232–235), making `_last_velocity` stale/unused storage. This is a minor code quality issue, not a correctness defect (the computation uses the correct values from the buffer).

### 4. Is 'stability' well-defined or a proxy metric?

Explicitly a proxy. The formula `1 / (1 + movement_intensity * 2)` with `movement_intensity = velocity_magnitude + curvature * 0.5` is a squashing function over combined motion signals. No formal definition from dynamical systems theory is used. Cold-start (< 2 states) returns `stability=0.5` (neutral), which is a reasonable default. The proxy is self-consistent and bounded [0,1], but the term "stability" implies a stronger claim than the implementation delivers.

### 5. Does the phase space have meaningful geometry or is it an arbitrary coordinate system?

The three axes occupy [0,1] after normalization but carry different physiological origins:
- **Entrainment**: autocorrelation of RR intervals at breath-rate lags (dimensionless)
- **Breath_rate_norm**: breaths/minute linearly scaled to [0,1] over a 4–20 bpm range
- **Amplitude_norm**: RR amplitude in ms linearly scaled to [0,1] over 0–200ms

Euclidean distances are computed between points as if the space is isotropic (phase.py:379–381, used in path integral). This assumes a unit change in entrainment is geometrically equivalent to a unit change in breath rate or amplitude — which is physiologically unexamined. The axis ranges were chosen empirically but their relative scaling is arbitrary.

The module docstring claims "3D manifold" (phase.py:3–4), but the implementation is a 3D Euclidean feature space. There is no metric tensor, no curvature tensor, no geodesics, and no local chart structure. "Manifold" is evocative rather than technically precise.

### 6. Boundary, cold start, and noisy input behaviour

**Cold start** (< 2 states, phase.py:180–210): Returns zero velocity, zero curvature, `stability=0.5`, `phase_label="warming up"`, soft mode still computed. Handled gracefully.

**Minimum dt protection** (phase.py:221–222): `max(dt, 0.001)` prevents division-by-zero. However, two near-simultaneous states (e.g., rapid updates) would produce artificially large velocity and curvature values since 1ms is treated as the minimum separation.

**No input smoothing**: Positions are mapped directly from HRV metrics with no smoothing. A single noisy RR interval can spike `amplitude`, changing axis 2 sharply; the resulting large velocity at t=n and near-zero velocity at t=n+1 produces a large apparent curvature (acceleration). The 30-state buffer does not smooth inputs — it accumulates history.

**history_signature normalization** (phase.py:255–260): Divides path speed by an empirical constant 0.5. This constant is undocumented — it implies that a "maximum reasonable" speed is 0.5 manifold-units/second. No calibration data or rationale is provided.

**trajectory_coherence** (phase.py:403–480): Near-zero velocity variance returns 0.8 (dwelling = high coherence). Negative autocorrelation is clamped to zero, losing information about oscillatory trajectories. The combined score (0.5 × magnitude autocorr + 0.5 × direction coherence) is methodologically reasonable.

## Finding

**Verdict: PARTIAL**

The code genuinely implements a 3D trajectory with stateful history, and velocity computation is mathematically sound. However, the claim as stated overstates the implementation in three respects:

1. **"Curvature" is acceleration magnitude, not geometric curvature.** The standard 3D curvature formula requires dividing by speed cubed, which the code does not do. Near-stationary trajectories will conflate curvature with acceleration. The field name and docstring create a misleading precision claim.

2. **"Stability" is a heuristic proxy, not formal stability.** The formula is intuitive and useful but does not derive from attractor analysis, eigenvalue decomposition, or basin geometry.

3. **The "manifold" claim is aspirational, not mathematical.** The space is a 3D Euclidean feature space with implicit isotropy assumptions. The axes carry different physiological origins that are not formally reconciled by the normalization.

These are not implementation bugs — the trajectory system is operationally coherent, the math is consistent, and the cold-start/boundary handling is appropriate. But the vocabulary ("manifold," "curvature," "stability") implies theoretical grounding that the implementation does not deliver.

## Notes

- The `_last_velocity` attribute at phase.py:123 and the assignment at line 247 is dead code — `prev_velocity` is always recomputed from the deque. This is harmless but could mislead a future developer.
- The 0.5 normalization constant in `history_signature` (line 260) and the 2.0 coefficient in `stability` (line 252) are implicit magic numbers. No test exercises calibration of these constants.
- `transition_proximity` is explicitly deferred (`= 0.0` always, phase.py:263–264) with a comment that it "Will need basin definitions." This is honest but means one of the `PhaseDynamics` fields is permanently a no-op.
- The test suite (test_phase.py) covers the main paths but does not test noisy input behaviour, the `history_signature` scaling, or the edge case where `dt1` is pinned at 0.001.
