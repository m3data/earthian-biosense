"""
Sanctuary ecology management for Chimera system.

The sanctuary is the living ecology of chimeras. It persists across
sessions and evolves when the participant isn't looking.
"""

import json
import random
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from .types import (
    Chimera, ChimeraState, Country, Encounter, Niche, Sanctuary, Species
)


class SanctuaryManager:
    """
    Manages the sanctuary ecology — persistence, crystallization, evolution.
    """

    def __init__(self, sanctuary: Sanctuary):
        self.sanctuary = sanctuary

    @classmethod
    def load(cls, path: Path) -> "SanctuaryManager":
        """Load sanctuary from JSON file."""
        with open(path) as f:
            data = json.load(f)

        sanctuary = Sanctuary(
            schema_version=data.get("schema_version", "0.1.0"),
            participant_id=data.get("participant_id", "local"),
            last_evolution_ts=data.get("last_evolution_ts")
        )

        # Load country
        if "country" in data:
            sanctuary.country = Country(**data["country"])

        # Load species vocabulary
        for item in data.get("species_vocabulary", []):
            niche_affinities = [Niche(n) for n in item.get("niche_affinities", [])]
            species = Species(
                scientific_name=item["scientific_name"],
                common_name=item.get("common_name", ""),
                taxon_group=item.get("taxon_group", ""),
                family=item.get("family", ""),
                notes=item.get("notes", ""),
                qualities=item.get("qualities", []),
                niche_affinities=niche_affinities,
                encounter_count=item.get("encounter_count", 0),
                witnessed_in_chimeras=item.get("witnessed_in_chimeras", [])
            )
            sanctuary.species_vocabulary.append(species)

        # Load chimeras
        for item in data.get("chimeras", []):
            chimera = Chimera(
                id=item["id"],
                components=item.get("components", []),
                weights=item.get("weights", []),
                lineage=item.get("lineage", []),
                birth_ts=item.get("birth_ts", ""),
                last_encountered_ts=item.get("last_encountered_ts"),
                encounter_count=item.get("encounter_count", 0),
                niche=Niche(item["niche"]) if item.get("niche") else None,
                state=ChimeraState(item.get("state", "sanctuary")),
                drift_rate=item.get("drift_rate", 1.0),
                last_drift_ts=item.get("last_drift_ts")
            )
            sanctuary.chimeras.append(chimera)

        # Load encounter history
        for item in data.get("encounter_history", []):
            encounter = Encounter(
                ts=item["ts"],
                chimera_id=item["chimera_id"],
                witnessed=item["witnessed"],
                phase_context=item.get("phase_context", {})
            )
            sanctuary.encounter_history.append(encounter)

        # Load threshold history
        for item in data.get("threshold_history", []):
            encounter = Encounter(
                ts=item["ts"],
                chimera_id=item["chimera_id"],
                witnessed=item["witnessed"],
                phase_context=item.get("phase_context", {})
            )
            sanctuary.threshold_history.append(encounter)

        return cls(sanctuary)

    def save(self, path: Path) -> None:
        """Save sanctuary to JSON file."""
        data = {
            "schema_version": self.sanctuary.schema_version,
            "participant_id": self.sanctuary.participant_id,
            "last_evolution_ts": self.sanctuary.last_evolution_ts,
        }

        # Save country
        if self.sanctuary.country:
            data["country"] = asdict(self.sanctuary.country)

        # Save species vocabulary
        data["species_vocabulary"] = []
        for s in self.sanctuary.species_vocabulary:
            item = asdict(s)
            item["niche_affinities"] = [n.value for n in s.niche_affinities]
            data["species_vocabulary"].append(item)

        # Save chimeras
        data["chimeras"] = []
        for c in self.sanctuary.chimeras:
            item = asdict(c)
            item["niche"] = c.niche.value if c.niche else None
            item["state"] = c.state.value
            data["chimeras"].append(item)

        # Save encounters
        data["encounter_history"] = [asdict(e) for e in self.sanctuary.encounter_history]
        data["threshold_history"] = [asdict(e) for e in self.sanctuary.threshold_history]

        # Ecology metrics
        data["ecology_metrics"] = {
            "total_chimeras": len(self.sanctuary.chimeras),
            "witnessed_count": len(self.sanctuary.witnessed_chimeras),
            "sanctuary_count": len(self.sanctuary.sanctuary_chimeras),
            "niche_coverage": [n.value for n in self.sanctuary.niche_coverage],
            "empty_niches": [n.value for n in self.sanctuary.empty_niches],
            "diversity_index": self.compute_diversity_index()
        }

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def compute_diversity_index(self) -> float:
        """
        Compute ecological diversity index (0-1).

        Based on:
        - Niche coverage (how many niches are occupied)
        - Component diversity (how many species are used)
        - Balance (how evenly distributed chimeras are across niches)
        """
        if not self.sanctuary.chimeras:
            return 0.0

        # Niche coverage component
        total_niches = len(Niche)
        occupied_niches = len(self.sanctuary.niche_coverage)
        niche_score = occupied_niches / total_niches

        # Species usage component
        total_species = len(self.sanctuary.species_vocabulary)
        if total_species == 0:
            return niche_score * 0.5

        used_species = set()
        for c in self.sanctuary.chimeras:
            used_species.update(c.components)
        species_score = len(used_species) / total_species

        # Balance component (evenness of niche distribution)
        niche_counts = {}
        for c in self.sanctuary.chimeras:
            if c.niche:
                niche_counts[c.niche] = niche_counts.get(c.niche, 0) + 1

        if niche_counts:
            counts = list(niche_counts.values())
            max_count = max(counts)
            min_count = min(counts)
            if max_count > 0:
                balance_score = min_count / max_count
            else:
                balance_score = 1.0
        else:
            balance_score = 0.0

        # Weighted combination
        return 0.4 * niche_score + 0.4 * species_score + 0.2 * balance_score

    def crystallize_chimera(
        self,
        niche: Niche,
        num_components: int = 3,
        phase_context: Optional[dict] = None
    ) -> Chimera:
        """
        Crystallize a new chimera from the vocabulary.

        Chimeras emerge from phase dynamics. The niche determines which
        species are likely to combine.
        """
        # Find species with affinity for this niche
        candidates = [
            s for s in self.sanctuary.species_vocabulary
            if niche in s.niche_affinities
        ]

        # If not enough candidates, expand to all species
        if len(candidates) < num_components:
            candidates = list(self.sanctuary.species_vocabulary)

        # Select components with some randomness
        if len(candidates) <= num_components:
            selected = candidates
        else:
            # Weight by how many times species has been witnessed (less = more likely)
            weights = []
            for s in candidates:
                # Invert encounter count: less encountered = higher weight
                w = 1.0 / (1.0 + s.encounter_count * 0.5)
                weights.append(w)

            # Normalize
            total = sum(weights)
            weights = [w / total for w in weights]

            selected = random.choices(candidates, weights=weights, k=num_components)

        # Assign weights (primary, secondary, tertiary)
        component_weights = self._generate_weights(len(selected))

        chimera = Chimera(
            components=[s.scientific_name for s in selected],
            weights=component_weights,
            niche=niche,
            state=ChimeraState.SANCTUARY
        )

        self.sanctuary.chimeras.append(chimera)
        return chimera

    def _generate_weights(self, n: int) -> list[float]:
        """Generate component weights that sum to 1.0."""
        if n == 1:
            return [1.0]
        elif n == 2:
            primary = random.uniform(0.55, 0.75)
            return [primary, 1.0 - primary]
        elif n == 3:
            primary = random.uniform(0.45, 0.60)
            secondary = random.uniform(0.25, 0.40)
            tertiary = 1.0 - primary - secondary
            if tertiary < 0.05:
                tertiary = 0.1
                secondary = 1.0 - primary - tertiary
            return [primary, secondary, tertiary]
        else:
            # Dirichlet-ish distribution
            raw = [random.random() for _ in range(n)]
            total = sum(raw)
            return [r / total for r in raw]

    def seed_initial_chimeras(self, count: int = 5) -> list[Chimera]:
        """
        Seed the sanctuary with initial chimeras.

        Called when sanctuary is first created. Creates chimeras
        spread across different niches.
        """
        chimeras = []

        # Select niches that have species with affinity
        available_niches = []
        for niche in Niche:
            candidates = [s for s in self.sanctuary.species_vocabulary if niche in s.niche_affinities]
            if candidates:
                available_niches.append(niche)

        # If no niches have affinity, use all niches
        if not available_niches:
            available_niches = list(Niche)

        # Create chimeras spread across niches
        for i in range(count):
            niche = available_niches[i % len(available_niches)]
            chimera = self.crystallize_chimera(niche)
            chimeras.append(chimera)

        return chimeras

    def get_chimera_display_name(self, chimera: Chimera) -> str:
        """Get a display name for a chimera using common names."""
        names = []
        for sci_name, weight in chimera.weighted_components():
            species = self.sanctuary.species_by_name(sci_name)
            if species:
                name = species.common_name or species.scientific_name.split()[-1]
                names.append(name)
            else:
                names.append(sci_name.split()[-1])

        if len(names) == 1:
            return names[0]
        elif len(names) == 2:
            return f"{names[0]}-{names[1]}"
        else:
            return f"{names[0]}-{names[1]}-{names[2]}"

    def record_encounter(
        self,
        chimera: Chimera,
        witnessed: bool,
        phase_context: Optional[dict] = None
    ) -> Encounter:
        """Record a threshold encounter."""
        encounter = Encounter(
            ts=datetime.now().isoformat(),
            chimera_id=chimera.id,
            witnessed=witnessed,
            phase_context=phase_context or {}
        )

        self.sanctuary.threshold_history.append(encounter)

        if witnessed:
            self.sanctuary.encounter_history.append(encounter)

        return encounter
