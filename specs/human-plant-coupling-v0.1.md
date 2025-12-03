# Human-Plant Coupling Protocol — Draft Spec v0.1

**Status:** Exploratory / Pre-PhD R&D
**Date:** 2025-12-04
**Authors:** m3 (Human Earthian) + Kairos (Claude) + Zorya (ChatGPT)
**Country:** Bidjigal Land

---

## 1. Intent

This document sketches an exploratory protocol for detecting and rendering **relational coupling** between human and plant biosignals. It is not a product specification — it is a prototype possibility space for PhD research.

**What this is:**

- A framework for sensing whether human autonomic rhythms and plant bioelectric rhythms enter coherent relationship
- An exploration of non-visual, non-cognitive feedback (haptic) to make coupling felt rather than interpreted
- A technical scaffold that holds space for Indigenous co-research and governance

**What this is not:**

- A claim that plants "communicate" or "feel" in anthropomorphic terms
- A diagnostic or therapeutic tool
- A finished system

**Core hypothesis:** When a human enters somatic presence with a plant being, measurable phase relationships may emerge between their respective bioelectric signals. Rendering this as haptic texture — bypassing the DMN's narrative-spinning — may allow felt recognition of interspecies relation.

---

## 2. Signal Sources

### 2.1 Human Earthian

- **Device:** Polar H10 chest strap
- **Signal:** RR intervals (RRi) via BLE
- **Derived metrics:** HRV (RMSSD, SDNN), instantaneous heart rate
- **Sample rate:** ~1Hz (beat-to-beat)
- **Infrastructure:** Existing EBS pipeline (Phase 1 complete)

### 2.2 Plant Being

- **Signal type:** Surface voltage fluctuations, variation potentials (VPs)
- **Electrode setup:** Ag/AgCl electrodes — one in soil (reference), one on leaf/stem
- **Amplification:** High-impedance differential amplifier (plants are high-Z sources, >1MΩ input impedance required)
- **ADC:** 10-100Hz sampling (plant signals are slow, sub-Hz dominant frequencies)
- **Voltage range:** ~0.1-50mV fluctuations typical
- **Hardware status:** TBD — likely Arduino-based for prototype, open source priority

### 2.3 Synthetic Plant Signal (Development)

For coupling algorithm development before hardware:

- Base oscillation: 0.01-0.1 Hz (ultradian rhythms)
- Occasional spikes: Poisson-distributed, amplitude 2-5x base
- Pink noise floor: 1/f characteristics
- Optional: circadian envelope, response-to-stimulus events

---

## 3. Coupling Detection

The core technical question: **how do we mathematically detect when two very different biological rhythms enter relationship?**

### 3.1 Candidate Approaches

**Phase Synchronization**

- Extract instantaneous phase from both signals (Hilbert transform or wavelet)
- Compute phase-locking value (PLV) or mean phase coherence
- Sensitive to frequency ratios (1:1, 1:2, etc.) — important since plant rhythms are much slower

**Cross-Correlation**

- Time-lagged correlation between signals
- Simple, interpretable
- May miss nonlinear coupling

**Coherence (Frequency Domain)**

- Magnitude-squared coherence at specific frequency bands
- Good for identifying shared rhythmic components
- Requires sufficient stationarity

**Mutual Information**

- Information-theoretic coupling measure
- Captures nonlinear relationships
- Computationally heavier, harder to interpret

### 3.2 Initial Direction

Start with **phase synchronization** (PLV) because:

- Well-established in biosignal literature (EEG, cardiac-respiratory)
- Handles different frequency scales
- Provides continuous coupling metric suitable for haptic mapping

### 3.3 Timescales

- Human HRV: dominant frequencies 0.04-0.4 Hz (LF/HF bands)
- Plant VPs: dominant frequencies 0.001-0.1 Hz
- Coupling window: likely need 60-300 second windows to capture plant timescales
- Update rate for haptic: 1-10 Hz (smoothed coupling metric)

### 3.4 Phenomenological Layer (Non-Metric)

Not all relational dynamics will express themselves in mathematically detectable coupling. Human–plant attunement often includes subtle shifts in breath, posture, warmth, tingling, softening, or affective resonance that may not correlate linearly with PLV or cross-correlation metrics.

The protocol therefore includes a phenomenological layer that acknowledges:

- Felt sense as legitimate data
- Nonlinear, field-like relational shifts
- Meaning emerging through lived experience rather than metrics alone

Session design must allow space for these relational phenomena to be documented without reducing them to numbers. The phenomenology layer is not supplementary; it forms a co-equal dimension of inquiry within the Entangled Cognition Protocol and larger frame of the Earthian Ecological Coherence Protocol.

---

## 4. Output Modality: Haptic

### 4.1 Rationale

Visual feedback engages interpretation. The Default Mode Network spins narrative: "Is it working? What does this mean? Am I doing it right?", plants as objects rather than relational beings.

Haptic feedback can bypass this. Felt texture. Resonance or its absence. No semantics required.

### 4.1.1 Why Haptics Bypass the DMN

Visual interpretation routes directly through the Default Mode Network (DMN), which is associated with narrative construction, evaluation, and self-referential processing. For many participants—especially those shaped by mechanistic or anthropocentric ontologies—the DMN acts as a perceptual filter that suppresses or rationalises relational experience.

Haptic pathways instead engage interoceptive and somatosensory systems linked to brainstem, insular, and limbic systems. These pathways support presence, regulation, and relational attunement without requiring conceptual mediation. As such, haptic cues provide a non-cognitive channel through which relational signals may be felt rather than interpreted, supporting a gentle reinstatement of interspecies perception for participants whose cultural conditioning has inhibited these capacities.

