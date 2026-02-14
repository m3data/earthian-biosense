"""Tests for phase space trajectory tracking.

Covers src/processing/phase.py — metrics-to-position mapping, trajectory
append, coherence computation, reset, phase label inference, and static helpers.
"""

import math
import pytest

from src.processing.hrv import HRVMetrics
from src.processing.phase import PhaseTrajectory, PhaseDynamics


# =============================================================================
# Metrics to Position
# =============================================================================

class TestMetricsToPosition:
    """Mapping HRV metrics to 3D manifold coordinates."""

    def test_normalized_zero_to_one(self, metrics_calm):
        traj = PhaseTrajectory()
        pos = traj._metrics_to_position(metrics_calm)
        for coord in pos:
            assert 0.0 <= coord <= 1.0

    def test_breath_rate_none_defaults_half(self, metrics_alert):
        """When breath_rate is None, breath coordinate defaults to 0.5."""
        traj = PhaseTrajectory()
        pos = traj._metrics_to_position(metrics_alert)
        assert pos[1] == 0.5  # breath coordinate

    def test_amplitude_clamping(self):
        """Amplitude > 200 should clamp to 1.0."""
        metrics = HRVMetrics(
            mean_rr=800, min_rr=500, max_rr=1100,
            amplitude=600,  # way above 200
            entrainment=0.5, entrainment_label="[entrained]",
            breath_rate=10.0, breath_steady=True,
            rr_volatility=0.1, mode_label="transitional", mode_score=0.5,
        )
        traj = PhaseTrajectory()
        pos = traj._metrics_to_position(metrics)
        assert pos[2] == 1.0  # amplitude coordinate clamped


# =============================================================================
# Phase Trajectory Append
# =============================================================================

class TestPhaseTrajectoryAppend:
    """Adding states and computing dynamics."""

    def test_first_append_warming_up(self, metrics_calm):
        traj = PhaseTrajectory()
        dynamics = traj.append(metrics_calm, timestamp=1.0)
        assert dynamics.phase_label == "warming up"
        assert dynamics.velocity_magnitude == 0.0

    def test_velocity_nonzero_on_change(self, metrics_calm, metrics_alert):
        """Moving from calm to alert should produce nonzero velocity."""
        traj = PhaseTrajectory()
        traj.append(metrics_calm, timestamp=1.0)
        traj.append(metrics_calm, timestamp=2.0)
        dynamics = traj.append(metrics_alert, timestamp=3.0)
        assert dynamics.velocity_magnitude > 0

    def test_stability_when_stationary(self, metrics_calm):
        """Repeated identical metrics should produce high stability."""
        traj = PhaseTrajectory()
        for t in range(5):
            dynamics = traj.append(metrics_calm, timestamp=float(t))
        # After several identical appends, stability should be high
        assert dynamics.stability > 0.5

    def test_soft_mode_computed(self, metrics_calm):
        """Soft mode inference should be populated on every append."""
        traj = PhaseTrajectory()
        dynamics = traj.append(metrics_calm, timestamp=1.0)
        assert dynamics.soft_mode is not None
        assert len(dynamics.soft_mode.membership) == 6


# =============================================================================
# Trajectory Coherence
# =============================================================================

class TestTrajectoryCoherence:
    """Coherence as trajectory autocorrelation."""

    def test_insufficient_data_zero(self, metrics_calm):
        traj = PhaseTrajectory()
        traj.append(metrics_calm, timestamp=1.0)
        traj.append(metrics_calm, timestamp=2.0)
        assert traj.compute_trajectory_coherence() == 0.0

    def test_stationary_high_coherence(self, metrics_calm):
        """Stationary trajectory (low variance) should produce high coherence."""
        traj = PhaseTrajectory()
        for t in range(20):
            traj.append(metrics_calm, timestamp=float(t))
        coherence = traj.compute_trajectory_coherence()
        assert coherence > 0.5

    def test_bounded_zero_to_one(self, metrics_calm, metrics_alert):
        """Coherence should always be in [0, 1]."""
        traj = PhaseTrajectory()
        # Alternate to create movement
        for t in range(20):
            m = metrics_calm if t % 2 == 0 else metrics_alert
            traj.append(m, timestamp=float(t))
        coherence = traj.compute_trajectory_coherence()
        assert 0.0 <= coherence <= 1.0


# =============================================================================
# Reset
# =============================================================================

class TestPhaseTrajectoryReset:
    """Clearing all trajectory state."""

    def test_reset_clears_all(self, metrics_calm):
        traj = PhaseTrajectory()
        for t in range(5):
            traj.append(metrics_calm, timestamp=float(t))
        traj.reset()
        assert len(traj.states) == 0
        assert traj.cumulative_path_length == 0.0
        assert traj.mode_history.get_current_mode() is None


# =============================================================================
# Phase Label Inference
# =============================================================================

class TestInferPhaseLabel:
    """Phase labels from dynamics, not just thresholds."""

    def test_entrained_dwelling(self):
        traj = PhaseTrajectory()
        label = traj._infer_phase_label(
            position=(0.8, 0.5, 0.5),
            velocity_mag=0.01,
            curvature=0.01,
            stability=0.85,
        )
        assert label == "entrained dwelling"

    def test_inflection(self):
        traj = PhaseTrajectory()
        label = traj._infer_phase_label(
            position=(0.6, 0.5, 0.5),
            velocity_mag=0.1,
            curvature=0.5,
            stability=0.3,
        )
        assert "inflection" in label

    def test_active_transition(self):
        traj = PhaseTrajectory()
        label = traj._infer_phase_label(
            position=(0.2, 0.5, 0.3),
            velocity_mag=0.2,
            curvature=0.1,
            stability=0.4,
        )
        assert label == "active transition"


# =============================================================================
# Static Helpers
# =============================================================================

class TestStaticHelpers:
    """Euclidean distance and vector magnitude."""

    def test_euclidean_distance(self):
        d = PhaseTrajectory._euclidean_distance((0, 0, 0), (3, 4, 0))
        assert abs(d - 5.0) < 1e-6

    def test_vector_magnitude(self):
        m = PhaseTrajectory._vector_magnitude((3, 4, 0))
        assert abs(m - 5.0) < 1e-6
