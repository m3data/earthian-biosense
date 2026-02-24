## Phase A Finding Under Review
`findings-a/03-phase-space-dynamics-validity.md` — Phase A verdict: **PARTIAL**

Phase A examined whether phase space dynamics (velocity, curvature, stability) are computed from a valid 3D trajectory manifold. It found velocity mathematically sound, curvature mislabeled, stability a heuristic proxy, and the "manifold" claim aspirational rather than mathematical. Verdict was PARTIAL.

## Phase A Verdict
PARTIAL — code is operationally coherent with consistent math, but vocabulary ("manifold," "curvature," "stability") implies theoretical grounding the implementation does not deliver.

## Counter-Evidence

Independent re-read of `phase.py` (full file) and `movement.py:104–198` (ModeHistory). Four specific questions investigated.

---

### 1. Is this genuinely a phase space or just a feature space with trajectory metaphors?

Phase A correctly classified this as "a 3D Euclidean feature space" and noted the "manifold" claim is aspirational. This finding is accurate but understates how far the implementation is from either of the two legitimate meanings of "phase space."

In dynamical systems, a phase space has coordinates whose values at time *t* determine the system's future evolution — the coordinates are state variables, not derived aggregates. The three axes here are:
- `entrainment`: autocorrelation of RR intervals over a rolling window (a derived aggregate)
- `breath_rate_norm`: respiratory rate normalized from a rolling estimate (a derived aggregate)
- `amplitude_norm`: RR amplitude normalized from a rolling estimate (a derived aggregate)

None are raw state variables; all are smoothed, windowed summary statistics. A true phase space for HRV would typically use the Takens delay-embedding of raw RR intervals to reconstruct an attractor — that is not done here.

The module docstring (phase.py:2–4) reads "Treats each moment as a point on a trajectory in a 3D manifold, not a dot on a line." The "phase" in the module title and docstring appears to reference the EECP concept of breath-heart phase coupling, not dynamical systems phase space. The terminology conflation is in the name of the module and class (`PhaseTrajectory`, `PhaseState`, `PhaseDynamics`), not just the "manifold" word.

Phase A caught the manifold issue but did not flag that the "phase space" framing itself is a misnomer in the dynamical systems sense. The full scope: the module name, the class names, and the field names all inherit the same conceptual overclaim.

---

### 2. Are the dynamical quantities (velocity, curvature) physically meaningful or arbitrary derivatives?

**Velocity** (phase.py:225–228): Valid first-order finite difference. Rate of change of the three feature coordinates with respect to time. Internally consistent, though the Euclidean combination of coordinates with different physiological origins is not formally justified. Phase A's assessment is accurate.

**Curvature as acceleration magnitude**: Phase A correctly identified the key error — `|r''(t)|` is computed rather than geometric curvature κ = |r'(t) × r''(t)| / |r'(t)|³. This audit confirms: the divergence is largest at low speeds, where a slow curve and a slow acceleration are indistinguishable, and at high speeds where the denominator (speed³) would substantially suppress the curvature value.

**Additional issue Phase A missed — naming collision in `PhaseDynamics`:**

The dataclass (phase.py:85) has a field named `acceleration_magnitude` with comment "Acceleration magnitude for movement annotation." But this is NOT the same as `curvature`. Tracing the assignment (phase.py:327):
```
acceleration_magnitude=abs(mode_score_accel)
```
`mode_score_accel` (phase.py:292) is the second derivative of the scalar `mode_score` (a 1D HRV summary) — not the 3D phase acceleration. The `curvature` field (line 244) is the 3D acceleration magnitude from the phase-space trajectory. Both fields are described as "acceleration magnitude" but they measure completely different quantities on different signals. A downstream consumer reading `acceleration_magnitude` from `PhaseDynamics` would receive the mode_score derivative, not the 3D trajectory acceleration.

**Non-uniform sampling in second derivative**: `dt_avg = (dt1 + dt2) / 2` (phase.py:239) is used to compute acceleration from two velocity estimates at different time gaps. This is an approximation — the proper non-uniform-grid second derivative formula is more complex. For irregular update cadences (e.g., 4s gap followed by 6s gap), the denominator underestimates or overestimates the true second derivative. Phase A did not flag this.

---

### 3. Does the stability metric have predictive value or is it just inverse velocity?

Phase A correctly described stability as a heuristic proxy. The formula `1 / (1 + 2*(|v| + 0.5*|a|))` combines velocity and curvature (acceleration magnitude), so it is not merely inverse velocity — it distinguishes slow-but-accelerating from fast-but-steady trajectories.

Two additional observations:

