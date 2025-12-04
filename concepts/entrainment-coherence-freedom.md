# Entrainment, Coherence, Freedom

**Status:** Working inquiry — empirically validated, new distinctions emerging
**Date:** 2025-12-04
**Updated:** 2025-12-04 (empirical validation, constrained/permeable distinction)
**Context:** Human-human coupling sessions (pA, pT, pM), single ANS feed + phenomenological constraint

---

## The Key Insight (2025-12-04)

**What we were calling "coherence" in the codebase was actually entrainment.**

The `coh` metric computed autocorrelation of RR intervals at breath-period lags. This measures *breath-heart phase coupling* — how tightly the heart rhythm is locked to respiratory rhythm. This is **entrainment**: local, instantaneous synchrony.

HeartMath and similar systems use this same approach and call it "coherence." But coherence, properly understood, is something else entirely.

**Coherence is trajectory integrity over time** — how well the system's movement through phase space hangs together. Not the grip, but the journey. Not whether oscillators are locked, but whether the path has form.

This distinction matters:
- A system can be *entrained* but not *coherent* (locked in a pattern but the trajectory is fragmented)
- A system can be *coherent* but not *entrained* (moving through basins with integrity but not phase-locked)
- The sweet spot is both: synergy

**Implementation change:** Renamed `coh` → `entrainment` throughout codebase. Added `compute_trajectory_coherence()` in `phase.py` to measure actual coherence via trajectory autocorrelation.

---

## The Triad

Three concepts for sensing relational dynamics in coupled systems:

### Entrainment

**How tightly systems are held in pattern.**

- A *state* of stabilised synchrony within constraints
- Phase-locked relationship between oscillators
- Local stability — measurable in short windows
- The grip, the lock, the constraint strength
- Can be imposed (pacemaker) or mutual (reciprocal)

*Metric territory:* Phase-locking value (PLV), cross-correlation, frequency matching

### Coherence

**How well patterns hang together over time.**

- A *trajectory* quality — integrity of movement through phase space
- Not about matching rhythms but about the shape of the path
- Global integrity — requires duration to assess
- Autocorrelation relevant: does the pattern persist? does it have form?
- Can exist without entrainment (moving through different attractors with integrity)

*Metric territory:* Autocorrelation, trajectory smoothness, attractor basin stability, recurrence

### Freedom

**How easily and wisely we can repattern.**

