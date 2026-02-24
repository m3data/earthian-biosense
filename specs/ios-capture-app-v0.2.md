# iOS Capture App Specification v0.2

**Status:** Draft
**Purpose:** Mobile biosignal capture with real-time self-reflection feedback
**Context:** EBS ecosystem, EECP protocol, personal coherence practice
**Version:** 0.2 (processing + feedback layer)
**Authors:** Mathew Mark Mytka + Claude Code (Kairos)
**Date:** 2025-12-30

---

## Design Philosophy

v0.2 evolves from "capture-only" to **capture + reflect**. The app becomes a self-reflection instrument that shows you where your nervous system is, helping you notice patterns and learn what supports your coherence.

**Principles:**
- **Informative, not prescriptive** — show state, don't direct behavior
- **Non-clinical aesthetic** — earth-warm, grounded, not medical
- **Phenomenological support** — the feedback aids felt-sense awareness
- **No gamification** — no scores, streaks, or performance pressure
- **Privacy-first** — all processing on-device, no cloud

**What v0.2 adds:**
- Real-time HRV metrics computation
- Phase dynamics tracking
- Mode classification with soft membership
- Visual feedback during sessions

**What v0.2 does NOT add:**
- Guidance, prompts, or breathing cues
- Goals or targets
- Session comparison or "improvement" tracking
- Post-session visualization replay (remains desktop)

---

## Processing Layer

### Porting from Python

The following must be ported to Swift:

#### 1. HRV Metrics (`HRVMetrics` struct)

```swift
struct HRVMetrics {
    let meanRR: Double      // ms
    let amplitude: Int      // max - min (ms)
    let entrainment: Double // 0-1, breath-heart coupling
    let entrainmentLabel: String
    let breathRate: Double? // breaths per minute
    let breathSteady: Bool
    let volatility: Double  // coefficient of variation
    let mode: String        // current mode label
    let modeScore: Double   // 0-1
}
```

**Computations required:**
- `compute_amplitude()` — max - min over window
- `compute_autocorrelation(lag:)` — for entrainment detection
- `compute_entrainment()` — autocorrelation at breath-period lag
- `estimate_breath_rate()` — peak detection in RR signal
- `compute_volatility()` — coefficient of variation
- `compute_mode()` — distance to 6 centroids, softmax

#### 2. Phase Dynamics (`PhaseDynamics` struct)

```swift
struct PhaseDynamics {
    let position: [Double]      // 3D: [entrainment, breathNorm, ampNorm]
    let velocity: [Double]      // rate of change
    let velocityMagnitude: Double
    let curvature: Double       // trajectory bending
    let stability: Double       // inverse velocity, 0-1
    let coherence: Double       // trajectory integrity, 0-1
    let movementAnnotation: String
}
```

**Computations required:**
- Position tracking in 3D phase space
- Velocity from position history (finite difference)
- Curvature from velocity history
- Stability from velocity magnitude
- Trajectory coherence via autocorrelation of positions

#### 3. Mode Classification

Six modes with soft membership:

| Mode | Characteristics |
|------|-----------------|
| `heightened alertness` | High volatility, low entrainment |
| `subtle alertness` | Attentive, moderate stability |
| `transitional` | Moving between states |
| `settling` | Approaching coherence |
| `rhythmic settling` | High entrainment, steady breath |
| `settled presence` | Sustained rhythmic settling |

**Implementation:**
- Store 6 centroids in feature space
- Compute weighted squared distance to each
- Apply softmax for membership probabilities
- Primary mode = highest membership
- Ambiguity = entropy of membership distribution

---

## Real-Time Display

### Recording View Updates

The existing `RecordingView` gains a feedback section:

```
┌─────────────────────────────────────┐
│  ❤️ 72 bpm                          │
│  RR: 832 ms                         │
├─────────────────────────────────────┤
│                                     │
│         [ MODE INDICATOR ]          │
│                                     │
│    ○ settling                       │
│    entrainment: ●●●○○ 0.58         │
│    coherence:   ●●○○○ 0.42         │
│                                     │
├─────────────────────────────────────┤
│  ⏱ 12:34                           │
│  [Stop Recording]                   │
└─────────────────────────────────────┘
```

### Feedback Elements

#### Mode Badge
- Current mode as text label
- Soft, muted color coding (earth tones, not traffic lights)
- Optional: secondary mode shown smaller if ambiguity is high

#### Entrainment Indicator
- Simple 5-dot scale (○ = empty, ● = filled)
- No judgment coloring
- Numeric value alongside

#### Coherence Indicator
- Same 5-dot scale
- Represents trajectory integrity, not "score"

#### Movement Annotation (optional)
- Subtle text: "settling", "accelerating", "dwelling"
- Helps notice transitions

### Visual Design Principles

- **No red/green** — avoid performance connotation
- **Earth-warm palette** — ochre, terracotta, sage, stone
- **Understated transitions** — smooth, not jarring
- **Readable at glance** — useful during eyes-closed practice

---

## Architecture

### Processing Pipeline

```
BLE Manager
    │
    ▼
RR Buffer (rolling 30 samples)
    │
    ├──▶ HRVProcessor
    │       │
    │       ▼
    │    HRVMetrics
    │
    └──▶ PhaseTracker
            │
            ▼
         PhaseDynamics
              │
              ▼
         ModeClassifier
              │
              ▼
         DisplayState (published to UI)
```

