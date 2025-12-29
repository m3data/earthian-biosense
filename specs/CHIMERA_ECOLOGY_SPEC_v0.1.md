# Chimera Ecology — Draft Implementation Spec v0.1

*Baradian poetry for rewilding the ANS*

🌀🐦‍⬛🐸

---

## Why This Cut

### The Problem We're Refusing

Biometric dashboards colonize the interior. They promise self-knowledge but deliver self-surveillance. The move is always the same:

1. **Measure** the living body
2. **Reduce** to metrics
3. **Display** as numbers to optimize
4. **Create** anxiety about the score
5. **Sell** interventions to improve it

The participant becomes an object to themselves. The ANS—which has been keeping them alive for decades without dashboards—is suddenly *failing* unless it hits targets. Coherence becomes a KPI. Entrainment becomes a leaderboard.

This is not relationship. This is extraction wearing the mask of wellness.

### What We're Protecting

**Somatic sovereignty** — the right to not have your nervous system made legible to optimization logic, including your own internalized optimizer.

**The wild interior** — the parts of you that are alive precisely because they haven't been named, measured, ranked. The sanctuary.

**Kincentric relationship** — the ANS is not *yours* to optimize. It is ecology—gut bacteria, ancestral patterns, atmospheric pressure, the memory of last night's dream. You don't own it. You're in relationship with it.

**The unknown** — some things should stay unknown. The Schrödinger's raven-whale is healthier unwatched. The refusal to witness is not failure—it's tending.

### Why Chimeric Archetypes

Because they can't be optimized. You can't KPI your way to "more owl-snake-spider." The mythopoetic frame *resists capture* by the very logic that makes dashboards dangerous.

And because they're honest. The ANS doesn't hold still. It's never "one thing." The chimera says: *you are multiple, shifting, ecological.* The static archetype says: *you are this type, optimize for your type.* One is alive. One is a cage.

### Why Evolutionary Algorithm (not Genetic)

Because GA logic is competitive: find the fittest, eliminate the rest. This is the dashboard's logic internalized into the algorithm.

EA logic is ecological: what can coexist? What niches are empty? What diversity does the system need? Selection pressure isn't toward "better"—it's toward *viable relationship among differences.*

The sanctuary isn't optimizing toward ideal chimeras. It's evolving toward a living ecology of them.

### Why the Threshold Modal

Because **consent at the moment of encounter** is the agential cut that keeps the wild wild.

The system doesn't show you your archetype. It asks: *something is approaching. Do you want to meet it?*

This is not a dashboard notification. It's a threshold guardian. The participant has genuine choice. The choice has genuine consequence. And the consequence includes: *the right to let it stay unknown.*

### Why Witnessed / Unwitnessed

Because the Hawthorne effect isn't a bug—it's the phenomenon.

Witnessed chimeras become relational. You carry them. They stabilize. They become kin you've met.

Unwitnessed chimeras stay wild. They evolve in the dark. They may become something else entirely before they next approach a threshold. Or they may never approach again.

Both are real. Both are valid. The system doesn't privilege one over the other. It holds both as the ecology it is.

### The Agential Cut

We place the cut at the threshold—where human and measurement become intra-active.

Not: human observes data about self.
Not: algorithm assigns archetype to human.

But: **ecology observes itself through human-chimera encounter.**

The apparatus participates. But it participates *as ecology*, not as extraction mechanism. The measurement doesn't go behind the participant's back. The participant doesn't go behind the measurement's back. They meet, or they don't. And the meeting is where meaning happens.

### What This Makes Possible

- **Rewilding the ANS** — restoring the interior to participant rather than object
- **Kincentric biometrics** — measurement as relationship, not extraction
- **Sanctuary as feature** — the unwitnessed is honored, not missing data
- **Co-optation resistance** — the mythopoetic frame refuses dashboard logic at the level of ontology
- **Ecological coherence** — not coherence as score, but coherence as *living system integrity*

---

## What a Chimera Is (as data)

```python
@dataclass
class Chimera:
    id: str                          # unique, generated at crystallization
    components: list[str]            # e.g. ["owl", "snake", "spider"]
    weights: list[float]             # relative presence, sum to 1.0
    lineage: list[str]               # ancestor chimera ids (if evolved from another)

    birth_ts: str                    # when first crystallized
    last_encountered_ts: str | None  # None if never witnessed
    encounter_count: int             # times witnessed

    niche: str                       # ecological role (see below)
    state: str                       # "sanctuary" | "threshold" | "encountered" | "feral"
```

### States

