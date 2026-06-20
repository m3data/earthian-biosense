---
id: SPEC-014
title: Two-Axis Mode Classification (stillness × trajectory coherence)
status: implemented
version: 1.0
created: 2026-06-20
implemented-date: 2026-06-20
author: Mat Mytka + Kairos
---

# SPEC-014 — Two-Axis Mode Classification

**Status:** implemented (retroactive — code shipped in `0e0ba12`, `cae4d87`, `71e7ee7` before this spec was written; this document anchors the intent and contracts after the fact, per the USDD gate).
**Scope:** Add trajectory coherence as a second, orthogonal classification axis alongside the existing calm/stillness scalar, in both engines (Python + Rust desktop) and both replay frontends. Additive and back-compatible; the existing 1-D mode is untouched.

> **Provenance note (USDD Constitutional Principle 13 — Intent-Anchored).** This spec is **retroactive documentation** of shipped code. That is itself a P13 risk: a spec mined from an implementation codifies whatever defects the implementation already has. To mitigate, the requirements below are written from the *intent* that drove the build (named in [[#Background]]), not read back off the code, and the code is then checked against them by a separate clean-context adversarial review ([[#TEST-014 / Verification]] → Adversarial Review). The proper order (SPEC → code) was not followed here; this spec exists to close that gap and to serve as the worked example of the build/ship USDD gate now wired into `vibe-mode`.

---

## Background — why this matters

EBS classifies autonomic state into six modes. As built, those six are **bins along a single scalar**, `calm_score`
(`hrv.py` = `entrainment·0.4 + breath_steady·0.3 + amp_norm·0.2 + inverse_volatility·0.1`),
sliced at five thresholds. The "soft membership in 4-D centroid space" (`movement.py`) is
reverse-engineered from that same scalar at the bin midpoints with the same weights — so the four
centroid dimensions are collinear by construction. It is softmax over distance **along a line**.

That single axis is the *stillness/entrainment* family. The project's own central distinction —
**coherence is not entrainment** (entrainment = local breath-heart sync; coherence = trajectory
integrity over time) — is therefore **absent from the classifier**. `trajectory_coherence` is
computed every tick (`phase.py::compute_trajectory_coherence`), logged, displayed, and streamed,
but the mode is decided *before* coherence exists and never consults it.

Empirically, across 36 sessions / 15,909 records, **corr(calm_score, coherence) = +0.001** — the two
axes are orthogonal. So coherence is free, independent information the 1-D label discards. Within a
single calm-rung, coherence ranges nearly full-scale (e.g. "transitional" spans coherence 0.00–0.88);
4.5% of alert-labelled records are genuinely fragmented (coh < 0.2) while 0.9% are high-coherence
(≥ 0.5) — same label, opposite journeys.

The fix is a **plane, not a longer line**: classify over (stillness × coherence). Coherence cannot be
folded into `calm_score` as a fifth weight — that would re-collapse the very distinction the project
calls its key insight.

## Goal

Add a soft-membership classification over a 2-D (calm × coherence) plane as an **additive** field
(`soft_mode_2d`), wired into both engines after coherence is available, persisted to session logs,
streamed/emitted on the live channels, and surfaced in both replay frontends — without altering the
existing 1-D `mode` / `soft_mode` path or breaking old session files.

## Non-goals (v1.0)

- Replacing or removing the 1-D `mode` / `soft_mode` (both retained verbatim).
- Hysteresis / state-machine smoothing on the 2-D modes (1-D keeps its hysteresis; 2-D is raw soft membership for now).
- Settling the **label vocabulary** — `reactive` / `engaged` / `transitional` / `constrained stillness` / `settled presence` are PROVISIONAL placeholders (a research-vocabulary decision, not an engineering one).
- Calibrating centroid placement / softmax temperature against labelled data (corpus skews low-coherence; tuning is [[#Phase 4 — Feedback]]).
- Feeding EEG / Muse S as a third axis (separate future surface; this plane is the frame it will plug into).
- Deduplicating the four copies of the centroid definition (see [[#ADR-014-3]] — explicit deferral).

---

## Requirements

### REQ-014-1 — Orthogonal second axis
The classifier MUST compute a soft membership over a 2-D plane whose axes are (a) the instantaneous
calm/stillness scalar (`mode_score`) and (b) trajectory coherence
(`compute_trajectory_coherence`). The coherence axis MUST be the longitudinal metric, sharing no
input terms with `calm_score`. *Verified by* [[#TEST-014-1]].

### REQ-014-2 — Coherence must bite
Holding `calm_score` fixed and varying coherence across its range MUST be able to change the primary
2-D mode. (If it cannot, coherence is doing no work and the feature is vacuous.) *Verified by* [[#TEST-014-2]].

### REQ-014-3 — Soft membership, normalised
`soft_mode_2d` MUST return a membership distribution over the 2-D modes summing to 1.0 (± 1e-6), a
`primary_mode`, a `secondary_mode`, and an `ambiguity` scalar defined identically to the 1-D field
(`1 − (top₁ − top₂)`). *Verified by* [[#TEST-014-3]].

### REQ-014-4 — Ambiguity must de-saturate
The 1-D ambiguity field is degenerate (six collinear centroids → near-uniform softmax → ambiguity
pinned at mean 0.996, min 0.941). The 2-D field MUST be **low near a centroid** and **high between
distant centroids**, i.e. the ambiguity field MUST move with position rather than sit at ceiling.
*Verified by* [[#TEST-014-4]].

> **Honesty note (from adversarial review):** this is met *structurally* (range 0.336–1.000, sd 0.060)
> but **weakly where the data lives**. The real corpus clusters in the reactive↔transitional border
> (centroids ~0.35 apart), where the field still reads ≈ 0.92 mean — only 0.076 below the 1-D's 0.996.
> The requirement is satisfied as written, but the *practical* de-saturation in the populated region
> is marginal until the centroids are spread / temperature tuned. This is the genuine research finding,
> not just engineering debt — see [[#Phase 4 — Feedback]] / OBS-014-2. The centroids being too tightly
> spaced for this corpus is itself a result about how little of the (calm × coherence) plane these
> sessions actually occupy.

### REQ-014-5 — Additive, back-compatible
Adding `soft_mode_2d` MUST NOT alter the existing 1-D `mode` / `soft_mode` / `mode_score` values, and
MUST NOT break parsing of pre-existing session files. The field is absent (or `null`) on records
predating this feature. *Verified by* [[#TEST-014-5]].

### REQ-014-6 — Canonical coherence value
The coherence fed to the 2-D classifier MUST be the same value that is logged and streamed in the
same tick (no recomputation, no reorder that would let the two diverge). *Verified by* [[#TEST-014-6]]
(integration: the logged `phase.coherence` equals the coherence used for `soft_mode_2d`).

### REQ-014-7 — Engine parity (scoped)
Given the **same `(calm, coherence)` input**, the Python and Rust `compute_2d_mode_membership`
implementations MUST produce the same primary mode and ambiguity (within floating-point tolerance).
*Verified by* [[#TEST-014-7]].

> **Scope correction (from adversarial review, 2026-06-20):** the 2-D classifier *function* is at
> four-way parity (verified). But the **upstream `compute_trajectory_coherence` is NOT** — the
> insufficient-data guard differs (`phase.py` effective gate ≥ 8 states; `phase.rs:314` ≥ 7), so at
> the warm-up boundary the two engines feed *different* coherence into the otherwise-identical
> classifier. This requirement is therefore scoped to the classifier function; the coherence-guard
> divergence is a **pre-existing** defect tracked in [[#Residue]] (a direction fork — changing the
> coherence metric is published-adjacent, deferred to Mat).

### NFR-014-1 — Per-tick cost
The 2-D computation MUST add negligible cost to the 1 Hz pipeline (five centroid distances + a softmax;
O(modes)). No new allocation per tick beyond the membership map.

### NFR-014-2 — Provisional labels are visibly provisional
The label set MUST be marked PROVISIONAL in code comments and in this spec, so the placeholder status
is not silently reified into research vocabulary.

---

## Contracts

### CON-014-1 — `compute_2d_mode_membership` (both engines)
```
compute_2d_mode_membership(calm_score: f64, coherence: f64,
                           temperature = 0.15,
                           previous_inference: Option<SoftModeInference>)
    -> SoftModeInference
```
- Inputs clamped to [0,1]. Equal-weighted squared Euclidean distance to each centroid; softmax over
  negative distances with max-subtraction for numerical stability.
- `MODE_CENTROIDS_2D` (calm, coherence): reactive (0.15, 0.12), engaged (0.30, 0.62),
  transitional (0.45, 0.35), constrained stillness (0.72, 0.15), settled presence (0.78, 0.68).
- Returns the existing `SoftModeInference` shape (membership / primary / secondary / ambiguity /
  distribution_shift), reused so downstream consumers need no new type.

### CON-014-2 — Session JSONL `phase.soft_mode_2d` (persisted)
Additive nested object under `phase`:
```json
"soft_mode_2d": {
  "primary": "transitional",
  "secondary": "reactive",
  "ambiguity": 0.41,
  "distribution_shift": 0.0012,
  "membership": { "transitional": 0.40, "reactive": 0.33, ... }
}
```
- Python engine: schema **1.2.0 → 1.4.0** (1.3.0 reserved for the Rust motion-channel lineage).
- Rust desktop engine: schema **1.4.0 → 1.5.0** (independent lineage).
- `null` / absent on pre-feature records.

### CON-014-3 — Live channels
- Python WebSocket `phase` message: adds `mode_score` and `soft_mode_2d` (additive keys; existing
  consumers ignore unknown keys — the wire test asserts only presence of a subset).
- Rust `ebs:phase` Tauri event: adds `soft_mode_2d` (and already carried `mode_score`).

---

## Architecture decisions

### ADR-014-1 — Plane, not a fifth weight
**Decision:** Introduce a separate 2-D classifier rather than adding coherence as a term in
`calm_score`. **Rationale:** folding coherence into the calm scalar re-collapses the orthogonal axis
into the stillness line, destroying the entrainment/coherence distinction (the project's key insight)
and re-degenerating the ambiguity field. The orthogonality (corr +0.001) is the asset; a plane
preserves it. **Consequence:** two membership fields coexist (`soft_mode` 1-D, `soft_mode_2d` 2-D);
the 1-D is retained for back-compat and its hysteresis.

### ADR-014-2 — Reuse `SoftModeInference`, equal-weight axes
**Decision:** Reuse the existing inference struct and weight the two axes equally (plain Euclidean).
**Rationale:** no prior reason to privilege stillness over integrity in a first cut; reusing the
struct means loggers/streamers/consumers need no new type. **Consequence:** temperature (0.15) and
centroid placement are the only tunables; both are flagged for [[#Phase 4 — Feedback]] calibration.

### ADR-014-3 — Duplicate the centroids across engines/frontends (DEFERRED dedupe)
**Decision (P15 deviation, logged):** the centroid table + softmax now exists in **four** places —
`Earthian-BioSense/src/processing/movement.py` (source of truth), `desktop/src-tauri/src/hrv/movement.rs`,
`viz/js/config.js`, and `desktop/src/js/config.js` — plus `modespace.js` duplicated across the two
frontends. **Rationale for deviating from P15 (Right Place for the Function):** the two engines are
different languages and the two frontends are an existing diverged copy; a shared definition would
require a build-time codegen or a shared data file loaded by all four, which is its own piece of work.
The user explicitly chose "port into the copy" for speed of parity. **Deferral:** a single canonical
centroid definition (e.g. a JSON the engines and frontends read, or codegen from the Python source)
is a tracked follow-up. **Owner:** Mat + Kairos, next EBS build session. **Risk if not done:** tuning
the centroids or renaming a region is a 4–6-file edit; drift between engines silently breaks
[[#REQ-014-7]] engine parity. *This is the kind of debt the gate exists to surface, not hide.*

> **Review addendum:** the duplication is worse than first stated — the softmax **temperature (0.15)**
> is a *fifth* hard-coded copy (`movement.py`, `movement.rs` caller, both `config.js` twins), not
> enumerated in the original ADR. Change it in one place and parity breaks silently. The canonical
> single-source-of-truth follow-up MUST cover centroids **and** temperature.

---

## Verification

### TEST-014-1 — Orthogonal axis present
Python `TestTwoDimensionalModeMembership::test_membership_sums_to_one` + Rust
`test_2d_membership_sums_to_one`: the function exists, takes (calm, coherence), returns normalised
membership over 5 modes. **PASS.**

### TEST-014-2 — Coherence bites (the core proof)
`test_coherence_axis_bites` (Py) / `test_2d_coherence_axis_bites` (Rust): calm fixed at 0.30,
coherence 0.05 → `reactive`, coherence 0.68 → `engaged`; primary differs. **PASS** (both engines).

### TEST-014-3 — Membership shape
`test_membership_sums_to_one`, `test_all_2d_modes_present`, quadrant tests
(`settled_coherent → settled presence`, `activated_fragmented → reactive`,
`activated_coherent → engaged`, `settled_fragmented → constrained stillness`). **PASS** (both engines).

### TEST-014-4 — Ambiguity de-saturates
`test_ambiguity_desaturated_at_centroid` (< 0.7 on a centroid) and
`test_ambiguity_high_between_centroids` (> 0.85 midway between reactive and settled presence). **PASS.**
Replay over 15,909 records: 1-D ambiguity 0.996 (pinned) → 2-D 0.336–1.000, sd 0.060.

### TEST-014-5 — Additive / back-compat
`test_inputs_clamped`; full suites green with no change to 1-D assertions (Python 135 passed incl. WS
contract; Rust 22 movement tests passed). Old sessions parse; `soft_mode_2d` absent ⇒ frontend falls
back to the JS twin.

### TEST-014-6 — Canonical coherence value
Integration (manual, `app.py` / `lib.rs` read): `soft_mode_2d` is computed from the same `coherence`
local that is passed to the logger and the broadcast in the same tick. **Confirmed by inspection;**
*not yet an automated assertion* — see [[#Residue]].

### TEST-014-7 — Engine parity
JS twin vs Python verified equal on the coherence-bites case (reactive vs engaged at calm 0.30); Rust
unit tests assert the same quadrant outcomes as Python. *No automated cross-engine numeric diff
harness yet* — see [[#Residue]].

### Adversarial Review (USDD P12 — clean-context, NON-NEGOTIABLE)
A separate clean-context review, given only this spec + the diff, mandated to find defects. Ran
2026-06-20; findings folded back here (see [[#Residue]]). *This is the gate step that was missing from
the original build and is the reason this spec exists.*

---

## Phase 4 — Feedback

- **OBS-014-1** — distribution of `soft_mode_2d.primary` over real sessions (currently
  transitional 57% / reactive 37% / engaged 4% / constrained stillness 1.5% / settled presence ~0%).
  `settled presence` is near-unreached because this corpus rarely pairs high calm with high coherence
  — a property of the corpus, and a signal the coherence axis may want its own scaling pass.
- **OBS-014-2** — 2-D ambiguity mean ≈ 0.92: the corpus clusters in the reactive↔transitional border,
  so most points genuinely sit between centroids. Temperature/placement tunable to use more of the
  range in the populated region.

## Residue (open, tracked)

### Clean-context adversarial review (2026-06-20) — outcome
A fresh-context reviewer (spec + diff only, mandated to find defects) ran the P12 gate. The 2-D
classifier math was confirmed at genuine four-way parity. It found bugs the generating session missed:

**Fixed same session (low-risk, clearly correct):**
- **S1-2 (reset state leak)** — neither engine's `reset()` cleared the 2-D inference, so the first
  `distribution_shift` of every subsequent session was computed against the *prior* session's last
  sample. Fixed in `phase.py::reset` and `phase.rs::reset` (added `_last_2d_inference = None`).
- **S2-2 (warm-up mislabel)** — the JS fallback painted `coherence == 0` (the insufficient-data
  sentinel) as the plane-origin → `reactive`, instead of suppressing. Fixed in both `config.js`
  copies (`getModeSpace2D` returns null when `coh === 0`).

**Deferred (direction forks / larger work — for Mat):**
- **S1-1 (coherence-guard divergence)** — `compute_trajectory_coherence` gates at ≥ 8 states (Python)
  vs ≥ 7 (Rust); one-tick warm-up divergence feeds different coherence to the two classifiers.
  *Pre-existing* in the coherence metric (published-adjacent); fixing it changes coherence semantics →
  Mat's call which guard is canonical. REQ-014-7 scoped to the classifier function meanwhile.
- **S2-1 (schema-version discriminator)** — same feature is Python 1.4.0 / Rust 1.5.0 with no shared
  "has soft_mode_2d" discriminator; works today only via presence-sniffing the key. Decide a shared
  discriminator or accept presence-sniffing as the contract.

### Other open
- **ADR-014-3 dedupe** — five copies (centroids + temperature); single source of truth deferred.
- **TEST-014-6/7 automation** — the "canonical coherence value" invariant and cross-engine numeric
  parity are verified by inspection, not by an automated assertion. Worth a small test each.
- **REQ-014-4 practical de-saturation** — marginal in the populated region (≈0.92); centroid spread /
  temperature tuning needed for the field to read as designed where the data lives.
- **Label vocabulary** — provisional; research-vocabulary call pending (Mat).
- **2-D hysteresis** — none yet; raw soft membership may flicker at boundaries on noisy input.

---

## Research Questions (open — investigate, do not act on in published work)

### RQ-SPEC014-1 — Is the under-occupied plane the instrument, the model, or the person?
**Status: HELD OPEN (2026-06-20). Not confirmed either way. Publication-adjacent.**

The plane is sparsely occupied (REQ-014-4 de-saturation is weak; `settled presence`
reached ~2/15,909). Investigating *why*, three nervous systems across three contexts
were compared, then the coherence metric itself was probed:

- **Cross-person, context-controlled:** dyadic participants A (calm 0.36 / coh 0.28)
  and B (0.34 / 0.26) occupy nearly the same patch (separation 0.031 vs within-spread
  0.084) — but confounded (a dyadic *coupling* session, they may be co-regulating).
- **Different person, settled context:** Gem-in-bath (iOS export `2026-06-17_011601`,
  reprocessed) centres coherence 0.25, **maxes at 0.50, 0% of session ≥ 0.5** — though
  the bath signal has RR artifacts (263–2898 ms) that depress trajectory coherence.
- **The tell:** Mat solo (0.28), A (0.28), B (0.26), Gem (0.25) all centre on the
  **random-walk noise floor (0.280)** measured by feeding the metric a random walk.
- **Metric ceiling test** (synthetic known-integrity paths through
  `compute_trajectory_coherence`): steady linear drift → 0.800 *(a hardcoded
  `variance<1e-10 → 0.8` degenerate branch, not computed)*; smooth accelerating drift
  → 0.746; **smooth breathing-like oscillation → 0.167 (below the noise floor)**;
  random walk → 0.280. The metric rewards monotonic **drift** and scores rhythmic
  **oscillation** at/below noise. The 2-D centroids place engaged/settled-presence at
  coherence 0.62/0.68 — in territory only smooth drift reaches.

**Critical interpretation (Mat) — do NOT read this as "the entrainment≠coherence
direction is wrong":** a smooth breathing oscillation IS *entrainment* (breath-heart
phase locking). The project's thesis is precisely that common usage mislabels
entrainment as "coherence." So the metric scoring that oscillation at the noise floor
may be the **entrainment ≠ coherence cut working as designed** — trajectory-integrity
is a genuinely different thing from rhythmic locking, and oscillation scoring low can
*vindicate* the distinction. The conceptual direction is not in question.

**The reframe (felt-sense corrects the analyst's context labels).** The "settled"
sessions probably weren't: Gem's bath was actually *stressful* (a child walked in
complaining mid-bath); Mat's meditation was *brief*, and his own practice needs
**30–40 min** to reach sustained settling. So the low coherence is most likely a
*correct* reading of states that genuinely weren't coherent. **Coherence is the slow
variable** (the journey / global integrity in the entrainment/coherence/freedom triad)
— it has a *characteristic timescale*, and almost nothing in this corpus runs long
enough to cross it. The noise-floor convergence is therefore most likely **corpus
undersampling of the phenomenon**, not "no nervous system reaches coherence."

**Three held-open layers, in leading order (none confirmed):**
1. **Corpus undersampling** — short / mixed / interrupted sessions don't reach
   *sustained* coherence (needs ~30–40 min and the right activity). Leading explanation.
2. **Threshold / centroid tuning** — the brief, transient excursions that *do* occur
   are real but the centroids miss them. Gem's bath held **~13s of genuine emerging
   coherence** (11s ≥ 0.45, longest single excursion 23s ≥ 0.4, 23 excursions ≥ 0.35,
   peak 0.50 over 18.6 min) — yet the `engaged` / `settled presence` centroids sit at
   coherence 0.62 / 0.68, *above where real settling actually lands*, so a true
   micro-settle is binned as transitional. Tune centroids to the band real excursions
   occupy.
3. **(secondary) Operationalization** — the metric may be a touch conservative
   (hardcoded 0.8 degenerate branch; lag-5; catches drift-style integrity). But the
   **entrainment ≠ coherence direction is NOT in question** — oscillation scoring low
   is the cut working, since a smooth breathing rhythm *is* entrainment.

**Validation design (the only thing that separates corpus-gap from instrument-error).**
Phenomenologically-labelled **long-duration** sessions: the participant marks their own
felt "settling now" (e.g. Mat at ~min 30 of a 40-min sit), and we test whether the
metric's coherence rises in the self-reported window — the mutual-constraint check,
felt sense ⇄ measurement validating each other. Multiple people; varied activities
(meditation, exercise, long-duration). **This needs more data, not more analysis of the
current corpus.**

**Cheap interim probes:** (1) oscillation period:lag sweep to map where rhythm vs drift
crosses; (2) relocate the 2-D coherence centroids to the band real excursions occupy
(~0.4–0.5) and re-check REQ-014-4 de-saturation; (3) make the modes sensitive to brief
excursions (a 13–23s settle should not read as noise). Publication-adjacent — nothing
in published work changes on this note; Mat drives.

---

## Provenance

- Sketch + data analysis: `Earthian-BioSense/docs/two-axis-mode-space-SKETCH.md`
- Commits: `0e0ba12` (Python engine), `cae4d87` (web viz + WS), `71e7ee7` (Rust engine + desktop viz)
- Related: [[SPEC-013-accelerometer-motion-channel]] (the prior additive-channel pattern this followed)
