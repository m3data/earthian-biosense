# Viz Refactor Plan

*Aligning the session replay visualization with DESIGN_PRINCIPLES.md*

---

## Current State

- `replay.html` is a 1200-line monolith with inline JS
- Basic 2D/3D views functional
- Schema updated to v1.0.0 (entrainment/coherence distinction)
- Module structure exists in `js/` but view modules are TODO
- Coherence field fixed to use `phase.coherence` (trajectory integrity)

---

## Design Principles Gap Analysis

| Principle | Current State | Gap |
|-----------|---------------|-----|
| **Earth-warm palette** | Clinical purples/grays, mode colors feel performative | Need ochres, ambers, terracottas |
| **No evaluative encoding** | Mode colors imply good/bad hierarchy | Neutral, non-judgmental encoding |
| **Flows over points** | Trail works but density view is point-based | Density should show flow patterns |
| **Delayed complexity** | All metrics visible immediately | Metrics hidden by default |
| **Annotation capability** | Not implemented | Participant marks moments with own language |
| **Reflection prompts** | Not implemented | Prompt before revealing data |
| **Phenomenological primacy** | Data-first display | Narrative invitation first |
| **Permission to disagree** | Not implemented | "This doesn't match my experience" option |
| **Gentle pacing** | Default speed feels observational | Default should feel immersive |

---

## Refactor Phases

### Phase 1: Code Structure

Extract from monolith into proper ES modules.

**Files to create/complete:**

```
viz/
├── replay.html          # Minimal shell, imports modules
├── css/
│   └── replay.css       # All styles extracted
└── js/
    ├── config.js        # Palette, constants, CONFIG object
    ├── session.js       # Session loading (already exists, update for schema)
    ├── playback.js      # Play/pause/scrub/speed state machine
    ├── transforms.js    # sampleToCanvas2D, sampleToCanvas3D
    ├── smoothing.js     # Catmull-Rom, perspective transforms
    ├── view2d.js        # Full 2D sketch extracted
    ├── view3d.js        # Full 3D sketch extracted
    ├── ui.js            # DOM updates, metric panel, controls
    └── main.js          # Entry point, event wiring
```

**Outcome:** Clean separation. Each file < 200 lines. Testable units.

---

### Phase 2: Earth-Warm Palette

Replace clinical colors with grounded, body-resonant tones.

**Current MODE_COLORS:**
```js
'heightened alertness': [255, 120, 80],   // alert orange
'subtle alertness': [220, 180, 100],      // yellow
'settling': [100, 160, 200],              // clinical blue
'transitional': [180, 150, 200],          // purple
'rhythmic settling': [120, 200, 160],     // mint
'coherent': [100, 220, 180],              // teal
'deep coherence': [80, 240, 200]          // bright teal
```

**Proposed EARTH_PALETTE:**
```js
// No state is "better" — just different textures of becoming
'alert stillness': [180, 140, 100],       // warm sand
'active transition': [200, 120, 90],      // terracotta
'settling into entrainment': [160, 130, 110], // clay
'entrained dwelling': [170, 150, 120],    // amber
'flowing (entrained)': [190, 160, 130],   // soft ochre
'inflection (seeking)': [150, 120, 100],  // deep earth
'inflection (from entrainment)': [165, 135, 105], // warm umber
'neutral dwelling': [175, 155, 135],      // sandstone
'transitional': [185, 145, 115],          // desert rose
'warming up': [140, 130, 120],            // cool clay
```

**Principle:** Colors differentiate without ranking. Warmth invites settling.

---

### Phase 3: Delayed Revelation

Start simple. Complexity on request.

**Initial state:**
- Just the trail, breathing softly
- No metrics panel visible
- No phase label
- No speed controls
- Single "Begin" button

**First interaction:**
- Trail starts moving
- Gentle prompt: "What do you notice?"

**On request (toggle):**
- Metrics panel fades in
- Phase label appears
- Speed controls available
- Timeline scrubber visible

**Implementation:**
- CSS classes: `.revealed`, `.hidden`
- State machine: `intro` → `playing` → `exploring`
- Transitions: 400ms ease-in-out

---

### Phase 4: Reflection Layer

Phenomenological primacy — felt sense before data.

**Pre-visualization prompt:**
```
Before we show you the session trace...

What do you remember feeling during this session?
What moments stand out?

[Free text input]

[Continue to visualization]
```

**During playback prompts (optional, toggleable):**
- At 25%: "What was moving here?"
- At 50%: "Does this shape feel familiar?"
- At 75%: "Is there something you want to linger on?"

**Implementation:**
- Modal overlay component
- Responses stored in session annotation object
- Prompts can be disabled in settings

---

### Phase 5: Annotation Capability

Participant language has equal epistemic weight.

**Interaction:**
- Click/tap on timeline or trail to mark a moment
- Popup: "What would you call this moment?"
- Preset options: "tightening", "softening", "opening", "dispersing", "holding"
- Custom text input

**Visual representation:**
- Small marker on timeline at annotation point
- Subtle glow on trail at that moment
- Annotations visible in sidebar list

**Disagreement option:**
- "This doesn't match my experience" button
- Opens note: "What did you actually feel?"
- Stored as annotation with `disagreement: true`

**Data structure:**
```json
{
  "annotations": [
    {
      "index": 142,
      "ts": "2025-12-04T18:54:12",
      "label": "softening",
      "custom": null,
      "disagreement": false
    },
    {
      "index": 287,
      "ts": "2025-12-04T18:58:30",
      "label": null,
      "custom": "something shifted but I can't name it",
      "disagreement": false
    }
  ]
}
```

---

### Phase 6: Entrainment/Coherence Display

Make the conceptual distinction visible.

**Current:** Single "Coherence" metric (actually trajectory coherence)

**Proposed:** Two distinct displays

| Metric | Meaning | Display |
|--------|---------|---------|
| **Entrainment** | Breath-heart phase coupling (local sync) | Vertical bar or ring |
| **Coherence** | Trajectory integrity (global pattern) | Horizontal position / separate bar |

**UI options:**
- Toggle: "Show entrainment / Show coherence / Show both"
- 2D view can use either for x-axis
- 3D view can use coherence for one axis, entrainment for another

**Labels:**
- Entrainment: "the grip" (local sync)
- Coherence: "the journey" (trajectory integrity)

---

## Implementation Order

1. **Phase 1** first — clean code enables everything else
2. **Phase 2** next — palette shift is high impact, low risk
3. **Phase 3** — delayed revelation changes the experience fundamentally
4. **Phase 6** — entrainment/coherence distinction is conceptually important
5. **Phase 4 & 5** — reflection and annotation are deeper features, can iterate

---

## Not In Scope (Future)

- Video/image export
- Multi-session comparison
- Real-time streaming replay
- Mobile-optimized views
- Accessibility audit (important but separate effort)

---

## Success Criteria

The refactor is complete when:

1. A participant can load a session and feel *recognized*, not *evaluated*
2. The visualization invites curiosity, not performance
3. Participant annotations are first-class data
4. The code is modular enough that changing the palette doesn't require touching view logic
5. The entrainment/coherence distinction is legible in the UI

---

*This plan is provisional. It will evolve as we learn from actual use.*
