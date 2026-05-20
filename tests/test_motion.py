"""Tests for the motion channel (SPEC-013).

Covers src/processing/motion.py — gravity removal, RMS magnitude, debounced
still/moving gating, and range-egress detection. Synthetic accelerometer ticks
encode physical situations the gate must distinguish: a stationary strap at any
orientation (gravity only), oscillation (a rep), and sustained motion (walking
out of range).
"""

import json

from src.processing.motion import (
    MotionProcessor,
    MotionState,
    MOTION_THRESHOLD_MG,
)


def still_tick(gravity=(0, 0, 1000), n=36):
    """A tick of identical samples — strap held at a fixed orientation."""
    return [tuple(gravity)] * n


def osc_tick(amp=400, gravity=(0, 0, 1000), n=36):
    """A tick oscillating ±amp on X around gravity — vigorous movement."""
    return [
        (gravity[0] + (amp if i % 2 == 0 else -amp), gravity[1], gravity[2])
        for i in range(n)
    ]


class TestStillDetection:
    """A stationary strap reads as still regardless of orientation."""

    def test_constant_gravity_is_still(self):
        proc = MotionProcessor()
        state = proc.update(still_tick())
        assert state.motion_mag < 1.0
        assert state.state == "still"
        assert state.confounded is False
        assert state.n_samples == 36

    def test_still_at_arbitrary_orientation(self):
        """Gravity removal is orientation-agnostic — a tilted strap is still."""
        proc = MotionProcessor()
        for _ in range(3):
            state = proc.update(still_tick(gravity=(700, -700, 100)))
        assert state.motion_mag < 1.0
        assert state.state == "still"

    def test_empty_tick_holds_state(self):
        proc = MotionProcessor()
        proc.update(still_tick())
        state = proc.update([])
        assert state.n_samples == 0
        assert state.motion_mag == 0.0
        assert state.state == "still"


class TestMovingDetection:
    """Oscillation produces a high magnitude and, after debounce, moving state."""

    def test_oscillation_magnitude_exceeds_threshold(self):
        proc = MotionProcessor()
        proc.update(still_tick())  # establish gravity
        state = proc.update(osc_tick(amp=400))
        assert state.motion_mag > MOTION_THRESHOLD_MG

    def test_sustained_oscillation_flips_to_moving(self):
        proc = MotionProcessor()
        proc.update(still_tick())
        proc.update(osc_tick())  # 1st moving candidate — debounce not yet met
        state = proc.update(osc_tick())  # 2nd — flips
        assert state.state == "moving"
        assert state.confounded is True

    def test_single_moving_tick_does_not_flip(self):
        """One moving tick amid stillness is debounced away (no flicker)."""
        proc = MotionProcessor()
        proc.update(still_tick())
        state = proc.update(osc_tick())  # single spike
        assert state.state == "still"
        # Returns to quiet — candidate run resets.
        state = proc.update(still_tick())
        assert state.state == "still"


class TestGravityTracking:
    """Sustained reorientation is absorbed into gravity; transients are not."""

    def test_gradual_reorientation_stays_still(self):
        """A slow drift in the gravity vector is not movement."""
        proc = MotionProcessor()
        proc.update(still_tick(gravity=(0, 0, 1000)))
        max_mag = 0.0
        # Drift Z->X over many ticks in small steps.
        for k in range(1, 21):
            gx = 50 * k
            gz = 1000 - 50 * k
            state = proc.update(still_tick(gravity=(gx, 0, gz), n=36))
            max_mag = max(max_mag, state.motion_mag)
        # Small per-tick steps stay under threshold despite large total change.
        assert max_mag < MOTION_THRESHOLD_MG
        assert state.state == "still"


class TestRangeEgress:
    """Sustained motion warns once per episode, then re-arms after stillness."""

    def test_warning_fires_once_during_sustained_motion(self):
        proc = MotionProcessor()
        proc.update(still_tick())
        warnings = [proc.update(osc_tick()).range_egress_warning for _ in range(10)]
        assert sum(warnings) == 1

    def test_warning_requires_sustained_not_brief_motion(self):
        """A brief moving burst below the sustained threshold never warns."""
        proc = MotionProcessor()
        proc.update(still_tick())
        # Two moving ticks (just enough to flip) then back to still.
        fired = proc.update(osc_tick()).range_egress_warning
        fired |= proc.update(osc_tick()).range_egress_warning
        for _ in range(3):
            fired |= proc.update(still_tick()).range_egress_warning
        assert fired is False

    def test_episode_rearm_after_stillness(self):
        proc = MotionProcessor()
        proc.update(still_tick())
        first = [proc.update(osc_tick()).range_egress_warning for _ in range(8)]
        # Settle back to still (debounce + reset).
        for _ in range(4):
            proc.update(still_tick())
        second = [proc.update(osc_tick()).range_egress_warning for _ in range(8)]
        assert sum(first) == 1
        assert sum(second) == 1


def test_motion_state_is_json_serializable():
    proc = MotionProcessor()
    state = proc.update(still_tick())
    payload = json.dumps(state.to_dict())
    assert json.loads(payload)["state"] == "still"