**The claim of "predictive value"** is never made by the code itself. The docstring and field comment say "low curvature & low velocity → high stability" — a definitional statement, not a validation claim. The audit questions whether stability has predictive value, but the code makes no such claim. The audit question is therefore asking more than the code asserts. The real concern is whether the *label* "stability" implies predictive validity that the code does not establish. That is a vocabulary-precision issue, consistent with Phase A's characterization.

**The cold-start default of 0.5** (phase.py:199) for stability differs from `EMPTY_DYNAMICS` which sets stability to 0.0 (phase.py:95). If code consumers use `EMPTY_DYNAMICS` as a sentinel and compare its stability against live computation during warm-up, they will get inconsistent behavior: live warm-up returns 0.5, sentinel returns 0.0. Phase A did not flag this.

---

### 4. What happens with the trajectory history — is there a memory leak or unbounded growth?

**Phase A's treatment was incomplete.** Phase A noted the `history_signature` 0.5 scaling constant as an undocumented "magic number" but did not identify the underlying semantic mismatch.

**`cumulative_path_length` semantic bug:**

`self.cumulative_path_length` (phase.py:122) accumulates total session path across all updates. It is never decremented. The deque `self.states` is bounded at `maxlen=30` (~30 seconds of history), but `cumulative_path_length` continues growing throughout the session.

`history_signature` is computed at phase.py:256–260:
```python
window_time = new_state.timestamp - self.states[0].timestamp
window_time = max(window_time, 1.0)
history_signature = self.cumulative_path_length / window_time
history_signature = min(1.0, history_signature / 0.5)
```

`self.states[0]` is the oldest item in the 30-element bounded deque — at most ~30 seconds old. `cumulative_path_length` is the total distance traveled since session start. So `history_signature` computes:

> (total path from session start) / (time span of last 30 states)

This is neither a windowed path rate nor a total path measure — it is a ratio that grows monotonically as the session lengthens, since the numerator is unbounded while the denominator is capped at ~30 seconds. With any non-trivial biosignal movement, `history_signature` will reach its `min(1.0, ...)` saturation ceiling within the first few minutes of a session and remain there for the rest of the session. Once saturated it conveys no information.

The docstring in the class header (phase.py:111) describes this as "History signature (path integral)" — which implies windowed behavior. Phase A's note about the 0.5 constant being undocumented is correct but secondary; the more fundamental problem is that the metric is broken by design for any session longer than a few minutes.

**`ModeHistory` is properly bounded**: `max_history=100` entries (movement.py:118), with pruning at line 143–144 (`self.history = self.history[-self.max_history:]`). This is adequate for typical session durations.

**`_last_velocity` dead code** (phase.py:123, 247): Phase A correctly identified this. Confirmed — `_last_velocity` is written on every update and reset on `reset()` but never read by any computation. `prev_velocity` is always recomputed from the deque.

---

## Revised Assessment

**Verdict: DOWNGRADE**

Phase A's PARTIAL verdict is directionally correct but understated two issues:

1. **`history_signature` is semantically broken**, not just under-documented. The `cumulative_path_length` / rolling-window-time ratio saturates early in every real session, rendering the metric a constant 1.0 for the majority of any session. Phase A framed this as a magic-constant concern (the 0.5 divisor); the actual severity is that the metric becomes uninformative within minutes.

2. **Naming collision in `PhaseDynamics.acceleration_magnitude`**: this field returns mode_score scalar acceleration, not 3D trajectory acceleration — making it easy to confuse with `curvature`. Phase A did not identify this.

Both the "phase space" and "manifold" terminology issues are real, as Phase A found. The code is operationally coherent for its immediate use cases (terminal UI, mode classification, coherence). But the `history_signature` issue is more than a vocabulary imprecision — it is an implementation defect affecting metric quality at normal session durations.

## Convergence Notes

**Agreement with Phase A:**
- Velocity computation is mathematically sound (finite difference)
- "Curvature" is acceleration magnitude, not geometric curvature — confirmed
- Stability is a heuristic proxy, not formal dynamical-systems stability — confirmed
- "Manifold" claim is aspirational, not mathematical — confirmed
- `_last_velocity` is dead code — confirmed
- `transition_proximity` is permanently 0.0 — confirmed
- The 3D coordinate space is genuinely used in all downstream computations — confirmed

**Phase B additions / corrections:**
- The "phase space" framing (not just "manifold") is itself a misnomer in the dynamical systems sense — Phase A stopped at manifold
- `history_signature` has a fundamental semantic mismatch (session-cumulative path / rolling-window time), not merely an undocumented scaling constant
- `PhaseDynamics.acceleration_magnitude` names mode_score scalar acceleration, not 3D trajectory acceleration — two different signals given the same conceptual label
- `EMPTY_DYNAMICS.stability = 0.0` conflicts with warm-up default of `stability = 0.5`
- Non-uniform sampling approximation in `dt_avg` introduces second-derivative error with irregular update cadences
