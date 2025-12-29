"""
Evolutionary Algorithm operators for Chimera Ecology.

These are EA (not GA) operators — selecting for viable coexistence
and diversity, not fitness or optimization.

Key principle: The sanctuary isn't optimizing toward ideal chimeras.
It's evolving toward a living ecology of them.
"""

import random
from datetime import datetime, timedelta
from typing import Optional

from .types import Chimera, ChimeraState, Niche, Sanctuary, Species


def drift(
    chimera: Chimera,
    sanctuary: Sanctuary,
    time_delta_hours: float
) -> bool:
    """
    Apply drift to a chimera based on unwatched time.

    Drift is a random walk through component-space:
    - Small probability of component swap
    - Weight redistribution
    - Influenced by what else lives in sanctuary

    Args:
        chimera: The chimera to drift
        sanctuary: The sanctuary ecology (for species vocabulary)
        time_delta_hours: Hours since last evolution

    Returns:
        True if chimera was modified, False otherwise
    """
    # Drift rate depends on witness history
    # Never-witnessed chimeras drift faster
    # Recently-witnessed chimeras drift slower
    base_drift_prob = 0.1  # 10% chance per hour of some drift

    if not chimera.is_witnessed:
        drift_multiplier = 1.5  # Faster drift
    elif chimera.state == ChimeraState.FERAL:
        drift_multiplier = 1.2  # Returned to wild, drifting again
    else:
        # Witnessed chimeras drift slower based on encounter count
        drift_multiplier = 1.0 / (1.0 + chimera.encounter_count * 0.3)

    effective_prob = base_drift_prob * drift_multiplier * time_delta_hours
    effective_prob = min(effective_prob, 0.8)  # Cap at 80%

    if random.random() > effective_prob:
        return False  # No drift this time

    modified = False

    # Possible drift operations:

    # 1. Weight shift (most common)
    if random.random() < 0.6 and len(chimera.weights) > 1:
        # Shift weight between components
        i, j = random.sample(range(len(chimera.weights)), 2)
        shift = random.uniform(0.05, 0.15) * random.choice([-1, 1])

        chimera.weights[i] += shift
        chimera.weights[j] -= shift

        # Clamp and renormalize
        chimera.weights = [max(0.05, w) for w in chimera.weights]
        total = sum(chimera.weights)
        chimera.weights = [w / total for w in chimera.weights]
        modified = True

    # 2. Component swap (less common)
    if random.random() < 0.2 and sanctuary.species_vocabulary:
        # Find species in same niche or family
        current_components = set(chimera.components)

        # Candidates: same niche affinity or same family
        candidates = []
        for s in sanctuary.species_vocabulary:
            if s.scientific_name in current_components:
                continue
            if chimera.niche and chimera.niche in s.niche_affinities:
                candidates.append(s)
            elif any(
                existing.family == s.family
                for sci_name in current_components
                for existing in sanctuary.species_vocabulary
                if existing.scientific_name == sci_name
            ):
                candidates.append(s)

        if candidates:
            # Swap the weakest component
            min_idx = chimera.weights.index(min(chimera.weights))
            new_species = random.choice(candidates)
            chimera.components[min_idx] = new_species.scientific_name
            modified = True

    # 3. Niche drift (rare)
    if random.random() < 0.05:
        # Drift toward adjacent niche
        adjacent = _get_adjacent_niches(chimera.niche)
        if adjacent:
            chimera.niche = random.choice(adjacent)
            modified = True

    if modified:
        chimera.last_drift_ts = datetime.now().isoformat()

    return modified


