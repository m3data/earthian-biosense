"""Phase space trajectory tracking for EarthianBioSense.

Treats each moment as a point on a trajectory in a 3D manifold,
not a dot on a line. Movement matters.

Manifold coordinates: (entrainment, breath_rate_norm, amplitude_norm)

Note on terminology:
- ENTRAINMENT = breath-heart phase coupling (local sync, the grip)
- COHERENCE = trajectory integrity over time (global, computed from trajectory autocorrelation)

The manifold position uses entrainment as one axis. Coherence is a property
of the trajectory *through* the manifold, not a coordinate within it.
"""

from dataclasses import dataclass, field
from collections import deque
from typing import Optional
import math
import time

from .hrv import HRVMetrics
from .movement import (
    SoftModeInference,
    ModeHistory,
    compute_soft_mode_membership,
    detect_mode_with_hysteresis,
    generate_movement_annotation,
    compose_movement_aware_label,
    detect_rupture_oscillation,
    VELOCITY_THRESHOLD,
    ACCELERATION_THRESHOLD,
    SETTLED_THRESHOLD,
)


@dataclass
class PhaseState:
    """A single point in phase space with timestamp."""
    timestamp: float
    position: tuple[float, float, float]  # (entrainment, breath, amplitude)


@dataclass
class PhaseDynamics:
    """Full dynamics at a moment: position + movement + history."""
    timestamp: float

    # Position in 3D manifold
    position: tuple[float, float, float]  # (entrainment, breath, amplitude)

    # First derivative - direction of movement
    velocity: tuple[float, float, float]  # (dent/dt, dbreath/dt, damp/dt)
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

    # === Movement-preserving classification (v1.1.0) ===
    # Soft mode inference - weighted membership across modes
    soft_mode: Optional[SoftModeInference] = None

    # Movement annotation - HOW we arrived (e.g., "settling from heightened alertness")
    movement_annotation: str = ""

    # Composed label with movement context
    movement_aware_label: str = ""

    # Hysteresis state: 'unknown', 'provisional', 'established'
    mode_status: str = "unknown"

    # Dwell time in current mode (seconds)
    dwell_time: float = 0.0

    # Second derivative of mode_score (scalar), NOT 3D trajectory acceleration.
    # The 3D trajectory acceleration is stored in the `curvature` field.
    mode_score_acceleration: float = 0.0


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
    - Movement-preserving mode classification (v1.1.0)
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

        # Movement-preserving classification state (v1.1.0)
        self.mode_history: ModeHistory = ModeHistory()
        self._last_soft_inference: Optional[SoftModeInference] = None
        self._last_mode_score: float = 0.0
        self._mode_score_velocity: float = 0.0

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
        # Entrainment: already 0-1
        ent = m.entrainment

        # Breath rate: normalize ~4-20 breaths/min → 0-1
        # 4 bpm → 0, 12 bpm → 0.5, 20 bpm → 1
        if m.breath_rate is not None:
            breath = max(0.0, min(1.0, (m.breath_rate - 4) / 16))
        else:
            breath = 0.5  # default to middle if unknown

        # Amplitude: normalize 0-200ms → 0-1
        amp = min(1.0, m.amplitude / 200)

        return (ent, breath, amp)

    def _compute_dynamics(self, new_state: PhaseState, metrics: HRVMetrics) -> PhaseDynamics:
        """Compute velocity, curvature, stability from trajectory."""

        if len(self.states) < 2:
            # Not enough history - return minimal dynamics
            # Still compute soft mode for early feedback
            soft_mode = compute_soft_mode_membership(
                entrainment=metrics.entrainment,
                breath_steady=metrics.breath_steady,
                amp_norm=min(1.0, metrics.amplitude / 200),
                volatility=metrics.rr_volatility,
                previous_inference=self._last_soft_inference
            )
            self._last_soft_inference = soft_mode
            self._last_mode_score = metrics.mode_score

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
                mode_score=metrics.mode_score,
                soft_mode=soft_mode,
                movement_annotation="insufficient data",
                movement_aware_label=soft_mode.primary_mode,
                mode_status="unknown",
                dwell_time=0.0,
                mode_score_acceleration=0.0
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

        # History signature: windowed path integral (distance within rolling buffer)
        # Uses only the rolling window, not cumulative session path, to avoid
        # saturating to 1.0 within minutes (P1-B fix from RAA-EBS-001).
        if len(self.states) >= 1:
            windowed_path = sum(
                self._euclidean_distance(
                    self.states[i].position, self.states[i + 1].position
                )
                for i in range(len(self.states) - 1)
            )
            windowed_path += self._euclidean_distance(
                self.states[-1].position, new_state.position
            )
            window_time = new_state.timestamp - self.states[0].timestamp
            window_time = max(window_time, 1.0)
            history_signature = min(1.0, windowed_path / window_time / 0.5)
        else:
            history_signature = 0.0

        # Transition proximity: defer for now
        # Will need basin definitions to compute meaningfully
        transition_proximity = 0.0

        # Phase label from dynamics (not just thresholds)
        phase_label = self._infer_phase_label(
            new_state.position, velocity_magnitude, curvature, stability
        )

        # === Movement-preserving classification (v1.1.0) ===

        # Compute soft mode membership
        amp_norm = min(1.0, metrics.amplitude / 200)
        soft_mode = compute_soft_mode_membership(
            entrainment=metrics.entrainment,
            breath_steady=metrics.breath_steady,
            amp_norm=amp_norm,
            volatility=metrics.rr_volatility,
            previous_inference=self._last_soft_inference
        )

        # Detect mode with hysteresis
        detected_mode, mode_confidence, mode_meta = detect_mode_with_hysteresis(
            soft_inference=soft_mode,
            mode_history=self.mode_history,
            timestamp=new_state.timestamp
        )

        # Compute mode_score velocity and acceleration for movement annotation
        mode_score_velocity = (metrics.mode_score - self._last_mode_score) / dt1
        mode_score_accel = (mode_score_velocity - self._mode_score_velocity) / dt1

        # Generate movement annotation
        movement_annotation = generate_movement_annotation(
            velocity_magnitude=abs(mode_score_velocity),
            mode_score_acceleration=mode_score_accel,
            previous_mode=mode_meta.get('previous_mode'),
            dwell_time=mode_meta.get('dwell_time', 0.0)
        )

        # Compose movement-aware label
        movement_aware_label = compose_movement_aware_label(detected_mode, movement_annotation)

        # Update history for next iteration
        self.mode_history.append(detected_mode, mode_confidence, new_state.timestamp)
        self._last_soft_inference = soft_mode
        self._last_mode_score = metrics.mode_score
        self._mode_score_velocity = mode_score_velocity

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
            mode_score=metrics.mode_score,  # keep original for backward compat
            soft_mode=soft_mode,
            movement_annotation=movement_annotation,
            movement_aware_label=movement_aware_label,
            mode_status=mode_meta.get('state_status', 'unknown'),
            dwell_time=mode_meta.get('dwell_time', 0.0),
            mode_score_acceleration=abs(mode_score_accel)
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

        Note: 'ent' here is entrainment (breath-heart sync), not coherence.
        Coherence (trajectory integrity) would require looking at the
        trajectory history, not just current position.
        """
        ent, breath, amp = position

        # High stability + high entrainment = settled/entrained dwelling
        if stability > 0.7 and ent > 0.6:
            return "entrained dwelling"

        # High curvature = turning point, transition
        if curvature > 0.3:
            if ent > 0.5:
                return "inflection (from entrainment)"
            else:
                return "inflection (seeking)"

        # High velocity + direction
        if velocity_mag > 0.1:
            if ent > 0.5:
                return "flowing (entrained)"
            else:
                return "active transition"

        # Low everything = dwelling but where?
        if stability > 0.6:
            if ent > 0.5:
                return "settling into entrainment"
            elif ent > 0.3:
                return "neutral dwelling"
            else:
                return "alert stillness"  # v1.1.0: "vigilant" -> "alert"

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
        # Reset movement-preserving state (v1.1.0)
        self.mode_history.clear()
        self._last_soft_inference = None
        self._last_mode_score = 0.0
        self._mode_score_velocity = 0.0

    def compute_trajectory_coherence(self, lag: int = 5) -> float:
        """
        Compute COHERENCE as trajectory autocorrelation.

        This is the key insight: coherence is NOT entrainment (breath-heart sync).
        Coherence is how well the trajectory through phase space hangs together
        over time — the autocorrelation of movement patterns.

        High coherence = the system's movement has integrity, patterns persist
        Low coherence = fragmented, reactive, no trajectory continuity

        Args:
            lag: Number of states to lag for autocorrelation (default 5 = ~5 seconds)

        Returns:
            coherence: 0-1 score of trajectory integrity
        """
        if len(self.states) < lag + 3:
            return 0.0  # Insufficient data

        # Extract velocity vectors from recent trajectory
        # We're asking: does the *pattern of movement* correlate with itself?
        positions = [s.position for s in self.states]

        # Compute velocity sequence (first differences)
        velocities = []
        for i in range(1, len(positions)):
            v = tuple(positions[i][j] - positions[i-1][j] for j in range(3))
            velocities.append(v)

        if len(velocities) < lag + 2:
            return 0.0

        # Compute autocorrelation of velocity magnitudes
        # This captures: is the *intensity* of movement consistent over time?
        v_mags = [self._vector_magnitude(v) for v in velocities]

        n = len(v_mags)
        mean_v = sum(v_mags) / n
        variance = sum((x - mean_v) ** 2 for x in v_mags) / n

        if variance < 1e-10:
            # Near-zero variance = perfectly still = high coherence (dwelling)
            return 0.8

        # Autocovariance at lag
        # Use n as denominator (matching variance above) for consistent normalization.
        # Using (n - lag) inflates the result by n/(n-lag) at small buffer sizes.
        autocovariance = sum(
            (v_mags[i] - mean_v) * (v_mags[i + lag] - mean_v)
            for i in range(n - lag)
        ) / n

        autocorr = autocovariance / variance

        # Also consider direction consistency (are we moving in consistent directions?)
        # Compute cosine similarity between velocity vectors at lag
        direction_coherence = 0.0
        count = 0
        for i in range(len(velocities) - lag):
            v1 = velocities[i]
            v2 = velocities[i + lag]
            mag1 = self._vector_magnitude(v1)
            mag2 = self._vector_magnitude(v2)
            if mag1 > 1e-6 and mag2 > 1e-6:
                dot = sum(v1[j] * v2[j] for j in range(3))
                cosine = dot / (mag1 * mag2)
                direction_coherence += (cosine + 1) / 2  # Normalize to 0-1
                count += 1

        if count > 0:
            direction_coherence /= count
        else:
            direction_coherence = 0.5  # Neutral if no movement

        # Combine magnitude autocorrelation and direction consistency
        # Both matter: coherent trajectory has consistent intensity AND direction patterns
        coherence = 0.5 * max(0.0, autocorr) + 0.5 * direction_coherence

        return max(0.0, min(1.0, coherence))
