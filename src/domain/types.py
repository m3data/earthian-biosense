"""Shared domain types for EarthianBioSense.

These types are used across storage, API, and application layers.
Extracted from api/websocket_server.py to break the storage→API dependency.
"""

from datetime import datetime
from dataclasses import dataclass


@dataclass
class SemioticMarker:
    """Semiotic state marker received from Semantic Climate."""
    timestamp: datetime
    curvature_delta: float | None = None
    entropy_delta: float | None = None
    coupling_psi: float | None = None
    label: str | None = None


@dataclass
class FieldEvent:
    """Manual field event marker."""
    timestamp: datetime
    event: str
    note: str | None = None
