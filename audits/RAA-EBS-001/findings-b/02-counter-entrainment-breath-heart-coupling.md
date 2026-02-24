## Phase A Finding Under Review
`findings-a/02-entrainment-breath-heart-coupling.md` — Claim: Entrainment metric captures breath-heart phase coupling (not coherence) on a 0-1 scale.

## Phase A Verdict
**PARTIAL** — 0-1 bounding confirmed. Entrainment/coherence distinction called "genuine and structural." Two material weaknesses identified: (1) not true phase coupling, but RR rhythmicity at breath-frequency lags; (2) `expected_breath_period` parameter unused, breaking the breath-rate-to-entrainment feedback path. Final note expressed uncertainty about whether `compute_trajectory_coherence` is actually called.

## Counter-Evidence

**CE-1: Autocorrelation formula has a normalization error — the clamp is corrective, not design**

`compute_autocorrelation()` (`hrv.py:43–62`) uses mixed denominators: `variance` is computed over the full `n` samples (line 52), while `autocovariance` is computed over `n - lag` samples (line 60). The returned value is therefore `n/(n-lag)` × the standard normalized autocorrelation.

Standard normalized autocorrelation is bounded `[-1, 1]` by the Cauchy-Schwarz inequality *when the same samples are used in both numerator and denominator*. With the mixed-denominator formula used here, the return value can exceed 1.0 at any lag. The inflation factor is `n/(n-lag)` — at the minimum buffer size (10 samples, `hrv.py:81`) with the largest lag (8 beats), the factor is `10/2 = 5.0`. A standard autocorrelation of 0.25 would return as 1.25.

Phase A assessed: *"clamping is correct and confirmed by test `test_clamped_zero_to_one`."* This framing is too generous. The clamp at `hrv.py:94` is a necessary correction for a formula error, not a design choice. The test confirms the clamp works but does not detect that the pre-clamp values can be inflated up to 5× the true autocorrelation at minimum buffer size. The entrainment score is systematically overestimated in small-window conditions (the most common case near session start).

The same mixed-denominator pattern appears in `compute_trajectory_coherence()` (`phase.py:440–454`), where `variance` divides by `n` and `autocovariance` divides by `n - lag`. That function also applies a final clamp (`phase.py:480`), masking the same formula issue.

**CE-2: The mode label layer directly conflates entrainment and coherence — Phase A missed this**

`compute_mode()` (`hrv.py:220–260`) maps `calm_score` to mode labels. The top two labels are `"emerging coherence"` (line 256) and `"coherent presence"` (line 258). The `calm_score` that triggers these labels is:

```
calm_score = entrainment * 0.4 + breath_steady * 0.3 + amp_norm * 0.2 + (1 - volatility * 5) * 0.1
```

Entrainment carries the largest single weight (40%). A high-entrainment subject with steady breath will reliably receive a `"coherent presence"` label — a label derived from the same entrainment score the system claims to distinguish from coherence. This is not just a naming issue: the `mode_label` field is streamed to downstream consumers and persisted to session logs. Users or downstream analysis code may reasonably treat `"coherent presence"` as a coherence measurement when it is structurally an entrainment-derived label.

Phase A characterized the entrainment/coherence distinction as "maintained with unusual care across both files." That care exists in docstrings, data structure comments, and the `compute_trajectory_coherence()` implementation — but it breaks down at the label-output layer, which is the layer most visible to users and downstream processing. The conceptual separation is structural in computation but leaks at the interface boundary.

**CE-3: `compute_trajectory_coherence` IS called — Phase A's final note was factually incorrect**

Phase A's Notes stated: *"there is no evidence in the examined files that it is called from `app.py` or streamed to downstream consumers."*

Independent inspection finds it called in two production paths:
- `src/app.py:311`: `self.latest_coherence = self.trajectory.compute_trajectory_coherence()` — called in the main processing loop, result stored as `latest_coherence`
- `scripts/process_session.py:123`: `coherence = trajectory.compute_trajectory_coherence(lag=5)` — called during offline session processing

