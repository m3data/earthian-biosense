# Counter-Finding B1: HRV Metrics Clinical Accuracy

## Phase A Finding Under Review

`findings-a/01-hrv-metrics-clinical-accuracy.md`

## Phase A Verdict

**PARTIAL** — Classic HRV metrics (RMSSD, SDNN, pNN50) are correctly implemented in iOS
(`HRVProcessor.swift`) per Task Force 1996 formulas, but absent from the Python pipeline
(`hrv.py`); cross-session aggregation is mathematically incorrect; no artifact filtering or
minimum recording length is enforced.

---

## Independent Analysis

### Files re-examined

- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/src/processing/hrv.py` — lines 1–296
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/ios/EBSCapture/EBSCapture/Processing/HRVProcessor.swift` — lines 1–388
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/ios/EBSCapture/EBSCapture/Services/Analytics/AnalyticsService.swift` — lines 190–209
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/ios/EBSCapture/EBSCapture/Services/Analytics/SessionSummaryCache.swift` — lines 185–231
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/tests/test_hrv.py` — lines 1–176
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/README.md` — lines 11–16
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/docs/metrics.md` — lines 253–264

---

## Counter-Evidence

### Where Phase A is confirmed

**Architecture split** — independently confirmed. `hrv.py` defines `HRVMetrics` with fields
`mean_rr`, `min_rr`, `max_rr`, `amplitude`, `entrainment`, `entrainment_label`, `breath_rate`,
`breath_steady`, `rr_volatility`, `mode_label`, `mode_score`. No RMSSD, SDNN, or pNN50 field
exists anywhere in the Python dataclass or processing path. `test_hrv.py` imports confirm this
by exhaustive enumeration (lines 10–19).

**iOS formulas** — independently confirmed as Task Force 1996 compliant. `computeRMSSD`
(HRVProcessor.swift:266–277), `computeSDNN` (282–292), `computePNN50` (297–309), and the
combined `computeClassicHRV` (312–342) all implement standard formulas. The pNN50 threshold is
`> 50` (not `>= 50`), which matches the Task Force definition.

**Cross-session math error** — independently confirmed and more precisely characterised than
Phase A reported. `AnalyticsService.swift:192–207` uses:

```
weight = session.rrCount / totalRRCount
weightedRMSSD += session.rmssd * weight
```

This computes a weighted mean of per-session RMSSDs. The correct pooled RMSSD requires
accumulating `sumSquaredDiffs` and `pairCount` across all sessions and then computing the final
square root — the square root and the mean do not commute. For SDNN the error is compounded:
not only does the same non-commutative averaging apply, but the between-session variance
component (differences of session means from the grand mean) is entirely excluded. Weighted
averaging of per-session SDNNs systematically underestimates total variability when sessions
differ meaningfully in mean RR.

**`docs/metrics.md` error** — confirmed. Line 255 reads "All metrics are computed in
`src/processing/hrv.py`", which is false for classic HRV metrics. The Python file contains no
such metrics.

### What Phase A missed or understated

**1. No automated tests for any iOS classic HRV code**

A glob search across the entire iOS directory finds zero Swift test files (`*Test*.swift` →
no matches). The `computeRMSSD`, `computeSDNN`, `computePNN50`, and `computeClassicHRV`
functions in `HRVProcessor.swift` are entirely untested by automated tests. The Python test
suite (`test_hrv.py`) covers only the Python custom metrics and has no analog in iOS. This
means the correctness of the iOS implementations rests solely on static code review — there is
no regression safety net. Phase A did not flag this gap.

**2. Minimum input guard is more permissive than Phase A stated**

Phase A stated "as few as 2 RR intervals" but did not fully characterise the clinical
implication. Both `computeRMSSD` and `computeClassicHRV` guard on `count >= 2`
(HRVProcessor.swift:267, 313). With exactly 2 RR intervals:
- RMSSD = the absolute difference between the two values — physiologically meaningless
- SDNN = half the absolute difference between the two values
- pNN50 = either 0% or 100% (single comparison)

`SessionSummaryCache.swift` calls `HRVProcessor.computeClassicHRV(allRRIntervals)` with no
minimum count gate before the call (line 198). A session that records just one heartbeat pair
produces stored `ClassicHRVMetrics` values that are labelled as RMSSD and SDNN but are
numerically degenerate. Phase A named this gap but did not characterise the degenerate output.

**3. `computeClassicHRV` integer arithmetic path**

In `computeClassicHRV` (lines 331–333), the squared difference is computed in Swift Int before
casting to Double:

```swift
let diff = rrIntervals[i] - rrIntervals[i - 1]   // Int
sumSquaredDiffs += Double(diff * diff)             // diff*diff as Int first
```

For physiological RR intervals (200–2000ms), maximum diff ≈ 1800ms, `1800 * 1800 = 3,240,000`
— well within Int64 bounds. No overflow risk in practice. However, this differs in type path
from the standalone `computeRMSSD` (which casts to Double before squaring). Both produce
identical results for normal physiological ranges, but the inconsistency between the combined
and standalone methods is a latent hazard if the input type ever widens. Phase A did not
examine this divergence.

**4. README distinction is less ambiguous than Phase A implied**

Phase A argued the README presents classic HRV metrics "without specifying they are iOS-only."
On re-read, README line 14–15 distinguishes:
- "Classic HRV metrics: RMSSD, SDNN, pNN50"
- "Custom HRV metrics: amplitude, entrainment (breath-heart coupling), breath rate estimation"

The co-listing of both metric families, with "Custom" explicitly named for the Python set,
implies classic metrics live elsewhere. The claim that the README is "presenting classic HRV
metrics as a top-level project feature without specifying they are iOS-only" is slightly
overstated — the distinction is implicit but present. The real documentation failure is
`docs/metrics.md:255` erroneously claiming the Python file is the sole implementation, not the
README itself.

**5. Ectopic beat sensitivity is understated as a concern for short research sessions**

Phase A correctly identifies no artifact detection. The clinical severity is worth being more
precise about: for typical short sessions (2–5 minutes, ~120–300 RR intervals), a single
ectopic beat introduces one anomalous successive difference. The effect on RMSSD is
proportional to `1/sqrt(N-1)` — for N=120, one ectopic at 300ms above baseline inflates RMSSD
by roughly `sqrt((300²)/119) ≈ 27ms`, which can more than double RMSSD in a low-variability
individual. pNN50 inflation from a single ectopic is similarly large at short N. The system
collects data from Polar H10, which does not strip ectopics from its RR stream (H10 reports all
detected RR intervals including those from ectopic beats). This is a concrete, quantifiable
clinical validity gap that Phase A named but did not quantify.

---

## Revised Assessment

**Verdict: AGREE**

Phase A's PARTIAL verdict is accurate and well-supported. The three main findings — Python
pipeline absence, cross-session aggregation math error, and clinical validity gaps (no artifact
filtering, no minimum recording length) — are all independently confirmed.

Phase A's analysis did miss two meaningful issues: the complete absence of automated iOS tests
for classic HRV methods, and the inadequate characterisation of the degenerate output from
the 2-RR minimum. These strengthen the case for PARTIAL but do not change the verdict category.

The README framing criticism is slightly overstated; the more precise documentation failure is
`docs/metrics.md:255`, which Phase A correctly identifies as erroneous.

---

## Convergence Notes

**Agree:** Architecture split finding — confirmed independently. Two metric systems, not
integrated. Python pipeline documents its own metrics without classic HRV.

**Agree:** Cross-session aggregation is mathematically incorrect — `computeWeightedHRV`
confirmed to use weighted means of per-session RMSSDs, which is not equivalent to pooled RMSSD.

**Agree:** "Clinically meaningful" is overstated without ectopic filtering and minimum
recording length enforcement.

**Agree:** SDNN uses population SD (N divisor) — minor deviation from Task Force N-1 standard.

**Strengthens Phase A:** iOS classic HRV is entirely untested by automated tests — Phase A
did not identify this gap.

**Strengthens Phase A:** 2-RR minimum produces degenerate clinical values — Phase A named
the guard but did not characterise the degenerate output.

**Nuances Phase A:** README distinction between classic and custom metrics is implicit but
present; the documentation failure is more precisely located in `docs/metrics.md:255`.
