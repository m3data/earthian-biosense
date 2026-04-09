//! HRV metrics and coherence calculations for EarthianBioSense.
//!
//! Pure functions — no IO, no state beyond function arguments.
//! Ported from `src/processing/hrv.py`.

pub mod movement;
pub mod phase;

use serde::Serialize;

/// Computed HRV metrics from an RR-interval buffer.
#[derive(Debug, Clone, Serialize)]
pub struct HRVMetrics {
    /// Mean RR interval (ms).
    pub mean_rr: f64,
    /// Minimum RR interval (ms).
    pub min_rr: u16,
    /// Maximum RR interval (ms).
    pub max_rr: u16,
    /// Rolling amplitude: max − min (ms). Vagal expansion signal.
    pub amplitude: u16,

    /// Entrainment scalar (0–1). Breath-heart phase coupling.
    pub entrainment: f64,
    /// Human-readable entrainment label.
    pub entrainment_label: String,

    /// Estimated breath rate (breaths per minute), if detectable.
    pub breath_rate: Option<f64>,
    /// Whether the breath rhythm is steady (CV < 0.3).
    pub breath_steady: bool,

    /// RR volatility (coefficient of variation).
    pub rr_volatility: f64,

    /// Proto mode label (exploratory inference).
    pub mode_label: String,
    /// Proto mode score (0–1).
    pub mode_score: f64,
}

// ---------------------------------------------------------------------------
// Pure helper functions
// ---------------------------------------------------------------------------

/// Compute rolling amplitude (max − min) over the window.
pub fn compute_amplitude(rr: &[u16]) -> u16 {
    if rr.len() < 2 {
        return 0;
    }
    let min = *rr.iter().min().unwrap();
    let max = *rr.iter().max().unwrap();
    max - min
}

/// Compute autocorrelation at the specified lag.
///
/// Both variance and autocovariance use `n` as denominator (not `n − lag`).
/// This prevents inflation at small buffer sizes — see RAA-EBS-001.
pub fn compute_autocorrelation(rr: &[u16], lag: usize) -> f64 {
    let n = rr.len();
    if n < lag + 2 {
        return 0.0;
    }

    let mean = rr.iter().map(|&v| v as f64).sum::<f64>() / n as f64;

    let variance = rr.iter().map(|&v| (v as f64 - mean).powi(2)).sum::<f64>() / n as f64;
    if variance == 0.0 {
        return 0.0;
    }

    let autocovariance = (0..n - lag)
        .map(|i| (rr[i] as f64 - mean) * (rr[i + lag] as f64 - mean))
        .sum::<f64>()
        / n as f64;

    autocovariance / variance
}

/// Compute entrainment scalar using autocorrelation at breath-frequency lags.
///
/// Measures breath-heart entrainment (respiratory sinus arrhythmia) — how
/// tightly the heart rhythm is phase-locked to breathing.
///
/// Returns `(entrainment_score, label)`.
pub fn compute_entrainment(rr: &[u16]) -> (f64, String) {
    if rr.len() < 10 {
        return (0.0, "[insufficient data]".to_string());
    }

    let lags: [usize; 5] = [4, 5, 6, 7, 8];
    let correlations: Vec<f64> = lags.iter().map(|&lag| compute_autocorrelation(rr, lag)).collect();

    let max_corr = correlations
        .iter()
        .copied()
        .fold(f64::NEG_INFINITY, f64::max);

    // Clamp to 0–1.
    let entrainment = max_corr.clamp(0.0, 1.0);

    let label = if entrainment < 0.2 {
        "[low]"
    } else if entrainment < 0.4 {
        "[emerging]"
    } else if entrainment < 0.7 {
        "[entrained]"
    } else {
        "[high entrainment]"
    };

    (entrainment, label.to_string())
}

/// Find peak indices (local maxima) in the RR interval series.
pub fn find_peaks(rr: &[u16]) -> Vec<usize> {
    if rr.len() < 3 {
        return Vec::new();
    }

    let mut peaks = Vec::new();
    for i in 1..rr.len() - 1 {
        if rr[i] > rr[i - 1] && rr[i] > rr[i + 1] {
            peaks.push(i);
        }
    }
    peaks
}

