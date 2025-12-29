"""
Vocabulary loader for Chimera Ecology.

Loads seed vocabulary from JSON (exported from species-browser)
and infers niche affinities from relational notes.
"""

import json
import re
from pathlib import Path
from typing import Optional

from .types import Species, Country, Niche, Sanctuary


# Keywords that suggest niche affinities
# These are patterns found in relational notes that hint at ecological roles
NICHE_KEYWORDS = {
    Niche.GRIP_PREDATOR: [
        "predator", "hunter", "hunting", "apex", "vigilance", "watching",
        "killed", "kills", "shark", "eagle", "hawk"
    ],
    Niche.GRIP_PREY: [
        "hiding", "hidden", "prey", "alert", "scurrying", "startled"
    ],
    Niche.GRIP_VIGILANT: [
        "guardian", "threshold", "watching", "observant", "vigilance",
        "warning", "warnings", "alert"
    ],
    Niche.GRIP_SHELTERING: [
        "shelter", "sheltering", "safety", "held", "holding", "protective",
        "cover", "home"
    ],
    Niche.FLOW_MIGRATORY: [
        "migratory", "seasonal", "cycles", "cyclic", "migration", "journey"
    ],
    Niche.FLOW_DISTRIBUTED: [
        "network", "distributed", "colony", "connected", "myceli"
    ],
    Niche.FLOW_SCANNING: [
        "see", "seeing", "vision", "scanning", "searching"
    ],
    Niche.FLOW_CALLING: [
        "calling", "laughing", "singing", "announcing", "parties", "vocal"
    ],
    Niche.TRANSITION_METAMORPHIC: [
        "shedding", "transformation", "metamorph", "change", "dissolv"
    ],
    Niche.TRANSITION_LIMINAL: [
        "threshold", "between", "liminal", "encounter", "close encounter"
    ],
    Niche.TRANSITION_TRICKSTER: [
        "trickster", "cheeky", "mischief", "disrupt", "get in the way"
    ],
    Niche.SETTLING_DORMANT: [
        "slow", "patience", "patient", "still", "dormant", "chill", "calm"
    ],
    Niche.SETTLING_ROOTED: [
        "rooted", "grounded", "tall", "proud", "ancient", "old"
    ],
    Niche.SETTLING_DAWN: [
        "dawn", "morning", "sunrise", "cyclic", "seasonal", "springtime"
    ],
    Niche.SETTLING_ELDER: [
        "elder", "wisdom", "wise", "guide", "guided", "teacher"
    ],
}


def infer_niche_affinities(notes: str, common_name: str = "", taxon_group: str = "") -> list[Niche]:
    """
    Infer niche affinities from relational notes.

    This is a heuristic — the participant's notes contain relational
    qualities that hint at ecological roles.
    """
    affinities = []
    text = f"{notes} {common_name}".lower()

    for niche, keywords in NICHE_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in text:
                if niche not in affinities:
                    affinities.append(niche)
                break  # One match per niche is enough

    # Taxon-based defaults if no notes match
    if not affinities:
        if taxon_group == "flora":
            affinities.append(Niche.SETTLING_ROOTED)
        elif taxon_group == "fungi":
            affinities.append(Niche.FLOW_DISTRIBUTED)

    return affinities


def extract_qualities(notes: str) -> list[str]:
    """
    Extract relational qualities from notes.

    These are the participant's felt-sense descriptions of relationship.
    """
    if not notes:
        return []

    # Split on common delimiters
    qualities = []

    # Try comma-separated
    if "," in notes:
        parts = [p.strip() for p in notes.split(",")]
        qualities.extend(p for p in parts if len(p) < 30)  # Short phrases only
    # Try "and" separated
    elif " and " in notes.lower():
        parts = [p.strip() for p in re.split(r'\s+and\s+', notes, flags=re.IGNORECASE)]
        qualities.extend(p for p in parts if len(p) < 30)
    else:
        # Use the whole note as a single quality if short enough
        if len(notes) < 50:
            qualities.append(notes)

    return qualities


def load_seed_vocabulary(
    seed_path: Path,
    include_maybe: bool = False
) -> tuple[list[Species], Country]:
    """
    Load seed vocabulary from species-browser export JSON.

    Args:
        seed_path: Path to seed_vocabulary_*.json
        include_maybe: Whether to include "maybe_kin" species

    Returns:
        Tuple of (species list, country context)
    """
    with open(seed_path) as f:
        data = json.load(f)

    # Build country context
    country = Country(
        name=data.get("country", "Unknown Country"),
        bioregion=data.get("country", "").split("/")[-1].strip() if "/" in data.get("country", "") else "",
        acknowledgment=f"Seed vocabulary from {data.get('country', 'this land')}."
    )

    species_list = []

    # Load meaningful kin
    for item in data.get("meaningful_kin", []):
        species = Species(
            scientific_name=item.get("scientific_name", ""),
            common_name=item.get("common_name", ""),
            taxon_group=item.get("taxon_group", ""),
            family=item.get("family", ""),
            notes=item.get("notes", ""),
            qualities=extract_qualities(item.get("notes", "")),
            niche_affinities=infer_niche_affinities(
                item.get("notes", ""),
                item.get("common_name", ""),
                item.get("taxon_group", "")
            )
        )
        if species.scientific_name:  # Skip empty entries
            species_list.append(species)

    # Optionally load maybe kin
    if include_maybe:
        for item in data.get("maybe_kin", []):
            species = Species(
                scientific_name=item.get("scientific_name", ""),
                common_name=item.get("common_name", ""),
                taxon_group=item.get("taxon_group", ""),
                family=item.get("family", ""),
                notes=item.get("notes", ""),
                qualities=extract_qualities(item.get("notes", "")),
                niche_affinities=infer_niche_affinities(
                    item.get("notes", ""),
                    item.get("common_name", ""),
                    item.get("taxon_group", "")
                )
            )
            if species.scientific_name:
                species_list.append(species)

    return species_list, country


def create_sanctuary_from_seed(seed_path: Path, include_maybe: bool = False) -> Sanctuary:
    """
    Create a new sanctuary from a seed vocabulary.

    The sanctuary starts empty of chimeras — they crystallize from
    phase dynamics during sessions.
    """
    species_list, country = load_seed_vocabulary(seed_path, include_maybe)

    return Sanctuary(
        country=country,
        species_vocabulary=species_list,
        chimeras=[],  # Chimeras crystallize during sessions
        encounter_history=[],
        threshold_history=[]
    )


def print_vocabulary_summary(species_list: list[Species]) -> None:
    """Print a summary of the loaded vocabulary."""
    print(f"\nLoaded {len(species_list)} species:\n")

    by_taxon = {}
    for s in species_list:
        by_taxon.setdefault(s.taxon_group, []).append(s)

    for taxon, species in sorted(by_taxon.items()):
        print(f"  {taxon}: {len(species)}")
        for s in species[:3]:  # Show first 3
            affinities = ", ".join(n.value for n in s.niche_affinities[:2])
            print(f"    - {s.display_name}: {affinities or '(no niche inferred)'}")
        if len(species) > 3:
            print(f"    ... and {len(species) - 3} more")

    print()

    # Niche coverage
    all_niches = set()
    for s in species_list:
        all_niches.update(s.niche_affinities)

    print(f"Niche coverage: {len(all_niches)}/{len(Niche)} niches")
    for niche in sorted(all_niches, key=lambda n: n.value):
        count = sum(1 for s in species_list if niche in s.niche_affinities)
        print(f"  {niche.value}: {count} species")
