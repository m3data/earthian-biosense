"""Tests for movement-preserving classification.

Covers src/processing/movement.py — soft mode inference, mode history,
hysteresis-aware detection, movement annotation, and rupture oscillation.
"""

import math
import pytest

from src.processing.movement import (
    SoftModeInference,
    ModeHistory,
    HysteresisConfig,
    MODE_CENTROIDS,
    DEFAULT_HYSTERESIS,
    compute_soft_mode_membership,
    detect_mode_with_hysteresis,
    generate_movement_annotation,
    detect_rupture_oscillation,
)


# =============================================================================
# Soft Mode Inference
# =============================================================================

class TestSoftModeInference:
    """Weighted membership across modes via softmax on centroid distances."""

    def test_membership_sums_to_one(self):
        result = compute_soft_mode_membership(
            entrainment=0.5, breath_steady=True, amp_norm=0.5, volatility=0.05
        )
        total = sum(result.membership.values())
        assert abs(total - 1.0) < 1e-6

    def test_high_entrainment_coherence(self):
        result = compute_soft_mode_membership(
            entrainment=0.85, breath_steady=True, amp_norm=0.8, volatility=0.02
        )
        assert result.primary_mode == "coherent presence"

    def test_low_entrainment_alertness(self):
        result = compute_soft_mode_membership(
            entrainment=0.05, breath_steady=False, amp_norm=0.1, volatility=0.2
        )
        assert "alertness" in result.primary_mode

    def test_boundary_ambiguity(self):
        """Mid-range inputs should produce higher ambiguity than extreme inputs."""
        mid = compute_soft_mode_membership(
            entrainment=0.4, breath_steady=False, amp_norm=0.4, volatility=0.1
        )
        extreme = compute_soft_mode_membership(
            entrainment=0.9, breath_steady=True, amp_norm=0.9, volatility=0.01
        )
        assert mid.ambiguity > extreme.ambiguity

    def test_temperature_sharpness(self):
        """Lower temperature should produce sharper (less ambiguous) distributions."""
        sharp = compute_soft_mode_membership(
            entrainment=0.7, breath_steady=True, amp_norm=0.6, volatility=0.04,
            temperature=0.3
        )
        soft = compute_soft_mode_membership(
            entrainment=0.7, breath_steady=True, amp_norm=0.6, volatility=0.04,
            temperature=2.0
        )
        # Sharper distribution has higher max weight
        max_sharp = max(sharp.membership.values())
        max_soft = max(soft.membership.values())
        assert max_sharp > max_soft

    def test_kl_divergence_computed(self):
        """Distribution shift (KL divergence) computed when previous inference provided."""
        first = compute_soft_mode_membership(
            entrainment=0.3, breath_steady=False, amp_norm=0.3, volatility=0.1
        )
        second = compute_soft_mode_membership(
            entrainment=0.7, breath_steady=True, amp_norm=0.7, volatility=0.03,
            previous_inference=first
        )
        assert second.distribution_shift is not None
        assert second.distribution_shift > 0  # different distributions

    def test_all_six_modes_present(self):
        result = compute_soft_mode_membership(
            entrainment=0.5, breath_steady=True, amp_norm=0.5, volatility=0.05
        )
        assert len(result.membership) == 6
        for mode in MODE_CENTROIDS:
            assert mode in result.membership

    def test_upper_modes_reachable_at_default_temperature(self):
        """P0-B regression: all six modes must clear their entry thresholds.

        At T=1.0, the softmax ceiling fell below entry thresholds for
        settling (0.19), emerging coherence (0.20), and coherent presence (0.22).
        The default temperature must be low enough for these to be enterable.
        """
        # coherent presence — needs membership >= 0.22
        cp = compute_soft_mode_membership(
            entrainment=0.8, breath_steady=True, amp_norm=0.75, volatility=0.01
        )
        assert cp.membership['coherent presence'] >= DEFAULT_HYSTERESIS['coherent presence'].entry_threshold

        # emerging coherence — needs membership >= 0.20
        ec = compute_soft_mode_membership(
            entrainment=0.65, breath_steady=True, amp_norm=0.65, volatility=0.03
        )
        assert ec.membership['emerging coherence'] >= DEFAULT_HYSTERESIS['emerging coherence'].entry_threshold

        # settling — needs membership >= 0.19
        s = compute_soft_mode_membership(
            entrainment=0.55, breath_steady=True, amp_norm=0.55, volatility=0.05
        )
        assert s.membership['settling'] >= DEFAULT_HYSTERESIS['settling'].entry_threshold


# =============================================================================
# Mode History
# =============================================================================