### New Components

```
EBSCapture/
├── Processing/
│   ├── HRVProcessor.swift      # HRV metrics computation
│   ├── PhaseTracker.swift      # Phase space dynamics
│   ├── ModeClassifier.swift    # 6-mode soft classification
│   └── ProcessingTypes.swift   # Structs (HRVMetrics, PhaseDynamics, etc.)
├── ViewModels/
│   └── SessionViewModel.swift  # Combines BLE + Processing, publishes state
└── Views/
    └── Components/
        ├── ModeIndicator.swift       # Mode badge
        ├── EntrainmentGauge.swift    # 5-dot entrainment display
        └── CoherenceGauge.swift      # 5-dot coherence display
```

### Data Flow

1. `BLEManager` receives RR intervals
2. `SessionViewModel` maintains rolling buffer
3. Every ~1 second (or every N RR intervals):
   - `HRVProcessor.compute(buffer)` → `HRVMetrics`
   - `PhaseTracker.update(metrics)` → `PhaseDynamics`
   - `ModeClassifier.classify(metrics, dynamics)` → mode + membership
4. `SessionViewModel` publishes combined `SessionState`
5. `RecordingView` observes and updates UI

### Session Recording

Processed metrics are optionally saved alongside raw data:

```json
{
  "ts": "2025-12-30T10:15:32.123Z",
  "hr": 72,
  "rr": [832],
  "metrics": {
    "amp": 145,
    "ent": 0.58,
    "mode": "settling",
    "coherence": 0.42
  }
}
```

This enables post-session analysis without re-processing.

---

## Implementation Notes

### Swift Considerations

- Use `Accelerate` framework for vectorized math (optional, for performance)
- `@Published` properties for reactive UI updates
- Avoid blocking main thread — processing is cheap but should be async
- Use `struct` for all data types (value semantics)

### Buffer Management

```swift
class RRBuffer {
    private var samples: [Int] = []
    private let maxSize = 30

    func append(_ rr: Int) {
        samples.append(rr)
        if samples.count > maxSize {
            samples.removeFirst()
        }
    }

    var array: [Int] { samples }
    var count: Int { samples.count }
}
```

### Entrainment Computation

Port directly from Python:

```swift
func computeAutocorrelation(_ samples: [Int], lag: Int) -> Double {
    guard samples.count >= lag + 2 else { return 0.0 }

    let n = samples.count
    let mean = Double(samples.reduce(0, +)) / Double(n)

    let variance = samples.map { pow(Double($0) - mean, 2) }.reduce(0, +) / Double(n)
    guard variance > 0 else { return 0.0 }

    var autocovariance = 0.0
    for i in 0..<(n - lag) {
        autocovariance += (Double(samples[i]) - mean) * (Double(samples[i + lag]) - mean)
    }
    autocovariance /= Double(n - lag)

    return autocovariance / variance
}
```

### Mode Centroids

```swift
let modeCentroids: [String: [String: Double]] = [
    "heightened alertness": [
        "entrainment": 0.1,
        "breathSteadyScore": 0.3,
        "ampNorm": 0.2,
        "inverseVolatility": 0.2
    ],
    "subtle alertness": [
        "entrainment": 0.25,
        "breathSteadyScore": 0.3,
        "ampNorm": 0.35,
        "inverseVolatility": 0.4
    ],
    // ... etc
]
```

---

## Testing Strategy

### Unit Tests

- `HRVProcessorTests`: verify metric computation matches Python output
- `PhaseTrackerTests`: verify dynamics computation
- `ModeClassifierTests`: verify classification against known inputs

### Integration Tests

- Feed recorded session through Swift pipeline
- Compare output to Python `process_session.py` output
- Ensure metrics match within tolerance (floating point)

### Manual Testing

- Side-by-side: iOS app + Python terminal app
- Verify mode transitions feel accurate
- Check UI responsiveness during rapid RR changes

---

## Out of Scope (v0.2)

These remain for future versions:

- **Breathing guidance** — pacing cues, visual breath guides
- **Session replay** — timeline scrubbing, historical viz
- **Comparative analysis** — session vs session, trends over time
- **Watch companion** — Apple Watch app
- **Sharing/export of processed data** — beyond raw JSONL
- **Customizable thresholds** — user-adjustable mode sensitivity

---

## Success Criteria

v0.2 is complete when:

1. ✅ HRV metrics computed in real-time on iOS
2. ✅ Phase dynamics tracked with coherence computation
3. ✅ Mode classification displayed during session
4. ✅ Visual feedback is readable and non-distracting
5. ✅ Processing matches Python output (validated via tests)
6. ✅ Battery impact remains acceptable for 60+ min sessions
7. ✅ Processed metrics saved to session file

---

## References

- `src/processing/hrv.py` — Python HRV implementation
- `src/processing/phase.py` — Python phase dynamics
- `src/processing/movement.py` — Mode centroids and classification
- `viz/DESIGN_PRINCIPLES.md` — Visualization ethics
- `specs/ios-capture-app-v0.1.md` — Previous version spec

---

*"The instrument shows you where you are. Where you go is yours to choose."*
