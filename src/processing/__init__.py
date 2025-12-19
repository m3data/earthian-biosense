# Signal processing
from .hrv import HRVMetrics, compute_hrv_metrics
from .phase import PhaseState, PhaseDynamics, PhaseTrajectory

# Movement-preserving classification (v1.1.0)
from .movement import (
    SoftModeInference,
    HysteresisConfig,
    ModeHistory,
    compute_soft_mode_membership,
    detect_mode_with_hysteresis,
    generate_movement_annotation,
    detect_rupture_oscillation,
)
from .schema import SCHEMA_VERSION, get_schema_version
