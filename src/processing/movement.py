"""Movement-preserving classification for EarthianBioSense.

This module implements soft membership, hysteresis-aware state transitions,
and movement annotation. The key insight: threshold cuts discard movement.
"Heightened alertness from settling" is fundamentally different from
"heightened alertness from threat capture" but hard thresholds give them
the same label.

Architecture adapted from semantic-climate-phase-space/src/basins.py (v0.3.0).

Classes:
    SoftModeInference: Weighted membership across modes
    HysteresisConfig: Per-mode entry/exit threshold configuration
    ModeHistory: Tracks mode sequence for hysteresis-aware detection

Functions:
    compute_soft_mode_membership: Softmax on distance to mode centroids
    detect_mode_with_hysteresis: State machine for stable transitions
    generate_movement_annotation: Human-readable movement context
    detect_rupture_oscillation: ABAB pattern detection
"""

from dataclasses import dataclass, asdict, field
from typing import Optional
import math


__all__ = [
    'SoftModeInference',
    'HysteresisConfig',
    'ModeHistory',
    'MODE_CENTROIDS',
    'DEFAULT_HYSTERESIS',
    'compute_soft_mode_membership',
    'detect_mode_with_hysteresis',
    'generate_movement_annotation',
    'detect_rupture_oscillation',
]


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SoftModeInference:
    """
    Weighted membership across modes.

    Replaces hard thresholds with probability-like weights. State changes
    are inferred from distribution shifts, not single threshold crossings.

    Attributes:
        membership: {mode_name: weight} for all modes, sum to 1.0
        primary_mode: Mode with highest membership weight
        secondary_mode: Mode with second highest weight (if within margin)
        ambiguity: 1 - (max_weight - second_weight), high = uncertain
        distribution_shift: KL divergence from previous timestep (if available)
    """
    membership: dict[str, float]
    primary_mode: str
    secondary_mode: Optional[str] = None
    ambiguity: float = 0.0
    distribution_shift: Optional[float] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class HysteresisConfig:
    """
    Per-mode entry/exit threshold configuration.

    Entry thresholds are lower than exit thresholds, making it easier
    to enter a state than to leave it. This prevents oscillation at
    boundaries and respects the principle that threshold crossing !=
    genuine state transition.

    Attributes:
        mode_name: Name of the mode this config applies to
        entry_threshold: Confidence threshold to enter this mode (lower)
        exit_threshold: Confidence threshold to exit this mode (higher)
        provisional_samples: Samples before provisional confirmation
        established_samples: Samples before established state
        entry_penalty: Confidence multiplier on new entry (< 1.0)
        settled_bonus: Confidence multiplier after settling (> 1.0)
    """
    mode_name: str
    entry_threshold: float = 0.3
    exit_threshold: float = 0.4
    provisional_samples: int = 3
    established_samples: int = 10
    entry_penalty: float = 0.7
    settled_bonus: float = 1.1

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class ModeHistory:
    """
    Tracks mode sequence for hysteresis-aware detection.

    Enables:
    - Residence time computation
    - Approach path tracking
    - Transition counting
    - Confidence modulation by history

    Attributes:
        history: List of (timestamp, mode, confidence) tuples
        max_history: Maximum entries to retain
    """
    max_history: int = 100
    history: list[tuple[float, str, float]] = field(default_factory=list)
    _current_mode: Optional[str] = field(default=None, repr=False)
    _previous_mode: Optional[str] = field(default=None, repr=False)
    _mode_entry_time: float = field(default=0.0, repr=False)
    _transition_count: int = field(default=0, repr=False)
    _state_status: str = field(default='unknown', repr=False)  # 'unknown', 'provisional', 'established'
    _provisional_since: float = field(default=0.0, repr=False)

    def append(self, mode: str, confidence: float, timestamp: float) -> None:
        """Add a mode entry to history."""
        # Track transitions
        if self._current_mode is not None and mode != self._current_mode:
            self._previous_mode = self._current_mode
            self._mode_entry_time = timestamp
            self._transition_count += 1
            self._state_status = 'unknown'

        if self._current_mode is None:
            self._mode_entry_time = timestamp

        self._current_mode = mode
        self.history.append((timestamp, mode, confidence))

        # Maintain max history
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

    def get_current_mode(self) -> Optional[str]:
        """Get the most recent mode."""
        return self._current_mode

    def get_previous_mode(self) -> Optional[str]:
        """Get the mode before the current one."""
        return self._previous_mode

    def get_dwell_time(self, current_timestamp: float) -> float:
        """Get time in current mode (seconds)."""
        if self._current_mode is None:
            return 0.0
        return current_timestamp - self._mode_entry_time

    def get_transition_count(self) -> int:
        """Get total number of mode transitions."""
        return self._transition_count

    def get_mode_sequence(self, n: Optional[int] = None) -> list[str]:
        """Get sequence of recent modes."""
        if n is None:
            return [mode for _, mode, _ in self.history]
        return [mode for _, mode, _ in self.history[-n:]]

    def get_state_status(self) -> str:
        """Get current state status ('unknown', 'provisional', 'established')."""
        return self._state_status

    def set_state_status(self, status: str, timestamp: float) -> None:
        """Set state status for hysteresis tracking."""
        if status not in ('unknown', 'provisional', 'established'):
            raise ValueError(f"Invalid state status: {status}")

        if status == 'provisional' and self._state_status != 'provisional':
            self._provisional_since = timestamp

        self._state_status = status

    def get_provisional_duration(self, current_timestamp: float) -> float:
        """Get time in provisional state (seconds)."""
        if self._state_status != 'provisional':
            return 0.0
        return current_timestamp - self._provisional_since

    def clear(self) -> None:
        """Clear all history."""
        self.history = []
        self._current_mode = None
        self._previous_mode = None
        self._mode_entry_time = 0.0
        self._transition_count = 0
        self._state_status = 'unknown'
        self._provisional_since = 0.0


