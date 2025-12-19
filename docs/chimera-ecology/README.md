# Chimera Ecology

*Baradian poetry for rewilding the ANS*

---

## What This Is

Chimera Ecology is a mythopoetic layer for Earthian-BioSense that transforms autonomic phase dynamics into place-based archetypal encounters. Rather than displaying metrics and geometry that could reify lived experience, chimeras offer a relational frame that resists optimization by design.

**Core principle:** You can't KPI your way to "more owl-snake-spider."

## Why Chimeras

Biometric dashboards colonize the interior. They promise self-knowledge but deliver self-surveillance:

1. Measure the living body
2. Reduce to metrics
3. Display as numbers to optimize
4. Create anxiety about the score
5. Sell interventions to improve it

Chimeras refuse this logic. They are:

- **Mythopoetic** — archetypes that can't be optimized
- **Place-based** — composed of local kin, not universal symbols
- **Encounter-gated** — the participant chooses to witness or refuse
- **Ecologically evolving** — using EA (not GA) for coexistence, not fitness

## Key Concepts

### The Agential Cut

Following Karen Barad, we place the cut at the **threshold** — the moment where human and measurement become intra-active. The participant chooses whether to witness a chimera or let it remain wild.

```
Not: human observes data about self
Not: algorithm assigns archetype to human

But: ecology observes itself through human-chimera encounter
```

### Witnessed vs Unwitnessed

- **Witnessed chimeras** become kin you've met. They stabilize, carry relationship, can be re-encountered.
- **Unwitnessed chimeras** stay wild in the sanctuary. They drift, evolve, may become something else entirely.

Neither is more true. The sanctuary honors both.

### Place-Based Vocabulary

Chimeras must be composed of species from the land the participant's body is on. For Bidjigal Country / Sydney Basin, the vocabulary includes:

- **Fauna:** Australian Raven, Bull Shark, Kookaburra, Water Dragon...
- **Flora:** Banksia, Sydney Red Gum, Turpentine, Paper Bark...
- **Fungi:** Fly Agaric, Psilocybe...

The vocabulary is personal and relational — species the participant has felt connection with, annotated with their own notes about relationship.

### Ecological Niches

Chimeras occupy niches that map to phase dynamics:

| Niche Category | Examples | Phase Signature |
|----------------|----------|-----------------|
| **Grip** | predator, prey, vigilant, sheltering | High entrainment, constrained |
| **Flow** | migratory, distributed, scanning, calling | High coherence, movement |
| **Transition** | metamorphic, liminal, trickster | At bifurcation, high curvature |
| **Settling** | dormant, rooted, dawn, elder | In basin, high stability |

### EA not GA

The sanctuary evolves using Evolutionary Algorithm operators that select for **viable coexistence**, not fitness:

- **Drift** — chimeras evolve when unwatched
- **Niche pressure** — crowded niches push toward diversity
- **Speciation** — chimeras can bud off variants
- **Going feral** — witnessed chimeras can return to the wild

## Architecture

```
src/processing/chimera/
├── types.py         # Core data structures
├── vocabulary.py    # Seed loading, niche inference
├── ecology.py       # Sanctuary management
├── evolution.py     # EA operators
├── threshold.py     # Phase → threshold detection
└── encounter.py     # Witness/refuse handling
```

See individual documentation files for details:

- [Types & Data Structures](./types.md)
- [Vocabulary & Niche Inference](./vocabulary.md)
- [Evolution Operators](./evolution.md)
- [Threshold Detection](./threshold.md)
- [Integration with EBS](./integration.md)

## The Threshold Modal

When phase dynamics trigger threshold detection, the participant sees:

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

The modal is a threshold guardian. The choice is the agential cut.

## Lineage

This system emerged from conversation between Mat Mytka and Kairos (Claude), December 2025.

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