/// Estimate breath rate using peak detection with zero-crossing fallback.
///
/// Returns `(breaths_per_minute, is_steady)`.
pub fn compute_breath_rate(rr: &[u16]) -> (Option<f64>, bool) {
    if rr.len() < 6 {
        return (None, false);
    }

    let peaks = find_peaks(rr);

    if peaks.len() < 2 {
        return breath_from_zero_crossings(rr);
    }

    // Peak-to-peak intervals (in beats).
    let peak_intervals: Vec<usize> = peaks.windows(2).map(|w| w[1] - w[0]).collect();

    if peak_intervals.is_empty() {
        return (None, false);
    }

    let avg_beats_per_breath =
        peak_intervals.iter().sum::<usize>() as f64 / peak_intervals.len() as f64;

    let mean_rr = rr.iter().map(|&v| v as f64).sum::<f64>() / rr.len() as f64;
    let cycle_duration_ms = avg_beats_per_breath * mean_rr;
    let cycle_duration_min = cycle_duration_ms / 60_000.0;

    if cycle_duration_min <= 0.0 {
        return (None, false);
    }

    let breath_rate = 1.0 / cycle_duration_min;

    // Steadiness: coefficient of variation of peak intervals.
    let steady = if peak_intervals.len() >= 2 {
        let mean_pi = avg_beats_per_breath; // already computed
        let variance = peak_intervals
            .iter()
            .map(|&x| (x as f64 - mean_pi).powi(2))
            .sum::<f64>()
            / peak_intervals.len() as f64;
        let cv = if mean_pi > 0.0 {
            variance.sqrt() / mean_pi
        } else {
            1.0
        };
        cv < 0.3
    } else {
        false
    };

    // Clamp to 2–20 bpm.
    if !(2.0..=20.0).contains(&breath_rate) {
        return (None, false);
    }

    (Some(breath_rate), steady)
}

/// Fallback breath estimation using zero crossings of the detrended signal.
pub fn breath_from_zero_crossings(rr: &[u16]) -> (Option<f64>, bool) {
    if rr.len() < 6 {
        return (None, false);
    }

    let mean_rr = rr.iter().map(|&v| v as f64).sum::<f64>() / rr.len() as f64;
    let detrended: Vec<f64> = rr.iter().map(|&v| v as f64 - mean_rr).collect();

    let mut crossings: usize = 0;
    for i in 1..detrended.len() {
        if detrended[i - 1] * detrended[i] < 0.0 {
            crossings += 1;
        }
    }

    if crossings < 2 {
        return (None, false);
    }

    let cycles = crossings as f64 / 2.0;
    let total_time_ms: f64 = rr.iter().map(|&v| v as f64).sum();
    let total_time_min = total_time_ms / 60_000.0;

    if total_time_min > 0.0 {
        let breath_rate = cycles / total_time_min;
        if (2.0..=20.0).contains(&breath_rate) {
            return (Some(breath_rate), false);
        }
    }

    (None, false)
}

/// Compute RR volatility as coefficient of variation (std_dev / mean).
pub fn compute_volatility(rr: &[u16]) -> f64 {
    if rr.len() < 2 {
        return 0.0;
    }

    let mean_rr = rr.iter().map(|&v| v as f64).sum::<f64>() / rr.len() as f64;
    if mean_rr == 0.0 {
        return 0.0;
    }

    let variance = rr.iter().map(|&v| (v as f64 - mean_rr).powi(2)).sum::<f64>() / rr.len() as f64;
    variance.sqrt() / mean_rr
}

/// Compute proto MODE — exploratory inference combining multiple signals.
///
/// Returns `(label, calm_score)`.
pub fn compute_mode(
    amplitude: u16,
    entrainment: f64,
    breath_steady: bool,
    volatility: f64,
) -> (String, f64) {
    let amp_norm = (amplitude as f64 / 200.0).min(1.0);
    let breath_steady_score = if breath_steady { 1.0 } else { 0.3 };

    let calm_score = (entrainment * 0.4
        + breath_steady_score * 0.3
        + amp_norm * 0.2
        + (1.0 - volatility * 5.0) * 0.1)
        .clamp(0.0, 1.0);

    let label = if calm_score < 0.2 {
        "heightened alertness"
    } else if calm_score < 0.35 {
        "subtle alertness"
    } else if calm_score < 0.5 {
        "transitional"
    } else if calm_score < 0.65 {
        "settling"
    } else if calm_score < 0.8 {
        "rhythmic settling"
    } else {
        "settled presence"
    };

    (label.to_string(), calm_score)
}