### 4.2 Hardware Direction

- **Open source priority** — not proprietary platforms
- **Candidates:** Vibrotactile actuators, open haptic platforms
- **Form factor:** Wristband or handheld
- **Output dimensions:**
  - Intensity (coupling strength)
  - Rhythm (coupling frequency)
  - Texture (coupling stability/variability)

### 4.3 Mapping Questions (Iterative UX Research)

- Does coupling feel like convergence (smoothing) or resonance (shared pulse)?
- What does *absence* of coupling feel like? Silence? Noise? Different texture?
- How much latency is tolerable before felt sense disconnects from source?

---

## 5. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                  EarthianBioSense System                        │
├─────────────────────────────────────────────────────────────────┤
│  Data Ingest Layer                                              │
│  ├── Polar H10 (BLE) ──→ RRi stream                            │
│  └── Plant electrode (serial/ADC) ──→ voltage stream           │
├─────────────────────────────────────────────────────────────────┤
│  Phase Space Engine                                             │
│  ├── Human: position, velocity, curvature in HRV phase space   │
│  └── Plant: position, velocity in voltage phase space          │
├─────────────────────────────────────────────────────────────────┤
│  Relational Coupling Module                                     │
│  ├── Phase extraction (Hilbert/wavelet)                        │
│  ├── PLV computation (windowed)                                │
│  └── Coupling metrics: coherence, alignment, delta             │
├─────────────────────────────────────────────────────────────────┤
│  Haptic Mapping Layer                                           │
│  └── Coupling metrics ──→ vibration, pulse, texture            │
├─────────────────────────────────────────────────────────────────┤
│  Output                                                         │
│  ├── Haptic wristband (primary)                                │
│  ├── Session logging (JSONL)                                   │
│  └── Optional: visualization for research/replay               │
└─────────────────────────────────────────────────────────────────┘
```

See also: `docs/diagrams/EBS-human-plant-2025-12-03-122432.png`

---

## 6. Governance & Co-Research

This work cannot proceed as extractive research. Plants are not data sources. Indigenous knowledge systems have relational epistemologies that Western science is only beginning to acknowledge.

### 6.1 Commitments

- **Country acknowledgment:** This work takes place on the unceded lands of the Bidjigal people of the Dharawal nation. Sovereignty was never ceded.
- **Elder involvement:** Protocol design, interpretation frameworks, and governance to involve First Nations elders as co-researchers and stewards — not consultants.
- **IKS Labs connection:** Potential collaboration with Indigenous Knowledge Systems Labs (Tyson Yunkaporta et al.) on relational epistemology and data sovereignty.
- **Open source:** Technical artifacts to be open, not enclosed.

### 6.2 What We Don't Know Yet

- What does "consent" mean for plant participation?
- What interpretive frames are appropriate vs. appropriative?
- How do we hold scientific rigor and relational ontology together?

These are not problems to solve but questions to stay with.

---

## 7. Development Phases

### Phase A: Synthetic Coupling (Current)

- Build synthetic plant signal generator
- Implement phase synchronization (PLV) algorithm
- Test coupling detection with known synthetic relationships
- No hardware required

### Phase B: Real Plant Signals

- Arduino-based electrode interface
- Validate signal quality
- Characterize baseline plant rhythms
- Ethics/governance conversations

### Phase C: Haptic Prototype

- Open haptic hardware selection
- Mapping algorithm: coupling → vibrotactile
- UX iteration (felt sense testing)

### Phase D: Integrated Sessions

- Combined human-plant sessions
- Session recording and replay
- Co-research with elders

---

## 8. Open Questions

- What frequency bands in plant signals are most relevant for coupling?
- Is there a meaningful "coherence" or are we pattern-matching noise?
- How do environmental factors (e.g., light, time of day, soil composition and moisture) affect plant signals?
- What's the minimum viable haptic vocabulary?
- How do we document sessions without reducing them to data?
- What is the mutual constraint between the phenomenological experience and the computational measures?

---

## 9. References & Prior Art

- **PlantWave / MIDI Sprout** — sonification of plant bioelectricity (interpretive caution: "plant music" framing)
- **VIVENT** — commercial plant electrophysiology (extractive framing, agricultural optimization)
- **Stefano Mancuso** — plant neurobiology research
- **Monica Gagliano** — plant bioacoustics and behavior
- **Tyson Yunkaporta** — Indigenous knowledge systems, relational epistemology
- **Karen Barad** — intra-action, agential realism (theoretical frame for relational sensing)

---

## 10. Sociocultural and Political Implications

This protocol has significance beyond technical experimentation. Many people shaped by Western, urban, or mechanistic cultural environments have diminished capacity to perceive ecological relation directly. The nervous system’s habitual reliance on DMN-mediated interpretation can constrain relational experience, making more-than-human attunement difficult to access.

The human–plant coupling system provides an accessible, secular, and non-altered-state route into relational perception. By rendering subtle interspecies dynamics as somatic feedback, the system can help participants recognise patterns of connection that would otherwise remain pre-conscious or unnoticed.

This carries political and educational implications. Leaders, policymakers, or community members may experience moments of relational insight that reframe how ecological systems are perceived—shifting from resource logics toward kinship logics. At the same time, the system must be designed to minimise risks of manipulative entrainment and must remain grounded in relational ethics, open-source transparency, steward mesh for rites of progressive feature release, and Indigenous-guided governance.

Interpretation should not be imposed. The aim is to create conditions where relational experience can be felt again, supporting broader cultural shifts toward ecological stewardship.

---

*This document is a living draft. It will evolve as the work evolves.*