# Proto-Labels

This document describes the current state of autonomic labels in EarthianBioSense - how they emerged, their empirical grounding, and the validation process underway.

## Status: Proto

The labels used in EBS are **proto-labels** - working hypotheses, not validated classifications.

They emerged from:

- Early observations of trajectory patterns
- Correlation with first-person phenomenological reports
- Iterative refinement through the mutual constraint process

They remain provisional until:

- Systematic validation studies are completed
- Cross-participant patterns are established
- First-person/third-person correlations are rigorously documented

This document describes the emergence process and current grounding, not final validated categories.

## The Mutual Constraint Process

Following Varela's neurophenomenological methodology, EBS labels emerged through **mutual constraint** between:

1. **Third-person data**: Trajectory patterns in phase space (velocity, curvature, stability, position)
2. **First-person reports**: What was actually happening experientially during those patterns

Neither source is privileged. Both constrain the other:

- Strange trajectory patterns prompt phenomenological inquiry ("What was happening here?")
- Phenomenological observations prompt pattern search ("What does that look like in the data?")

### Example: Discovering "Vigilant Stillness"

**Observation (third-person)**: Sessions showed extended periods of high stability (~1.0), low-moderate coherence, contracted amplitude. The trajectory was essentially frozen - not moving through phase space.

**Question**: What does it feel like when this pattern appears?

**First-person report**: "I was paying close attention but not relaxed. Alert. Watching. Processing something. Not stressed exactly, but not at ease either."

**Refinement**: This isn't "calm" (which might show higher coherence) or "stressed" (which might show higher volatility). It's a third thing - stable vigilance. The body holding still while attention is engaged.

**Label**: "vigilant stillness"

### Example: Discovering "Inflection (Seeking)"

**Observation (third-person)**: High curvature moments - the trajectory sharply turning in phase space. Not at a particular position, but a particular *movement pattern*.

**Question**: What precedes or accompanies these turns?

**First-person report**: "Something was shifting. I was looking for... something. Not sure what. A turning point. Like the system was trying different configurations."

**Refinement**: High curvature without being in the coherent region suggests searching - the system exploring phase space for a new attractor.

**Label**: "inflection (seeking)"

## Current Labels and Their Grounding

### Warming Up

**Pattern**: Insufficient data points for reliable dynamics computation.

**Grounding**: Technical necessity - needs enough trajectory history to compute velocity/curvature.

**First-person correlation**: Session beginning, body hasn't settled, signal quality establishing.

### Vigilant Stillness

**Pattern**:

- Stability > 0.8
- Velocity magnitude < 0.05
- Coherence < 0.4
- Extended duration (not transient)

**Grounding**: Multiple sessions showed this pattern during:

- Reading or intellectual work
- Processing difficult content
- Sustained attention tasks
- Emotional processing without activation

**First-person correlation**: "Watchful," "attentive but not relaxed," "holding," "processing"

**Key insight**: This is not the absence of something - it's a distinct state. The body actively holding still.

### Active Transition

**Pattern**:

- Velocity magnitude > 0.15
- Any coherence level
- Any curvature

**Grounding**: Simply moving through phase space rapidly. State is changing.

**First-person correlation**: "Something shifting," "unsettled," "in motion"

**Key insight**: Transition is neutral - could be moving toward or away from coherence.

### Inflection (Seeking)

**Pattern**:

- Curvature > 0.25
- Not currently in coherent region (coherence < 0.5)
- Recent trajectory not from coherent region

**Grounding**: Sharp turns in phase space when not coherent suggest the system is searching for a new configuration.

**First-person correlation**: "Looking for something," "turning point," "trying to settle but not finding it"

**Key insight**: Seeking is a specific dynamic - not just "low coherence" but actively searching.

### Inflection (From Coherence)

**Pattern**:

- Curvature > 0.25
- Recently was in coherent region (coherence was > 0.5)
- Coherence dropping

**Grounding**: Sharp turn while leaving coherent state - something disrupted the coherence.

**First-person correlation**: "Lost it," "got distracted," "pulled out of flow"

