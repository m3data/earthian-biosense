"""HRV metrics and coherence calculations for EarthianBioSense."""

from dataclasses import dataclass
import math


@dataclass
class HRVMetrics:
    """Computed HRV metrics from RR interval buffer."""
    # Basic stats
    mean_rr: float  # ms
    min_rr: int  # ms
    max_rr: int  # ms

    # Rolling amplitude (vagal expansion signal)
    amplitude: int  # ms (max - min)

    # Coherence scalar (0-1)
    coherence: float
    coherence_label: str  # [low], [emerging], [coherent], [high coherence]

    # Breath estimation
    breath_rate: float | None  # breaths per minute
    breath_steady: bool  # is breath rhythm stable?

    # Volatility
    rr_volatility: float  # coefficient of variation

    # MODE (proto) - exploratory inference
    mode_label: str
    mode_score: float  # 0-1


def compute_amplitude(rr_intervals: list[int]) -> int:
    """Compute rolling amplitude (max - min) over window."""
    if len(rr_intervals) < 2:
        return 0
    return max(rr_intervals) - min(rr_intervals)


def compute_autocorrelation(rr_intervals: list[int], lag: int) -> float:
    """Compute autocorrelation at specified lag."""
    n = len(rr_intervals)
    if n < lag + 2:
        return 0.0

    mean = sum(rr_intervals) / n

    # Compute variance
    variance = sum((x - mean) ** 2 for x in rr_intervals) / n
    if variance == 0:
        return 0.0

    # Compute autocovariance at lag
    autocovariance = sum(
        (rr_intervals[i] - mean) * (rr_intervals[i + lag] - mean)
        for i in range(n - lag)
    ) / (n - lag)

    return autocovariance / variance


def compute_coherence(rr_intervals: list[int], expected_breath_period: int = 5) -> tuple[float, str]:
    """
    Compute coherence scalar using autocorrelation at expected breath period.

    Coherent breathing at ~6 breaths/min = ~10s period = ~10-12 RR intervals at 60 BPM.
    We look for strong autocorrelation at lags corresponding to breath cycle.

    Returns (coherence_score, label)
    """
    if len(rr_intervals) < 10:
        return 0.0, "[insufficient data]"

    # Check autocorrelation at multiple lags around expected breath period
    # At ~60 BPM, breath period of 10s = ~10 beats
    # We'll check lags 4-8 (covering ~4-8 beat breath cycles)
    lags = [4, 5, 6, 7, 8]
    correlations = [compute_autocorrelation(rr_intervals, lag) for lag in lags]

    # Peak autocorrelation indicates rhythmic oscillation
    max_corr = max(correlations) if correlations else 0.0

    # Clamp to 0-1 range (autocorrelation can be negative)
    coherence = max(0.0, min(1.0, max_corr))

    # Apply labels
    if coherence < 0.2:
        label = "[low]"
    elif coherence < 0.4:
        label = "[emerging]"
    elif coherence < 0.7:
        label = "[coherent]"
    else:
        label = "[high coherence]"

    return coherence, label


def find_peaks(rr_intervals: list[int]) -> list[int]:
    """Find peak indices in RR interval series (local maxima)."""
    if len(rr_intervals) < 3:
        return []

    peaks = []
    for i in range(1, len(rr_intervals) - 1):
        if rr_intervals[i] > rr_intervals[i-1] and rr_intervals[i] > rr_intervals[i+1]:
            peaks.append(i)

    return peaks


def compute_breath_rate(rr_intervals: list[int], timestamps_ms: list[float] | None = None) -> tuple[float | None, bool]:
    """
    Estimate breath rate using peak detection.

    Returns (breaths_per_minute, is_steady)
    """
    if len(rr_intervals) < 6:
        return None, False

    peaks = find_peaks(rr_intervals)

    if len(peaks) < 2:
        # Fallback: try zero-crossing method
        return _breath_from_zero_crossings(rr_intervals)

    # Calculate peak-to-peak intervals (in number of beats)
    peak_intervals = [peaks[i+1] - peaks[i] for i in range(len(peaks) - 1)]

    if not peak_intervals:
        return None, False

    # Average beats per breath cycle
    avg_beats_per_breath = sum(peak_intervals) / len(peak_intervals)

    # Convert to breaths per minute
    # If avg RR is ~1000ms (60 BPM), and breath cycle is ~10 beats, that's 6 breaths/min
    mean_rr = sum(rr_intervals) / len(rr_intervals)
    cycle_duration_ms = avg_beats_per_breath * mean_rr
    cycle_duration_min = cycle_duration_ms / 60000

    if cycle_duration_min > 0:
        breath_rate = 1 / cycle_duration_min
    else:
        return None, False

    # Check steadiness: coefficient of variation of peak intervals
    if len(peak_intervals) >= 2:
        mean_pi = sum(peak_intervals) / len(peak_intervals)
        variance = sum((x - mean_pi) ** 2 for x in peak_intervals) / len(peak_intervals)
        cv = math.sqrt(variance) / mean_pi if mean_pi > 0 else 1.0
        steady = cv < 0.3  # Less than 30% variation = steady
    else:
        steady = False

    # Clamp to reasonable breath rate range (2-20 breaths/min)
    if breath_rate < 2 or breath_rate > 20:
        return None, False

    return breath_rate, steady


