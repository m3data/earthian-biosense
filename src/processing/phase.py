"""Phase space trajectory tracking for EarthianBioSense.

Treats each moment as a point on a trajectory in a 3D manifold,
not a dot on a line. Movement matters.

Manifold coordinates: (coherence, breath_rate_norm, amplitude_norm)
"""

from dataclasses import dataclass, field
from collections import deque
import math
import time

from .hrv import HRVMetrics


@dataclass
class PhaseState:
    """A single point in phase space with timestamp."""
    timestamp: float
    position: tuple[float, float, float]  # (coherence, breath, amplitude)


@dataclass
class PhaseDynamics:
    """Full dynamics at a moment: position + movement + history."""
    timestamp: float

    # Position in 3D manifold
    position: tuple[float, float, float]  # (coherence, breath, amplitude)

    # First derivative - direction of movement
    velocity: tuple[float, float, float]  # (dcoh/dt, dbreath/dt, damp/dt)
    velocity_magnitude: float

    # Second derivative magnitude - quality of movement
    curvature: float

    # Derived qualities
    stability: float              # low curvature & low velocity → high stability
    transition_proximity: float   # placeholder - defer until basins emerge from data
    history_signature: float      # path integral over window

    # Labels (backward compat)
    phase_label: str
    mode_score: float  # collapsed scalar for terminal UI


# Default/empty dynamics for cold start
EMPTY_DYNAMICS = PhaseDynamics(
    timestamp=0,
    position=(0.0, 0.0, 0.0),
    velocity=(0.0, 0.0, 0.0),
    velocity_magnitude=0.0,
    curvature=0.0,
    stability=0.0,
    transition_proximity=0.0,
    history_signature=0.0,
    phase_label="initializing",
    mode_score=0.0
)


