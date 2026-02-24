"""
Threshold detection for Chimera Ecology.

Thresholds are moments when a chimera approaches the modal —
ready for potential encounter. The participant can then choose
to witness or refuse.

The threshold is the agential cut. The choice is where meaning happens.
"""

import random
from datetime import datetime, timedelta
from typing import Optional

from .types import Chimera, ChimeraState, Niche, Sanctuary


# Phase dynamics that suggest different niches
NICHE_PHASE_SIGNATURES = {
    # Grip niches: high entrainment, constrained
    Niche.GRIP_PREDATOR: {
        "entrainment_min": 0.5,
        "velocity_max": 0.1,
        "stability_min": 0.6,
        "phase_labels": ["alert stillness", "entrained dwelling"]
    },
    Niche.GRIP_PREY: {
        "entrainment_min": 0.4,
        "curvature_min": 0.2,  # High alertness
        "phase_labels": ["alert stillness", "inflection (seeking)"]
    },
    Niche.GRIP_VIGILANT: {
        "entrainment_min": 0.3,
        "stability_min": 0.5,
        "phase_labels": ["alert stillness"]
    },
    Niche.GRIP_SHELTERING: {
        "entrainment_min": 0.4,
        "stability_min": 0.7,
        "coherence_min": 0.5,
        "phase_labels": ["entrained dwelling", "coherent dwelling"]
    },

    # Flow niches: high coherence, movement
    Niche.FLOW_MIGRATORY: {
        "coherence_min": 0.5,
        "velocity_min": 0.05,
        "phase_labels": ["flowing (entrained)", "active transition"]
    },
    Niche.FLOW_DISTRIBUTED: {
        "coherence_min": 0.4,
        "phase_labels": ["neutral dwelling", "settling into entrainment"]
    },
    Niche.FLOW_SCANNING: {
        "velocity_min": 0.08,
        "curvature_min": 0.15,
        "phase_labels": ["active transition", "inflection (seeking)"]
    },
    Niche.FLOW_CALLING: {
        "entrainment_min": 0.4,
        "phase_labels": ["flowing (entrained)", "entrained dwelling"]
    },

    # Transition niches: at or approaching bifurcation
    Niche.TRANSITION_METAMORPHIC: {
        "curvature_min": 0.25,
        "stability_max": 0.4,
        "phase_labels": ["inflection (seeking)", "inflection (from entrainment)"]
    },
    Niche.TRANSITION_LIMINAL: {
        "curvature_min": 0.2,
        "phase_labels": ["active transition", "inflection (seeking)", "inflection (from entrainment)"]
    },
    Niche.TRANSITION_TRICKSTER: {
        "velocity_min": 0.1,
        "curvature_min": 0.2,
        "phase_labels": ["active transition", "inflection (seeking)"]
    },

    # Settling niches: in basin, stability
    Niche.SETTLING_DORMANT: {
        "velocity_max": 0.05,
        "stability_min": 0.7,
        "phase_labels": ["neutral dwelling", "alert stillness"]
    },
    Niche.SETTLING_ROOTED: {
        "stability_min": 0.6,
        "coherence_min": 0.4,
        "phase_labels": ["coherent dwelling", "entrained dwelling", "neutral dwelling"]
    },
    Niche.SETTLING_DAWN: {
        "stability_min": 0.5,
        "phase_labels": ["settling into entrainment", "rhythmic settling"]
    },
    Niche.SETTLING_ELDER: {
        "coherence_min": 0.5,
        "stability_min": 0.6,
        "phase_labels": ["coherent dwelling", "entrained dwelling"]
    },
}


