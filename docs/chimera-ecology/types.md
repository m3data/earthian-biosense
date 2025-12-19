# Types & Data Structures

Core data structures for Chimera Ecology.

---

## Species

A species from the local ecology — kin, not symbol.

```python
@dataclass
class Species:
    scientific_name: str      # "Corvus coronoides"
    common_name: str          # "Australian Raven"
    taxon_group: str          # "fauna" | "flora" | "fungi"
    family: str               # "Corvidae"

    # Relational (from participant's notes)
    notes: str                # "Threshold guardians"
    qualities: list[str]      # ["watching", "calling"]

    # Niche affinities (inferred from notes)
    niche_affinities: list[Niche]

    # Accumulated through encounter
    encounter_count: int
    witnessed_in_chimeras: list[str]
```

Species come from the land, not from universal archetypes. The `notes` field carries the participant's felt relationship.

---

## Chimera

A chimeric archetype composed of local species.

```python
@dataclass
class Chimera:
    id: str                   # "chimera_abc123"

    # Composition
    components: list[str]     # Species scientific names
    weights: list[float]      # Relative presence, sum to 1.0

    # Lineage
    lineage: list[str]        # Ancestor chimera IDs

    # Temporal
    birth_ts: str
    last_encountered_ts: str | None
    encounter_count: int

    # Ecology
    niche: Niche | None
    state: ChimeraState

    # Evolution
    drift_rate: float         # Higher = faster drift
    last_drift_ts: str | None
```

### Chimera States

| State | Meaning |
|-------|---------|
| `sanctuary` | Living in the unwitnessed, evolving in the dark |
| `threshold` | Approaching the modal, ready for encounter |
| `encountered` | Has been witnessed, stabilized |
| `feral` | Was witnessed but returned to wild |

---

## Niche

Ecological niches that chimeras occupy. These emerge from phase dynamics.

```python
class Niche(Enum):
    # Grip — high entrainment, constrained
    GRIP_PREDATOR = "grip/predator"
    GRIP_PREY = "grip/prey"
    GRIP_VIGILANT = "grip/vigilant"
    GRIP_SHELTERING = "grip/sheltering"

    # Flow — high coherence, movement
    FLOW_MIGRATORY = "flow/migratory"
    FLOW_DISTRIBUTED = "flow/distributed"
    FLOW_SCANNING = "flow/scanning"
    FLOW_CALLING = "flow/calling"

    # Transition — at bifurcation
    TRANSITION_METAMORPHIC = "transition/metamorphic"
    TRANSITION_LIMINAL = "transition/liminal"
    TRANSITION_TRICKSTER = "transition/trickster"

    # Settling — in basin, stability
    SETTLING_DORMANT = "settling/dormant"
    SETTLING_ROOTED = "settling/rooted"
    SETTLING_DAWN = "settling/dawn"
    SETTLING_ELDER = "settling/elder"
```

### Niche ↔ Phase Mapping

| Niche | Phase Signature |
|-------|-----------------|
| grip/predator | High entrainment, low velocity, stability > 0.6 |
| grip/vigilant | Entrainment > 0.3, "vigilant stillness" label |
| flow/migratory | High coherence, velocity > 0.05, movement |
| transition/liminal | Curvature > 0.2, at inflection point |
| settling/dormant | Very low velocity, high stability |
| settling/elder | High coherence, high stability |

---

## Sanctuary

The living ecology of chimeras for a participant.

```python
@dataclass
class Sanctuary:
    schema_version: str       # "0.1.0"
    participant_id: str       # "local"

    country: Country | None
    species_vocabulary: list[Species]

    chimeras: list[Chimera]
    encounter_history: list[Encounter]
    threshold_history: list[Encounter]

    last_evolution_ts: str | None
```

### Properties

- `sanctuary_chimeras` — unwitnessed or feral
- `witnessed_chimeras` — have been encountered
- `niche_coverage` — which niches are occupied
- `empty_niches` — available for drift attraction

---

## Country

The land context for a vocabulary.

```python
@dataclass
class Country:
    name: str              # "Bidjigal Country"
    bioregion: str         # "Sydney Basin"
    acknowledgment: str    # Custodian acknowledgment
    bounds: dict | None    # Geographic bounds
```

---

## Encounter

Record of a threshold encounter.

```python
@dataclass
class Encounter:
    ts: str
    chimera_id: str
    witnessed: bool        # True if witnessed, False if refused
    phase_context: dict    # Phase dynamics at encounter
```

Both witnessed and refused encounters are recorded. The `witnessed=False` records are the Schrödinger's raven-whales — patterns that approached but were allowed to stay wild.