The coherence computation is active in both the live capture pipeline and the session replay tool. Phase A's concern in the Notes section was unfounded.

**CE-4: Entrainment and coherence are computationally coupled through the manifold construction**

`compute_trajectory_coherence()` operates on trajectory positions `(entrainment, breath_norm, amplitude_norm)`. When entrainment is stable and high, the trajectory clusters in the high-entrainment corner of the manifold — low position variance, low velocity magnitudes. The variance of velocity magnitudes approaches zero. At `phase.py:444–446`:

```python
if variance < 1e-10:
    # Near-zero variance = perfectly still = high coherence (dwelling)
    return 0.8
```

A subject sustaining high, stable entrainment will have low trajectory velocity variance, triggering this branch and receiving coherence = 0.8 by hardcoded assignment. The entrainment/coherence distinction is architecturally defined — but the specific path from *stable entrainment* to *high coherence* is baked into the implementation. Phase A's claim that "the conceptual separation is structurally enforced" holds for the computational paths, but misses this coupling via the manifold geometry.

**CE-5: "Phase coupling" framing is farther from the implementation than Phase A suggested**

Phase A correctly identified that the method measures "RR rhythmicity at breath-frequency lags." But the framing of what this means deserves sharper characterization.

True breath-heart phase coupling involves tracking the instantaneous phase difference between two coupled oscillators. Single-signal proxies do exist: HF power (0.15–0.4 Hz) extracts the proportion of cardiac variance at respiratory frequencies using frequency decomposition. The autocorrelation-at-lags approach in the code is a time-domain approximation but fundamentally operates on amplitude correlation — it asks "does the signal look similar to itself `k` beats ago?" not "are two signals' phases locked?" There is no phase variable, no reference oscillator, and no phase difference being computed. The metric is more accurately described as *periodic amplitude structure of the RR series at fixed beat lags*, which is a proxy for RSA but not a phase coupling measure.

Phase A's description of this as "a valid proxy but falls short of the 'phase coupling' framing" is accurate but understates the methodological distance. This matters for claims in documentation and downstream interpretation.

## Revised Assessment

**Verdict: DOWNGRADE**

Phase A's PARTIAL verdict correctly identified the two most significant weaknesses (no breath signal input, unused parameter) and confirmed the structural entrainment/coherence distinction in computation. However, Phase A's assessment was too generous in three respects:

1. **Numerical robustness**: The autocorrelation formula has a normalization error that produces values up to 5× the true autocorrelation at minimum buffer size. The clamp masks this error rather than the computation being inherently bounded. Phase A described the bounding as "correctly implemented" — this overstates the quality.

2. **Conceptual conflation at label layer**: Phase A missed that `compute_mode()` applies "coherence" labels (`"emerging coherence"`, `"coherent presence"`) directly to an entrainment-weighted score. The separation Phase A praised in docstrings and data structures is not maintained at the output boundary, where it matters most for downstream users.

3. **Factual error**: Phase A's Notes section stated `compute_trajectory_coherence` may not be called — it is called in two production paths.

## Convergence Notes

**Agrees with Phase A:**
- The 0-1 output is bounded (clamp works; CE-1 revises *why* it needs to be there)
- The entrainment/coherence distinction exists in docstrings, data structures, and at the computation-level
- `expected_breath_period` parameter is dead code that severs the breath rate–entrainment feedback path
- The lag coverage gap (slow breathing at ~6/min may peak outside lags 4–8) is a real limitation

**Disagrees with or extends Phase A:**
- CE-1: Bounding is "correctly implemented" → bounding masks a formula error; implementation is worse than described
- CE-2: Mode label layer conflates the two concepts; Phase A missed this entirely
- CE-3: Phase A's note about `compute_trajectory_coherence` not being called is factually wrong
- CE-4: The coherence computation is not fully independent of entrainment by manifold geometry; Phase A did not examine this path
- CE-5: "Phase coupling" framing deserves sharper critique than Phase A offered
