"""
Encounter handling for Chimera Ecology.

Encounters are the agential cut — the moment where human and
measurement become intra-active. The participant chooses to
witness or refuse, and both choices are valid.

Witnessed chimeras become kin you've met.
Unwitnessed chimeras stay wild.
Neither is more true.
"""

from datetime import datetime, timedelta
from typing import Optional

from .types import Chimera, ChimeraState, Encounter, Sanctuary


def on_witnessed(
    chimera: Chimera,
    sanctuary: Sanctuary,
    phase_context: Optional[dict] = None
) -> Encounter:
    """
    Handle a witnessed encounter.

    What happens when participant says 'yes' at threshold:
    - State → "encountered"
    - Timestamp recorded
    - Chimera stabilizes (drift rate decreases)
    - May influence niche pressure on others
    - Becomes kin you've met

    Args:
        chimera: The chimera that was witnessed
        sanctuary: The sanctuary ecology
        phase_context: Phase dynamics at the moment of encounter

    Returns:
        The encounter record
    """
    now = datetime.now().isoformat()

    # Update chimera state
    chimera.state = ChimeraState.ENCOUNTERED
    chimera.last_encountered_ts = now
    chimera.encounter_count += 1

    # Stabilize: reduce drift rate
    chimera.drift_rate *= 0.7  # 30% reduction per witness
    chimera.drift_rate = max(chimera.drift_rate, 0.1)  # Floor at 0.1

    # Update species encounter counts
    for species_name in chimera.components:
        species = sanctuary.species_by_name(species_name)
        if species:
            species.encounter_count += 1
            if chimera.id not in species.witnessed_in_chimeras:
                species.witnessed_in_chimeras.append(chimera.id)

    # Create encounter record
    encounter = Encounter(
        ts=now,
        chimera_id=chimera.id,
        witnessed=True,
        phase_context=phase_context or {}
    )

    sanctuary.encounter_history.append(encounter)
    sanctuary.threshold_history.append(encounter)

    return encounter


def on_refused(
    chimera: Chimera,
    sanctuary: Sanctuary,
    phase_context: Optional[dict] = None
) -> Encounter:
    """
    Handle a refused encounter.

    What happens when participant says 'not now' at threshold:
    - State returns to "sanctuary"
    - No encounter logged (but threshold event logged)
    - Chimera continues drifting, possibly faster
    - Schrödinger's raven-whale preserved
    - Refusal honored as sanctuary-tending

    Args:
        chimera: The chimera that was refused
        sanctuary: The sanctuary ecology
        phase_context: Phase dynamics at the moment of refusal

    Returns:
        The threshold record (not an encounter)
    """
    now = datetime.now().isoformat()

    # Return to sanctuary
    chimera.state = ChimeraState.SANCTUARY

    # Increase drift rate slightly — it continues evolving
    chimera.drift_rate *= 1.1
    chimera.drift_rate = min(chimera.drift_rate, 2.0)  # Cap at 2.0

    # Create threshold record (witnessed=False)
    threshold_event = Encounter(
        ts=now,
        chimera_id=chimera.id,
        witnessed=False,
        phase_context=phase_context or {}
    )

    # Only log to threshold history, not encounter history
    sanctuary.threshold_history.append(threshold_event)

    return threshold_event


def maybe_go_feral(
    chimera: Chimera,
    feral_threshold_days: int = 30
) -> bool:
    """
    Check if a witnessed chimera should return to the wild.

    Witnessed chimeras may go feral if not encountered for a long time:
    - State → "feral"
    - Drift rate increases again
    - May become something else before next threshold
    - The kookaburra-banksia you met may not be what returns

    Args:
        chimera: The chimera to check
        feral_threshold_days: Days without encounter before going feral

    Returns:
        True if chimera went feral, False otherwise
    """
    if chimera.state != ChimeraState.ENCOUNTERED:
        return False

    if not chimera.last_encountered_ts:
        return False

    try:
        last_encounter = datetime.fromisoformat(chimera.last_encountered_ts)
        days_since = (datetime.now() - last_encounter).days

        if days_since >= feral_threshold_days:
            chimera.state = ChimeraState.FERAL
            chimera.drift_rate = 1.0  # Reset drift rate
            return True

    except ValueError:
        pass

    return False


def check_all_for_feral(
    sanctuary: Sanctuary,
    feral_threshold_days: int = 30
) -> list[str]:
    """
    Check all witnessed chimeras for potential feral transition.

    Returns:
        List of chimera IDs that went feral
    """
    feral_ids = []

    for chimera in sanctuary.witnessed_chimeras:
        if maybe_go_feral(chimera, feral_threshold_days):
            feral_ids.append(chimera.id)

    return feral_ids


def get_encounter_summary(sanctuary: Sanctuary) -> dict:
    """
    Get a summary of encounter history.
    """
    total_thresholds = len(sanctuary.threshold_history)
    total_witnessed = len(sanctuary.encounter_history)
    total_refused = total_thresholds - total_witnessed

    # Witness rate
    witness_rate = total_witnessed / total_thresholds if total_thresholds > 0 else 0

    # Most witnessed chimeras
    chimera_counts = {}
    for encounter in sanctuary.encounter_history:
        chimera_counts[encounter.chimera_id] = chimera_counts.get(encounter.chimera_id, 0) + 1

    most_witnessed = sorted(chimera_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    # Recent encounters
    recent = sanctuary.encounter_history[-5:] if sanctuary.encounter_history else []

    return {
        "total_thresholds": total_thresholds,
        "total_witnessed": total_witnessed,
        "total_refused": total_refused,
        "witness_rate": witness_rate,
        "most_witnessed": most_witnessed,
        "recent_encounters": [
            {
                "chimera_id": e.chimera_id,
                "ts": e.ts,
                "phase_label": e.phase_context.get("phase_label", "")
            }
            for e in recent
        ]
    }
