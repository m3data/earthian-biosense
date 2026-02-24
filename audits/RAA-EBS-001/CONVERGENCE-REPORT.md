# Convergence Report — RAA-EBS-001

**Date:** 2026-02-24
**Evaluator:** convergence-eval agent
**Phase A findings:** 5 (A1–A5) + SYNTHESIS-A
**Phase B findings:** 5 (B1–B5)
**Overall confidence:** 0.77

---

## Summary Table

| Finding | Claim | Phase A | Phase B | Convergence | Verdict |
|---------|-------|---------|---------|-------------|---------|
| C1 | HRV metrics clinical accuracy | PARTIAL | AGREE | 0.85 | CONVERGE |
| C2 | Entrainment as breath-heart phase coupling | PARTIAL | DOWNGRADE | 0.45 | DIVERGE |
| C3 | Phase space dynamics validity | PARTIAL | DOWNGRADE | 0.55 | DIVERGE |
| C4 | Mode classification soft membership | PARTIAL | DOWNGRADE | 0.40 | DIVERGE |
| C5 | Architecture separation of concerns | PARTIAL | DOWNGRADE | 0.65 | PARTIAL DIVERGE |

---

## Per-Finding Analysis

---

### C1 — HRV Metrics Clinical Accuracy

**Phase A:** PARTIAL
**Phase B:** AGREE
**Convergence score: 0.85 — CONVERGE**

#### Agreement
Both passes independently confirm every major finding:
- Classic HRV metrics (RMSSD, SDNN, pNN50) are absent from the Python pipeline; they exist only in the iOS `HRVProcessor.swift`.
- iOS formulas are Task Force 1996 compliant.
- Cross-session aggregation in `AnalyticsService.swift` is mathematically incorrect — weighted mean of per-session RMSSDs does not equal RMSSD of the pooled dataset; same applies to SDNN (between-session variance excluded).
- `docs/metrics.md:255` erroneously claims the Python file is the sole implementation.
- No artifact or ectopic beat filtering in either codebase; no minimum recording length guard.

#### Divergence
Phase B nuances one point: Phase A described the README as presenting classic HRV metrics "without specifying they are iOS-only." Phase B finds this slightly overstated — the README explicitly labels a separate "Custom HRV metrics" set for Python, making the distinction implicit. The precise documentation failure is `docs/metrics.md:255`, not the README.

Phase B adds two issues Phase A missed:
- **No automated tests for any iOS classic HRV methods.** Zero Swift test files exist across the entire iOS directory. Correctness of `computeRMSSD`, `computeSDNN`, `computePNN50`, and `computeClassicHRV` rests solely on static review.
- **2-RR minimum produces degenerate clinical values.** Phase A named the guard without characterising the output: with exactly 2 RR intervals, RMSSD = absolute difference of two values; pNN50 = 0% or 100%. Both are physiologically meaningless. `SessionSummaryCache.swift` applies no count gate before calling `computeClassicHRV`.
- Phase B also characterises the ectopic inflation quantitatively: for N=120 intervals, one ectopic at 300ms above baseline inflates RMSSD by ~27ms, which can more than double RMSSD in low-variability individuals.

#### Structurally unresolvable by static analysis
Whether the cross-session aggregation error is clinically material depends on how much session-to-session mean RR varies across an individual's sessions — this requires runtime data.

---

### C2 — Entrainment as Breath-Heart Phase Coupling

**Phase A:** PARTIAL
**Phase B:** DOWNGRADE
**Convergence score: 0.45 — DIVERGE**

#### Agreement
Both passes agree on:
- 0–1 output is bounded (clamp at `hrv.py:94` works).
- The entrainment/coherence distinction is structurally present in docstrings, data structures, and separate computation paths.
- `expected_breath_period` parameter is dead code — accepted but never used inside `compute_entrainment()`.
- Lag coverage gap: slow resonant breathing (~6 breaths/min, lag ~10 beats) falls outside the checked range [4, 5, 6, 7, 8].
- The computation measures "RR rhythmicity at breath-frequency lags," not true phase coupling.

#### Divergence
Phase B finds three issues that materially weaken Phase A's assessment:

**1. Autocorrelation normalization error (not just a missing feature).**
`compute_autocorrelation()` (`hrv.py:43–62`) uses mixed denominators: variance computed over `n` samples, autocovariance over `n - lag` samples. The return value inflates by `n/(n-lag)`. At minimum buffer size (10 samples) with lag 8, the inflation factor is `10/2 = 5.0`. Phase A described the clamp as "correctly implemented" — Phase B correctly reframes it: the clamp is masking a formula error, not implementing a design choice. The entrainment score is systematically overestimated in small-window conditions. The same mixed-denominator error exists in `compute_trajectory_coherence()` (`phase.py:440–454`), where it is also masked by a final clamp.

**2. Mode label layer conflates entrainment and coherence (Phase A missed entirely).**
`compute_mode()` (`hrv.py:220–260`) maps `calm_score` to labels including `"emerging coherence"` and `"coherent presence"`. The `calm_score` formula weights entrainment at 40% — the largest single factor. These labels are streamed and persisted. A downstream consumer or user reading `"coherent presence"` from a session log has no indication it is an entrainment-derived label. Phase A praised the conceptual separation as "maintained with unusual care"; that care exists at the computation level but fails at the output boundary where it matters most.

**3. Phase A's factual error on `compute_trajectory_coherence`.**
Phase A's Notes stated there was "no evidence that `compute_trajectory_coherence` is called from `app.py` or streamed." Phase B finds it called in two production paths: `src/app.py:311` (`self.latest_coherence = self.trajectory.compute_trajectory_coherence()`) and `scripts/process_session.py:123`. The coherence computation is active in both the live pipeline and offline session replay.

**4. Coherence computation is not independent of entrainment via manifold geometry.**
`compute_trajectory_coherence()` operates on trajectory positions that include entrainment as an axis. When entrainment is high and stable, trajectory positions cluster in the high-entrainment corner — low variance, low velocity, triggering the hardcoded `return 0.8` branch at `phase.py:444–446`. The conceptual distinction holds at the computational-path level, but the specific path from *stable entrainment* → *high coherence score* is baked into the manifold geometry.