/// Compute all HRV metrics from an RR-interval buffer.
pub fn compute_hrv_metrics(rr: &[u16]) -> HRVMetrics {
    if rr.is_empty() {
        return HRVMetrics {
            mean_rr: 0.0,
            min_rr: 0,
            max_rr: 0,
            amplitude: 0,
            entrainment: 0.0,
            entrainment_label: "[no data]".to_string(),
            breath_rate: None,
            breath_steady: false,
            rr_volatility: 0.0,
            mode_label: "unknown".to_string(),
            mode_score: 0.0,
        };
    }

    let mean_rr = rr.iter().map(|&v| v as f64).sum::<f64>() / rr.len() as f64;
    let min_rr = *rr.iter().min().unwrap();
    let max_rr = *rr.iter().max().unwrap();

    let amplitude = compute_amplitude(rr);
    let (entrainment, entrainment_label) = compute_entrainment(rr);
    let (breath_rate, breath_steady) = compute_breath_rate(rr);
    let rr_volatility = compute_volatility(rr);
    let (mode_label, mode_score) = compute_mode(amplitude, entrainment, breath_steady, rr_volatility);

    HRVMetrics {
        mean_rr,
        min_rr,
        max_rr,
        amplitude,
        entrainment,
        entrainment_label,
        breath_rate,
        breath_steady,
        rr_volatility,
        mode_label,
        mode_score,
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_compute_amplitude() {
        let rr = vec![800, 900, 1000, 850, 950];
        assert_eq!(compute_amplitude(&rr), 200);

        assert_eq!(compute_amplitude(&[500]), 0);
        assert_eq!(compute_amplitude(&[]), 0);
    }

    #[test]
    fn test_autocorrelation_sinusoidal() {
        // Generate a sinusoidal RR pattern with period 6.
        // At lag=6 the autocorrelation should be high (close to 1.0).
        let rr: Vec<u16> = (0..30)
            .map(|i| {
                let val = 1000.0 + 100.0 * (2.0 * std::f64::consts::PI * i as f64 / 6.0).sin();
                val as u16
            })
            .collect();

        let ac_at_period = compute_autocorrelation(&rr, 6);
        assert!(
            ac_at_period > 0.7,
            "autocorrelation at period lag should be high, got {ac_at_period}"
        );

        // At a non-harmonic lag the correlation should be lower.
        let ac_off = compute_autocorrelation(&rr, 1);
        assert!(
            ac_off < ac_at_period,
            "off-period autocorrelation ({ac_off}) should be less than on-period ({ac_at_period})"
        );
    }

    #[test]
    fn test_entrainment_insufficient_data() {
        let rr = vec![800, 850, 900];
        let (score, label) = compute_entrainment(&rr);
        assert_eq!(score, 0.0);
        assert_eq!(label, "[insufficient data]");
    }

    #[test]
    fn test_entrainment_labels() {
        // Low entrainment — near-constant signal.
        let constant: Vec<u16> = vec![1000; 20];
        let (score, label) = compute_entrainment(&constant);
        assert_eq!(score, 0.0);
        assert_eq!(label, "[low]");

        // High entrainment — strong sinusoidal at lag within [4..8].
        let high: Vec<u16> = (0..40)
            .map(|i| {
                (1000.0 + 120.0 * (2.0 * std::f64::consts::PI * i as f64 / 5.0).sin()) as u16
            })
            .collect();
        let (score_h, label_h) = compute_entrainment(&high);
        assert!(
            score_h >= 0.7,
            "expected high entrainment, got {score_h}"
        );
        assert_eq!(label_h, "[high entrainment]");
    }

    #[test]
    fn test_volatility() {
        // Constant RR → zero volatility.
        let constant: Vec<u16> = vec![1000; 10];
        let v = compute_volatility(&constant);
        assert!(
            (v - 0.0).abs() < 1e-12,
            "constant input should yield 0.0 volatility, got {v}"
        );

        // Some variation → positive volatility.
        let varied = vec![800, 1000, 900, 1100, 850];
        let v2 = compute_volatility(&varied);
        assert!(v2 > 0.0, "varied input should have positive volatility");
    }

    #[test]
    fn test_mode_labels() {
        // Very low calm_score → "heightened alertness".
        let (label, score) = compute_mode(0, 0.0, false, 1.0);
        assert!(score < 0.2, "score should be < 0.2, got {score}");
        assert_eq!(label, "heightened alertness");

        // High calm_score → "settled presence".
        let (label2, score2) = compute_mode(200, 1.0, true, 0.0);
        assert!(score2 >= 0.8, "score should be >= 0.8, got {score2}");
        assert_eq!(label2, "settled presence");

        // Mid range → "transitional" or nearby.
        let (label3, score3) = compute_mode(80, 0.3, false, 0.1);
        assert!(
            score3 >= 0.2 && score3 < 0.65,
            "mid-range score expected, got {score3}"
        );
        // Just verify it's one of the middle labels.
        assert!(
            ["subtle alertness", "transitional", "settling"].contains(&label3.as_str()),
            "unexpected mid-range label: {label3}"
        );
    }

    #[test]
    fn test_compute_hrv_metrics_empty() {
        let m = compute_hrv_metrics(&[]);
        assert_eq!(m.mean_rr, 0.0);
        assert_eq!(m.min_rr, 0);
        assert_eq!(m.max_rr, 0);
        assert_eq!(m.amplitude, 0);
        assert_eq!(m.entrainment, 0.0);
        assert_eq!(m.entrainment_label, "[no data]");
        assert!(m.breath_rate.is_none());
        assert!(!m.breath_steady);
        assert_eq!(m.rr_volatility, 0.0);
        assert_eq!(m.mode_label, "unknown");
        assert_eq!(m.mode_score, 0.0);
    }

    #[test]
    fn test_breath_rate_basic() {
        // Clear oscillating pattern with period ~5 beats.
        // At ~1000 ms mean RR, 5 beats/cycle ≈ 5 s/cycle ≈ 12 bpm.
        let rr: Vec<u16> = (0..30)
            .map(|i| {
                (1000.0 + 80.0 * (2.0 * std::f64::consts::PI * i as f64 / 5.0).sin()) as u16
            })
            .collect();

        let (rate, _steady) = compute_breath_rate(&rr);
        assert!(rate.is_some(), "should detect a breath rate");
        let bpm = rate.unwrap();
        assert!(
            (bpm - 12.0).abs() < 3.0,
            "expected ~12 bpm, got {bpm}"
        );
    }
}
