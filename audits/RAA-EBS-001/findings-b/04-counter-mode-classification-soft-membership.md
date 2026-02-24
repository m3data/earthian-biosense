## Phase A Finding Under Review

`findings-a/04-mode-classification-soft-membership.md` — Mode classification uses soft membership across 6 centroids with hysteresis and movement annotation. Schema v1.1.0 documents all required fields.

## Phase A Verdict

**PARTIAL** — Soft membership and hysteresis are properly implemented; movement annotation is post-hoc, not a classification input; centroids are analytically derived, not data-derived.

## Counter-Evidence

Independent re-read of `movement.py` (full), `hrv.py:220–261`, `phase.py:177–328`.

### 1. Centroids: Phase A underreported the structural severity

Phase A correctly noted centroids are reverse-engineered from `compute_mode` threshold midpoints. It noted the linear structure of the original threshold system. What it missed is the **binary encoding problem for `breath_steady_score`**.

`compute_soft_mode_membership()` (`movement.py:369`) converts `breath_steady: bool` to either `1.0` (steady) or `0.3` (unsteady). This is the only input to the `breath_steady_score` feature dimension. However, four of the six centroids define `breath_steady_score` values that are **never achievable**:

| Mode | Centroid bss | Achievable? |
|---|---|---|
| heightened alertness | 0.3 | YES |
| subtle alertness | 0.3 | YES |
| transitional | 0.5 | **NO** |
| settling | 0.8 | **NO** |
| emerging coherence | 1.0 | YES |
| coherent presence | 1.0 | YES |

The theoretical 4D feature space is degenerate for this feature: one axis has only two possible values (0.3 or 1.0), but centroids are defined at 0.5 and 0.8. The `transitional` and `settling` centroids exist at positions **no real physiological input can occupy**. The weighted squared distance from any real position to these centroids always includes a non-zero penalty of at least `0.3*(0.5−0.3)^2 = 0.012` (bss gap to transitional) or `0.3*(0.8−0.3)^2 = 0.075` (bss gap to settling, unsteady) / `0.3*(1.0−0.8)^2 = 0.012` (bss gap to settling, steady).

Phase A described the centroids as "uniformly spaced along the calm_score axis." The deeper problem is that the claimed 4D geometry has a degenerate axis, which undermines the soft membership premise.

### 2. Hysteresis: Phase A confirmed mechanism but did not verify reachability of thresholds

Phase A confirmed that `detect_mode_with_hysteresis()` implements a three-state machine with per-mode entry/exit thresholds. What Phase A did not check is whether those thresholds are **geometrically achievable** given the softmax at T=1.0 with six closely-spaced centroids.

Direct analysis of softmax ceiling: With temperature=1.0 and six modes whose centroids are near-uniformly spaced over a bounded [0,1]^4 space, the maximum achievable membership for any mode is close to the uniform baseline of 1/6 ≈ 0.167. Computing the softmax exactly at each centroid yields:

| Mode | Centroid membership (T=1.0) | Entry threshold | Enterable? |
|---|---|---|---|
| heightened alertness | ~0.198 | 0.18 | YES |
| subtle alertness | ~0.188 | 0.18 | YES |
| transitional | ~0.179 | 0.17 | YES |
| settling | ~0.179 (at centroid) | 0.19 | **NO** |
| emerging coherence | ~0.187 | 0.20 | **NO** |
| coherent presence | ~0.195 | 0.22 | **NO** |

Worked example for `coherent presence` centroid (0.8, 1.0, 0.75, 0.95), T=1.0: weighted squared distances to the six modes from this centroid position are 0 (self), 0.012, 0.049, 0.169, 0.330, 0.460. Softmax yields: exp(-0)/Σ ≈ 1.0 / 5.13 ≈ 0.195. Entry threshold is 0.22. The threshold **exceeds the maximum achievable membership**.

The same analysis applies at the extreme physiologically coherent input (entrainment=1.0, breath_steady=True, amp_norm=1.0, volatility=0): membership for `coherent presence` ≈ 0.209. Still below 0.22.

For `settling`: the closest real position (steady breath, other features at settling centroid) produces `emerging coherence` as the winner — `emerging coherence` centroid (bss=1.0) is closer than `settling` centroid (bss=0.8) whenever breath is steady. Settling is effectively **dominated by emerging coherence** for steady-breath inputs, and penalised by bss mismatch for unsteady-breath inputs.