class PhaseTrajectory:
    """Rolling buffer of PhaseStates with dynamics computation.

    Tracks trajectory through 3D manifold and computes:
    - Velocity (finite difference)
    - Curvature (second derivative magnitude)
    - Stability (inverse of movement intensity)
    - History signature (path integral)
    """

    def __init__(self, window_size: int = 30):
        """Initialize trajectory buffer.

        Args:
            window_size: Number of states to keep. At ~1 state/second,
                        30 = ~30 seconds of trajectory history.
        """
        self.states: deque[PhaseState] = deque(maxlen=window_size)
        self.cumulative_path_length: float = 0.0
        self._last_velocity: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def append(self, metrics: HRVMetrics, timestamp: float | None = None) -> PhaseDynamics:
        """Add new state from HRV metrics, compute dynamics.

        Args:
            metrics: Current HRV metrics snapshot
            timestamp: Optional timestamp (uses time.time() if not provided)

        Returns:
            PhaseDynamics with full trajectory analysis
        """
        if timestamp is None:
            timestamp = time.time()

        position = self._metrics_to_position(metrics)
        new_state = PhaseState(timestamp, position)

        # Compute dynamics before adding (need previous states)
        dynamics = self._compute_dynamics(new_state, metrics)

        # Update path integral
        if len(self.states) > 0:
            prev = self.states[-1]
            step_distance = self._euclidean_distance(prev.position, position)
            self.cumulative_path_length += step_distance

        self.states.append(new_state)

        return dynamics

    def _metrics_to_position(self, m: HRVMetrics) -> tuple[float, float, float]:
        """Map HRV metrics to manifold coordinates (all normalized 0-1)."""
        # Coherence: already 0-1
        coh = m.coherence

        # Breath rate: normalize ~4-20 breaths/min → 0-1
        # 4 bpm → 0, 12 bpm → 0.5, 20 bpm → 1
        if m.breath_rate is not None:
            breath = max(0.0, min(1.0, (m.breath_rate - 4) / 16))
        else:
            breath = 0.5  # default to middle if unknown

        # Amplitude: normalize 0-200ms → 0-1
        amp = min(1.0, m.amplitude / 200)

        return (coh, breath, amp)

    def _compute_dynamics(self, new_state: PhaseState, metrics: HRVMetrics) -> PhaseDynamics:
        """Compute velocity, curvature, stability from trajectory."""

        if len(self.states) < 2:
            # Not enough history - return minimal dynamics
            return PhaseDynamics(
                timestamp=new_state.timestamp,
                position=new_state.position,
                velocity=(0.0, 0.0, 0.0),
                velocity_magnitude=0.0,
                curvature=0.0,
                stability=0.5,  # neutral
                transition_proximity=0.0,
                history_signature=0.0,
                phase_label="warming up",
                mode_score=metrics.mode_score
            )

        # Get recent states for derivative computation
        prev = self.states[-1]
        prev_prev = self.states[-2] if len(self.states) >= 2 else prev

        # Time deltas
        dt1 = new_state.timestamp - prev.timestamp
        dt2 = prev.timestamp - prev_prev.timestamp

        # Avoid division by zero
        dt1 = max(dt1, 0.001)
        dt2 = max(dt2, 0.001)

        # Velocity: finite difference (first derivative)
        velocity = tuple(
            (new_state.position[i] - prev.position[i]) / dt1
            for i in range(3)
        )
        velocity_magnitude = self._vector_magnitude(velocity)

        # Previous velocity for curvature
        prev_velocity = tuple(
            (prev.position[i] - prev_prev.position[i]) / dt2
            for i in range(3)
        )

        # Curvature: magnitude of acceleration (second derivative)
        # Using average dt for acceleration computation
        dt_avg = (dt1 + dt2) / 2
        acceleration = tuple(
            (velocity[i] - prev_velocity[i]) / dt_avg
            for i in range(3)
        )
        curvature = self._vector_magnitude(acceleration)

        # Store for next iteration
        self._last_velocity = velocity

        # Stability: inverse relationship with movement intensity
        # High velocity + high curvature = low stability
        movement_intensity = velocity_magnitude + curvature * 0.5
        stability = 1.0 / (1.0 + movement_intensity * 2)
        stability = max(0.0, min(1.0, stability))

        # History signature: path integral normalized by window time
        window_time = new_state.timestamp - self.states[0].timestamp if self.states else 1.0
        window_time = max(window_time, 1.0)
        history_signature = self.cumulative_path_length / window_time
        # Normalize to roughly 0-1 range (empirical scaling)
        history_signature = min(1.0, history_signature / 0.5)

        # Transition proximity: defer for now
        # Will need basin definitions to compute meaningfully
        transition_proximity = 0.0

        # Phase label from dynamics (not just thresholds)
        phase_label = self._infer_phase_label(
            new_state.position, velocity_magnitude, curvature, stability
        )

        return PhaseDynamics(
            timestamp=new_state.timestamp,
            position=new_state.position,
            velocity=velocity,
            velocity_magnitude=velocity_magnitude,
            curvature=curvature,
            stability=stability,
            transition_proximity=transition_proximity,
            history_signature=history_signature,
            phase_label=phase_label,
            mode_score=metrics.mode_score  # keep original for backward compat
        )

    def _infer_phase_label(
        self,
        position: tuple[float, float, float],
        velocity_mag: float,
        curvature: float,
        stability: float
    ) -> str:
        """Infer phase label from dynamics, not just position thresholds.

        This is still provisional - letting patterns emerge rather than
        imposing ontology.
        """
        coh, breath, amp = position

        # High stability + high coherence = settled coherence
        if stability > 0.7 and coh > 0.6:
            return "coherent dwelling"

        # High curvature = turning point, transition
        if curvature > 0.3:
            if coh > 0.5:
                return "inflection (from coherence)"
            else:
                return "inflection (seeking)"

        # High velocity + direction toward coherence
        if velocity_mag > 0.1:
            # Check if moving toward higher coherence
            # (would need velocity[0] but keeping simple for now)
            if coh > 0.5:
                return "flowing coherence"
            else:
                return "active transition"

        # Low everything = dwelling but where?
        if stability > 0.6:
            if coh > 0.5:
                return "settling into coherence"
            elif coh > 0.3:
                return "neutral dwelling"
            else:
                return "vigilant stillness"

        # Default: transitional
        return "transitional"

    @staticmethod
    def _euclidean_distance(p1: tuple[float, ...], p2: tuple[float, ...]) -> float:
        """Compute Euclidean distance between two points."""
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(p1, p2)))

    @staticmethod
    def _vector_magnitude(v: tuple[float, ...]) -> float:
        """Compute magnitude of a vector."""
        return math.sqrt(sum(x ** 2 for x in v))

    def get_recent_trajectory(self, n: int = 10) -> list[PhaseState]:
        """Get the n most recent states for visualization/analysis."""
        return list(self.states)[-n:]

    def reset(self):
        """Clear trajectory buffer and path integral."""
        self.states.clear()
        self.cumulative_path_length = 0.0
        self._last_velocity = (0.0, 0.0, 0.0)