def detect_threshold(
    phase_dynamics: dict,
    hrv_metrics: dict,
    sanctuary: Sanctuary,
    cooldown_minutes: int = 5
) -> Optional[Chimera]:
    """
    Detect if a chimera is approaching the threshold modal.

    Conditions that might trigger:
    - Phase label transition
    - Curvature spike (trajectory inflection)
    - Stability drop then recovery (perturbation response)
    - Niche match between current ANS state and sanctuary dweller
    - Time since last encounter
    - Ecological pressure

    Args:
        phase_dynamics: Current phase dynamics from EBS
        hrv_metrics: Current HRV metrics from EBS
        sanctuary: The sanctuary ecology
        cooldown_minutes: Minimum time between threshold events

    Returns:
        Candidate chimera if threshold detected, None otherwise
    """
    # Check cooldown
    if sanctuary.threshold_history:
        last_threshold = sanctuary.threshold_history[-1]
        try:
            last_ts = datetime.fromisoformat(last_threshold.ts)
            if datetime.now() - last_ts < timedelta(minutes=cooldown_minutes):
                return None  # Too soon
        except ValueError:
            pass

    # Extract phase values
    entrainment = hrv_metrics.get("entrainment", 0)
    velocity = phase_dynamics.get("velocity_mag", 0)
    curvature = phase_dynamics.get("curvature", 0)
    stability = phase_dynamics.get("stability", 0.5)
    coherence = phase_dynamics.get("coherence", 0)
    phase_label = phase_dynamics.get("phase_label", "")

    # Find matching niches based on current phase dynamics
    matching_niches = []
    match_scores = {}

    for niche, signature in NICHE_PHASE_SIGNATURES.items():
        score = 0
        matches = 0
        total = 0

        # Check each criterion
        if "entrainment_min" in signature:
            total += 1
            if entrainment >= signature["entrainment_min"]:
                matches += 1
                score += entrainment

        if "velocity_min" in signature:
            total += 1
            if velocity >= signature["velocity_min"]:
                matches += 1
                score += velocity

        if "velocity_max" in signature:
            total += 1
            if velocity <= signature["velocity_max"]:
                matches += 1
                score += 1 - velocity

        if "curvature_min" in signature:
            total += 1
            if curvature >= signature["curvature_min"]:
                matches += 1
                score += curvature

        if "stability_min" in signature:
            total += 1
            if stability >= signature["stability_min"]:
                matches += 1
                score += stability

        if "stability_max" in signature:
            total += 1
            if stability <= signature["stability_max"]:
                matches += 1
                score += 1 - stability

        if "coherence_min" in signature:
            total += 1
            if coherence >= signature["coherence_min"]:
                matches += 1
                score += coherence

        if "phase_labels" in signature:
            total += 1
            if phase_label in signature["phase_labels"]:
                matches += 1
                score += 1

        # Require at least half of criteria to match
        if total > 0 and matches >= total / 2:
            matching_niches.append(niche)
            match_scores[niche] = score / total

    if not matching_niches:
        return None

    # Find chimeras in matching niches
    candidates = []
    for chimera in sanctuary.sanctuary_chimeras:
        if chimera.niche in matching_niches:
            # Weight by niche match score and time since last encounter
            weight = match_scores.get(chimera.niche, 0.5)

            # Boost chimeras that haven't been seen recently
            if chimera.last_encountered_ts:
                try:
                    last_enc = datetime.fromisoformat(chimera.last_encountered_ts)
                    days_since = (datetime.now() - last_enc).days
                    weight += min(days_since * 0.1, 0.5)
                except ValueError:
                    pass
            else:
                weight += 0.3  # Never witnessed bonus

            candidates.append((chimera, weight))

    if not candidates:
        # No chimeras match — maybe crystallize a new one?
        # This is a threshold for a chimera that doesn't exist yet
        return None

    # Probabilistic selection weighted by match score
    total_weight = sum(w for _, w in candidates)
    r = random.random() * total_weight
    cumulative = 0

    for chimera, weight in candidates:
        cumulative += weight
        if r <= cumulative:
            # Update state
            chimera.state = ChimeraState.THRESHOLD
            return chimera

    # Fallback
    selected = candidates[0][0]
    selected.state = ChimeraState.THRESHOLD
    return selected


def should_trigger_threshold(
    phase_dynamics: dict,
    hrv_metrics: dict,
    trigger_sensitivity: float = 0.5
) -> bool:
    """
    Check if current phase dynamics warrant checking for threshold.

    This is a pre-filter before the full detect_threshold() call.
    Helps avoid unnecessary computation during stable periods.

    Args:
        phase_dynamics: Current phase dynamics
        hrv_metrics: Current HRV metrics
        trigger_sensitivity: 0-1, higher = more triggers

    Returns:
        True if threshold detection should run
    """
    # Trigger on phase label transitions
    phase_label = phase_dynamics.get("phase_label", "")
    transition_labels = [
        "inflection (seeking)",
        "inflection (from entrainment)",
        "active transition",
        "settling into entrainment"
    ]
    if phase_label in transition_labels:
        return True

    # Trigger on curvature spikes
    curvature = phase_dynamics.get("curvature", 0)
    if curvature > 0.3:
        return True

    # Trigger on stability recovery after drop
    stability = phase_dynamics.get("stability", 0.5)
    velocity = phase_dynamics.get("velocity_mag", 0)
    if stability > 0.7 and velocity < 0.05:
        # High stability, low movement — dwelling
        if random.random() < trigger_sensitivity * 0.3:
            return True

    # Random trigger based on sensitivity
    if random.random() < trigger_sensitivity * 0.05:
        return True

    return False


def get_threshold_context(
    phase_dynamics: dict,
    hrv_metrics: dict
) -> dict:
    """
    Build context dict for threshold encounter logging.
    """
    return {
        "phase_label": phase_dynamics.get("phase_label", ""),
        "entrainment": hrv_metrics.get("entrainment", 0),
        "coherence": phase_dynamics.get("coherence", 0),
        "stability": phase_dynamics.get("stability", 0),
        "velocity_mag": phase_dynamics.get("velocity_mag", 0),
        "curvature": phase_dynamics.get("curvature", 0),
        "position": phase_dynamics.get("position", []),
    }
