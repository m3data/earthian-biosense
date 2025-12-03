# Session Replay Visualization

Phenomenological and topological replay of EarthianBioSense sessions.

## Architecture

```
viz/
├── replay.html          # Main entry (current monolith, to be refactored)
├── css/
│   └── replay.css       # Styles
└── js/
    ├── config.js        # Central configuration & color palette
    ├── session.js       # Session data loading & derived computations
    ├── playback.js      # Timeline control (play, pause, scrub, speed)
    ├── transforms.js    # Coordinate mappings (sample → canvas/3D)
    ├── smoothing.js     # Catmull-Rom spline & smoothing utilities
    ├── view2d.js        # 2D temporal view (TODO)
    └── view3d.js        # 3D topology view (TODO)
```

## Views

### 2D Temporal ("Phenomenological")
- Present moment vivid, past dissolves into depth
- Trail recedes toward vanishing point
- Optimized for re-entering felt sense of session
- Supports first-person annotation

### 3D Topology ("Topological")
- Phase space: Coherence × Stability × Amplitude
- Dwell density reveals attractor basins
- Rotatable, zoomable
- Reveals structure of autonomic landscape

## Ontological Notes

These visualizations encode assumptions:

1. **Axes selection**: We privilege coherence, stability, amplitude — but the ANS has many more dimensions. What's collapsed?

2. **Trail length**: 80 samples (~2.5 min window). What temporal scale does this privilege? What rhythms become visible/invisible?

3. **Smoothing**: Catmull-Rom interpolation removes high-frequency jitter. Is that "noise" or signal? The choice to smooth is a choice about what matters.

4. **Dwell density**: Shows *where* the ANS lingers, not *when* or *how it got there*. Temporal order is lost.

5. **Color = Mode**: The mode classification is already interpretive. We're visualizing an interpretation, not raw data.

## Usage

```bash
# Serve locally (required for ES modules)
python -m http.server 8000 --directory viz/

# Open in browser
open http://localhost:8000/replay.html
```

Load a session `.jsonl` file from `sessions/` directory.

## Keyboard Shortcuts

- `Space` — Play/Pause
- `←` / `→` — Step backward/forward
- `1-4` — Playback speed

## Next Steps

- [ ] Complete modularization (extract view2d.js, view3d.js)
- [ ] Fix 3D trail smoothing (currently jittery)
- [ ] Fix 3D legend rendering
- [ ] Add annotation capability (mark moments for first-person notes)
- [ ] Export capabilities (image, video, annotated JSON)
