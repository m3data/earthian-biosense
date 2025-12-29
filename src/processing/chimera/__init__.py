"""
Chimera Ecology — Baradian poetry for rewilding the ANS

This module implements mythopoetic archetypes that crystallize from
autonomic phase dynamics. Chimeras are composed of local kin (species)
and resist optimization by design.

Key concepts:
- Chimeras can't be KPI'd — the mythopoetic frame resists capture
- The cut is at the threshold — participant chooses to witness or not
- Witnessed chimeras stabilize; unwitnessed stay wild in the sanctuary
- EA (not GA) — selection for coexistence, not fitness

See docs/CHIMERA_ECOLOGY_SPEC_v0.1.md for full specification.
"""

from .types import Species, Chimera, Sanctuary, Country, Encounter
from .vocabulary import load_seed_vocabulary
from .ecology import SanctuaryManager
from .evolution import drift, apply_niche_pressure, maybe_speciate
from .threshold import detect_threshold
from .encounter import on_witnessed, on_refused, maybe_go_feral

__all__ = [
    "Species",
    "Chimera",
    "Sanctuary",
    "Country",
    "Encounter",
    "load_seed_vocabulary",
    "SanctuaryManager",
    "drift",
    "apply_niche_pressure",
    "maybe_speciate",
    "detect_threshold",
    "on_witnessed",
    "on_refused",
    "maybe_go_feral",
]
