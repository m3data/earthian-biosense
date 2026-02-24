## Claim

Mode classification uses soft membership across 6 centroids with hysteresis and movement annotation. Schema v1.1.0 documents all required fields.

## Files Examined

- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/src/processing/movement.py` — lines 1–704 (full file)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/src/processing/hrv.py` — lines 220–260 (`compute_mode`)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/src/processing/phase.py` — lines 177–328 (`_compute_dynamics`)
- `/Users/m3untold/Code/EarthianLabs/Earthian-BioSense/src/processing/schema.py` — lines 1–42 (full file)

## Evidence

### 1. Are there exactly 6 centroids? What defines them?

`MODE_CENTROIDS` in `movement.py:212–255` defines exactly 6 named modes:
- `heightened alertness`, `subtle alertness`, `transitional`, `settling`, `emerging coherence`, `coherent presence`

Each centroid is a point in a 4-dimensional feature space: `(entrainment, breath_steady_score, amp_norm, inverse_volatility)`. Feature weights are defined in `FEATURE_WEIGHTS` (`movement.py:258–263`): entrainment=0.4, breath_steady_score=0.3, amp_norm=0.2, inverse_volatility=0.1.

**Derivation method:** The centroids are analytically defined, not data-derived. The comment at `movement.py:205–208` explicitly states they are "derived from reverse-engineering calm_score formula at threshold midpoints." Each centroid corresponds to the midpoint of the calm_score range for the equivalent threshold band in `hrv.py:compute_mode` (lines 247–260). This means centroid placement is inherited from the pre-existing threshold system, not learned from biosignal data.

### 2. Is soft membership computed (distance-based probabilities, not just argmin)?

Yes. `compute_soft_mode_membership()` (`movement.py:342–431`) implements genuine soft membership:

- Builds a position vector from the 4 features (`movement.py:369–377`)
- Computes feature-weighted squared Euclidean distance from the current position to each of the 6 centroids (`movement.py:379–386`)
- Applies softmax over negative distances with an adjustable temperature parameter (`movement.py:388–397`): `weight_i = exp(-d_i / T) / Σ exp(-d_j / T)`, with numerical stability offset
- Returns a `SoftModeInference` dataclass with: full membership dict (all 6 weights, summing to 1.0), primary mode, secondary mode, ambiguity score (1 - margin between top two), and optional KL divergence from previous inference (`movement.py:411–424`)

This is a well-formed probabilistic soft assignment — not argmin.

### 3. Is hysteresis implemented to prevent mode flickering?

Yes. `detect_mode_with_hysteresis()` (`movement.py:438–557`) implements a proper three-state machine:

- **States:** `unknown → provisional → established` (tracked in `ModeHistory._state_status`)
- **Asymmetric thresholds:** Per-mode `HysteresisConfig` (`movement.py:71–101`) separates `entry_threshold` from `exit_threshold` (exit is always higher). For example, `coherent presence` has entry=0.22, exit=0.28 (`movement.py:316–324`).
- **Entry penalty:** New mode confidence is multiplied by `entry_penalty` (< 1.0) on entry (`movement.py:499, 544`)
- **Settled bonus:** Confidence is boosted by `settled_bonus` (> 1.0) after `established_samples` dwell time (`movement.py:522`)
- **Exit guard:** When established, mode only exits if `raw_confidence >= current_config.exit_threshold`. Below this, the system stays in current mode and returns `exit_threshold * 0.9` as confidence (`movement.py:528–532`)

`ModeHistory` (`movement.py:103–198`) tracks history, dwell time, transition counts, and provisional duration.

### 4. Does movement annotation actually influence classification?

**No — movement annotation is post-hoc descriptive labeling, not a classification input.**

The classification pipeline in `phase.py:_compute_dynamics` (lines 271–328) is:
1. `compute_soft_mode_membership()` — computes membership from HRV features
2. `detect_mode_with_hysteresis()` — selects final mode using state machine
3. `generate_movement_annotation()` — generates annotation from velocity/acceleration/dwell_time
4. `compose_movement_aware_label()` — appends annotation to mode name as a string

Movement annotation is computed *after* classification is complete (`phase.py:291–303`). It does not modify membership weights, hysteresis thresholds, centroid distances, or which mode is selected. The velocity and acceleration used for annotation come from the mode_score scalar (`hrv.py` output), not the phase-space position vector that feeds classification.

Furthermore, `compose_movement_aware_label()` (`movement.py:628–641`) explicitly strips "settled" from composed labels: if `movement_annotation` is `"insufficient data"`, `"unknown"`, or `"settled"`, the plain mode name is returned unchanged. This means the most meaningful annotation state ("settled") is transparent to downstream consumers who read only the label.

The module's name ("movement-preserving classification") and docstring intent suggest movement should constrain or modify classification. The actual design is movement-annotated classification — a meaningful distinction, but one where movement is observational, not causal.

### 5. Is the v1.1.0 schema claim accurate — are all documented fields present?

`schema.py:12–21` documents 6 new v1.1.0 fields for the phase object:

| Schema field | PhaseDynamics field | Present? |
|---|---|---|
| `movement_annotation` | `movement_annotation` (`phase.py:73`) | YES |
| `movement_aware_label` | `movement_aware_label` (`phase.py:76`) | YES |
| `mode_status` | `mode_status` (`phase.py:79`) | YES |
| `dwell_time` | `dwell_time` (`phase.py:82`) | YES |
| `acceleration_mag` | `acceleration_magnitude` (`phase.py:85`) | YES (name mismatch) |
| `soft_mode` | `soft_mode` (`phase.py:70`) | YES |

All 6 fields are present. Minor inconsistency: schema.py documents `acceleration_mag` but the dataclass field is named `acceleration_magnitude`. Consumers reading schema docs would find the field under a slightly different name.

## Finding

**Verdict: PARTIAL**

Soft membership is genuinely implemented — the softmax-on-distances approach produces a real probability distribution across all 6 modes, not argmin. Hysteresis is properly implemented with asymmetric entry/exit thresholds, a three-state machine (unknown/provisional/established), and per-mode calibration. The v1.1.0 schema fields are all present in `PhaseDynamics`, with one minor naming discrepancy (`acceleration_mag` vs `acceleration_magnitude`).

However, two claims exceed implementation. First, the centroids are analytically derived from the existing threshold system (reverse-engineered from `compute_mode` in `hrv.py`), not learned from physiological data. The soft membership architecture is sound, but the centroids inherit the assumptions and potential biases of the original scalar threshold design. Second — and more significantly — movement annotation does not influence classification. It is computed after the mode is determined and appended as a string label. The module positions itself as "movement-preserving classification," but the implementation is better described as "classification with movement annotation." Movement context is tracked and exposed, but it does not feed back into membership computation, hysteresis decisions, or mode selection. The `compose_movement_aware_label()` function additionally suppresses the "settled" annotation from the composed label, meaning the richest temporal context is invisible in the primary label field.

## Notes

- The two-system architecture (legacy `compute_mode` in `hrv.py` + new `movement.py`) means `HRVMetrics.mode_label`/`mode_score` and `PhaseDynamics.soft_mode`/`movement_aware_label` are computed independently and may diverge. `hrv.py`'s `compute_mode` is still called in the pipeline and its output populates `mode_score` in `PhaseDynamics` (used as the mode_score velocity input). This creates a latent coupling: the new soft membership's movement annotation velocity is derived from the old system's scalar output, not from the new soft membership score.
- Temperature parameter in `compute_soft_mode_membership()` is hardcoded to `1.0` at all call sites in `phase.py`. The mechanism for tuning soft/sharp membership exists but is not exposed to users or configuration.
- The centroids are uniformly spaced along the calm_score axis, which means the soft membership geometry reflects the linear structure of the original threshold system. Physiological distributions may not be uniformly distributed along this axis.
- The `detect_rupture_oscillation()` function (`movement.py:648–703`) is defined and exported but its integration point into the wider system is not visible in these files — it is unclear if it is called during normal processing.