def _breath_from_zero_crossings(rr_intervals: list[int]) -> tuple[float | None, bool]:
    """Fallback breath estimation using zero crossings of detrended signal."""
    if len(rr_intervals) < 6:
        return None, False

    mean_rr = sum(rr_intervals) / len(rr_intervals)
    detrended = [rr - mean_rr for rr in rr_intervals]

    # Count zero crossings
    crossings = 0
    for i in range(1, len(detrended)):
        if detrended[i-1] * detrended[i] < 0:
            crossings += 1

    if crossings < 2:
        return None, False

    # Each breath cycle has ~2 zero crossings (up and down)
    cycles = crossings / 2

    # Estimate time span
    total_time_ms = sum(rr_intervals)
    total_time_min = total_time_ms / 60000

    if total_time_min > 0:
        breath_rate = cycles / total_time_min
        if 2 <= breath_rate <= 20:
            return breath_rate, False  # Zero-crossing is less steady by definition

    return None, False


def compute_volatility(rr_intervals: list[int]) -> float:
    """Compute RR volatility as coefficient of variation."""
    if len(rr_intervals) < 2:
        return 0.0

    mean_rr = sum(rr_intervals) / len(rr_intervals)
    if mean_rr == 0:
        return 0.0

    variance = sum((x - mean_rr) ** 2 for x in rr_intervals) / len(rr_intervals)
    std_dev = math.sqrt(variance)

    return std_dev / mean_rr


def compute_mode(amplitude: int, coherence: float, breath_steady: bool, volatility: float) -> tuple[str, float]:
    """
    Compute MODE (proto) - exploratory inference combining multiple signals.

    This is hypothesis-building only, not ground truth.
    Maps to provisional autonomic state categories.
    """
    # Normalize amplitude to 0-1 scale (0-200ms range typical)
    amp_norm = min(1.0, amplitude / 200)

    # Composite score weighted by different factors
    # High coherence + steady breath + moderate amplitude = coherent state
    # High volatility + low coherence = vigilance/stress
    # Low amplitude + low coherence = suppressed/disengaged

    # Simple weighted combination for proto version
    calm_score = (coherence * 0.4 +
                  (1.0 if breath_steady else 0.3) * 0.3 +
                  amp_norm * 0.2 +
                  (1 - volatility * 5) * 0.1)  # Lower volatility = calmer

    calm_score = max(0.0, min(1.0, calm_score))

    # Map to provisional labels
    if calm_score < 0.2:
        label = "heightened vigilance"
    elif calm_score < 0.35:
        label = "subtle vigilance"
    elif calm_score < 0.5:
        label = "transitional"
    elif calm_score < 0.65:
        label = "settling"
    elif calm_score < 0.8:
        label = "emerging coherence"
    else:
        label = "coherent presence"

    return label, calm_score


def compute_hrv_metrics(rr_intervals: list[int]) -> HRVMetrics:
    """Compute all HRV metrics from RR interval buffer."""
    if not rr_intervals:
        return HRVMetrics(
            mean_rr=0, min_rr=0, max_rr=0,
            amplitude=0, coherence=0, coherence_label="[no data]",
            breath_rate=None, breath_steady=False,
            rr_volatility=0, mode_label="unknown", mode_score=0
        )

    mean_rr = sum(rr_intervals) / len(rr_intervals)
    min_rr = min(rr_intervals)
    max_rr = max(rr_intervals)

    amplitude = compute_amplitude(rr_intervals)
    coherence, coherence_label = compute_coherence(rr_intervals)
    breath_rate, breath_steady = compute_breath_rate(rr_intervals)
    volatility = compute_volatility(rr_intervals)
    mode_label, mode_score = compute_mode(amplitude, coherence, breath_steady, volatility)

    return HRVMetrics(
        mean_rr=mean_rr,
        min_rr=min_rr,
        max_rr=max_rr,
        amplitude=amplitude,
        coherence=coherence,
        coherence_label=coherence_label,
        breath_rate=breath_rate,
        breath_steady=breath_steady,
        rr_volatility=volatility,
        mode_label=mode_label,
        mode_score=mode_score
    )