**Key insight**: Leaving coherence has a different quality than never being there.

### Settling Into Coherence

**Pattern**:

- Velocity decreasing
- Coherence increasing or stable-high
- Curvature low
- Position approaching coherent region

**Grounding**: The characteristic approach pattern - decelerating as you land.

**First-person correlation**: "Landing," "finding the groove," "dropping in"

**Key insight**: Settling has a trajectory shape - not sudden, but gradual approach with decreasing speed.

### Flowing Coherence

**Pattern**:

- Coherence > 0.5
- Moderate velocity (0.05-0.15)
- Low curvature
- Moving within coherent region

**Grounding**: Coherent but not frozen - there's still movement, but it's within the coherent zone.

**First-person correlation**: "Flow," "in rhythm," "surfing"

**Key insight**: Coherence isn't static - you can move while staying coherent.

### Coherent Dwelling

**Pattern**:

- Coherence > 0.5
- Velocity magnitude < 0.05
- Curvature < 0.1
- Stability > 0.8

**Grounding**: Stable in the coherent region - not moving, not turning, dwelling.

**First-person correlation**: "Deep coherence," "settled," "home"

**Key insight**: The "goal state" for many practices - stable, sustained coherence.

### Neutral Dwelling

**Pattern**:

- Stability > 0.8
- Coherence 0.2-0.5
- Low velocity, low curvature

**Grounding**: Stable but not particularly coherent or vigilant - just settled in a neutral zone.

**First-person correlation**: "Baseline," "nothing particular," "just being"

**Key insight**: Not all dwelling is coherent or vigilant - there's a middle ground.

## What's Not Yet Labeled

The current label set is incomplete. Patterns observed but not yet formalized:

- **Agitated transition**: High velocity + high volatility + not settling
- **Coherence collapse**: Rapid exit from coherent state (faster than normal inflection)
- **Oscillating search**: Repeated inflection-seeking without finding attractor
- **Deep rest**: Very low HR, expanded amplitude, slow breath, not quite "coherent" in the rhythmic sense

These await further observation and first-person correlation before becoming labels.

## Validation Approach

### Current Status

Labels are grounded in:

- ~10 sessions with first-person correlation and LLM-assisted somatic cueing
- Multiple participants (developer/researcher + family members of different and ages) with varying somatic literacy
- Iterative refinement over several sessions
- Sense-checking against phenomenological reports

### What's Needed

1. **Multi-participant validation**: Do these patterns generalize beyond the early participants?
2. **Blind correlation studies**: Can an interpreter identify states from data without knowing the context?
3. **Inter-rater reliability**: Do multiple observers agree on labels?
4. **Phenomenological rigor**: Structured first-person protocols, not just informal reports
5. **Edge cases**: What breaks the labels? Where do they fail?

### Planned Studies

- Coupled sessions with naive participants (EBS + LLM conversation)
- Structured phenomenological interviewing during/after sessions
- Comparison with established HRV protocols
- Cross-validation with other biosignal modalities (EEG, GSR)
- Dual participant sessions to explore interpersonal dynamics both phenomenologically and in data

## Epistemological Humility

These labels are **tools for seeing**, not **ground truth categories**.

They emerged from a specific process (mutual constraint), specific participants (the developer and family members of different ages), and a specific context (self-observation during varied activities).

They may:

- Not generalize to all people
- Miss important patterns
- Conflate distinct states
- Be biased by the observer's expectations

The "proto" designation is not modesty - it's accuracy. These are hypotheses under investigation, not validated findings.

## Using Proto-Labels

Despite their provisional status, proto-labels are useful for:

1. **Real-time orientation**: Rough sense of what's happening
2. **Pattern recognition**: Noticing recurrent signatures
3. **Hypothesis generation**: "Is vigilant stillness always correlated with X?"
4. **Communication**: Shared vocabulary for discussing sessions

They should not be used for:

- Clinical diagnosis
- Definitive state classification
- Comparison across individuals (without baseline calibration)
- Claims of validated science

---

*"A proto-label is a finger pointing at the moon. Don't mistake it for the moon."*
