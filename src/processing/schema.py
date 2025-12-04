"""Session data schema versioning for EarthianBioSense.

Tracks breaking changes to the session data format so old sessions
can be identified and reprocessed if needed.
"""

# Schema version - increment on breaking changes to session format
SCHEMA_VERSION = "1.0.0"

# Changelog:
# 1.0.0 (2025-12-04) - Entrainment/coherence distinction
#   - Renamed coh → ent (entrainment)
#   - Renamed coh_label → ent_label
#   - Added compute_trajectory_coherence() for true coherence measurement
#   - Phase labels updated: "coherent dwelling" → "entrained dwelling", etc.
#   - Prior sessions (v0) used "coh" to mean breath-heart entrainment
#
# 0.x (pre-2025-12-04) - Pre-distinction
#   - coh = breath-heart autocorrelation (actually entrainment)
#   - "coherence" labels were misnomers

def get_schema_version() -> str:
    """Return current schema version string."""
    return SCHEMA_VERSION
