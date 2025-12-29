"""
Core types for Chimera Ecology.

Chimeras are mythopoetic archetypes composed of local species (kin).
They crystallize from autonomic phase dynamics and resist optimization
by design — you can't KPI your way to "more owl-snake-spider".
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid


class ChimeraState(Enum):
    """States a chimera can occupy."""
    SANCTUARY = "sanctuary"      # Living in the unwitnessed, evolving in the dark
    THRESHOLD = "threshold"      # Approaching the modal, ready for potential encounter
    ENCOUNTERED = "encountered"  # Has been witnessed at least once, stabilized
    FERAL = "feral"              # Was encountered but returned to sanctuary, drifting


class Niche(Enum):
    """
    Ecological niches that chimeras occupy.
    These emerge from phase space dynamics, not arbitrary assignment.
    """
    # Grip niches — high entrainment, constrained
    GRIP_PREDATOR = "grip/predator"      # High entrainment, low velocity, watching
    GRIP_PREY = "grip/prey"              # High entrainment, high curvature, hiding
    GRIP_VIGILANT = "grip/vigilant"      # Watchful stillness, holding pattern
    GRIP_SHELTERING = "grip/sheltering"  # Protective holding, covering

    # Flow niches — high coherence, low entrainment, movement
    FLOW_MIGRATORY = "flow/migratory"    # Larger rhythms, seasonal patterns
    FLOW_DISTRIBUTED = "flow/distributed"  # No center, networked
    FLOW_SCANNING = "flow/scanning"      # Moving attention, searching
    FLOW_CALLING = "flow/calling"        # Vocalization, announcement

    # Transition niches — at or approaching bifurcation
    TRANSITION_METAMORPHIC = "transition/metamorphic"  # Dissolution, transformation
    TRANSITION_LIMINAL = "transition/liminal"          # At threshold, between states
    TRANSITION_TRICKSTER = "transition/trickster"      # Boundary-crossing, disruption

    # Settling niches — in basin, stability
    SETTLING_DORMANT = "settling/dormant"    # Held stillness, hibernation
    SETTLING_ROOTED = "settling/rooted"      # Grounded, anchored
    SETTLING_DAWN = "settling/dawn"          # Temporal anchor, cyclic
    SETTLING_ELDER = "settling/elder"        # Accumulated wisdom, guidance


@dataclass
class Species:
    """
    A species from the local ecology — kin, not symbol.

    Species are the building blocks of chimeras. They come from the land
    the participant's body is on, not from universal archetypes.
    """
    scientific_name: str
    common_name: str
    taxon_group: str  # "fauna" | "flora" | "fungi"
    family: str

    # Relational qualities (from participant's notes)
    notes: str = ""
    qualities: list[str] = field(default_factory=list)

    # Niche affinities (which niches this species tends toward)
    niche_affinities: list[Niche] = field(default_factory=list)

    # Accumulated through encounter
    encounter_count: int = 0
    witnessed_in_chimeras: list[str] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return self.common_name or self.scientific_name


@dataclass
class Chimera:
    """
    A chimeric archetype composed of local species.

    Chimeras crystallize from autonomic phase dynamics. They are
    mythopoetic — resisting optimization by design.
    """
    id: str = field(default_factory=lambda: f"chimera_{uuid.uuid4().hex[:8]}")

    # Composition
    components: list[str] = field(default_factory=list)  # Species scientific names
    weights: list[float] = field(default_factory=list)   # Relative presence, sum to 1.0

    # Lineage
    lineage: list[str] = field(default_factory=list)     # Ancestor chimera IDs

    # Temporal
    birth_ts: str = field(default_factory=lambda: datetime.now().isoformat())
    last_encountered_ts: Optional[str] = None
    encounter_count: int = 0

    # Ecology
    niche: Optional[Niche] = None
    state: ChimeraState = ChimeraState.SANCTUARY

    # Drift tracking
    drift_rate: float = 1.0  # Higher = faster drift. Decreases with witnessing.
    last_drift_ts: Optional[str] = None

    @property
    def is_witnessed(self) -> bool:
        return self.last_encountered_ts is not None

    @property
    def component_names(self) -> list[str]:
        """Return just the species names for display."""
        return self.components

    def weighted_components(self) -> list[tuple[str, float]]:
        """Return (species_name, weight) pairs sorted by weight descending."""
        pairs = list(zip(self.components, self.weights))
        return sorted(pairs, key=lambda x: x[1], reverse=True)


@dataclass
class Encounter:
    """Record of a threshold encounter."""
    ts: str
    chimera_id: str
    witnessed: bool  # True if witnessed, False if refused
    phase_context: dict = field(default_factory=dict)  # Phase dynamics at encounter


@dataclass
class Country:
    """
    The land context for a vocabulary.

    Chimeras must be place-based — composed of kin from the land
    the participant's body is on.
    """
    name: str                    # e.g., "Bidjigal Country"
    bioregion: str               # e.g., "Sydney Basin"
    acknowledgment: str          # Custodian acknowledgment
    bounds: Optional[dict] = None  # Geographic bounds if relevant


@dataclass
class Sanctuary:
    """
    The living ecology of chimeras for a participant.

    The sanctuary is where chimeras live between sessions. Witnessed
    chimeras stabilize; unwitnessed chimeras drift and evolve.
    """
    schema_version: str = "0.1.0"
    participant_id: str = "local"

    country: Optional[Country] = None
    species_vocabulary: list[Species] = field(default_factory=list)

    chimeras: list[Chimera] = field(default_factory=list)
    encounter_history: list[Encounter] = field(default_factory=list)
    threshold_history: list[Encounter] = field(default_factory=list)  # Includes refused

    last_evolution_ts: Optional[str] = None

    @property
    def sanctuary_chimeras(self) -> list[Chimera]:
        """Chimeras currently in sanctuary (unwitnessed or feral)."""
        return [c for c in self.chimeras if c.state in (ChimeraState.SANCTUARY, ChimeraState.FERAL)]

    @property
    def witnessed_chimeras(self) -> list[Chimera]:
        """Chimeras that have been witnessed."""
        return [c for c in self.chimeras if c.state == ChimeraState.ENCOUNTERED]

    @property
    def niche_coverage(self) -> list[Niche]:
        """Which niches are currently occupied."""
        return list(set(c.niche for c in self.chimeras if c.niche))

    @property
    def empty_niches(self) -> list[Niche]:
        """Which niches have no chimeras."""
        occupied = set(self.niche_coverage)
        return [n for n in Niche if n not in occupied]

    def chimera_by_id(self, chimera_id: str) -> Optional[Chimera]:
        """Find a chimera by ID."""
        for c in self.chimeras:
            if c.id == chimera_id:
                return c
        return None

    def species_by_name(self, scientific_name: str) -> Optional[Species]:
        """Find a species by scientific name."""
        for s in self.species_vocabulary:
            if s.scientific_name == scientific_name:
                return s
        return None