def _get_adjacent_niches(niche: Optional[Niche]) -> list[Niche]:
    """Get niches that are 'adjacent' to the given niche."""
    if not niche:
        return list(Niche)

    # Define adjacency based on niche categories
    adjacency = {
        # Grip niches are adjacent to each other and to transition
        Niche.GRIP_PREDATOR: [Niche.GRIP_VIGILANT, Niche.FLOW_SCANNING, Niche.TRANSITION_LIMINAL],
        Niche.GRIP_PREY: [Niche.GRIP_VIGILANT, Niche.GRIP_SHELTERING, Niche.SETTLING_DORMANT],
        Niche.GRIP_VIGILANT: [Niche.GRIP_PREDATOR, Niche.GRIP_PREY, Niche.GRIP_SHELTERING],
        Niche.GRIP_SHELTERING: [Niche.GRIP_VIGILANT, Niche.SETTLING_ROOTED, Niche.SETTLING_ELDER],

        # Flow niches are adjacent to each other
        Niche.FLOW_MIGRATORY: [Niche.FLOW_SCANNING, Niche.TRANSITION_METAMORPHIC],
        Niche.FLOW_DISTRIBUTED: [Niche.FLOW_MIGRATORY, Niche.SETTLING_ROOTED],
        Niche.FLOW_SCANNING: [Niche.GRIP_PREDATOR, Niche.FLOW_MIGRATORY],
        Niche.FLOW_CALLING: [Niche.FLOW_SCANNING, Niche.SETTLING_DAWN],

        # Transition niches connect grip/flow to settling
        Niche.TRANSITION_METAMORPHIC: [Niche.FLOW_MIGRATORY, Niche.SETTLING_DORMANT],
        Niche.TRANSITION_LIMINAL: [Niche.GRIP_PREDATOR, Niche.TRANSITION_TRICKSTER],
        Niche.TRANSITION_TRICKSTER: [Niche.TRANSITION_LIMINAL, Niche.FLOW_CALLING],

        # Settling niches are adjacent to each other
        Niche.SETTLING_DORMANT: [Niche.SETTLING_ROOTED, Niche.GRIP_PREY],
        Niche.SETTLING_ROOTED: [Niche.SETTLING_DORMANT, Niche.SETTLING_ELDER, Niche.GRIP_SHELTERING],
        Niche.SETTLING_DAWN: [Niche.SETTLING_ROOTED, Niche.FLOW_CALLING],
        Niche.SETTLING_ELDER: [Niche.SETTLING_ROOTED, Niche.GRIP_SHELTERING],
    }

    return adjacency.get(niche, [])


def apply_niche_pressure(sanctuary: Sanctuary) -> list[str]:
    """
    Apply ecological niche pressure to the sanctuary.

    This is selection for viable coexistence, not fitness:
    - Chimeras in same niche compete (one may go dormant)
    - Empty niches attract drift toward them
    - Witnessed apex patterns cast shadow (suppress similar unwitnessed)
    - Diversity is selected FOR, not against

    Returns:
        List of events that occurred (for logging)
    """
    events = []

    # Count chimeras per niche
    niche_counts = {}
    for c in sanctuary.chimeras:
        if c.niche:
            niche_counts.setdefault(c.niche, []).append(c)

    # 1. Competition in crowded niches
    for niche, chimeras in niche_counts.items():
        if len(chimeras) > 2:  # More than 2 in same niche
            # The weakest (least witnessed, most recently born) may go dormant
            # But only unwitnessed ones can be suppressed
            unwitnessed = [c for c in chimeras if not c.is_witnessed]
            if unwitnessed:
                # Sort by birth time (newest first)
                unwitnessed.sort(key=lambda c: c.birth_ts, reverse=True)
                # Suppress the newest unwitnessed
                victim = unwitnessed[0]
                victim.state = ChimeraState.SANCTUARY
                victim.drift_rate *= 1.5  # Increase drift, may speciate away
                events.append(f"Niche pressure: {victim.id} suppressed in {niche.value}")

    # 2. Witnessed chimeras cast shadow
    for c in sanctuary.witnessed_chimeras:
        if c.niche:
            # Find unwitnessed chimeras in same niche with similar components
            for other in sanctuary.sanctuary_chimeras:
                if other.niche == c.niche and other.id != c.id:
                    # Check component overlap
                    overlap = set(c.components) & set(other.components)
                    if len(overlap) >= 2:  # High overlap
                        # Push toward adjacent niche
                        adjacent = _get_adjacent_niches(other.niche)
                        if adjacent:
                            old_niche = other.niche
                            other.niche = random.choice(adjacent)
                            events.append(
                                f"Shadow effect: {other.id} pushed from {old_niche.value} to {other.niche.value}"
                            )

    # 3. Empty niches attract drift
    empty_niches = sanctuary.empty_niches
    if empty_niches:
        # Find chimeras that could drift toward empty niches
        for c in sanctuary.sanctuary_chimeras:
            if random.random() < 0.1:  # 10% chance
                # Check if any component has affinity for empty niche
                for species_name in c.components:
                    species = sanctuary.species_by_name(species_name)
                    if species:
                        for empty_niche in empty_niches:
                            if empty_niche in species.niche_affinities:
                                old_niche = c.niche
                                c.niche = empty_niche
                                events.append(
                                    f"Empty niche attraction: {c.id} drifted from {old_niche.value if old_niche else 'none'} to {empty_niche.value}"
                                )
                                break
                        break

    return events


