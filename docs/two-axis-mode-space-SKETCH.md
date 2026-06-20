# Two-Axis Mode Space — Sketch → Built

**Status:** BUILT (2026-06-20, fork 1). Sketch grounded in 36 sessions / 15,909 records;
now wired into the pipeline as an additive `soft_mode_2d` field (schema 1.4.0).

**Implementation:**
- `movement.py` — `MODE_CENTROIDS_2D` + `compute_2d_mode_membership(calm, coherence)`
- `phase.py` — additive `PhaseDynamics.soft_mode_2d`; `PhaseTrajectory.compute_2d_mode()`
- `app.py` — computes it right after `latest_coherence`, consuming the canonical value
- `session_logger.py` — serialises `phase.soft_mode_2d` (additive)
- `schema.py` — 1.2.0 → 1.4.0 (1.3.0 reserved for Rust motion channel)
- 13 new tests in `tests/test_movement.py::TestTwoDimensionalModeMembership`
- 1-D path untouched; old sessions parse unchanged

**Validation (replay over 15,909 real records):**
- Ambiguity de-saturated: 1-D 0.996 (min 0.941) → 2-D 0.336–1.000, sd 0.060 (it moves).
- Old "subtle alertness" splits 50% reactive / 45% transitional / 5% engaged.
- 21% of old "settling" is actually `constrained stillness` (brittle) — a cut the
  1-D ladder could not make.

**Open follow-ups (tuning, not correctness):**
- 2-D ambiguity mean is still ~0.92 — the corpus clusters in the low-calm/low-mid-
  coherence border zone, so most points genuinely sit between `reactive` and
  `transitional`. Temperature (0.15) and centroid placement are tunable to use more
  of the ambiguity range in the populated region.
- `coherence` itself is skewed low (mean 0.28); `settled presence` is near-unreached
  (2/15,909) because these sessions rarely pair high calm with high coherence. That's
  a property of the corpus, not the scheme — but the coherence axis may want its own
  calibration pass.
- Not yet surfaced on the WebSocket broadcast / replay viz — logged only. Next step.
- Label set is PROVISIONAL (see `movement.py`) — research-vocabulary call for Mat.

---

## (original sketch follows)

## The finding

The six modes are bins along a **single scalar**, `calm_score`
(`hrv.py:271` = `entrainment·0.4 + breath_steady·0.3 + amp·0.2 + inv_volatility·0.1`).
The "soft membership in 4-D centroid space" (`movement.py`) is reverse-engineered
*from that same scalar at the bin midpoints*, using the same weights — so the four
centroid dimensions are collinear by construction. It is softmax over distance **along a line**.

`trajectory_coherence` (`phase.py:416`) is computed every tick, logged, displayed
(the `COH` bar), and broadcast — but **never reaches the classifier**. The mode is
finalised inside `latest_metrics` *before* coherence is even computed (`app.py:179`).
They ride the same packet and never touch.

## Why this is structural, not a wiring bug

- `calm_score` is **instantaneous** stillness (this tick).
- `coherence` is **longitudinal** trajectory integrity (lag-5 autocorrelation of
  velocity + directional persistence). Shares *no terms* with calm_score.
- Empirically orthogonal: **corr(calm, coherence) = +0.001** across 15,909 records.

You cannot fix this by appending coherence as a 5th weight in `calm_score` — that
re-collapses the entrainment/coherence distinction the project calls its key insight.
The fix is a **plane**, not a longer line.

## The plane

```
          COHERENCE (trajectory integrity) ^
   high   |   STILL + FRAGMENTED         SETTLED PRESENCE          |
          |   (brittle stillness,        (resting in attractor,    |
          |    freeze/hold)               permeable coherence)     |
          |                                                         |
          |   ACTIVATED + FRAGMENTED     ACTIVATED + COHERENT       |
   low    |   (reactive, scattered,      (flow, rhythmic activity,  |
          |    true dysregulation)        "holding doing work")     |
          +---------------------------------------------------------+
              low  CALM / stillness (instantaneous)            high
```

The four quadrants already have names in this repo's vocabulary:

- **CLAUDE.md** already distinguishes *constrained vs permeable coherence* and
  *holding (alertness doing work) vs settling (resting in attractor)*. That **is** the
  coherence axis — the team already felt the 1-D ladder was insufficient.
- The existing `movement_annotation` (still/moving) + `movement_aware_label`
  (e.g. `"subtle alertness (still)"`) is a **hand-built proxy** for this second axis.
  Coherence is the principled quantity it was approximating.

## What the data says changes

Real sessions, current 1-D labels vs the coherence they hide:

| current calm-label | n | coherence mean | coherence range |
|---|---|---|---|
| subtle alertness | 2294 | 0.28 | 0.00 – 0.79 |
| transitional | 3710 | 0.28 | 0.00 – 0.88 |
| settling | 800 | 0.28 | 0.00 – 0.64 |

A single stillness-rung spans nearly the entire coherence axis. Concretely, of the
records labelled alert-family (calm < 0.35):

- **4.5%** are genuinely **fragmented** (coherence < 0.2) — reactive/scattered.
- **0.9%** are actually **high-coherence** (≥ 0.5) — moving with integrity.

Same label. Opposite journeys. The ladder calls them the same thing.

## The ambiguity field is degenerate as built

`ambiguity = 1 − (top₁ − top₂)` (`movement.py:411`). Because six centroids strung
along one line sit nearly equidistant, softmax memberships go near-uniform, so:

- **ambiguity mean = 0.996, min = 0.941** across all sessions. It is pinned at ceiling.

The field meant to carry "honesty about the classifier's grip on a continuous thing"
is stuck at maximally-uncertain and barely moves. A genuine second axis would give it
something real to be ambiguous *between* — de-saturating it. That is the cheapest test
of whether soft-membership earns its keep at all.

## The fork

1. **Promote the axis you already have** — feed `coherence` into a 2-D mode scheme
   today. Small, reveals whether the soft-membership machinery buys anything once there
   are two real dimensions. Risk: low.
2. **Hold placeholders, design for Muse** — let EEG be the axis-breaker and design the
   joint manifold from scratch. Coherence (the cheap second axis) is still available as
   a third dimension; the Muse is genuinely orthogonal substrate, not reverse-engineered.

Recommendation: do (1) first — it's the controlled experiment that tells you whether the
2-D structure is real *before* adding a third substrate whose value depends on the same
machinery working.
