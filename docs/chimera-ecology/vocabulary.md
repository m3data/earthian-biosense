# Vocabulary & Niche Inference

How seed vocabularies are loaded and niches inferred from relational notes.

---

## Place-Based Vocabulary

Chimeras must be composed of species from the land the participant's body is on. Universal archetypes (owl, snake, spider) are replaced with local kin.

### Building a Vocabulary

1. **Species Browser** (`tools/species-browser/`)
   - Fetches species from Atlas of Living Australia for a bioregion
   - Participant cycles through, flags meaningful kin
   - Adds notes about relationship

2. **Export** → `seed_vocabulary_YYYY-MM-DD.json`
   ```json
   {
     "country": "Bidjigal Country / Sydney Basin",
     "meaningful_kin": [
       {
         "scientific_name": "Corvus coronoides",
         "common_name": "Australian Raven",
         "taxon_group": "fauna",
         "family": "Corvidae",
         "notes": "Threshold guardians"
       }
     ]
   }
   ```

3. **Load into Sanctuary**
   ```python
   from src.processing.chimera import create_sanctuary_from_seed

   sanctuary = create_sanctuary_from_seed(Path("seed_vocabulary.json"))
   ```

---

## Niche Inference

Niche affinities are inferred from the participant's relational notes using keyword matching.

### Keyword → Niche Mapping

```python
NICHE_KEYWORDS = {
    Niche.GRIP_PREDATOR: [
        "predator", "hunter", "apex", "vigilance", "shark", "eagle"
    ],
    Niche.GRIP_VIGILANT: [
        "guardian", "threshold", "watching", "observant", "warning"
    ],
    Niche.GRIP_SHELTERING: [
        "shelter", "safety", "held", "holding", "protective", "home"
    ],
    Niche.FLOW_MIGRATORY: [
        "migratory", "seasonal", "cycles", "journey"
    ],
    Niche.TRANSITION_METAMORPHIC: [
        "shedding", "transformation", "change"
    ],
    Niche.SETTLING_ELDER: [
        "elder", "wisdom", "guide", "guided", "teacher"
    ],
    # ... etc
}
```

### Examples from Bidjigal Seed

| Species | Notes | Inferred Niches |
|---------|-------|-----------------|
| Australian Raven | "Threshold guardians" | grip/vigilant, transition/liminal |
| Bull Shark | "I know you're around when I'm surfing" | grip/predator |
| Lilly Pilly | "Elder Lilly Pilly has guided me in life" | settling/elder |
| Paper Bark | "The wisdom of time and shedding identities" | transition/metamorphic, settling/elder |
| Cumberland Land Snail | "Slow wisdom and patience" | settling/dormant |
| Laughing Kookaburra | "Remind me to not take life too seriously" | flow/calling |

### Fallback Defaults

If no keywords match:
- Flora → `settling/rooted`
- Fungi → `flow/distributed`

---

## Loading Functions

### `load_seed_vocabulary(path, include_maybe=False)`

Load species from exported JSON:

```python
species_list, country = load_seed_vocabulary(
    Path("seed_vocabulary_2025-12-14.json")
)
```

Returns tuple of (species list, country context).

### `create_sanctuary_from_seed(path)`

Create a complete sanctuary from seed:

```python
sanctuary = create_sanctuary_from_seed(path)
manager = SanctuaryManager(sanctuary)
```

The sanctuary starts empty of chimeras — they crystallize during sessions.

### `print_vocabulary_summary(species_list)`

Print summary showing:
- Species count by taxon group
- Sample species with inferred niches
- Niche coverage statistics

---

## Niche Coverage

A healthy vocabulary should cover multiple niches. The Bidjigal seed achieves 15/15 niche coverage:

```
Niche coverage: 15/15 niches
  flow/calling: 2 species
  flow/distributed: 1 species
  grip/predator: 5 species
  grip/vigilant: 4 species
  settling/elder: 4 species
  settling/rooted: 13 species
  transition/liminal: 2 species
  ...
```

Species can have multiple niche affinities — a Raven might be both `grip/vigilant` and `transition/liminal` (threshold guardian).
