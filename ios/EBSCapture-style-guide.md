# Earthian UI Style Guide  
**EBSCapture & Earthian Biosensing Interfaces**

Version: 0.1  
Status: Living document  
Intent: Calm, grounded, life-affirming interfaces for biosensing and coherence tools

---

## 1. Design Ethos

Earthian UI is not decorative.  
It is **regulative infrastructure**.

The interface should:
- Reduce sympathetic nervous system load
- Support inward attention and bodily listening
- Feel calm, grounded, and alive
- Never feel gamified, clinical, or extractive

If a choice increases visual excitement but increases cognitive load, it is wrong.

Primary stance:
> *The UI listens with the user.*

---

## 2. Core Principles

### 2.1 Restraint over expressiveness
- Fewer colors, used with intention
- No gratuitous animation
- No visual noise
- Space is a feature

### 2.2 State over decoration
Color communicates **state**, not branding.  
If a color does not encode meaning, it should not be present.

### 2.3 Backgrounds carry the Earthian tone
- Data remains simple and legible
- Earthian warmth lives in surfaces, cards, and accents
- Avoid loud chromatic foregrounds

### 2.4 Calm by default
The UI should feel appropriate for:
- slow breathing
- sustained attention
- quiet environments
- reflective states

---

## 3. Color System

### 3.1 Base Earth-Warm Palette

```css
--bg-deep:        #0a0a0f;
--bg:             #0d0d12;
--bg-surface:     #12121a;
--bg-elevated:    #1a1a24;

--border-subtle:  #1a1a24;
--border:         #222;
--border-emphasis:#333;

--text:           #e0e0e0;
--text-muted:     #aaa;
--text-dim:       #666;
--text-faint:     #444;
```

Usage:
- `bg-deep`: app root / window background
- `bg-surface`: main content areas
- `bg-elevated`: cards, panels, contained views
- Avoid pure black and pure white

---

### 3.2 Earth-Warm Accents

```css
--amber:       #b49070;
--amber-dim:   #8a6a50;
--ochre:       #c4956a;
--terracotta:  #cd6e46;
--sage:        #829b82;
--sage-dim:    #5a7a5a;
--slate:       #7a9ac4;
--slate-dim:   #5a7a9a;
```

Rules:
- Accents are **never dominant**
- Use low saturation and low opacity by default
- Prefer dim variants unless emphasis is required

---

### 3.3 Quadrant / State Colors

```css
--settled:     #829b82;  // calm, coherent, grounded
--journey:     #c4956a;  // transitioning, searching
--activated:   #cd6e46;  // recording, engaged, active
--fragmented:  #7a9ac4;  // disrupted, incoherent
```

Usage rules:
- Encode **system or physiological state**
- Do not use as background fills
- Best applied to:
  - icons
  - dots
  - bars
  - subtle glows
  - labels

---

## 4. Typography

### 4.1 General

- Use system fonts (SF Pro)
- Avoid novelty fonts
- Prefer clarity and calm over personality

### 4.2 Hierarchy

- Titles: large, restrained, confident
- Data (e.g. BPM): prominent but not aggressive
- Labels: secondary, never shouting

Avoid:
- ALL CAPS
- Excessive bold
- Condensed styles

---

## 5. Layout & Composition

### 5.1 Vertical Rhythm

- Assume constrained vertical space
- Content should scroll naturally
- Never rely on “everything fits on one screen”

Rules:
- Avoid vertical `Spacer()` for layout control
- Use padding and fixed spacing instead
- Prefer `ScrollView` for main screens

---

### 5.2 Cards & Surfaces

Cards are containment, not decoration.

Recommended:
- Rounded rectangles
- Soft elevation via color, not shadow
- Subtle contrast against background

Avoid:
- Hard dividers
- Heavy drop shadows
- Visual stacking effects

---

### 5.3 Safe Areas

- Respect safe areas by default
- Use `.safeAreaInset` for persistent controls
- Never globally ignore safe areas for content

---

## 6. Interaction & Feedback

### 6.1 Buttons

- Large enough to feel secure
- Rounded, soft edges
- Clear affordance without aggression

Primary actions:
- Calm blue or muted Earthian tone
- No flashing or pulsing by default

---

### 6.2 Animation

Animation is optional and rare.

Allowed:
- Gentle transitions
- State changes that reduce ambiguity

Avoid:
- Pulsing indicators
- Bouncing
- Gamified motion
- Attention-seeking effects

---

## 7. Biosensing-Specific Guidance

### 7.1 Live Data

- Data should feel *present*, not urgent
- Avoid rapid color changes
- Prefer smoothing and stability

### 7.2 Recording Mode

Recording is a **mode**, not just a button.

When recording:
- UI should become quieter
- Visual density should reduce
- Accents may warm slightly (e.g. terracotta, dimmed)

---

## 8. Anti-Patterns (Do Not Do)

- Bright white backgrounds
- Neon or high-saturation colors
- Competitive visual metaphors
- “Fitness app” tropes
- Gamification elements
- Excessive metrics on one screen

---

## 9. Decision Heuristic

When unsure, ask:

> Does this choice increase coherence, calm, and embodied presence?

If not, remove or simplify.

---

## 10. Living Nature of This Guide

This guide evolves with:
- user experience
- physiological response
- device constraints
- Earthian practice

Clarity and restraint outrank novelty at all times.