# =============================================================================
# Mode Centroids and Hysteresis Configuration
# =============================================================================

# Feature space: (entrainment, breath_steady_score, amp_norm, inverse_volatility)
# Derived from reverse-engineering calm_score formula at threshold midpoints
#
# NOTE: "vigilance" renamed to "alertness" per v1.1.0 terminology update
# "Alertness" is neutral - awake and attentive.
# "Vigilance" carries threat/hypervigilance connotations.

MODE_CENTROIDS = {
    # calm_score midpoint: 0.1 (< 0.2)
    'heightened alertness': {
        'entrainment': 0.1,
        'breath_steady_score': 0.3,  # not steady
        'amp_norm': 0.2,
        'inverse_volatility': 0.2   # high volatility
    },
    # calm_score midpoint: 0.275 (0.2-0.35)
    'subtle alertness': {
        'entrainment': 0.25,
        'breath_steady_score': 0.3,
        'amp_norm': 0.35,
        'inverse_volatility': 0.4
    },
    # calm_score midpoint: 0.425 (0.35-0.5)
    'transitional': {
        'entrainment': 0.4,
        'breath_steady_score': 0.5,
        'amp_norm': 0.45,
        'inverse_volatility': 0.6
    },
    # calm_score midpoint: 0.575 (0.5-0.65)
    'settling': {
        'entrainment': 0.55,
        'breath_steady_score': 0.8,
        'amp_norm': 0.55,
        'inverse_volatility': 0.75
    },
    # calm_score midpoint: 0.725 (0.65-0.8)
    'emerging coherence': {
        'entrainment': 0.65,
        'breath_steady_score': 1.0,
        'amp_norm': 0.65,
        'inverse_volatility': 0.85
    },
    # calm_score midpoint: 0.9 (>= 0.8)
    'coherent presence': {
        'entrainment': 0.8,
        'breath_steady_score': 1.0,
        'amp_norm': 0.75,
        'inverse_volatility': 0.95
    }
}

# Feature weights (match calm_score formula weights)
FEATURE_WEIGHTS = {
    'entrainment': 0.4,
    'breath_steady_score': 0.3,
    'amp_norm': 0.2,
    'inverse_volatility': 0.1
}