class TestModeHistory:
    """Mode sequence tracking for hysteresis."""

    def test_append_tracking(self):
        history = ModeHistory()
        history.append("settling", 0.6, 1.0)
        history.append("settling", 0.65, 2.0)
        assert history.get_current_mode() == "settling"
        assert len(history.history) == 2

    def test_transition_counting(self):
        history = ModeHistory()
        history.append("settling", 0.6, 1.0)
        history.append("transitional", 0.4, 2.0)
        history.append("settling", 0.6, 3.0)
        assert history.get_transition_count() == 2

    def test_dwell_time(self):
        history = ModeHistory()
        history.append("settling", 0.6, 10.0)
        history.append("settling", 0.65, 15.0)
        assert history.get_dwell_time(20.0) == 10.0

    def test_max_history_truncation(self):
        history = ModeHistory(max_history=5)
        for i in range(10):
            history.append("settling", 0.6, float(i))
        assert len(history.history) == 5

    def test_clear(self):
        history = ModeHistory()
        history.append("settling", 0.6, 1.0)
        history.append("transitional", 0.4, 2.0)
        history.clear()
        assert history.get_current_mode() is None
        assert history.get_transition_count() == 0
        assert len(history.history) == 0


# =============================================================================
# Hysteresis-Aware Detection
# =============================================================================

class TestDetectModeWithHysteresis:
    """State machine: unknown -> provisional -> established."""

    def test_first_entry_provisional(self):
        """First detection should enter provisional state with entry penalty."""
        # Use low temperature to sharpen distribution above entry threshold
        soft = compute_soft_mode_membership(
            entrainment=0.8, breath_steady=True, amp_norm=0.7, volatility=0.03,
            temperature=0.1
        )
        history = ModeHistory()
        mode, confidence, meta = detect_mode_with_hysteresis(soft, history, 1.0)
        assert meta['state_status'] == 'provisional'
        assert meta['transition_type'] == 'entry'
        # Entry penalty should reduce confidence below raw
        assert confidence < soft.membership[soft.primary_mode]

    def test_sustained_establishment(self):
        """Staying in same mode long enough transitions to established."""
        history = ModeHistory()
        soft = compute_soft_mode_membership(
            entrainment=0.8, breath_steady=True, amp_norm=0.7, volatility=0.03,
            temperature=0.1
        )
        # First entry
        mode, confidence, _ = detect_mode_with_hysteresis(soft, history, 0.0)
        history.append(mode, confidence, 0.0)

        # Sustain for enough samples to cross provisional_samples threshold
        established = False
        for t in range(1, 20):
            soft = compute_soft_mode_membership(
                entrainment=0.8, breath_steady=True, amp_norm=0.7, volatility=0.03,
                temperature=0.1,
                previous_inference=soft
            )
            mode, confidence, meta = detect_mode_with_hysteresis(
                soft, history, float(t)
            )
            history.append(mode, confidence, float(t))
            if meta['state_status'] == 'established':
                established = True
                break

        assert established

    def test_entry_penalty_applied(self):
        """Entry penalty reduces raw confidence on mode entry."""
        soft = compute_soft_mode_membership(
            entrainment=0.8, breath_steady=True, amp_norm=0.7, volatility=0.03,
            temperature=0.1
        )
        history = ModeHistory()
        mode, confidence, meta = detect_mode_with_hysteresis(soft, history, 1.0)
        raw = soft.membership[soft.primary_mode]
        # Confidence should be penalized (entry_penalty < 1.0)
        assert confidence < raw


# =============================================================================
# Movement Annotation
# =============================================================================

class TestGenerateMovementAnnotation:
    """Human-readable movement context."""

    def test_settled(self):
        annotation = generate_movement_annotation(
            velocity_magnitude=0.01,
            acceleration_magnitude=0.0,
            previous_mode=None,
            dwell_time=10.0,
        )
        assert annotation == "settled"

    def test_still_with_approach(self):
        annotation = generate_movement_annotation(
            velocity_magnitude=0.01,
            acceleration_magnitude=0.0,
            previous_mode="heightened alertness",
            dwell_time=2.0,  # within RECENT_TRANSITION_WINDOW
        )
        assert "still" in annotation
        assert "from heightened alertness" in annotation

    def test_accelerating(self):
        annotation = generate_movement_annotation(
            velocity_magnitude=0.1,
            acceleration_magnitude=0.05,
            previous_mode=None,
            dwell_time=1.0,
        )
        assert "accelerating" in annotation


# =============================================================================
# Rupture Oscillation Detection
# =============================================================================

class TestDetectRuptureOscillation:
    """ABAB pattern detection in mode transitions."""

    def test_abab_detected(self):
        history = ModeHistory()
        modes = ["settling", "alertness", "settling", "alertness",
                 "settling", "alertness"]
        for i, mode in enumerate(modes):
            history.append(mode, 0.5, float(i))

        result = detect_rupture_oscillation(history, window=6, min_transitions=4)
        assert result is not None
        assert result['transition_count'] >= 4

    def test_stable_no_rupture(self):
        history = ModeHistory()
        for i in range(10):
            history.append("settling", 0.6, float(i))

        result = detect_rupture_oscillation(history)
        assert result is None
