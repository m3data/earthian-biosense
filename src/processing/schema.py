"""Session data schema versioning for EarthianBioSense.

Tracks breaking changes to the session data format so old sessions
can be identified and reprocessed if needed.
"""

# Schema version - increment on breaking changes to session format
SCHEMA_VERSION = "1.1.0"

# Changelog:
#
# 1.1.0 (2025-12-19) - Movement-preserving classification
#   - Added movement.py module with soft mode inference
#   - New JSONL fields in phase object:
#     - movement_annotation: how you arrived (e.g., "settling from heightened alertness")
#     - movement_aware_label: composed label with movement context
#     - mode_status: 'unknown', 'provisional', 'established'
#     - dwell_time: seconds in current mode
#     - acceleration_mag: second derivative of mode_score
#     - soft_mode: weighted membership across all modes
#   - Hysteresis-aware state transitions (entry != exit thresholds)
#   - Terminology change: "vigilance" → "alertness"
#     - "heightened vigilance" → "heightened alertness"
#     - "subtle vigilance" → "subtle alertness"
#     - "vigilant stillness" → "alert stillness"
#   - Architecture adapted from semantic-climate-phase-space/src/basins.py (v0.3.0)
#
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
