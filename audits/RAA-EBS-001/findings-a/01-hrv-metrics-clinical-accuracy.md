# Finding A1: HRV Metrics Clinical Accuracy

## Claim

From `README.md` line 14: "Classic HRV metrics: RMSSD, SDNN, pNN50 (clinically meaningful parasympathetic indicators)"

The claim is that RMSSD, SDNN, and pNN50 are computed correctly as clinically meaningful parasympathetic indicators. This is presented as a top-level feature of EarthianBioSense alongside other HRV metrics.

## Files Examined

- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/src/processing/hrv.py` — lines 1–296 (Python processing pipeline, entire file)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/tests/test_hrv.py` — lines 1–176 (Python HRV test suite)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/tests/conftest.py` — lines 1–125 (test fixtures)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/ios/EBSCapture/EBSCapture/Processing/HRVProcessor.swift` — lines 1–388 (iOS HRV implementation)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/ios/EBSCapture/EBSCapture/Services/Analytics/SessionSummaryCache.swift` — lines 1–266 (session summary computation)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/ios/EBSCapture/EBSCapture/Services/Analytics/AnalyticsService.swift` — lines 1–209 (profile analytics)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/ios/EBSCapture/EBSCapture/Models/SessionSummary.swift` — lines 1–55 (session data model)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/docs/metrics.md` — lines 1–264 (metrics documentation)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/README.md` — lines 1–229

## Evidence

### RMSSD/SDNN/pNN50 are absent from the Python pipeline

The Python file `hrv.py` contains no implementation of RMSSD, SDNN, or pNN50. The file implements: `compute_amplitude`, `compute_autocorrelation`, `compute_entrainment`, `find_peaks`, `compute_breath_rate`, `_breath_from_zero_crossings`, `compute_volatility`, `compute_mode`, and `compute_hrv_metrics`. The `HRVMetrics` dataclass fields are: `mean_rr`, `min_rr`, `max_rr`, `amplitude`, `entrainment`, `entrainment_label`, `breath_rate`, `breath_steady`, `rr_volatility`, `mode_label`, `mode_score`. No classic HRV metrics appear.

The Python test suite (`test_hrv.py`) correspondingly tests none of these metrics. The test imports list: `compute_amplitude`, `compute_autocorrelation`, `compute_entrainment`, `find_peaks`, `compute_breath_rate`, `compute_volatility`, `compute_mode`, `compute_hrv_metrics`, `HRVMetrics`. No RMSSD, SDNN, or pNN50.

### RMSSD/SDNN/pNN50 are implemented in the iOS codebase

`HRVProcessor.swift` contains three functions and one combined method:

- **`computeRMSSD`** (lines 266–277): Computes `sqrt(sum of squared successive differences / (N-1))`. This matches the Task Force 1996 definition.
- **`computeSDNN`** (lines 282–292): Computes `sqrt(sum of squared deviations from mean / N)` — population standard deviation using N as divisor.
- **`computePNN50`** (lines 297–309): Counts successive differences `> 50ms`, divides by `N-1`, multiplies by 100. Matches Task Force 1996.
- **`computeClassicHRV`** (lines 312–342): Efficient combined single-pass implementation computing all three metrics together. Uses the same formulas as the individual methods.

These are called from `SessionSummaryCache.swift` line 198: `HRVProcessor.computeClassicHRV(allRRIntervals)`, which accumulates all RR intervals across a session's JSONL records and computes the metrics over the complete session dataset.

### Documentation inconsistency

`docs/metrics.md` line 255 states: "All metrics are computed in `src/processing/hrv.py`." The five metrics documented in that file are: Amplitude, Coherence (entrainment), Breath rate, Volatility, Mode. RMSSD, SDNN, and pNN50 do not appear as documented metrics in `docs/metrics.md`. The Python pipeline metrics documentation and the README features list are therefore inconsistent: docs say five custom metrics, README advertises classic HRV metrics as a top-level feature.

### Cross-session aggregation math issue

`AnalyticsService.swift` lines 192–208 aggregates RMSSD and SDNN across sessions using RR-count-weighted averaging:

```
overall_RMSSD = sum(session.rmssd * session.rrCount) / totalRRCount
```

This is mathematically incorrect. RMSSD involves a square root of a mean of squared values. The weighted mean of per-session RMSSD values is not equal to RMSSD computed over the pooled RR interval dataset. The correct approach for pooling RMSSD would require re-accumulating the sum of squared successive differences, not averaging the square roots. Similarly, weighted-average SDNN does not equal SDNN of the combined dataset because between-session variance is excluded.

### Clinical adequacy gaps

No artifact detection or ectopic beat filtering is present in either the Python or Swift codebase. This is a significant clinical gap: ectopic beats (premature atrial/ventricular contractions) produce anomalous RR intervals that inflate RMSSD and pNN50 values substantially.

The Task Force of the European Society of Cardiology (1996) recommends minimum recording lengths for valid HRV interpretation: 5 minutes for short-term measures, 24 hours for long-term. No minimum recording length check is enforced before computing or displaying RMSSD, SDNN, or pNN50. Sessions could be very short; `computeClassicHRV` returns non-zero values with as few as 2 RR intervals.

SDNN uses N as the variance divisor (population standard deviation), whereas the Task Force standard uses sample standard deviation (N-1). For typical session lengths (hundreds of RR intervals) this difference is negligible in practice, but represents a minor deviation from the formal definition.

## Finding

**Verdict: PARTIAL**

The claim that RMSSD, SDNN, and pNN50 are computed correctly as clinically meaningful parasympathetic indicators is partially confirmed. The iOS app's `HRVProcessor.swift` implements all three metrics with formulas consistent with Task Force 1996 definitions, and applies them to accumulated per-session RR intervals. However, the claim is compromised in three ways:

First, RMSSD, SDNN, and pNN50 are entirely absent from the Python processing pipeline (`hrv.py`), which is the system's primary documented pipeline. The Python codebase uses a different set of custom metrics (amplitude, autocorrelation-based entrainment, volatility). The README presents classic HRV metrics as a top-level project feature without specifying they are iOS-only, and `docs/metrics.md` erroneously points to `hrv.py` as the implementation location.

Second, the cross-session aggregation in `AnalyticsService.swift` (weighted average of per-session RMSSD/SDNN values) is mathematically incorrect — it does not produce valid RMSSD or SDNN estimates for the combined dataset.

Third, neither codebase implements artifact or ectopic beat filtering, and no minimum window length is enforced for clinical validity. Calling these metrics "clinically meaningful" without these safeguards overstates their clinical applicability for a research tool — they are mathematically correct implementations that produce values in the expected ranges, but do not meet the quality-control standards implied by clinical validity.

## Notes

- **Architecture split is the primary finding**: Two independent HRV metric systems exist — a custom Python set (entrainment/amplitude-based) and classic iOS metrics (RMSSD/SDNN/pNN50). They are not integrated; the Python pipeline does not produce classic HRV metrics, and the iOS classic metrics are not part of the live streaming or real-time processing path.
- **pNN50 threshold**: Uses strictly `> 50ms` (not `>= 50ms`). The Task Force standard specifies "> 50ms" which matches the implementation.
- **SDNN N vs N-1**: Using N gives population SD. For N ≥ 100 (a session of ~2 minutes at 60 BPM), the difference from sample SD is <0.5% — practically inconsequential.
- **Short-window RMSSD**: The iOS HRV computation correctly runs over all RR intervals collected during a session rather than a rolling window, which is the appropriate clinical approach. This is better practice than computing RMSSD over a 20-sample rolling window.
- **Testability**: The iOS implementations are testable from static analysis. The RMSSD formula is standard and verifiable. The pNN50 formula is standard. The cross-session averaging error is detectable by mathematical inspection alone. The absence from the Python pipeline is confirmed by exhaustive code search.
- **What to verify by running code**: Ectopic beat sensitivity (would require synthetic RR datasets with injected ectopics); minimum recording length behavior (confirmed by code reading — no guard exists).