#### Structurally unresolvable by static analysis
Whether autocorrelation-at-fixed-lags is a defensible RSA proxy for the specific populations and protocols EBS targets (vs. whether Phase A's methodological critique is too strict) requires empirical validation against sessions with simultaneous breath sensor data.

---

### C3 — Phase Space Dynamics Validity

**Phase A:** PARTIAL
**Phase B:** DOWNGRADE
**Convergence score: 0.55 — DIVERGE**

#### Agreement
Both passes agree on:
- Velocity computation (first-order finite difference) is mathematically correct.
- "Curvature" field is acceleration magnitude `|r''(t)|`, not geometric curvature κ = `|r'×r''| / |r'|³`. The distinction matters at low and high speeds.
- "Stability" is a heuristic squashing function `1 / (1 + 2*(|v| + 0.5*|a|))`, not formal dynamical-systems stability.
- "Manifold" claim is aspirational, not mathematical — the space is a 3D Euclidean feature space with implicit isotropy.
- `transition_proximity` is permanently 0.0 (deferred "will need basin definitions").
- `_last_velocity` is dead code.
- The 3D coordinate space is genuinely used in all downstream computations.

#### Divergence
Phase B identifies two defects Phase A did not raise:

**1. `history_signature` is semantically broken (not just underdocumented).**
Phase A noted the 0.5 normalisation constant as an undocumented magic number. Phase B finds a deeper problem: `history_signature` divides `self.cumulative_path_length` (total session path since start, unbounded) by the time span of the last 30 states (~30 seconds). As session length grows, the numerator grows without bound while the denominator is capped. With any non-trivial biosignal activity, `history_signature` saturates to its `min(1.0, ...)` ceiling within the first few minutes and remains there for the rest of the session. Once saturated it is informationally inert. This is not a calibration problem — it is a metric that structurally cannot represent session-length variation after warm-up.

**2. `PhaseDynamics.acceleration_magnitude` naming collision.**
The `acceleration_magnitude` field in `PhaseDynamics` (`phase.py:85`) is assigned from `abs(mode_score_accel)` — the second derivative of the scalar `mode_score` (the legacy `hrv.py` output). This is completely different from the 3D trajectory acceleration stored in the `curvature` field. Both are described using "acceleration magnitude" language in comments, but they measure different quantities on different signals. A downstream consumer reading `acceleration_magnitude` would receive the mode_score scalar derivative, not anything from the 3D phase trajectory.

Phase B additionally notes:
- The "phase space" terminology (not just "manifold") is a misnomer in the dynamical systems sense: the axes are derived aggregates (smoothed windowed statistics), not raw state variables. A true HRV phase space would use Takens delay-embedding of raw RR intervals.
- `EMPTY_DYNAMICS.stability = 0.0` conflicts with the warm-up cold-start default of `stability = 0.5` — inconsistent sentinel value.
- Non-uniform sampling approximation in `dt_avg = (dt1 + dt2) / 2` introduces second-derivative error with irregular update cadences.

#### Structurally unresolvable by static analysis
Whether the heuristic stability proxy or the Euclidean isotropy assumptions have meaningful predictive value for EECP's research goals requires empirical comparison against validated physiological stability measures.

---

### C4 — Mode Classification Soft Membership

**Phase A:** PARTIAL
**Phase B:** DOWNGRADE
**Convergence score: 0.40 — DIVERGE**

#### Agreement
Both passes agree on:
- Soft membership is genuine: softmax on weighted squared Euclidean distances produces a real probability distribution, not argmin.
- Hysteresis state machine exists with asymmetric entry/exit thresholds and a three-state machine (unknown/provisional/established).
- Centroids are analytically derived from `compute_mode()` threshold midpoints, not learned from physiological data.
- Movement annotation is post-hoc: computed after mode selection, appended as a string label, with no feedback into membership weights, distances, or hysteresis.
- The `"settled"` annotation is suppressed from composed labels by `compose_movement_aware_label()`.
- Schema v1.1.0 fields are all present, with one minor naming discrepancy (`acceleration_mag` in schema vs. `acceleration_magnitude` in dataclass).
- Temperature is hardcoded to 1.0 at all call sites.

#### Divergence
Phase B finds two critical geometric flaws Phase A did not identify:

**1. Degenerate feature space: `breath_steady_score` has only two achievable values.**
`compute_soft_mode_membership()` converts the boolean `breath_steady` to either 1.0 (steady) or 0.3 (unsteady). Four of the six centroids define `breath_steady_score` at intermediate values (0.5 for `transitional`, 0.8 for `settling`) that no real input can produce. The theoretical 4D feature space has a degenerate axis. The `settling` mode is effectively dominated by `emerging coherence` for steady-breath inputs (the `emerging coherence` centroid at bss=1.0 is closer than `settling` at bss=0.8 when breath is steady) and penalised by bss mismatch for unsteady inputs.

**2. Softmax ceiling falls below entry thresholds for three modes.**
With temperature=1.0 and six closely-spaced centroids in a bounded [0,1]⁴ space, the maximum achievable softmax membership for any mode approaches the uniform baseline (1/6 ≈ 0.167). Phase B computes membership at the exact centroid positions:

| Mode | Centroid membership (T=1.0) | Entry threshold | Enterable? |
|------|----------------------------|-----------------|-----------:|
| heightened alertness | ~0.198 | 0.18 | YES |
| subtle alertness | ~0.188 | 0.18 | YES |
| transitional | ~0.179 | 0.17 | YES |
| settling | ~0.179 | 0.19 | **NO** |
| emerging coherence | ~0.187 | 0.20 | **NO** |
| coherent presence | ~0.195 | 0.22 | **NO** |

Even at the most physiologically coherent possible input (entrainment=1.0, breath_steady=True, amp_norm=1.0, volatility=0), `coherent presence` membership ≈ 0.209 — still below its 0.22 entry threshold. The three upper modes — representing the calmer, more meaningful half of the classification scale — **cannot be entered through the normal first-entry path**. When these modes are proposed but fail the confidence gate, the state machine defaults to `transitional` (`movement.py:504, 553–555`). The hysteresis mechanism works as a gate; it just cannot open for the modes that matter most to EBS's stated purpose.

Phase B additionally notes: the movement annotation tracks the legacy `compute_mode()` scalar's velocity (not the soft membership distribution). A rising soft membership trajectory could correspond to a falling `mode_score` scalar, producing a structurally contradictory movement annotation.

#### Structurally unresolvable by static analysis
Whether the softmax ceiling can be resolved by tuning temperature below 1.0 (the mechanism exists) is an empirical calibration question. Whether the centroid geometry is "good enough" for research purposes requires empirical data about real physiological distributions along these feature axes.

---

### C5 — Architecture Separation of Concerns

**Phase A:** PARTIAL
**Phase B:** DOWNGRADE
**Convergence score: 0.65 — PARTIAL DIVERGE**

#### Agreement
Both passes confirm all of Phase A's primary findings:
- No event bus — the mechanism is `H10Client._callbacks`, a synchronous callback list; `TerminalUI.on_data()` contains all pipeline logic.
- `SessionLogger` in `app.py` imports `SemioticMarker` and `FieldEvent` from `api/websocket_server.py` — storage→API type dependency.
- `TerminalUI` god-object holds `logger`, `ws_server`, `trajectory` and coordinates pipeline scheduling, logging, broadcasting, and display.
- REST API (`rest.py`) is documented but absent.
- iOS `HRVProcessor.swift` mirrors Python algorithms with no enforcement mechanism — algorithmic drift risk.
- Individual processing modules (`hrv.py`, `phase.py`, `movement.py`) are BLE-agnostic; BLE modules do not import from processing.

#### Divergence
Phase B identifies three findings Phase A missed:

**1. Global singleton in `device_registry.py`.**
`device_registry.py:157–170` defines a module-level mutable `_registry`. `scanner.py` silently consumes it when no registry is injected. This is hidden shared state in the BLE layer — test isolation fails if `scan_for_labeled_devices()` is called multiple times in the same process; and device configuration is an implicit global rather than an explicit dependency. Phase A stated individual modules "respect layer boundaries" — this qualifies that claim for the BLE sublayer.

**2. Chimera module entirely absent from Phase A's analysis.**
`src/processing/chimera/` is a six-file, ~1100-line module with a full internal architecture (`types.py`, `vocabulary.py`, `ecology.py`, `evolution.py`, `encounter.py`, `threshold.py`) and a complete exported public API. It is not imported anywhere in the live execution path (`app.py`, `dual_test.py`). Phase A's import matrix and architectural assessment were built on an incomplete picture of the codebase surface. When chimera is wired in, the architectural questions Phase A raised (storage, API, BLE coupling) become live for this module.

**3. `DualTestSession` as second storage implementation.**
`dual_test.py` contains a `DualTestSession` class (lines 38–105) that writes JSONL in the same schema format as `SessionLogger` but does not use or extend it. There are now two independent storage implementations in `src/`, neither in a `storage/` module. The storage fragmentation is systemic, not an incidental misplacement of `SessionLogger`.

#### Structurally unresolvable by static analysis
Whether the chimera module's disconnection is intentional staging versus architectural drift requires author intent. The callback design in `H10Client` technically supports future pub/sub decoupling; whether the refactoring investment is warranted is a product decision.

---

## Structurally Unresolvable Findings

The following questions cannot be resolved by static analysis alone and require empirical validation or author clarification:

1. **Entrainment lag range adequacy** (C2): Whether fixed lags [4–8 beats] are sufficient for the specific breathing patterns EBS participants use requires session data with independent breath sensor measurements.

2. **Autocorrelation inflation clinical impact** (C2): How often minimum-buffer conditions (10 samples) occur in real sessions, and whether the 5× inflation ceiling affects downstream mode classification materially.

3. **Softmax ceiling remediation via temperature** (C4): Whether reducing temperature from 1.0 (e.g., to 0.1–0.5) resolves the threshold reachability problem is computationally verifiable but requires an informed calibration decision about the desired sharpness of mode membership.

4. **Cross-session aggregation error magnitude** (C1): Whether the weighted-mean vs. pooled-RMSSD discrepancy is clinically significant depends on between-session mean RR variance for individual users.

5. **`history_signature` usage in downstream systems** (C3): If `history_signature` is not actually consumed by any downstream logic (it appears in `PhaseDynamics` output but may not be used), the saturation defect may be inert. This requires tracing all consumers of `PhaseDynamics`.

6. **Chimera integration intent** (C5): Whether the dormant chimera module represents planned-but-not-yet-wired functionality or an abandoned design direction.

---

## Prioritised Remediation Actions

Ordered by severity. P0 = critical (correctness affected); P1 = high (validity claim broken); P2 = medium (confidence/documentation); P3 = low (technical debt).

### P0 — Critical

**P0-A: Fix autocorrelation normalization error** (`hrv.py:43–62`)
The mixed-denominator formula inflates autocorrelation by up to 5× at small buffer sizes. The clamp masks the error rather than the computation being bounded by design. The same error exists in `compute_trajectory_coherence()` (`phase.py:440–454`). Fix: use the same sample set in numerator and denominator (standard normalized autocorrelation). Re-validate entrainment scores against known-periodic test signals.

**P0-B: Fix softmax ceiling below entry thresholds for upper modes** (`movement.py:266–324`, call sites in `phase.py`)
Three of the six modes (`settling`, `emerging coherence`, `coherent presence`) are structurally unreachable at T=1.0. Either: (a) lower temperature at call sites (e.g., T=0.1–0.3) to sharpen softmax and clear the thresholds, or (b) recalibrate entry thresholds to match the geometric ceiling at the chosen temperature. The current design creates a classifier that cannot enter the states most meaningful to the system's stated purpose.

### P1 — High

**P1-A: Fix cross-session RMSSD/SDNN aggregation** (`AnalyticsService.swift:192–207`)
Replace weighted mean of per-session RMSSDs with proper pooled computation: accumulate `sumSquaredDiffs` and `pairCount` across all sessions, compute pooled RMSSD from the accumulated totals. SDNN requires tracking per-session means and computing between-session variance explicitly (or re-accumulating all RR intervals across sessions).

**P1-B: Fix `history_signature` semantic mismatch** (`phase.py:256–260`)
`cumulative_path_length / rolling_window_time` saturates to 1.0 within minutes. Replace with a genuinely windowed measure: use only the path length accumulated within the current 30-state window (compute from `self.states` deque, not the session-cumulative counter), divided by the time span of that same window. Alternatively, remove `history_signature` from `PhaseDynamics` output until it can be defined with consistent semantics.

**P1-C: Fix degenerate `breath_steady_score` centroid positions** (`movement.py:212–255`)
The `transitional` (bss=0.5) and `settling` (bss=0.8) centroids are unreachable because `breath_steady_score` is binary (0.3 or 1.0). Redesign `transitional` and `settling` centroids so their `breath_steady_score` component uses achievable values (0.3 or 1.0), or replace the boolean `breath_steady` input with a continuous measure. Document the centroid derivation method explicitly.

**P1-D: Remove or correct "coherence" mode labels** (`hrv.py:220–260`)
`"emerging coherence"` and `"coherent presence"` mode labels are computed from an entrainment-weighted score. Either rename them (e.g., `"high entrainment"`, `"sustained entrainment"`) to accurately reflect their derivation, or document explicitly in the label output that these labels are entrainment-derived, not trajectory-coherence-derived. The docstring distinction between entrainment and coherence exists at the computation level but fails at the label output boundary.

### P2 — Medium

**P2-A: Add minimum session length guard and degenerate output protection** (`HRVProcessor.swift:267, 313`)
Apply a minimum RR count guard (suggest: ≥ 60 intervals, ~1 minute at 60 BPM) before computing or storing RMSSD, SDNN, pNN50. Below this threshold, return nil/missing rather than a numerically degenerate value. Update `SessionSummaryCache.swift` to gate on this minimum before calling `computeClassicHRV`.

**P2-B: Wire up `expected_breath_period` or remove it** (`hrv.py:65–106`)
The parameter is accepted, never used. Either: (a) implement adaptive lag selection by deriving the dominant breath period from `compute_breath_rate()` output and passing it to `compute_entrainment()`, or (b) remove the dead parameter to prevent misleading future developers about what is wired up. Document the decision.

**P2-C: Rename or document `PhaseDynamics.acceleration_magnitude`** (`phase.py:85, 327`)
This field contains the second derivative of the scalar `mode_score`, not 3D trajectory acceleration. Rename it (e.g., `mode_score_acceleration`) to distinguish it from the `curvature` field, which contains the 3D phase acceleration. Add clear comments to both fields specifying which signal they derive from.

**P2-D: Add automated tests for iOS classic HRV methods**
`computeRMSSD`, `computeSDNN`, `computePNN50`, and `computeClassicHRV` in `HRVProcessor.swift` have zero automated tests. Add XCTest cases covering: known-valid RR sequences with ground-truth RMSSD/SDNN/pNN50 values, the 2-RR degenerate case, and boundary inputs. The cross-session aggregation fix (P1-A) should also be covered by tests.

**P2-E: Fix `docs/metrics.md:255`**
Line 255 states "All metrics are computed in `src/processing/hrv.py`." This is false for RMSSD, SDNN, and pNN50. Correct to specify that Python computes custom metrics (amplitude, entrainment, breath rate, volatility, mode) and iOS computes classic metrics (RMSSD, SDNN, pNN50) from stored RR intervals.

**P2-F: Isolate storage layer**
Move `SessionLogger` from `app.py` to `src/storage/session_logger.py`. Move `SemioticMarker` and `FieldEvent` from `api/websocket_server.py` to `src/domain/types.py` (or equivalent shared types module). Consolidate `DualTestSession` (`dual_test.py:38–105`) into the same storage module or extend `SessionLogger` to cover dual-test use cases. The current state — two storage implementations in two app-level files, neither isolated — makes the storage layer structurally invisible.

### P3 — Low / Technical Debt

**P3-A: Rename vocabulary to match implementation**
- `curvature` → `acceleration_magnitude_3d` (or document that it is `|r''(t)|`, not κ)
- `stability` docstring should specify "heuristic squashing function" rather than implying dynamical-systems stability
- `PhaseTrajectory`, `PhaseState`, `PhaseDynamics` class names: document that "phase" refers to the EECP breath-heart phase concept, not dynamical systems phase space
- `history_signature` field: document or remove after P1-B resolution

**P3-B: Remove or integrate dead code**
- `_last_velocity` (`phase.py:123, 247`) — dead code, remove
- `EMPTY_DYNAMICS.stability = 0.0` vs. warm-up default `0.5` — align the sentinel value
- `detect_rupture_oscillation()` (`movement.py:648–703`) — document its integration point or mark as unintegrated

**P3-C: Remove global singleton or make it an explicit parameter** (`device_registry.py:157–170`)
The `get_registry()` singleton causes hidden shared state. Prefer explicit dependency injection — pass a `DeviceRegistry` instance through the call chain rather than relying on the module-level `_registry`.

**P3-D: Integrate or formally defer chimera module**
`src/processing/chimera/` (~1100 lines) is dormant. Either: (a) document it as "planned, not yet integrated" in `CLAUDE.md` and add a TODO for the integration point into `phase.py`/`movement.py`, or (b) move it out of `src/processing/` to a staging directory to avoid its presence implying production integration.

**P3-E: Enforce lag coverage for slow breathing**
The lag range [4, 5, 6, 7, 8] misses the ~10-beat period associated with ~6 breaths/min (the breathing pattern associated with resonance in the EBS research context). Extend to [4, 5, 6, 7, 8, 9, 10, 11, 12] or use the `expected_breath_period` parameter (after P2-B) to adapt dynamically.

---

## Overall Confidence Assessment

**Overall audit confidence: 0.77**

The cross-pass analysis reveals a consistent pattern confirmed independently by both passes: the system is **operationally functional** with internally consistent implementations, while its **self-description consistently exceeds what the implementation delivers**. This pattern held across all five claims — none were CONFIRMED, none were NOT CONFIRMED. Phase B strengthened this picture by finding additional defects (P0-A, P0-B, P1-B, P1-C, P1-D) that Phase A did not surface.

Confidence is not 1.0 for three reasons:
1. **Phase B found substantive Phase A errors** in C2 (factual error about `compute_trajectory_coherence` being inactive) and C4 (missed the softmax ceiling problem and degenerate feature space). These are genuine Phase A weaknesses, not just additions.
2. **Some findings require empirical validation** — see Structurally Unresolvable section. Particularly, the practical impact of the entrainment lag gap and the autocorrelation inflation cannot be assessed from static analysis alone.
3. **Chimera module unexamined by Phase A** — Phase B's discovery of the ~1100-line dormant module means the Phase A architectural analysis was incomplete.

The highest-severity remediation actions (P0-A and P0-B) are both convergent: Phase B independently confirmed the autocorrelation normalization issue and derived the softmax ceiling mathematically. Neither rests solely on one pass's analysis.

---

*Generated by RAA-EBS-001 convergence-eval agent. Read-only analysis of target codebase. No target files modified.*
