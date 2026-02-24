"""JSONL timeseries logger for session data.

Extracted from app.py to isolate the storage layer.
"""

import json
from datetime import datetime
from pathlib import Path

from domain.types import SemioticMarker, FieldEvent
from processing.hrv import HRVMetrics
from processing.phase import PhaseDynamics
from processing.schema import SCHEMA_VERSION


class SessionLogger:
    """JSONL timeseries logger for session data."""

    def __init__(self, session_dir: str = "sessions"):
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(exist_ok=True)
        self.session_file: Path | None = None
        self.file_handle = None
        self.pending_semiotic: SemioticMarker | None = None
        self.pending_field_event: FieldEvent | None = None

    def start_session(self) -> Path:
        """Start a new session log file."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.session_file = self.session_dir / f"{timestamp}.jsonl"
        self.file_handle = open(self.session_file, 'w')

        # Write header record with schema version
        header = {
            "type": "session_start",
            "ts": datetime.now().isoformat(),
            "schema_version": SCHEMA_VERSION,
            "note": "ent=entrainment (breath-heart sync), coherence=trajectory integrity"
        }
        self.file_handle.write(json.dumps(header) + '\n')
        self.file_handle.flush()

        return self.session_file

    def log(
        self,
        timestamp: datetime,
        hr: int,
        rr_intervals: list[int],
        metrics: HRVMetrics | None,
        dynamics: PhaseDynamics | None = None,
        coherence: float | None = None
    ):
        """Log a data point to the session file.

        Includes both scalar metrics (backward compat) and rich phase dynamics.
        """
        if not self.file_handle:
            return

        record = {
            "ts": timestamp.isoformat(),
            "hr": hr,
            "rr": rr_intervals,
        }

        if metrics:
            record["metrics"] = {
                "amp": metrics.amplitude,
                "ent": round(metrics.entrainment, 3),  # entrainment (breath-heart sync)
                "ent_label": metrics.entrainment_label,
                "breath": round(metrics.breath_rate, 1) if metrics.breath_rate else None,
                "volatility": round(metrics.rr_volatility, 4),
                # Keep flat mode fields for backward compat
                "mode": metrics.mode_label,
                "mode_score": round(metrics.mode_score, 3),
            }

        if dynamics:
            record["phase"] = {
                "position": [round(p, 4) for p in dynamics.position],
                "velocity": [round(v, 4) for v in dynamics.velocity],
                "velocity_mag": round(dynamics.velocity_magnitude, 4),
                "curvature": round(dynamics.curvature, 4),
                "stability": round(dynamics.stability, 4),
                "history_signature": round(dynamics.history_signature, 4),
                "phase_label": dynamics.phase_label,
                "coherence": round(coherence, 4) if coherence is not None else None,
                # === Movement-preserving classification (v1.1.0) ===
                "movement_annotation": dynamics.movement_annotation,
                "movement_aware_label": dynamics.movement_aware_label,
                "mode_status": dynamics.mode_status,
                "dwell_time": round(dynamics.dwell_time, 2),
                "acceleration_mag": round(dynamics.mode_score_acceleration, 4),
            }
            # Add soft_mode if available (nested object)
            if dynamics.soft_mode:
                record["phase"]["soft_mode"] = {
                    "primary": dynamics.soft_mode.primary_mode,
                    "secondary": dynamics.soft_mode.secondary_mode,
                    "ambiguity": round(dynamics.soft_mode.ambiguity, 4),
                    "distribution_shift": round(dynamics.soft_mode.distribution_shift, 6)
                        if dynamics.soft_mode.distribution_shift is not None else None,
                    # Include top 3 membership weights for debugging/visualization
                    "membership": {
                        k: round(v, 4) for k, v in sorted(
                            dynamics.soft_mode.membership.items(),
                            key=lambda x: x[1],
                            reverse=True
                        )[:3]
                    }
                }

        # Add semiotic marker if received from Semantic Climate
        if self.pending_semiotic:
            record["semiotic"] = {
                "curvature_delta": self.pending_semiotic.curvature_delta,
                "entropy_delta": self.pending_semiotic.entropy_delta,
                "coupling_psi": self.pending_semiotic.coupling_psi,
                "label": self.pending_semiotic.label
            }
            self.pending_semiotic = None  # Clear after logging

        # Add field event if received
        if self.pending_field_event:
            record["field_event"] = {
                "event": self.pending_field_event.event,
                "note": self.pending_field_event.note
            }
            self.pending_field_event = None  # Clear after logging

        self.file_handle.write(json.dumps(record) + '\n')
        self.file_handle.flush()

    def add_semiotic_marker(self, marker: SemioticMarker):
        """Store semiotic marker from Semantic Climate for next log entry."""
        self.pending_semiotic = marker

    def add_field_event(self, event: FieldEvent):
        """Store field event for next log entry."""
        self.pending_field_event = event

    def close(self):
        """Close the session file."""
        if self.file_handle:
            self.file_handle.close()
            self.file_handle = None
