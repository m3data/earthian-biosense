# Phase A Synthesis — RAA-EBS-001

**Date:** 2026-02-24
**Auditor:** a-synthesis agent
**Phase A findings reviewed:** 5 (A1–A5)

---

## 1. One-Line Summary of Each Finding

| ID | Claim | Verdict | Summary |
|----|-------|---------|---------|
| A1 | HRV metrics (RMSSD/SDNN/pNN50) are clinically accurate | **PARTIAL** | iOS implements the formulas correctly; Python pipeline has none of these metrics; cross-session RMSSD/SDNN aggregation is mathematically incorrect; no artifact filtering anywhere. |
| A2 | Entrainment captures breath-heart phase coupling on a 0–1 scale | **PARTIAL** | Bounded 0–1 is correct; entrainment/coherence distinction is genuine and structurally enforced; but the computation is RR autocorrelation at fixed lags (no breath signal), and the breath rate estimate never feeds into entrainment despite an architectural provision for this. |
| A3 | Phase space dynamics (velocity, curvature, stability) are computed from a valid 3D trajectory manifold | **PARTIAL** | 3D trajectory and velocity are real; curvature is acceleration magnitude (not geometric curvature); stability is a heuristic squashing function, not formal dynamical stability; "manifold" is aspirational rather than mathematically precise. |
| A4 | Mode classification uses soft membership across 6 centroids with hysteresis and movement annotation | **PARTIAL** | Soft membership (softmax-on-distances) and hysteresis (3-state machine, asymmetric thresholds) are genuine; centroids are analytically derived (not data-learned); movement annotation is post-hoc labeling that does not influence classification. |
| A5 | Architecture maintains separation of concerns between device, processing, API, and storage layers | **PARTIAL** | Module-level import boundaries are clean; but the documented event bus does not exist, `SessionLogger` lives in `app.py` and imports API types, `TerminalUI` is a god-object, and the REST API is entirely absent. |

All five findings returned **PARTIAL**. No finding was CONFIRMED or NOT CONFIRMED.

---

## 2. Patterns — Where Concerns Cluster

### Pattern 1: Vocabulary claims exceed implementation precision (all 5 findings)

The most consistent pattern across every finding is a gap between the conceptual vocabulary used in documentation, docstrings, and naming, and what the code actually delivers:

- "Phase coupling" (A2) → RR autocorrelation at fixed lags with no breath signal
- "Manifold" (A3) → 3D Euclidean feature space with implicit isotropy assumptions
- "Curvature" (A3) → `|acceleration|`, not κ = |r'×r''| / |r'|³
- "Stability" (A3) → heuristic inverse of velocity+curvature, not attractor analysis
- "Movement-preserving classification" (A4) → classification followed by movement annotation
- "Event bus" (A5) → direct-call callback chain in `TerminalUI.on_data()`

The code is operationally consistent and internally coherent. The issue is precision of claim, not correctness of computation. The vocabulary used implies theoretical grounding that the implementation has not yet delivered.

### Pattern 2: Architectural scaffolding present but unconnected (A2, A4, A5)

Several features have structural provisions that are not operational:

- `expected_breath_period` parameter in `compute_entrainment()` is accepted, never used (A2)
- `compute_breath_rate()` and `compute_entrainment()` are computed independently from the same RR series with no cross-feed (A2)
- `compute_trajectory_coherence()` in `phase.py` is defined but likely not called in the live pipeline (A2, consistent with A5's pipeline trace)
- `H10Client._callbacks` supports multiple subscribers but only one is registered (A5)
- Temperature parameter for soft membership is hardcoded to 1.0 at all call sites (A4)
- `detect_rupture_oscillation()` is defined in `movement.py` but its integration point is unverified (A4)

These are incomplete features masquerading as implemented ones. They represent technical debt that could mislead future developers about what is active.

### Pattern 3: Dual-system architecture without integration or deprecation (A1, A4)

Two parallel metric systems coexist without reconciliation:

- **HRV metrics**: Python pipeline uses custom metrics (amplitude, autocorrelation entrainment, volatility); iOS uses clinical RMSSD/SDNN/pNN50. Neither integrates with the other; they share only the JSONL schema as an informal boundary (A1).
- **Mode classification**: Legacy `compute_mode()` in `hrv.py` (scalar threshold system) and new `movement.py` (soft membership + hysteresis) run independently. The new system's movement annotation velocity is derived from the old system's scalar output — a latent coupling from the old layer into the new (A4).

Neither old system has been deprecated or marked as legacy. Both produce outputs that appear in the pipeline simultaneously, with no documented relationship between them.

### Pattern 4: Missing empirical grounding for quantitative claims (A1, A2, A3, A4)

Several quantitative choices lack calibration evidence:

- Mode centroids reverse-engineered from threshold midpoints, not learned from biosignal data (A4)
- Fixed entrainment lags [4,5,6,7,8] beats — not validated against breath frequency distributions; likely to miss slow resonant breathing at ~6 breaths/min (lag ~10) (A2)
- Phase space axis scaling (breath: 4–20 bpm range; amplitude: 0–200ms) is empirically assumed; Euclidean isotropy across physiologically incommensurable axes (A3)
- `history_signature` speed normalisation constant 0.5 and stability coefficient 2.0 are magic numbers with no documented basis (A3)
- No minimum window length enforced for clinical HRV metrics (A1)
- No ectopic beat filtering (A1)

---

## 3. Findings Most Worth Adversarial Review

### Priority 1 — A2 (Entrainment as breath-heart phase coupling)

This is the highest-value target for Phase B because the claim is central to the system's conceptual identity ("entrainment" is a first-class term in EECP) and the gap is both interpretive and structural.

Phase A found: the computation is RR autocorrelation at fixed lags, without a breath signal. The breath rate estimate is computed independently from the same RR series and never fed into entrainment. The very breathing pattern associated with coherence-promoting practice (slow resonant ~6/min) falls outside the checked lag range [4–8 beats].

Phase B should independently verify: (a) whether autocorrelation-at-fixed-lags is a defensible proxy for RSA in HRV research literature, or whether Phase A's criticism is too strict; (b) whether the lag range gap at slow breathing is genuinely consequential for the populations/protocols EBS targets; (c) whether the dead `expected_breath_period` parameter indicates an incomplete feature or a deliberate simplification.

### Priority 2 — A1 (Cross-session HRV aggregation error)

Phase A identified a specific, verifiable mathematical defect: `AnalyticsService.swift` aggregates per-session RMSSD values using RR-count-weighted averaging, which is not algebraically equivalent to RMSSD of the pooled dataset. This is a concrete claim about a concrete formula.

Phase B should independently verify: (a) whether the formula as written is genuinely incorrect, or whether there's a use-case in which weighted RMSSD averaging is an acceptable approximation; (b) whether `SessionSummaryCache.swift` correctly accumulates per-session RR intervals before passing to `computeClassicHRV`; (c) whether the Python pipeline's complete absence of RMSSD/SDNN/pNN50 is accurately characterised.

### Priority 3 — A4 (Movement annotation vs. movement-preserving classification)

The distinction Phase A draws — "movement-preserving classification" versus "classification with movement annotation" — is subtle but material to the v1.1.0 feature claim. Phase A asserts movement does not influence classification; it only describes it post-hoc.

Phase B should independently verify: (a) whether there is any code path by which velocity, acceleration, or movement state feeds back into centroid distances, hysteresis thresholds, or mode selection; (b) whether the suppression of "settled" annotation in `compose_movement_aware_label()` is intentional design or an oversight; (c) whether the two-system coupling (mode_score from legacy `compute_mode()` feeding the new system's movement annotation) creates correctness risks.

---

## 4. Contradictions and Cross-Finding Tensions

### Coherent: A2 and A5 on trajectory coherence being inactive

A2 noted that `compute_trajectory_coherence()` exists in `phase.py` but may not be called in the live pipeline. A5's trace of `app.py` and `TerminalUI.on_data()` confirms the live pipeline calls `compute_hrv_metrics()` and `trajectory.append()` — there is no call to `trajectory.get_coherence()` or equivalent in the described data path. The two findings independently converge on this gap without either explicitly calling it out as the headline. Neither contradicts the other; together they strengthen the concern.

### Tension: A5 (clean module boundaries) vs. A2/A4 (internal dual-system coupling)

A5 characterises the module-level import matrix as clean — processing modules do not import from BLE, API, or storage. This is accurate at the static import level. However, A2 and A4 identify dynamic coupling patterns that don't show up in the import graph: `compute_mode()` output feeding `movement.py`'s annotation velocity (A4), and `compute_breath_rate()` and `compute_entrainment()` operating on the same RR series without coordination (A2). The architecture looks clean from outside the processing layer but has internal entanglement within it that A5's import-matrix analysis does not capture.

### No direct contradictions between findings

All five findings are independently consistent. No finding asserts something that another finding contradicts. The dual-system pattern (A1/A4) and the vocabulary-precision pattern (all five) are mutually reinforcing observations from different angles.

---

## 5. Overall Assessment

The Phase A audit reveals a system that is **operationally functional but conceptually overreaching in its self-description**. The code does what it does consistently and with reasonable care — bounded outputs, cold-start handling, stateful history, genuine probabilistic soft membership. The concerns are not about broken implementations; they are about claims that exceed what is delivered.

The most significant structural issues, in order of severity:

1. **Entrainment without a breath signal** (A2) — the central physiological claim of the system is a one-sided proxy, and its most important use case (slow resonant breathing) is likely systematically underdetected.
2. **Cross-session RMSSD/SDNN aggregation error** (A1) — a concrete mathematical defect in the iOS analytics path.
3. **Movement annotation that doesn't move the classifier** (A4) — v1.1.0 is marketed as "movement-preserving classification" but movement is observational, not causal.
4. **Event bus and REST API absent** (A5) — documented architecture does not match implementation.
5. **Curvature/stability/manifold vocabulary** (A3) — imprecise naming that could mislead downstream interpretation.
