"""Session data schema versioning for EarthianBioSense.

Tracks breaking changes to the session data format so old sessions
can be identified and reprocessed if needed.
"""

# Schema version - increment on breaking changes to session format
SCHEMA_VERSION = "1.2.0"

# NOTE ON ENGINE DIVERGENCE (2026-05-23): the Python and Rust desktop engines
# have separate schema lineages. The Rust desktop reached 1.3.0 with the
# accelerometer motion channel (v0.4.0); this Python lineage does not include
# that record format, so the version numbers are NOT directly comparable across
# engines. Unifying the two lineages is a tracked follow-up, not done here.
#
# Changelog:
#
# 1.2.0 (2026-05-23) - Signed phase coupling
#   - New JSONL field in metrics object:
#     - phase_coupling: signed breath-band coupling (-1..1). entrainment is its
#       non-negative part; anti-phase (<0) is now distinct from decoupled (~0).
#   - Additive and back-compatible: old sessions load unchanged; readers that
#     don't know the field ignore it. Reprocessing old raw RR repopulates it.
#   - Fixes the entrainment=0 wall in the somatic phase space: the clamp in
#     compute_entrainment discarded the negative half of the autocorrelation,
#     collapsing anti-phase onto decoupled. See ebs-review Layer 4.
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