- A *meta-property* — only visible across transitions
- Not just looseness (that's potential anergy)
- The capacity for transition *in service of coherence*
- Relational intelligence: knowing when to release, when to hold
- Requires longitudinal view — pattern of patterns across sessions/basins

*Metric territory:* Transition dynamics, basin crossing quality, return-to-coherence patterns (too early to formalize)

---

## Temporal Scales

| Concept | Window |
|---------|--------|
| Entrainment | Instantaneous / short (seconds to minutes) |
| Coherence | Medium duration / session-scale (minutes to session) |
| Freedom | Longitudinal / across sessions and transitions |

---

## Relational Dynamics Grid

|  | Low Coherence | High Coherence |
|---|---|---|
| **Low Entrainment** | Anergy | Chaordic |
| **High Entrainment** | Rigid lock | Synergy |

### Anergy
- Decoupled, dissipated
- Motion without coherence — random walk
- Phenomenology: flatness, disconnection, "nothing happening"

### Rigid Lock
- High grip, low trajectory integrity
- Stuck in pattern that may be decaying
- Phenomenology: forced, mechanical, "going through motions"

### Synergy
- High grip, high integrity
- Stable resonance — the pattern is alive
- Phenomenology: aliveness, "something moving through us"

### Chaordic
- Variable grip, high integrity
- Moving *through* patterns with coherence
- The jazz ensemble — not locked, but together
- Phenomenology: creative tension, "riding the edge," improvisational flow

### Pathological cell (unnamed)
- High freedom, low coherence
- Reactive repatterning without wisdom
- Chaos that feels like agency but has no trajectory integrity
- The nervous system that can't settle anywhere

---

## Freedom as Horizon

Freedom is named but not yet modeled. It shapes what we pay attention to:

- "Transition felt forced" vs "transition felt available" vs "couldn't find the exit"
- Quality of basin crossings
- Return-to-coherence after perturbation — how quickly? through what path?

As session data accumulates, patterns may emerge that make freedom tractable.

---

## Empirical Validation (2025-12-04)

Two sessions confirmed the entrainment/coherence inversion:

| Session | Activity | Coherence | Entrainment |
|---------|----------|-----------|-------------|
| pM_182343 | Self-talk (processing tension) | **0.47** (peak) | 0.0-0.5 (volatile) |
| pM_182343 | Rhythmic chanting | 0.21-0.33 | **0.42-0.55** (sustained) |
| pM_185104 | Meditation (7 min) | **0.55-0.56** (peak) | 0.0 |
| pM_185104 | Dancing/singing | 0.20-0.34 | **0.50-0.58** (sustained) |

**Pattern:** Cognitive processing / meditation → high coherence, low entrainment. Rhythmic activity → high entrainment, lower coherence.

The system appears to use different modes:
- **Coherence mode:** Trajectory integrity without breath-heart lock (meditation, internal processing)
- **Entrainment mode:** Active reorganization with strong local coupling (movement, rhythm, chanting)

---

## Constrained vs. Permeable Coherence

**Critical distinction the current metrics cannot capture.**

Trajectory autocorrelation measures *that* coherence exists, not *how* it's maintained. Two phenomenologically opposite states can produce similar coherence scores:

| | Constrained Coherence | Permeable Coherence |
|---|---|---|
| **Mechanism** | System *held* still | System *settled* still |
| **Stability source** | Vigilance doing work | Attractor basin depth |
| **Perturbation response** | Disrupted, snaps back | Absorbs, flows through |
| **Phenomenology** | Effortful, watchful | Effortless, present |
| **Autonomic signature** | Dorsal vagal (freeze) | Ventral vagal (social engagement) |

**Participant context (pM):** Nervous system shaped by early trauma. "Vigilant stillness" may be accurate — system holding pattern through effort, not resting in it. The 20-minute threshold for "sinking into presence" may mark the shift from constrained to permeable.

**Implication:** Coherence 0.55 in a 3-minute meditation represents *organizing toward* depth, not arrival. The body needs time to trust that stillness isn't a trap.

**Future direction:** HRV complexity metrics (sample entropy, DFA alpha) would distinguish constrained from permeable coherence. Constrained = lower entropy, more rigid correlations. Permeable = higher entropy within bounds, healthy 1/f scaling.

---

## Open Questions

- ~~Can we distinguish entrainment-without-coherence from coherence-without-entrainment in the session data?~~ **Yes — confirmed empirically.**
- What does the autocorrelation structure look like in high-coherence vs low-coherence sessions?
- How do perturbations (phase B3 in EECP) show up in the metrics? Is there a "perturbation signature"?
- Can phenomenological reports of "freedom" be correlated with transition dynamics in the ANS trace?
- **NEW:** Can HRV complexity distinguish constrained from permeable coherence?
- **NEW:** What does 20+ minutes of meditation show — does coherence plateau or deepen beyond "holding"?
- **NEW:** Does the entrainment/coherence inversion hold with instrument play (producing rhythm vs. receiving rhythm)?

---

## Relation to EECP

These concepts refine the coherence detection layer (Phase C) of the EECP protocol:

- **Entrainment** → short-window phase metrics (current implementation: `compute_entrainment()` in `hrv.py`)
- **Coherence** → trajectory-level analysis (new: `compute_trajectory_coherence()` in `phase.py`)
- **Freedom** → longitudinal/meta-analysis (future horizon)

The protocol streams entrainment, phase dynamics, and trajectory coherence. Coherence is now logged at 1Hz and validated against session data. The constrained/permeable distinction points toward HRV complexity as the next instrumentation layer.

---

## Implementation Notes

### Entrainment (`hrv.py:compute_entrainment()`)
- Autocorrelation of RR intervals at breath-period lags (4-8 beats)
- Detects respiratory sinus arrhythmia / breath-heart phase coupling
- Returns 0-1 score + label: [low], [emerging], [entrained], [high entrainment]

### Coherence (`phase.py:compute_trajectory_coherence()`)
- Autocorrelation of velocity magnitudes across trajectory
- Direction consistency via cosine similarity of velocity vectors at lag
- Combines magnitude autocorrelation (50%) + direction coherence (50%)
- Returns 0-1 score of trajectory integrity

### Key Differences
| | Entrainment | Coherence |
|---|---|---|
| **What it measures** | Breath-heart phase lock | Trajectory integrity |
| **Input** | RR intervals | Phase space positions |
| **Window** | ~10-20 beats | ~30 seconds of trajectory |
| **Can exist without the other** | Yes | Yes |
| **HeartMath calls this** | "Coherence" (misnomer) | (not measured) |

---

*This document is a working inquiry. It will evolve as session data accumulates and concepts are tested against empirical traces.*