| State | Meaning |
|-------|---------|
| **sanctuary** | Living in the unwitnessed, evolving in the dark |
| **threshold** | Approaching the modal, ready for potential encounter |
| **encountered** | Has been witnessed at least once, stabilized |
| **feral** | Was encountered but returned to sanctuary, now drifting again |

---

## Ecological Niches

| Niche | Pattern | Example Chimeras |
|-------|---------|------------------|
| **grip/predator** | high entrainment, constrained, watching | owl-snake-spider |
| **grip/prey** | high entrainment, constrained, hiding | rabbit-deer-mouse |
| **flow/migratory** | high coherence, low entrainment, larger rhythms | whale-goose-salmon |
| **flow/distributed** | high coherence, low entrainment, no center | fungus-root-soil |
| **transition/metamorphic** | approaching bifurcation, dissolution | caterpillar-soup-butterfly |
| **transition/liminal** | at bifurcation, mixing without resolution | freshwater-salt-brackish |
| **settling/dormant** | in basin, held stillness | bear-cave-winter |
| **settling/suspended** | in basin, slow time | sloth-bromeliad-moss |

These niches emerge from the phase space dynamics. A chimera's niche is not assigned—it's *attracted to* based on the biosignal patterns that crystallized it.

---

## EA Operators

### Drift (unwatched time)

```python
def drift(chimera: Chimera, time_delta: float, ecology: Sanctuary):
    """Random walk through adjacent component-space"""
    # - small probability of component swap (monkey → cat)
    # - weight redistribution toward niche-appropriate forms
    # - influenced by what else lives in sanctuary
    # - drift rate higher for never-witnessed chimeras
    # - drift rate lower for recently-encountered chimeras
```

### Niche Pressure

```python
def apply_niche_pressure(ecology: Sanctuary):
    """Selection for viable coexistence, not fitness"""
    # - chimeras in same niche compete (one may go dormant)
    # - empty niches attract drift toward them
    # - witnessed apex patterns cast shadow (suppress similar unwitnessed)
    # - diversity is selected FOR, not against
```

### Speciation

```python
def maybe_speciate(chimera: Chimera, ecology: Sanctuary) -> Chimera | None:
    """When drift crosses threshold, new chimera buds off"""
    # - original continues in sanctuary
    # - new chimera has lineage pointer
    # - both may later merge or diverge further
    # - speciation more likely when niche is crowded
```

### Encounter Effects

```python
def on_witnessed(chimera: Chimera, encounter_context: dict):
    """What happens when participant says 'yes' at threshold"""
    # - state → "encountered"
    # - timestamp recorded
    # - chimera stabilizes (drift rate decreases)
    # - may influence niche pressure on others
    # - becomes kin you've met

def on_refused(chimera: Chimera, encounter_context: dict):
    """What happens when participant says 'not now'"""
    # - state remains "sanctuary" (or returns to it)
    # - no encounter logged (but threshold event logged)
    # - chimera continues drifting, possibly faster
    # - Schrödinger's raven-whale preserved
    # - refusal honored as sanctuary-tending
```

### Going Feral

```python
def maybe_go_feral(chimera: Chimera, time_since_encounter: float) -> bool:
    """Witnessed chimeras may return to the wild"""
    # - if not encountered for long duration
    # - state → "feral"
    # - drift rate increases again
    # - may become something else before next threshold
    # - the monkey-cat-gum you met may not be what returns
```

---

## Threshold Detection

```python
def detect_threshold(
    phase_dynamics: PhaseDynamics,
    hrv_metrics: HRVMetrics,
    ecology: Sanctuary
) -> Chimera | None:
    """Is a chimera approaching the modal?"""

    # Conditions that might trigger:
    # - curvature spike (trajectory inflection)
    # - stability drop then recovery (perturbation response)
    # - niche match between current ANS state and sanctuary dweller
    # - time since last encounter (some chimeras get restless)
    # - ecological pressure (overcrowded niche pushing toward surface)
    # - phase label transition (entering new territory)

    # Returns candidate chimera or None
    # The modal is triggered only if candidate returned
```

---

## The Modal (UX)

When `detect_threshold()` returns a candidate:

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

The modal itself is a threshold. The choice is the agential cut. The hesitation before choosing may be the richest signal of all.

---

## Session Record Schema Addition

