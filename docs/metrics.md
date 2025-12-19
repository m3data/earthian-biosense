# Metrics

This document describes the HRV-derived metrics computed by EarthianBioSense, including their calculation methods, rationale, and interpretation.

## Overview

EBS computes five core metrics from the RR interval stream:

| Metric | Range | What It Captures |
|--------|-------|------------------|
| **Amplitude (amp)** | 0-500+ ms | HRV magnitude - how much the heart rate varies |
| **Coherence (coh)** | 0.0-1.0 | Rhythmic ordering - how organized the variability pattern is |
| **Breath rate** | ~3-25 bpm | Estimated respiratory rate from RRi oscillation |
| **Volatility** | 0.0-1.0 | Normalized instability - how erratic the signal is |
| **Mode** | categorical | Autonomic state inference - alertness to coherence spectrum |

---

## Amplitude (amp)

### What It Is

Amplitude measures the range of RR interval variation within the analysis window:

```
amp = max(RRi) - min(RRi)
```

### Rationale

Unlike RMSSD or SDNN, amplitude captures the *span* of variability rather than average deviation. This is more intuitive for real-time feedback: "How much is your heart rate actually swinging?"

A contracted amplitude (low variability range) often indicates:

- Sympathetic dominance
- Stress, alertness, or cognitive load
- Reduced parasympathetic influence

An expanded amplitude indicates:

- Greater parasympathetic activity
- Relaxation, openness
- Capacity for flexible response

### Interpretation

| Range | Interpretation |
|-------|----------------|
| < 50 ms | Contracted - low variability, possibly stressed or cognitively loaded |
| 50-150 ms | Moderate - typical waking range |
| > 150 ms | Expanded - high variability, relaxed or in coherent state |

Note: Individual baselines vary significantly. These ranges are heuristic, not diagnostic.

### Window

Computed over the current RRi buffer (~20 samples, roughly 15-25 seconds depending on heart rate).

---

## Coherence (coh)

### What It Is

Coherence measures the rhythmic ordering of the HRV signal using autocorrelation at the estimated breath period.

```python
# Simplified logic
breath_period_samples = samples_per_breath_cycle
autocorr = correlation(RRi, RRi_shifted_by_breath_period)
coh = max(0, autocorr)  # Clamp negative values
```

### Rationale

Standard coherence measures (HeartMath) use spectral analysis to detect a peak around 0.1 Hz. This requires:

- Sufficient data (often 60+ seconds)
- Stationarity assumptions
- FFT computation

EBS uses autocorrelation instead because:

1. **Real-time capable**: Can compute on shorter windows
2. **Directly interpretable**: "How much does the signal repeat at the breath rhythm?"
3. **Robust to non-stationarity**: Doesn't assume fixed frequency structure

High coherence means the RRi pattern is repeating rhythmically at the breath frequency - the heart is "entrained" to respiration.

### Calculation Details

1. Estimate breath period from RRi oscillation (peak detection in smoothed signal)
2. Compute autocorrelation at that lag
3. Normalize to 0-1 range
4. Apply smoothing to reduce jitter

### Interpretation

| Range | Label | Meaning |
|-------|-------|---------|
| 0.0-0.2 | [low] | No clear rhythmic pattern |
| 0.2-0.4 | [emerging] | Rhythm beginning to establish |
| 0.4+ | [coherent] | Clear rhythmic entrainment |

### Limitations

- Requires detectable breath rhythm (fails during breath-holding, erratic breathing)
- Short windows increase noise
- Not equivalent to spectral coherence measures - different method, related concept

---

## Breath Rate

### What It Is

Estimated respiratory rate derived from the oscillation pattern in RR intervals.

### Rationale

Respiration modulates heart rate via respiratory sinus arrhythmia (RSA). By detecting the dominant oscillation frequency in the RRi signal, we can estimate breath rate without a dedicated respiration sensor.

### Calculation

1. Smooth the RRi signal
2. Detect peaks and troughs
3. Compute average cycle duration
4. Convert to breaths per minute