# Default hysteresis configuration per mode
# NOTE: With 6 modes, uniform distribution gives ~0.167 per mode.
# Thresholds are calibrated relative to this baseline:
# - Entry: slightly above uniform (0.18-0.22)
# - Exit: higher to prevent oscillation (0.22-0.28)
DEFAULT_HYSTERESIS = {
    'heightened alertness': HysteresisConfig(
        mode_name='heightened alertness',
        entry_threshold=0.18,
        exit_threshold=0.24,
        provisional_samples=3,
        established_samples=8,
        entry_penalty=0.85,
        settled_bonus=1.05
    ),
    'subtle alertness': HysteresisConfig(
        mode_name='subtle alertness',
        entry_threshold=0.18,
        exit_threshold=0.24,
        provisional_samples=3,
        established_samples=8,
        entry_penalty=0.85,
        settled_bonus=1.05
    ),
    'transitional': HysteresisConfig(
        mode_name='transitional',
        entry_threshold=0.17,  # easiest to enter
        exit_threshold=0.22,
        provisional_samples=2,  # shorter - it's transitional
        established_samples=5,
        entry_penalty=0.9,
        settled_bonus=1.0  # no bonus for transitional
    ),
    'settling': HysteresisConfig(
        mode_name='settling',
        entry_threshold=0.19,
        exit_threshold=0.25,
        provisional_samples=3,
        established_samples=10,  # settling takes time
        entry_penalty=0.8,
        settled_bonus=1.1
    ),
    'emerging coherence': HysteresisConfig(
        mode_name='emerging coherence',
        entry_threshold=0.20,
        exit_threshold=0.26,
        provisional_samples=3,
        established_samples=10,
        entry_penalty=0.8,
        settled_bonus=1.1
    ),
    'coherent presence': HysteresisConfig(
        mode_name='coherent presence',
        entry_threshold=0.22,  # hardest to enter
        exit_threshold=0.28,
        provisional_samples=5,
        established_samples=15,  # deep state
        entry_penalty=0.75,
        settled_bonus=1.15
    )
}

# Movement annotation thresholds
VELOCITY_THRESHOLD = 0.03      # calm_score units/second (below = "still")
ACCELERATION_THRESHOLD = 0.01  # calm_score units/second^2 (above = significant)
SETTLED_THRESHOLD = 5.0        # seconds dwelling to count as "settled"
RECENT_TRANSITION_WINDOW = 3.0 # seconds to include "from {previous}" context

# Rupture oscillation detection
OSCILLATION_WINDOW = 10        # samples to look back
MIN_OSCILLATION_TRANSITIONS = 4  # minimum transitions to flag rupture


# =============================================================================
# Soft Mode Inference
# =============================================================================

def compute_soft_mode_membership(
    entrainment: float,
    breath_steady: bool,
    amp_norm: float,
    volatility: float,
    temperature: float = 1.0,
    previous_inference: Optional[SoftModeInference] = None
) -> SoftModeInference:
    """
    Compute weighted membership across all modes.

    Uses softmax on negative squared distances to mode centroids.
    This replaces hard threshold cuts with probability-like weights,
    preserving ambiguity at boundaries.

    Args:
        entrainment: Breath-heart entrainment score (0-1)
        breath_steady: Whether breath rhythm is stable
        amp_norm: Normalized HRV amplitude (0-1)
        volatility: RR volatility coefficient of variation
        temperature: Softmax temperature (lower = sharper, higher = softer)
        previous_inference: Previous SoftModeInference for distribution shift

    Returns:
        SoftModeInference with membership weights across all modes
    """
    # Build current position vector
    breath_steady_score = 1.0 if breath_steady else 0.3
    inverse_volatility = max(0.0, min(1.0, 1.0 - volatility * 5))

    position = {
        'entrainment': entrainment,
        'breath_steady_score': breath_steady_score,
        'amp_norm': amp_norm,
        'inverse_volatility': inverse_volatility
    }

    # Compute weighted squared distances to each centroid
    distances = {}
    for mode_name, centroid in MODE_CENTROIDS.items():
        dist_sq = 0.0
        for feature, weight in FEATURE_WEIGHTS.items():
            diff = position[feature] - centroid[feature]
            dist_sq += weight * (diff ** 2)
        distances[mode_name] = dist_sq

    # Apply softmax: weight_i = exp(-d_i / T) / sum(exp(-d_j / T))
    # Use negative distances so closer = higher weight
    max_neg_dist = max(-d for d in distances.values())  # numerical stability

    exp_weights = {}
    for mode_name, dist in distances.items():
        exp_weights[mode_name] = math.exp((-dist - max_neg_dist) / temperature)

    total = sum(exp_weights.values())
    membership = {k: v / total for k, v in exp_weights.items()}

    # Find primary and secondary modes
    sorted_modes = sorted(membership.items(), key=lambda x: x[1], reverse=True)
    primary_mode = sorted_modes[0][0]
    primary_weight = sorted_modes[0][1]

    secondary_mode = None
    secondary_weight = 0.0
    if len(sorted_modes) > 1:
        secondary_mode = sorted_modes[1][0]
        secondary_weight = sorted_modes[1][1]

    # Compute ambiguity: high when top two are close
    ambiguity = 1.0 - (primary_weight - secondary_weight)

    # Compute distribution shift (KL divergence) if previous inference available
    distribution_shift = None
    if previous_inference is not None:
        epsilon = 1e-10
        kl = 0.0
        for mode_name in membership:
            p = membership[mode_name]
            q = previous_inference.membership.get(mode_name, epsilon)
            if p > epsilon:
                kl += p * math.log((p + epsilon) / (q + epsilon))
        distribution_shift = kl

    return SoftModeInference(
        membership=membership,
        primary_mode=primary_mode,
        secondary_mode=secondary_mode,
        ambiguity=ambiguity,
        distribution_shift=distribution_shift
    )