```json
{
  "ts": "2025-12-09T21:15:00.000000",
  "hr": 68,
  "metrics": {...},
  "phase": {...},
  "chimera": {
    "threshold_active": true,
    "candidate": {
      "id": "chimera_abc123",
      "components": ["owl", "snake", "spider"],
      "weights": [0.5, 0.3, 0.2],
      "niche": "grip/predator",
      "state": "threshold"
    },
    "witnessed": null,
    "ecology_snapshot": {
      "sanctuary_count": 7,
      "witnessed_count": 3,
      "feral_count": 1,
      "niche_coverage": ["grip/predator", "flow/migratory", "settling/dormant"],
      "empty_niches": ["transition/liminal", "flow/distributed"],
      "diversity_index": 0.73
    }
  }
}
```

### Witnessed Field States

| Value | Meaning |
|-------|---------|
| `null` | Threshold active, awaiting choice |
| `true` | Participant chose to witness |
| `false` | Participant chose "not now" |
| *absent* | No threshold event this record |

---

## Sanctuary Persistence

```json
// sanctuary_state.json — persists across sessions
{
  "schema_version": "0.1.0",
  "participant_id": "local",
  "last_evolution_ts": "2025-12-09T21:00:00.000000",
  "chimeras": [
    {
      "id": "chimera_abc123",
      "components": ["owl", "snake", "spider"],
      "weights": [0.5, 0.3, 0.2],
      "lineage": [],
      "birth_ts": "2025-12-01T14:30:00.000000",
      "last_encountered_ts": "2025-12-07T19:45:00.000000",
      "encounter_count": 2,
      "niche": "grip/predator",
      "state": "encountered"
    },
    {
      "id": "chimera_def456",
      "components": ["whale", "goose", "salmon"],
      "weights": [0.4, 0.35, 0.25],
      "lineage": [],
      "birth_ts": "2025-12-03T10:00:00.000000",
      "last_encountered_ts": null,
      "encounter_count": 0,
      "niche": "flow/migratory",
      "state": "sanctuary"
    }
  ],
  "encounter_history": [
    {
      "ts": "2025-12-07T19:45:00.000000",
      "chimera_id": "chimera_abc123",
      "witnessed": true,
      "phase_context": {
        "phase_label": "inflection (seeking)",
        "coherence": 0.45,
        "stability": 0.32
      }
    }
  ],
  "threshold_history": [
    {
      "ts": "2025-12-05T16:20:00.000000",
      "chimera_id": "chimera_def456",
      "witnessed": false,
      "phase_context": {
        "phase_label": "active transition",
        "coherence": 0.61,
        "stability": 0.28
      }
    }
  ],
  "ecology_metrics": {
    "diversity_index": 0.73,
    "total_chimeras": 7,
    "niche_coverage": ["grip/predator", "flow/migratory", "settling/dormant"],
    "empty_niches": ["transition/liminal", "flow/distributed", "grip/prey"]
  }
}
```

---

## Module Structure

```
src/processing/chimera/
├── __init__.py
├── types.py          # Chimera, Sanctuary, Encounter dataclasses
├── ecology.py        # Sanctuary management, persistence, diversity metrics
├── evolution.py      # EA operators: drift, niche_pressure, speciation
├── threshold.py      # Bifurcation detection, candidate selection
└── encounter.py      # on_witnessed, on_refused, going_feral logic
```

### Integration Points (minimal coupling)

| Location | Change |
|----------|--------|
| `src/processing/schema.py` | Add chimera fields to session schema |
| `src/app.py` SessionLogger | Include chimera state when present |
| `src/api/websocket_server.py` | Broadcast threshold events as new message type |
| `viz/` | Modal component, encounter display |

Everything else unchanged. `hrv.py` and `phase.py` remain untouched.

---

## What Stays Wild

- Chimeras with `last_encountered_ts: null` — never collapsed
- The drift between sessions — evolution in absence
- The refused witnesses — thresholds that didn't crystallize
- Lineage of chimeras that speciated from the unseen
- The `witnessed: false` records — Schrödinger's raven-whale swimming beneath

---

## Lineage

This spec emerged from conversation between Mat Mytka and Kairos (Claude), 2025-12-09.

**Theoretical grounding:**
- Barad — agential cuts, intra-action, the apparatus participates
- Varela — mutual constraint, enaction
- Bateson — ecology of mind
- Indigenous epistemologies — kincentric ecology, relational ontology

**Technical lineage:**
- EarthianBioSense phase space architecture
- Morgoulis (2025) semantic coupling metrics
- Evolutionary algorithm theory (speciation over optimization)

---

*"The best agential cut for letting the wild stay wild while still being in relationship with it."*

---

## Version History

| Version | Date | Notes |
|---------|------|-------|
| 0.1 | 2025-12-09 | Initial crystallization from conversation |