def maybe_speciate(
    chimera: Chimera,
    sanctuary: Sanctuary
) -> Optional[Chimera]:
    """
    Check if a chimera should speciate (bud off a new chimera).

    Speciation happens when:
    - Chimera has drifted significantly
    - Niche is crowded
    - Enough time has passed

    Returns:
        New chimera if speciation occurred, None otherwise
    """
    # Base probability
    speciation_prob = 0.05  # 5% base

    # Increase if niche is crowded
    if chimera.niche:
        niche_count = sum(1 for c in sanctuary.chimeras if c.niche == chimera.niche)
        if niche_count > 2:
            speciation_prob += 0.1 * (niche_count - 2)

    # Increase based on drift history
    if chimera.last_drift_ts:
        try:
            last_drift = datetime.fromisoformat(chimera.last_drift_ts)
            drift_age = (datetime.now() - last_drift).total_seconds() / 3600
            if drift_age < 24:  # Recent drift
                speciation_prob += 0.05
        except ValueError:
            pass

    # Never-witnessed chimeras speciate more easily
    if not chimera.is_witnessed:
        speciation_prob *= 1.5

    # Cap probability
    speciation_prob = min(speciation_prob, 0.4)

    if random.random() > speciation_prob:
        return None

    # Speciation: create new chimera with modified components
    new_chimera = Chimera(
        components=list(chimera.components),
        weights=list(chimera.weights),
        lineage=chimera.lineage + [chimera.id],
        niche=chimera.niche,
        state=ChimeraState.SANCTUARY,
        drift_rate=chimera.drift_rate * 1.2
    )

    # Modify the new chimera slightly
    if len(new_chimera.weights) > 1:
        # Shuffle weights
        random.shuffle(new_chimera.weights)

    # Maybe swap a component
    if sanctuary.species_vocabulary and random.random() < 0.5:
        available = [
            s for s in sanctuary.species_vocabulary
            if s.scientific_name not in new_chimera.components
        ]
        if available:
            new_species = random.choice(available)
            swap_idx = random.randint(0, len(new_chimera.components) - 1)
            new_chimera.components[swap_idx] = new_species.scientific_name

    # Maybe shift niche
    adjacent = _get_adjacent_niches(new_chimera.niche)
    if adjacent and random.random() < 0.3:
        new_chimera.niche = random.choice(adjacent)

    sanctuary.chimeras.append(new_chimera)
    return new_chimera


def evolve_sanctuary(
    sanctuary: Sanctuary,
    time_delta_hours: float
) -> dict:
    """
    Run a full evolution cycle on the sanctuary.

    This is called between sessions or periodically to let the
    sanctuary ecology evolve.

    Returns:
        Dictionary with evolution events and statistics
    """
    events = []
    stats = {
        "chimeras_drifted": 0,
        "speciation_events": 0,
        "niche_pressure_events": 0
    }

    # 1. Apply drift to all sanctuary chimeras
    for chimera in sanctuary.sanctuary_chimeras:
        if drift(chimera, sanctuary, time_delta_hours):
            stats["chimeras_drifted"] += 1
            events.append(f"Drift: {chimera.id}")

    # 2. Apply niche pressure
    pressure_events = apply_niche_pressure(sanctuary)
    events.extend(pressure_events)
    stats["niche_pressure_events"] = len(pressure_events)

    # 3. Check for speciation
    # Copy list to avoid modification during iteration
    for chimera in list(sanctuary.sanctuary_chimeras):
        new_chimera = maybe_speciate(chimera, sanctuary)
        if new_chimera:
            stats["speciation_events"] += 1
            events.append(f"Speciation: {chimera.id} -> {new_chimera.id}")

    # Update timestamp
    sanctuary.last_evolution_ts = datetime.now().isoformat()

    return {
        "events": events,
        "stats": stats,
        "timestamp": sanctuary.last_evolution_ts
    }
