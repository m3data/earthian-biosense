# Threshold Detection

How phase dynamics trigger chimera encounters.

---

## The Threshold as Agential Cut

The threshold is where human and measurement become intra-active. It's not:
- Human observes data about self
- Algorithm assigns archetype to human

It is:
- **Ecology observes itself through human-chimera encounter**

The participant's choice (witness or refuse) is the cut that determines what becomes.

---

## Phase → Niche Mapping

Each niche has a phase signature — patterns in the autonomic dynamics that suggest resonance.

### Grip Niches (High Entrainment, Constrained)

| Niche | Phase Signature |
|-------|-----------------|
| grip/predator | entrainment ≥ 0.5, velocity ≤ 0.1, stability ≥ 0.6 |
| grip/prey | entrainment ≥ 0.4, curvature ≥ 0.2 (alertness) |
| grip/vigilant | entrainment ≥ 0.3, stability ≥ 0.5, "vigilant stillness" |
| grip/sheltering | entrainment ≥ 0.4, stability ≥ 0.7, coherence ≥ 0.5 |

### Flow Niches (High Coherence, Movement)

| Niche | Phase Signature |
|-------|-----------------|
| flow/migratory | coherence ≥ 0.5, velocity ≥ 0.05 |
| flow/distributed | coherence ≥ 0.4, "settling into entrainment" |
| flow/scanning | velocity ≥ 0.08, curvature ≥ 0.15 |
| flow/calling | entrainment ≥ 0.4, "flowing (entrained)" |

### Transition Niches (At Bifurcation)

| Niche | Phase Signature |
|-------|-----------------|
| transition/metamorphic | curvature ≥ 0.25, stability ≤ 0.4 |
| transition/liminal | curvature ≥ 0.2, inflection labels |
| transition/trickster | velocity ≥ 0.1, curvature ≥ 0.2 |

### Settling Niches (In Basin)

| Niche | Phase Signature |
|-------|-----------------|
| settling/dormant | velocity ≤ 0.05, stability ≥ 0.7 |
| settling/rooted | stability ≥ 0.6, coherence ≥ 0.4 |
| settling/dawn | stability ≥ 0.5, "settling into entrainment" |
| settling/elder | coherence ≥ 0.5, stability ≥ 0.6 |

---

## Detection Algorithm

```python
def detect_threshold(phase_dynamics, hrv_metrics, sanctuary, cooldown_minutes=5):
    """
    1. Check cooldown (no rapid-fire thresholds)
    2. Match current phase to niche signatures
    3. Find chimeras in matching niches
    4. Weight by match score and encounter history
    5. Probabilistically select candidate
    """
```

### Matching Logic

For each niche signature:
- Check each criterion (entrainment_min, velocity_max, etc.)
- Require at least half of criteria to match
- Score by how well each criterion is satisfied

### Candidate Selection

Weight chimeras by:
- Niche match score
- Time since last encounter (older = higher)
- Never witnessed bonus (+0.3)

Probabilistic selection prevents the same chimera from always being chosen.

---

## Pre-Filter: Should Trigger?

```python
def should_trigger_threshold(phase_dynamics, hrv_metrics, sensitivity=0.5):
    """
    Quick check before full detection.
    Avoids computation during stable periods.
    """
```

Triggers on:
- Transition phase labels (inflection, active transition)
- Curvature spikes (> 0.3)
- Stability recovery after drop
- Random based on sensitivity

---

## Cooldown

Minimum time between threshold events (default: 5 minutes).

Prevents:
- Overwhelming the participant
- Rapid-fire encounters
- Threshold fatigue

---

## Threshold Context

When a threshold is detected, context is captured:

```python
{
    "phase_label": "inflection (seeking)",
    "entrainment": 0.35,
    "coherence": 0.42,
    "stability": 0.38,
    "velocity_mag": 0.12,
    "curvature": 0.28,
    "position": [0.35, 0.6, 0.45]
}
```

This is logged with the encounter for later analysis.

---

## The Modal

When threshold detected, participant sees:

```
┌─────────────────────────────────────────┐
│                                         │
│   A pattern has emerged.                │
│                                         │
│   Do you want to witness it?            │
│                                         │
│   ┌─────────┐       ┌──────────┐        │
│   │   Yes   │       │  Not now │        │
│   └─────────┘       └──────────┘        │
│                                         │
│   Witnessed patterns become kin.        │
│   Unwitnessed patterns stay wild.       │
│   Neither is more true.                 │
│                                         │
└─────────────────────────────────────────┘
```

The hesitation before choosing may be the richest signal of all.