```python
breath_rate = 60 / average_cycle_duration_seconds
```

### Interpretation

| Range | Interpretation |
|-------|----------------|
| < 6 bpm | Very slow - deep relaxation, meditation, or possible artifact |
| 6-12 bpm | Slow - relaxed, coherence-promoting range |
| 12-18 bpm | Normal - typical resting breath |
| > 18 bpm | Fast - possibly anxious, effortful, or physically active |

### Limitations

- Returns `null` when no clear oscillation is detected
- Accuracy decreases with low amplitude or erratic patterns
- Cannot distinguish nasal vs. mouth breathing, depth, etc.

---

## Volatility

### What It Is

A normalized measure of signal instability - how erratic or "jumpy" the RRi signal is.

```python
volatility = std(RRi_differences) / mean(RRi)
```

### Rationale

Volatility captures something different from amplitude. A signal can have:

- High amplitude, low volatility: Large but smooth oscillations (coherent)
- High amplitude, high volatility: Large and erratic swings (unstable)
- Low amplitude, low volatility: Flat, contracted (alert stillness)
- Low amplitude, high volatility: Small but erratic (agitated but contracted)

### Interpretation

| Range | Interpretation |
|-------|----------------|
| < 0.02 | Very stable - smooth signal |
| 0.02-0.05 | Moderate - typical range |
| > 0.05 | Volatile - erratic, possibly stressed or transitioning |

### Use in Mode Classification

Volatility is one input to the mode inference algorithm. High volatility during transition periods is expected; sustained high volatility may indicate unresolved activation.

---

## Mode

### What It Is

An inferred autonomic state based on the pattern of other metrics. Mode represents a position on the alertness-to-coherence spectrum.

### Modes

| Mode | Signature | Interpretation |
|------|-----------|----------------|
| `heightened alertness` | Low coherence, low amplitude, possibly elevated HR | Sympathetic activation, stress |
| `subtle alertness` | Low-moderate coherence, moderate amplitude, stable | Watchful but not activated - attentive calm |
| `transitional` | Mixed signals, moderate volatility | Between states, no clear pattern |
| `settling` | Rising coherence or amplitude, decreasing volatility | Moving toward parasympathetic dominance |
| `emerging coherence` | Coherence rising above threshold, stabilizing | Coherent pattern establishing |
| `coherent` | High coherence, expanded amplitude, low volatility | Established rhythmic coherence |

### Calculation

Mode is computed via a weighted scoring system that considers:

- Coherence level and trend
- Amplitude relative to session baseline
- Volatility
- Breath rate (very slow or very fast affects classification)
- Recent trajectory (settling vs. activating)

The `mode_score` (0-1) indicates confidence in the classification.

### Limitations

- Mode is inferential, not directly measured
- Individual differences in baseline states affect accuracy
- Best interpreted as tendency, not diagnosis
- Proto-classification pending further validation

---

## Metric Relationships

The metrics are not independent. Key relationships:

```
                    ┌─────────────┐
                    │  Coherence  │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
         ┌────────┐  ┌──────────┐  ┌───────────┐
         │  Amp   │  │  Breath  │  │ Volatility│
         └────────┘  └──────────┘  └───────────┘
              │            │            │
              └────────────┼────────────┘
                           │
                           ▼
                      ┌────────┐
                      │  Mode  │
                      └────────┘
```

- **Coherence requires breath rhythm**: No detectable breath pattern → coherence unmeasurable
- **Amplitude modulates coherence visibility**: Very low amplitude makes coherence detection noisy
- **Volatility inversely related to coherence**: High volatility typically means low coherence
- **Mode integrates all signals**: The overall autonomic inference

---

## Implementation Notes

All metrics are computed in `src/processing/hrv.py`. Key parameters:

- Buffer size: ~20 RRi samples
- Update rate: Every new RRi (~1 second)
- Smoothing: Exponential moving average on coherence to reduce jitter
- Normalization: Amplitude normalized to 0-1 for phase space using session max

---

*"Metrics are not the territory. They are lenses that make certain patterns visible."*
