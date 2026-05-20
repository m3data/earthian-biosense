"""Motion channel for EarthianBioSense (SPEC-013).

Derives a body-motion signal from the Polar H10 accelerometer so the mode
classifier can tell *HR elevated by movement* from *HR elevated by arousal*.
Without this, exercise tachycardia and affective activation are indistinguishable
in cardiac features, and the mode taxonomy silently mislabels one as the other.

Pipeline (per ~1Hz tick of accelerometer samples):
    1. Gravity removal  — per-sample EMA tracks the static gravity vector;
       the dynamic component is sample minus that estimate. Sustained
       reorientation bleeds into gravity; transient movement does not.
    2. Magnitude        — RMS of the per-sample dynamic magnitude over the tick.
    3. Gating           — debounced still/moving state (hysteresis: a flip
       requires several consecutive ticks, so single-sample jitter doesn't
       toggle the state).
    4. Range egress     — sustained motion is a leading indicator of imminent
       BLE dropout (the body walking out of range). Fires once per episode.

The `confounded` flag (== moving) is what the classifier consumes: in v0.1 we
annotate motion-confounded readings, we do not yet re-weight the classifier.

Classes:
    MotionState: Per-tick motion summary
    MotionProcessor: Stateful per-tick motion derivation

Thresholds here are provisional and calibrated on the first labelled-activity
sessions (stationary vs kettlebell vs walking), mirroring how movement.py
treats its empirical thresholds.
"""

from dataclasses import dataclass, asdict
import math


__all__ = [
    "MotionState",
    "MotionProcessor",
    "MOTION_THRESHOLD_MG",
    "GRAVITY_EMA_ALPHA",
    "STILL_DEBOUNCE_TICKS",
    "MOVING_DEBOUNCE_TICKS",
    "RANGE_EGRESS_SUSTAINED_TICKS",
]


# Dynamic-acceleration RMS (mg) above which a tick is a "moving" candidate.
# Resting noise after gravity removal is a few mg; fidget tens; a rep hundreds.
# Provisional — calibrate on labelled sessions.
MOTION_THRESHOLD_MG = 60.0

# EMA coefficient for the running gravity estimate. Small = slow to absorb
# orientation change, so transient movement stays in the dynamic component.
GRAVITY_EMA_ALPHA = 0.1

# Hysteresis: consecutive candidate ticks required before the state flips.
STILL_DEBOUNCE_TICKS = 2
MOVING_DEBOUNCE_TICKS = 2

# Consecutive moving ticks that count as sustained motion -> egress warning.
RANGE_EGRESS_SUSTAINED_TICKS = 4


@dataclass
class MotionState:
    """Per-tick motion summary.

    Attributes:
        motion_mag: RMS of dynamic (gravity-removed) magnitude over the tick, mg
        state: "still" or "moving" (debounced)
        confounded: True when moving — attached to the tick's mode classification
        n_samples: Number of accelerometer samples in this tick
        sustained_moving_ticks: Consecutive moving ticks (0 when still)
        range_egress_warning: True on the tick sustained motion first crosses
            the egress threshold (fires once per episode)
    """
    motion_mag: float
    state: str
    confounded: bool
    n_samples: int
    sustained_moving_ticks: int = 0
    range_egress_warning: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class MotionProcessor:
    """Stateful per-tick motion derivation from accelerometer samples.

    Feed one tick of samples (each an (x, y, z) triple in milli-g) per call to
    `update`. State (gravity estimate, gate, debounce/episode counters) persists
    across ticks.
    """

    def __init__(
        self,
        threshold_mg: float = MOTION_THRESHOLD_MG,
        gravity_alpha: float = GRAVITY_EMA_ALPHA,
        still_debounce: int = STILL_DEBOUNCE_TICKS,
        moving_debounce: int = MOVING_DEBOUNCE_TICKS,
        egress_ticks: int = RANGE_EGRESS_SUSTAINED_TICKS,
    ):
        self.threshold_mg = threshold_mg
        self.gravity_alpha = gravity_alpha
        self.still_debounce = still_debounce
        self.moving_debounce = moving_debounce
        self.egress_ticks = egress_ticks

        self._gravity: tuple[float, float, float] | None = None
        self._state = "still"
        self._candidate_run = 0  # consecutive ticks the candidate disagrees with state
        self._sustained_moving = 0  # consecutive confirmed moving ticks
        self._egress_warned = False

    def update(self, samples) -> MotionState:
        """Process one tick of accelerometer samples.

        Args:
            samples: sequence of (x, y, z) triples in milli-g.

        Returns:
            MotionState for this tick.
        """
        n = len(samples)
        if n == 0:
            # No data this tick — hold state, report zero motion.
            return MotionState(
                motion_mag=0.0,
                state=self._state,
                confounded=(self._state == "moving"),
                n_samples=0,
                sustained_moving_ticks=self._sustained_moving,
                range_egress_warning=False,
            )

        sum_sq = 0.0
        for x, y, z in samples:
            if self._gravity is None:
                self._gravity = (float(x), float(y), float(z))
            gx, gy, gz = self._gravity
            dx, dy, dz = x - gx, y - gy, z - gz
            sum_sq += dx * dx + dy * dy + dz * dz
            a = self.gravity_alpha
            self._gravity = (
                gx + a * (x - gx),
                gy + a * (y - gy),
                gz + a * (z - gz),
            )

        motion_mag = math.sqrt(sum_sq / n)
        candidate = "moving" if motion_mag > self.threshold_mg else "still"

        # Debounced state transition.
        if candidate == self._state:
            self._candidate_run = 0
        else:
            self._candidate_run += 1
            needed = self.moving_debounce if candidate == "moving" else self.still_debounce
            if self._candidate_run >= needed:
                self._state = candidate
                self._candidate_run = 0

        # Sustained-motion / egress tracking.
        warning = False
        if self._state == "moving":
            self._sustained_moving += 1
            if self._sustained_moving >= self.egress_ticks and not self._egress_warned:
                warning = True
                self._egress_warned = True
        else:
            self._sustained_moving = 0
            self._egress_warned = False

        return MotionState(
            motion_mag=motion_mag,
            state=self._state,
            confounded=(self._state == "moving"),
            n_samples=n,
            sustained_moving_ticks=self._sustained_moving,
            range_egress_warning=warning,
        )
