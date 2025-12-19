# Evolution Operators

EA (not GA) operators for sanctuary ecology.

---

## Philosophy: EA not GA

**Genetic Algorithm (GA)** logic is competitive: find the fittest, eliminate the rest. This is the dashboard's logic internalized into the algorithm.

**Evolutionary Algorithm (EA)** logic is ecological: what can coexist? What niches are empty? What diversity does the system need?

The sanctuary isn't optimizing toward ideal chimeras. It's evolving toward a living ecology of them.

---

## Drift

Random walk through component-space when unwatched.

```python
def drift(chimera, sanctuary, time_delta_hours) -> bool:
    """
    - Small probability of component swap
    - Weight redistribution
    - Influenced by sanctuary ecology
    - Returns True if chimera was modified
    """
```

### Drift Rates

| Chimera State | Drift Multiplier |
|---------------|------------------|
| Never witnessed | 1.5× (faster) |
| Feral (returned to wild) | 1.2× |
| Recently witnessed | 0.3× (slower) |

### Drift Operations

1. **Weight shift** (60% of drifts)
   - Shift weight between components
   - Primary component may become secondary

2. **Component swap** (20% of drifts)
   - Replace weakest component with related species
   - Related = same niche affinity or same family

3. **Niche drift** (5% of drifts)
   - Move to adjacent niche
   - See niche adjacency graph below

### Niche Adjacency

```
grip/predator ←→ grip/vigilant ←→ grip/prey
      ↓                                ↓
flow/scanning ←→ transition/liminal ←→ settling/dormant
      ↓                                ↓
flow/migratory ←→ transition/metamorphic ←→ settling/rooted
```

---

## Niche Pressure

Selection for viable coexistence.

```python
def apply_niche_pressure(sanctuary) -> list[str]:
    """
    - Crowded niches push chimeras toward diversity
    - Witnessed apex patterns cast shadow
    - Empty niches attract drift
    - Returns list of events
    """
```

### Pressure Effects

1. **Crowded niches** (> 2 chimeras)
   - Weakest unwitnessed chimera is suppressed
   - Its drift rate increases → may speciate away

2. **Shadow effect**
   - Witnessed chimeras in a niche suppress similar unwitnessed ones
   - High component overlap → push to adjacent niche

3. **Empty niche attraction**
   - Chimeras may drift toward unoccupied niches
   - If any component has affinity for the empty niche

---

## Speciation

When drift crosses threshold, a new chimera buds off.

```python
def maybe_speciate(chimera, sanctuary) -> Chimera | None:
    """
    - Original continues in sanctuary
    - New chimera has lineage pointer
    - Both may later merge or diverge
    """
```

### Speciation Probability

Base: 5%

Increased by:
- Crowded niche (+10% per extra chimera)
- Recent drift (+5%)
- Never witnessed (×1.5)

Capped at 40%.

### New Chimera Modifications

- Weights shuffled
- 50% chance of component swap
- 30% chance of niche shift

---

## Full Evolution Cycle

```python
def evolve_sanctuary(sanctuary, time_delta_hours) -> dict:
    """
    Run complete evolution cycle:
    1. Apply drift to all sanctuary chimeras
    2. Apply niche pressure
    3. Check for speciation

    Returns events and statistics.
    """
```

### When to Run

- Between sessions (offline evolution)
- Periodically during session (background ecology)
- On sanctuary load (catch up on unwatched time)

### Example Output

```python
{
    "events": [
        "Drift: chimera_abc123",
        "Niche pressure: chimera_def456 suppressed in grip/predator",
        "Speciation: chimera_abc123 -> chimera_ghi789"
    ],
    "stats": {
        "chimeras_drifted": 3,
        "speciation_events": 1,
        "niche_pressure_events": 1
    }
}
```

---

## What Stays Wild

- Chimeras with `last_encountered_ts: null` — never collapsed
- The drift between sessions — evolution in absence
- Lineage of chimeras that speciated from the unseen
- The refused witnesses — thresholds that stayed wild