**Consequence:** Three of the six modes (`settling`, `emerging coherence`, `coherent presence`) cannot be entered through the normal first-entry path. When these modes are proposed and confidence falls below the entry threshold, the state machine defaults to `transitional` (`movement.py:504`, `553-555`). The hysteresis mechanism functions correctly as a gate, but what Phase A described as "properly implemented" is a gate that cannot open for the calmer half of the mode spectrum.

The code comment at `movement.py:266–269` acknowledges thresholds are "slightly above uniform (0.18–0.22)" and calibrated relative to the uniform baseline. This demonstrates design intent to calibrate near-uniform membership. What the designer did not compute is that centroid membership at T=1.0 is itself only slightly above uniform — insufficient to clear the threshold for upper modes.

The temperature parameter exists in `compute_soft_mode_membership()` signature (default 1.0) but Phase A correctly noted it is never varied at call sites. Reducing temperature (e.g., to 0.1) would sharpen the softmax and likely resolve the reachability problem, but the mechanism exists and is simply not activated.

### 3. Movement annotation: Phase A was correct, with one underemphasised coupling

Phase A's finding that movement annotation is post-hoc is confirmed. The pipeline order in `phase.py:271–303` is: (1) compute soft mode membership, (2) detect mode with hysteresis, (3) compute movement annotation, (4) compose label. No feedback.

One additional issue Phase A noted but understated: `mode_score_velocity` (line 291) is computed from `metrics.mode_score`, which is the **legacy `hrv.py.compute_mode` scalar output** — not from the new soft membership distribution. The movement annotation's velocity and acceleration track the old system's dynamics. This means the "movement-preserving" annotation traces a different trajectory than the soft membership it annotates. A rising soft membership could correspond to a falling `mode_score` scalar (they are independently computed), producing a contradictory movement annotation.

### 4. Soft membership sum: Phase A was correct

Softmax normalization at `movement.py:396–397` divides each exp weight by the sum. The numerical stability offset ensures the minimum distance mode always contributes exp(0)=1.0, making total always ≥ 1.0. Membership always sums to exactly 1.0 within floating-point precision. No edge case breaks this.

The KL divergence (lines 415–423) for `distribution_shift` uses epsilon=1e-10 guards, preventing log(0). This is well-formed.

## Revised Assessment

**Verdict: DOWNGRADE**

Phase A's PARTIAL verdict was too generous. The implementation has two critical geometric flaws that Phase A did not surface:

1. **Degenerate feature space**: `breath_steady_score` has only two achievable values (0.3 or 1.0), but four centroids are defined at intermediate values (0.5, 0.8) that no real input can produce. The theoretical 4D soft membership geometry does not match the actual (3D continuous + 1D binary) input space.

2. **Softmax ceiling below entry thresholds**: With T=1.0 and six closely-spaced centroids, the maximum achievable softmax membership for `settling`, `emerging coherence`, and `coherent presence` falls below their respective entry thresholds (0.19, 0.20, 0.22). These three modes — the calmer, physiologically meaningful half of the scale — are structurally unreachable through the first-entry path. The hysteresis mechanism works as designed, but the design creates a gate that cannot open for the modes that matter most to the system's stated purpose.

Phase A correctly identified that centroids are analytically derived and movement annotation is post-hoc. Phase A incorrectly described the hysteresis as "properly implemented" without verifying that the thresholds are achievable, and did not investigate the binary encoding constraint on the feature space.

## Convergence Notes

**Agreement with Phase A:**
- Centroids are analytically derived, not data-derived ✓
- Soft membership is genuine (softmax on distances, not argmin) ✓
- Three-state hysteresis machine exists with asymmetric thresholds ✓
- Movement annotation is post-hoc, not a classification input ✓
- "Settled" annotation is suppressed from composed labels ✓
- Schema fields present with minor naming discrepancy ✓
- Soft membership sums to 1.0 ✓
- Temperature hardcoded to 1.0 ✓

**Disagreement with Phase A:**
- Phase A: "hysteresis is properly implemented" — **contested**. Threshold reachability depends on softmax geometry; three modes fail this test at T=1.0.
- Phase A: centroid placement critique was limited to "uniformly spaced along calm_score axis" — **understated**. The binary encoding of `breath_steady_score` makes four centroid positions impossible to reach, with `settling` effectively dominated by `emerging coherence` for steady-breath inputs.
- Phase A: characterized velocity/movement annotation coupling as "latent coupling" in Notes — **understated**. The movement annotation tracks a different trajectory (legacy scalar) than the soft membership system, creating a structural contradiction in the "movement-preserving" label.
