"""Tests for HRV metrics computation.

Covers src/processing/hrv.py — amplitude, autocorrelation, entrainment,
peak detection, breath rate, volatility, mode inference, and the full pipeline.
"""

import math
import pytest

from src.processing.hrv import (
    compute_amplitude,
    compute_autocorrelation,
    compute_entrainment,
    find_peaks,
    compute_breath_rate,
    compute_volatility,
    compute_mode,
    compute_hrv_metrics,
    HRVMetrics,
)


class TestComputeAmplitude:
    """Rolling amplitude: max - min over window."""

    def test_oscillating_signal(self, rr_with_oscillation):
        amp = compute_amplitude(rr_with_oscillation)
        # sin amplitude is +/-80, int truncation gives ~152
        assert 140 <= amp <= 160

    def test_constant_intervals(self, rr_constant):
        assert compute_amplitude(rr_constant) == 0

    def test_single_interval(self):
        assert compute_amplitude([1000]) == 0

    def test_empty(self, rr_empty):
        assert compute_amplitude(rr_empty) == 0


class TestComputeAutocorrelation:
    """Autocorrelation at specified lag."""

    def test_periodic_signal_at_period_lag(self, rr_with_oscillation):
        # Period is 5, so autocorrelation at lag 5 should be high (near 1)
        ac = compute_autocorrelation(rr_with_oscillation, lag=5)
        assert ac > 0.8

    def test_periodic_signal_at_half_period(self, rr_with_oscillation):
        # Lag 2-3 for period 5 — should be negative (anti-phase)
        ac = compute_autocorrelation(rr_with_oscillation, lag=2)
        assert ac < 0

    def test_constant_signal(self, rr_constant):
        # Zero variance -> returns 0.0
        assert compute_autocorrelation(rr_constant, lag=3) == 0.0

    def test_insufficient_data(self, rr_very_short):
        # 3 intervals, lag 5 -> not enough
        assert compute_autocorrelation(rr_very_short, lag=5) == 0.0

    def test_no_inflation_at_small_buffer(self):
        """P0-A regression: autocorrelation must not inflate at small n with large lag.

        With n=10 and lag=8, the old mixed-denominator formula inflated by
        n/(n-lag) = 5.0. The corrected formula uses n for both variance
        and autocovariance, so the result stays bounded by [-1, 1].
        """
        rr = [1000 + int(80 * math.sin(2 * math.pi * i / 5)) for i in range(10)]
        ac = compute_autocorrelation(rr, lag=8)
        assert -1.0 <= ac <= 1.0
        # At lag 8, period 5: not aligned with period, so should be modest
        assert abs(ac) < 0.5

    def test_consistent_denominator(self):
        """Verify normalization doesn't depend on lag for a white-noise-like signal.

        For truly random data, autocorrelation at any lag should be near zero.
        If the formula uses mixed denominators, large lags inflate the result.
        """
        import random
        rng = random.Random(123)
        rr = [rng.randint(900, 1100) for _ in range(20)]
        ac_lag2 = abs(compute_autocorrelation(rr, lag=2))
        ac_lag8 = abs(compute_autocorrelation(rr, lag=8))
        # Both should be small (near zero) for random data
        assert ac_lag2 < 0.5
        assert ac_lag8 < 0.5


class TestComputeEntrainment:
    """Breath-heart entrainment score from autocorrelation."""

    def test_entrained_signal_high_score(self, rr_with_oscillation):
        score, label = compute_entrainment(rr_with_oscillation)
        assert score > 0.4
        assert label in ("[entrained]", "[high entrainment]")

    def test_noisy_signal_low_score(self, rr_noisy):
        score, label = compute_entrainment(rr_noisy)
        assert score < 0.4

    def test_short_signal_insufficient(self, rr_very_short):
        score, label = compute_entrainment(rr_very_short)
        assert score == 0.0
        assert label == "[insufficient data]"

    def test_clamped_zero_to_one(self, rr_with_oscillation):
        score, _ = compute_entrainment(rr_with_oscillation)
        assert 0.0 <= score <= 1.0


class TestFindPeaks:
    """Local maxima detection in RR interval series."""

    def test_oscillation_has_peaks(self, rr_with_oscillation):
        peaks = find_peaks(rr_with_oscillation)
        assert len(peaks) > 0
        # Peaks should be roughly every 5 samples (period of oscillation)
        for idx in peaks:
            assert rr_with_oscillation[idx] > rr_with_oscillation[idx - 1]
            assert rr_with_oscillation[idx] > rr_with_oscillation[idx + 1]

    def test_constant_no_peaks(self, rr_constant):
        assert find_peaks(rr_constant) == []

    def test_short_signal_no_peaks(self):
        assert find_peaks([1000, 1050]) == []

    def test_single_peak(self):
        # Valley-peak-valley
        signal = [900, 900, 900, 1100, 900, 900, 900]
        peaks = find_peaks(signal)
        assert peaks == [3]


class TestComputeBreathRate:
    """Breath rate estimation from peak detection."""

    def test_entrained_signal_reasonable_rate(self, rr_with_oscillation):
        rate, steady = compute_breath_rate(rr_with_oscillation)
        assert rate is not None
        # Period of 5 beats at 1000ms = 5s cycle = 12 breaths/min
        assert 8 <= rate <= 16

    def test_insufficient_data(self, rr_very_short):
        rate, steady = compute_breath_rate(rr_very_short)
        assert rate is None
        assert steady is False


class TestComputeVolatility:
    """RR volatility as coefficient of variation."""

    def test_constant_zero_volatility(self, rr_constant):
        assert compute_volatility(rr_constant) == 0.0

    def test_noisy_positive_volatility(self, rr_noisy):
        vol = compute_volatility(rr_noisy)
        assert vol > 0.0

    def test_empty_zero(self, rr_empty):
        assert compute_volatility(rr_empty) == 0.0


class TestComputeMode:
    """Mode inference from combined HRV signals."""

    def test_high_calm_coherence(self):
        label, score = compute_mode(
            amplitude=160, entrainment=0.8, breath_steady=True, volatility=0.03
        )
        assert score > 0.6
        assert label in ("rhythmic settling", "settled presence")

    def test_low_calm_alertness(self):
        label, score = compute_mode(
            amplitude=40, entrainment=0.05, breath_steady=False, volatility=0.2
        )
        assert score < 0.35
        assert "alertness" in label


class TestComputeHRVMetrics:
    """Full pipeline: RR intervals -> HRVMetrics."""

    def test_full_pipeline_fields(self, rr_with_oscillation):
        m = compute_hrv_metrics(rr_with_oscillation)
        assert isinstance(m, HRVMetrics)
        assert m.mean_rr > 0
        assert m.amplitude > 0
        assert 0.0 <= m.entrainment <= 1.0
        assert m.mode_label != ""
        assert 0.0 <= m.mode_score <= 1.0

    def test_empty_input_defaults(self, rr_empty):
        m = compute_hrv_metrics(rr_empty)
        assert m.mean_rr == 0
        assert m.amplitude == 0
        assert m.entrainment == 0
        assert m.entrainment_label == "[no data]"
        assert m.breath_rate is None
        assert m.mode_label == "unknown"
