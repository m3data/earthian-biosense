#!/usr/bin/env python3
"""Process raw dyadic session into format suitable for replay visualization.

Takes raw dyadic JSONL (with participant A/B, hr, rr fields) and computes
phase dynamics for each participant stream, outputting processed JSONL
compatible with replay.html.

Usage:
    python viz/process_dyadic.py sessions/dyadic_2025-12-13_122906.jsonl

Output:
    sessions/dyadic_2025-12-13_122906_processed.jsonl
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from collections import deque

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from processing.hrv import compute_hrv_metrics
from processing.phase import PhaseTrajectory


class ParticipantStream:
    """Manages RR buffer and phase trajectory for one participant."""

    def __init__(self, participant_id: str, window_size: int = 20):
        self.participant_id = participant_id
        self.rr_buffer: deque[int] = deque(maxlen=window_size)
        self.trajectory = PhaseTrajectory(window_size=30)
        self.record_count = 0

    def add_record(self, record: dict) -> dict | None:
        """Add a raw record, compute metrics, return processed record."""
        ts_str = record.get('ts')
        hr = record.get('hr')
        rr_list = record.get('rr', [])

        # Add valid RR intervals to buffer
        for rr in rr_list:
            if 300 < rr < 1500:  # Filter physiologically valid range
                self.rr_buffer.append(rr)

        # Need minimum data to compute meaningful metrics
        if len(self.rr_buffer) < 6:
            return None

        self.record_count += 1

        # Compute HRV metrics from buffer
        rr_as_list = list(self.rr_buffer)
        metrics = compute_hrv_metrics(rr_as_list)

        # Parse timestamp for phase trajectory
        try:
            ts = datetime.fromisoformat(ts_str).timestamp()
        except:
            ts = self.record_count  # Fallback to counter

        # Update trajectory and get dynamics
        dynamics = self.trajectory.append(metrics, ts)

        # Compute trajectory coherence
        coherence = self.trajectory.compute_trajectory_coherence(lag=5)

        # Build processed record matching single-participant format
        processed = {
            'ts': ts_str,
            'participant': self.participant_id,
            'hr': hr,
            'rr': rr_list,
            'metrics': {
                'amp': metrics.amplitude,
                'ent': round(metrics.entrainment, 4),
                'ent_label': metrics.entrainment_label,
                'breath': round(metrics.breath_rate, 1) if metrics.breath_rate else None,
                'volatility': round(metrics.rr_volatility, 4),
                'mode': metrics.mode_label,
                'mode_score': round(metrics.mode_score, 3)
            },
            'phase': {
                'position': [round(p, 4) for p in dynamics.position],
                'velocity': [round(v, 4) for v in dynamics.velocity],
                'velocity_mag': round(dynamics.velocity_magnitude, 4),
                'curvature': round(dynamics.curvature, 4),
                'stability': round(dynamics.stability, 4),
                'history_signature': round(dynamics.history_signature, 4),
                'phase_label': dynamics.phase_label,
                'coherence': round(coherence, 4)
            }
        }

        return processed


def process_dyadic_session(input_path: Path) -> Path:
    """Process raw dyadic session file into viz-compatible format."""

    print(f"Processing: {input_path}")

    # Read all records
    records = []
    header = None

    with open(input_path) as f:
        for line in f:
            record = json.loads(line.strip())
            if record.get('type') == 'session_start':
                header = record
            else:
                records.append(record)

    if not header:
        raise ValueError("No session header found")

    if header.get('session_type') != 'dyadic':
        raise ValueError(f"Not a dyadic session: {header.get('session_type')}")

    print(f"  Session type: dyadic")
    print(f"  Raw records: {len(records)}")

    # Initialize participant streams
    streams = {
        'A': ParticipantStream('A'),
        'B': ParticipantStream('B')
    }

    # Process records
    processed_records = []

    for record in records:
        participant = record.get('participant')
        if participant not in streams:
            continue

        processed = streams[participant].add_record(record)
        if processed:
            processed_records.append(processed)

    print(f"  Processed A: {streams['A'].record_count} records")
    print(f"  Processed B: {streams['B'].record_count} records")
    print(f"  Total output: {len(processed_records)} records")

    # Sort by timestamp to interleave properly
    processed_records.sort(key=lambda r: r['ts'])

    # Build output header
    output_header = {
        'type': 'session_start',
        'ts': header['ts'],
        'schema_version': '1.0.0',
        'session_type': 'dyadic',
        'participants': header.get('participants', {'A': {}, 'B': {}}),
        'note': header.get('note', ''),
        'processed': True
    }

    # Write output
    output_path = input_path.with_name(
        input_path.stem + '_processed' + input_path.suffix
    )

    with open(output_path, 'w') as f:
        f.write(json.dumps(output_header) + '\n')
        for record in processed_records:
            f.write(json.dumps(record) + '\n')

    print(f"  Output: {output_path}")

    return output_path


def main():
    if len(sys.argv) < 2:
        print("Usage: python process_dyadic.py <session.jsonl>")
        print("\nProcesses raw dyadic session for replay visualization.")
        sys.exit(1)

    input_path = Path(sys.argv[1])

    if not input_path.exists():
        print(f"Error: File not found: {input_path}")
        sys.exit(1)

    output_path = process_dyadic_session(input_path)
    print(f"\nDone. Load {output_path.name} in replay.html")


if __name__ == '__main__':
    main()
