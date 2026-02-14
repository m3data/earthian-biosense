"""Shared fixtures for EarthianBioSense test suite.

Fixtures encode physiological meaning, not arbitrary data.
RR intervals reflect real autonomic patterns; HRVMetrics instances
represent recognizable states that the system claims to distinguish.
"""

import math
import random
import pytest

from src.processing.hrv import HRVMetrics


# =============================================================================
# RR Interval Buffers
# =============================================================================

@pytest.fixture
def rr_steady_60bpm():
    """30 constant 1000ms intervals — calm, zero variability.

    60 BPM resting heart rate with no respiratory modulation.
    Represents a theoretical baseline or suppressed vagal tone.
    """
    return [1000] * 30


@pytest.fixture
def rr_with_oscillation():
    """Sinusoidal +/-80ms at period 5 — entrained RSA pattern.

    Simulates respiratory sinus arrhythmia: heart rate rises on inhale,
    falls on exhale. Period of 5 beats at ~60 BPM ≈ 12 breaths/min.
    This is the canonical "entrained" signal.
    """
    return [1000 + int(80 * math.sin(2 * math.pi * i / 5)) for i in range(30)]


@pytest.fixture
def rr_noisy():
    """Random 650-1100ms, seed 42 — alert/stressed.

    High variability without rhythmic structure. Represents
    sympathetic dominance or environmental reactivity.
    """
    rng = random.Random(42)
    return [rng.randint(650, 1100) for _ in range(30)]


@pytest.fixture
def rr_very_short():
    """3 intervals — below minimum for most computations."""
    return [1000, 950, 1050]


@pytest.fixture
def rr_empty():
    """Empty list — no data."""
    return []


@pytest.fixture
def rr_constant():
    """20 identical intervals — zero variance edge case."""
    return [800] * 20


# =============================================================================
# HRVMetrics Instances
# =============================================================================

@pytest.fixture
def metrics_calm():
    """High entrainment, steady breath, coherent presence."""
    return HRVMetrics(
        mean_rr=1000.0,
        min_rr=920,
        max_rr=1080,
        amplitude=160,
        entrainment=0.75,
        entrainment_label="[high entrainment]",
        breath_rate=6.0,
        breath_steady=True,
        rr_volatility=0.04,
        mode_label="coherent presence",
        mode_score=0.85,
    )


@pytest.fixture
def metrics_alert():
    """Low entrainment, high volatility, heightened alertness."""
    return HRVMetrics(
        mean_rr=750.0,
        min_rr=650,
        max_rr=1100,
        amplitude=450,
        entrainment=0.1,
        entrainment_label="[low]",
        breath_rate=None,
        breath_steady=False,
        rr_volatility=0.15,
        mode_label="heightened alertness",
        mode_score=0.15,
    )


@pytest.fixture
def metrics_transitional():
    """Mid-range values — between states."""
    return HRVMetrics(
        mean_rr=870.0,
        min_rr=800,
        max_rr=950,
        amplitude=150,
        entrainment=0.35,
        entrainment_label="[emerging]",
        breath_rate=10.0,
        breath_steady=False,
        rr_volatility=0.08,
        mode_label="transitional",
        mode_score=0.45,
    )