# =============================================================================
# Hysteresis-Aware Detection
# =============================================================================

def detect_mode_with_hysteresis(
    soft_inference: SoftModeInference,
    mode_history: ModeHistory,
    timestamp: float
) -> tuple[str, float, dict]:
    """
    Hysteresis-aware mode detection.

    Entry thresholds are lower than exit thresholds, making it easier
    to enter a state than to leave it. This prevents oscillation at
    boundaries from noise.

    State machine:
        UNKNOWN -> PROVISIONAL (on entry) -> ESTABLISHED (after N samples)
        ESTABLISHED -> PROVISIONAL (on potential exit) -> UNKNOWN (confirmed)

    Args:
        soft_inference: Current soft mode membership
        mode_history: ModeHistory for state tracking
        timestamp: Current timestamp

    Returns:
        tuple: (mode_name, confidence, metadata)
        metadata includes: state_status, transition_type, dwell_time
    """
    proposed_mode = soft_inference.primary_mode
    raw_confidence = soft_inference.membership[proposed_mode]

    # Build metadata
    metadata = {
        'raw_confidence': raw_confidence,
        'dwell_time': 0.0,
        'previous_mode': mode_history.get_previous_mode(),
        'state_status': 'unknown',
        'transition_type': None  # 'entry', 'exit', 'sustained', None
    }

    current_mode = mode_history.get_current_mode()
    state_status = mode_history.get_state_status()
    dwell_time = mode_history.get_dwell_time(timestamp)

    metadata['dwell_time'] = dwell_time
    metadata['state_status'] = state_status

    # Get hysteresis configs
    current_config = DEFAULT_HYSTERESIS.get(
        current_mode,
        HysteresisConfig(current_mode or 'unknown')
    )
    proposed_config = DEFAULT_HYSTERESIS.get(
        proposed_mode,
        HysteresisConfig(proposed_mode)
    )

    final_mode = proposed_mode
    final_confidence = raw_confidence

    if current_mode is None:
        # First entry - use entry threshold
        if raw_confidence >= proposed_config.entry_threshold:
            final_mode = proposed_mode
            final_confidence = raw_confidence * proposed_config.entry_penalty
            mode_history.set_state_status('provisional', timestamp)
            metadata['transition_type'] = 'entry'
            metadata['state_status'] = 'provisional'
        else:
            final_mode = 'transitional'
            final_confidence = 0.3
            metadata['state_status'] = 'unknown'

    elif proposed_mode == current_mode:
        # Staying in same mode - check for establishment
        final_mode = current_mode
        final_confidence = raw_confidence

        if state_status == 'provisional':
            prov_duration = mode_history.get_provisional_duration(timestamp)
            # Convert samples to seconds (assuming ~1Hz)
            if prov_duration >= proposed_config.provisional_samples:
                mode_history.set_state_status('established', timestamp)
                metadata['state_status'] = 'established'
                metadata['transition_type'] = 'sustained'

        if state_status == 'established' and dwell_time >= current_config.established_samples:
            final_confidence = min(1.0, raw_confidence * current_config.settled_bonus)

    else:
        # Potential transition to different mode
        if state_status == 'established':
            # Established state - need to cross exit threshold to leave
            if raw_confidence < current_config.exit_threshold:
                # Can't exit yet - stay in current mode
                final_mode = current_mode
                final_confidence = current_config.exit_threshold * 0.9
                metadata['transition_type'] = None
            else:
                # Crossing exit threshold - go provisional for new mode
                final_mode = proposed_mode
                final_confidence = raw_confidence * proposed_config.entry_penalty
                mode_history.set_state_status('provisional', timestamp)
                metadata['state_status'] = 'provisional'
                metadata['transition_type'] = 'exit'
        else:
            # Provisional or unknown - easier to transition
            if raw_confidence >= proposed_config.entry_threshold:
                final_mode = proposed_mode
                final_confidence = raw_confidence * proposed_config.entry_penalty
                mode_history.set_state_status('provisional', timestamp)
                metadata['state_status'] = 'provisional'
                metadata['transition_type'] = 'entry'
            else:
                # Revert to current or transitional
                if current_mode:
                    final_mode = current_mode
                    final_confidence = raw_confidence
                else:
                    final_mode = 'transitional'
                    final_confidence = 0.3

    return (final_mode, final_confidence, metadata)


