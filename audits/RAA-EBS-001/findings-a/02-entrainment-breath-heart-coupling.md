## Claim
Entrainment metric captures breath-heart phase coupling (not coherence) on a 0-1 scale.

## Files Examined
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/src/processing/hrv.py` — lines 1–296 (full file); key functions: `compute_entrainment` (65–106), `compute_breath_rate` (122–170), `compute_hrv_metrics` (263–295)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/src/processing/phase.py` — lines 1–481 (full file); key: `PhaseTrajectory._metrics_to_position` (160–175), `compute_trajectory_coherence` (403–480), docstring (1–14)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/tests/test_hrv.py` — lines 63–83 (TestComputeEntrainment class)

## Evidence

**Sub-claim 1: Entrainment is computed as breath-heart phase coupling**

`compute_entrainment()` (`hrv.py:65–106`) computes autocorrelation of the raw RR interval series at fixed lags `[4, 5, 6, 7, 8]` beats. The docstring frames this as measuring RSA (respiratory sinus arrhythmia) — "how tightly the heart rhythm is phase-locked to breathing." However, the implementation does not use any breath signal as input. It takes only `rr_intervals` and looks for self-similarity in the cardiac series at those beat-count lags.

This is an indirect proxy. True breath-heart phase coupling requires either: (a) a breath sensor signal to cross-correlate against cardiac intervals, or (b) explicit frequency-domain analysis (e.g., HF power band, 0.15–0.4 Hz). The autocorrelation-at-fixed-lags approach detects *any* rhythmicity in the RR series at 4–8 beat periods, which ordinarily corresponds to breath-induced RSA but cannot discriminate breath coupling from other periodic cardiac influences (e.g., locomotion cadence, vasomotor waves).

**Sub-claim 2: Breath rate estimation feeds into entrainment**

`compute_entrainment()` accepts an `expected_breath_period: int = 5` parameter, suggesting it was designed to adapt to estimated breath rate. However:
- The parameter is **never used inside the function body** — lags are unconditionally set to `[4, 5, 6, 7, 8]` (line 87).
- In `compute_hrv_metrics()` (line 278), `compute_entrainment(rr_intervals)` is called with no second argument, always using the default.
- `compute_breath_rate()` runs independently (line 279) and its output is never passed to `compute_entrainment()`.

The breath rate estimate and the entrainment score are computed from the same RR data via different code paths that do not talk to each other. The adaptive lag mechanism is structurally present (as an unused parameter) but not operational.

**Sub-claim 3: Entrainment/coherence distinction maintained in code**

The distinction is genuine and structural, not merely documented. Evidence:

- `phase.py` docstring (lines 8–13) defines the distinction explicitly in code: entrainment = breath-heart phase coupling (local sync), coherence = trajectory integrity over time (global).
- `compute_trajectory_coherence()` (`phase.py:403–480`) computes coherence as autocorrelation of velocity magnitude sequences plus directional cosine similarity across the 3D manifold trajectory — a fundamentally different computation from entrainment.
- `PhaseTrajectory._metrics_to_position()` (`phase.py:160–175`) uses `entrainment` as a manifold coordinate axis and the docstring at line 342–344 explicitly notes: "Note: 'ent' here is entrainment (breath-heart sync), not coherence. Coherence (trajectory integrity) would require looking at the trajectory history, not just current position."
- `HRVMetrics` dataclass docstring (`hrv.py:18–19`) flags: "Note: This measures respiratory sinus arrhythmia / breath-heart sync. NOT trajectory coherence."

The conceptual separation is structurally enforced: coherence is computed only at the `PhaseTrajectory` level from trajectory state, while entrainment is computed at the signal-processing level from RR intervals.

**Sub-claim 4: Output genuinely bounded 0-1**

`compute_entrainment()` line 94: `entrainment = max(0.0, min(1.0, max_corr))`. Autocorrelation ranges in `[-1, 1]`; negative values are clamped to 0. The clamping is correct and confirmed by test `test_clamped_zero_to_one` (`test_hrv.py:80–82`).

**Sub-claim 5: Signal processing method appropriateness**

The autocorrelation-at-lags approach is computationally valid for detecting periodic structure in RR intervals. For RSA detection from a single cardiac signal (no separate breath input), it is a reasonable first-pass approach used in basic HRV toolkits. However, it carries two interpretive limitations:

1. **Fixed lags assume a specific HR–breath relationship.** Lags 4–8 beats correspond to breath cycles of 4–8 RR intervals. At 60 BPM and 6 breaths/min, the breath period is ~10 beats — outside the checked range. At 60 BPM and 10–15 breaths/min (rest range), lags 4–6 are appropriate. At lower heart rates or slower breathing, the peak lag shifts and may be missed.

2. **No discriminability from non-respiratory oscillations.** The method cannot determine whether periodic RR structure at those lags is breath-induced versus artefactual (e.g., movement, Mayer waves at ~0.1 Hz).

## Finding

**Verdict: PARTIAL**

The claim that entrainment captures breath-heart phase coupling on a 0-1 scale is partially confirmed. The 0-1 bounding is correct and robustly implemented. The entrainment/coherence distinction is genuine, structural, and maintained with unusual care across both files. These aspects of the claim are confirmed.

However, two material weaknesses limit the claim's precision:

First, the entrainment computation is not true breath-heart phase coupling — it is RR interval autocorrelation at fixed lags that approximate breath-frequency periodicity. Without a breath signal input, the metric cannot isolate respiratory-driven cardiac modulation from other periodic cardiac influences. The code is measuring *RR rhythmicity at breath-frequency lags*, which is a valid proxy but falls short of the "phase coupling" framing in the claim.

Second, the breath rate estimation does not feed into the entrainment computation, despite architectural provisions for this (`expected_breath_period` parameter). This is a structural disconnection: the two most relevant computations — breath rate and entrainment — are computed independently from the same RR data, without cross-informing each other. If breath rate is estimated at a period outside the checked lags (4–8 beats), the entrainment score will be systematically underestimated.

## Notes

- **Dead parameter:** `expected_breath_period` in `compute_entrainment()` signature is accepted but never used. This is either an incomplete feature or dead code — either way it should be removed or wired up.
- **Circular proxy:** `compute_breath_rate()` uses peak detection on the RR series to estimate the breath rate; `compute_entrainment()` also looks for peaks/periodicity in the same RR series. Both are measuring RSA from the same signal at slightly different angles. If a breath sensor (accelerometer chest expansion, respiratory belt, nasal airflow) were added, both could be grounded in an independent reference.
- **Lag coverage gap:** At resting HR of 60 BPM with slow diaphragmatic breathing at 6 breaths/min (~10s period), the autocorrelation peak would be at lag ~10 beats — outside the checked range of [4, 5, 6, 7, 8]. The very breathing pattern associated with coherence-promoting practice (slow, resonant breathing ~6/min) may be systematically under-detected by the current lag selection.
- **Negative autocorrelation:** Clamping negative autocorrelations to 0 loses information. Anti-correlated patterns (alternating long-short RR intervals) may indicate certain physiological states worth distinguishing from "no rhythmicity."
- **`compute_trajectory_coherence()` status:** This method exists in `PhaseTrajectory` but there is no evidence in the examined files that it is called from `app.py` or streamed to downstream consumers. If it exists but is not called, the coherence concept is defined but not active.