# =============================================================================
# Movement Annotation
# =============================================================================

def generate_movement_annotation(
    velocity_magnitude: Optional[float],
    acceleration_magnitude: Optional[float],
    previous_mode: Optional[str],
    dwell_time: float,
    velocity_threshold: float = VELOCITY_THRESHOLD,
    acceleration_threshold: float = ACCELERATION_THRESHOLD,
    settled_threshold: float = SETTLED_THRESHOLD
) -> str:
    """
    Generate human-readable movement annotation.

    This is the key to movement-preserving classification: the annotation
    encodes HOW you arrived at a state, not just WHERE you are.

    Args:
        velocity_magnitude: Rate of change of calm_score
        acceleration_magnitude: Second derivative of calm_score
        previous_mode: Mode transitioned from (if any)
        dwell_time: Seconds in current region
        velocity_threshold: Below this is "still"
        acceleration_threshold: Above this is significant acceleration
        settled_threshold: Dwell time above this is "settled"

    Returns:
        str: Annotation like "settled from subtle alertness"

    Examples:
        - Low velocity, high dwell, from settling -> "settled"
        - High velocity, positive acceleration -> "accelerating"
        - Low velocity, from heightened alertness -> "still from heightened alertness"
    """
    if velocity_magnitude is None:
        return "insufficient data"

    parts = []

    # Determine movement state
    is_still = velocity_magnitude < velocity_threshold
    is_settled = is_still and dwell_time >= settled_threshold

    if is_settled:
        parts.append("settled")
    elif is_still:
        parts.append("still")
    else:
        # Moving - check acceleration
        if acceleration_magnitude is not None:
            if acceleration_magnitude > acceleration_threshold:
                parts.append("accelerating")
            elif acceleration_magnitude < -acceleration_threshold:
                parts.append("decelerating")
            else:
                parts.append("moving")
        else:
            parts.append("moving")

    # Add approach context if recently transitioned
    if previous_mode is not None and dwell_time < RECENT_TRANSITION_WINDOW:
        parts.append(f"from {previous_mode}")

    return " ".join(parts) if parts else "unknown"


def compose_movement_aware_label(mode: str, movement_annotation: str) -> str:
    """
    Compose full movement-aware label.

    Args:
        mode: Current mode (e.g., "settling")
        movement_annotation: Movement context (e.g., "still from heightened alertness")

    Returns:
        str: Full label like "settling (still from heightened alertness)"
    """
    if movement_annotation in ("insufficient data", "unknown", "settled"):
        return mode
    return f"{mode} ({movement_annotation})"


# =============================================================================
# Rupture Oscillation Detection
# =============================================================================

def detect_rupture_oscillation(
    mode_history: ModeHistory,
    window: int = OSCILLATION_WINDOW,
    min_transitions: int = MIN_OSCILLATION_TRANSITIONS
) -> Optional[dict]:
    """
    Detect ABAB patterns in mode transitions.

    Rapid oscillation between two modes may indicate rupture or
    boundary instability that warrants attention.

    Args:
        mode_history: ModeHistory to analyze
        window: Number of recent entries to examine
        min_transitions: Minimum transitions to flag as rupture

    Returns:
        dict with pattern info if detected, None otherwise
        {'pattern': ['A', 'B', 'A', 'B'], 'modes': ('A', 'B'), 'count': 4}
    """
    sequence = mode_history.get_mode_sequence(window)

    if len(sequence) < min_transitions + 1:
        return None

    # Count transitions
    transitions = 0
    for i in range(1, len(sequence)):
        if sequence[i] != sequence[i-1]:
            transitions += 1

    if transitions < min_transitions:
        return None

    # Check for ABAB pattern (alternating between exactly 2 modes)
    unique_modes = set(sequence)
    if len(unique_modes) != 2:
        return None

    # Verify it's actually alternating
    modes = list(unique_modes)
    is_alternating = True
    for i in range(1, len(sequence)):
        if sequence[i] == sequence[i-1]:
            is_alternating = False
            break

    if not is_alternating:
        return None

    return {
        'pattern': sequence,
        'modes': tuple(modes),
        'transition_count': transitions,
        'onset_index': len(mode_history.history) - len(sequence)
    }
