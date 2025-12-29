#!/usr/bin/env python3
"""Process raw session (e.g., from iOS capture) into enriched format with computed metrics.

Takes raw JSONL with ts, hr, rr fields and computes:
- HRV metrics (amplitude, entrainment, breath rate, volatility, mode)
- Phase dynamics (position, velocity, curvature, stability, coherence)
- Movement-preserving classification (soft mode, movement annotation)

Usage:
    python scripts/process_session.py sessions/ios-exports/2025-12-29_101121.jsonl

Output:
    sessions/ios-exports/2025-12-29_101121_processed.jsonl
"""

import json
import sys
from pathlib import Path
from collections import deque

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from processing.hrv import compute_hrv_metrics
from processing.phase import PhaseTrajectory


def process_session(input_path: Path) -> Path:
    """Process raw session file into enriched format with computed metrics."""

    print(f"Processing: {input_path}")
    print("=" * 50)

    # Read all records
    lines = input_path.read_text().strip().split('\n')
    records = [json.loads(line) for line in lines]

    # Find header and footer
    header = None
    footer = None
    data_records = []

    for record in records:
        if record.get('type') == 'session_start':
            header = record
        elif record.get('type') == 'session_end':
            footer = record
        elif 'hr' in record and 'rr' in record:
            data_records.append(record)

    if not header:
        # Create synthetic header for legacy files
        header = {
            'type': 'session_start',
            'ts': data_records[0]['ts'] if data_records else '',
            'schema_version': '1.1.0',
            'source': 'unknown'
        }

    print(f"Source: {header.get('source', 'unknown')}")
    print(f"Schema: {header.get('schema_version', 'unknown')}")
    print(f"Raw records: {len(data_records)}")

    # Initialize processing state
    rr_buffer: deque[int] = deque(maxlen=30)
    trajectory = PhaseTrajectory(window_size=30)
    processed_records = []
    record_count = 0

    for record in data_records:
        ts_str = record.get('ts')
        hr = record.get('hr')
        rr_list = record.get('rr', [])

        # Add valid RR intervals to buffer
        for rr in rr_list:
            if 300 < rr < 1500:  # Filter physiologically valid range
                rr_buffer.append(rr)

        # Need minimum data to compute meaningful metrics
        if len(rr_buffer) < 6:
            # Output raw record with placeholder metrics
            processed = {
                'ts': ts_str,
                'hr': hr,
                'rr': rr_list,
                'metrics': {
                    'amp': 0,
                    'ent': 0.0,
                    'ent_label': '[insufficient data]',
                    'breath': None,
                    'volatility': 0.0,
                    'mode': 'unknown',
                    'mode_score': 0.0
                },
                'phase': {
                    'position': [0.0, 0.5, 0.0],
                    'velocity': [0.0, 0.0, 0.0],
                    'velocity_mag': 0.0,
                    'curvature': 0.0,
                    'stability': 0.5,
                    'history_signature': 0.0,
                    'phase_label': 'warming up',
                    'coherence': 0.0,
                    'movement_annotation': 'insufficient data',
                    'movement_aware_label': 'unknown'
                }
            }
            processed_records.append(processed)
            continue

        record_count += 1

        # Compute HRV metrics from buffer
        rr_as_list = list(rr_buffer)
        metrics = compute_hrv_metrics(rr_as_list)

        # Update trajectory and get dynamics
        # Use record count as pseudo-timestamp to avoid datetime issues
        dynamics = trajectory.append(metrics, float(record_count))

        # Compute trajectory coherence
        coherence = trajectory.compute_trajectory_coherence(lag=5)

        # Build processed record
        processed = {
            'ts': ts_str,
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
                'position': [round(p, 4) for p in dynamics.position] if dynamics else [0, 0.5, 0],
                'velocity': [round(v, 4) for v in dynamics.velocity] if dynamics else [0, 0, 0],
                'velocity_mag': round(dynamics.velocity_magnitude, 4) if dynamics else 0.0,
                'curvature': round(dynamics.curvature, 4) if dynamics else 0.0,
                'stability': round(dynamics.stability, 4) if dynamics else 0.5,
                'history_signature': round(dynamics.history_signature, 4) if dynamics else 0.0,
                'phase_label': dynamics.phase_label if dynamics else 'warming up',
                'coherence': round(coherence, 4),
                'movement_annotation': dynamics.movement_annotation if dynamics else 'unknown',
                'movement_aware_label': dynamics.movement_aware_label if dynamics else 'unknown'
            }
        }

        # Add soft mode if available
        if dynamics and dynamics.soft_mode:
            processed['phase']['soft_mode'] = {
                'primary': dynamics.soft_mode.primary_mode,
                'secondary': dynamics.soft_mode.secondary_mode,
                'ambiguity': round(dynamics.soft_mode.ambiguity, 4),
                'membership': {k: round(v, 4) for k, v in dynamics.soft_mode.membership.items()}
            }

        processed_records.append(processed)

    print(f"Processed records: {record_count}")

    # Build output header
    output_header = {
        'type': 'session_start',
        'ts': header.get('ts', ''),
        'schema_version': '1.1.0',
        'source': header.get('source', 'unknown'),
        'device_id': header.get('device_id'),
        'processed': True,
        'note': 'ent=entrainment (breath-heart sync), coherence=trajectory integrity'
    }

    # Write output
    output_path = input_path.with_name(
        input_path.stem + '_processed' + input_path.suffix
    )

    with open(output_path, 'w') as f:
        f.write(json.dumps(output_header) + '\n')
        for record in processed_records:
            f.write(json.dumps(record) + '\n')
        if footer:
            f.write(json.dumps(footer) + '\n')

    print(f"Output: {output_path}")
    print("=" * 50)

    # Summary stats
    if processed_records:
        all_rr = []
        for r in processed_records:
            all_rr.extend(r.get('rr', []))
        if all_rr:
            print(f"RR intervals: {len(all_rr)}")
            print(f"RR range: {min(all_rr)} - {max(all_rr)} ms")

        # Final metrics from last record
        last = processed_records[-1]
        print(f"Final mode: {last['metrics']['mode']} ({last['metrics']['mode_score']:.2f})")
        print(f"Final coherence: {last['phase']['coherence']:.3f}")

    return output_path


def main():
    if len(sys.argv) < 2:
        print("Usage: python process_session.py <session.jsonl>")
        print("\nProcesses raw session (e.g., iOS capture) into enriched format.")
        print("Computes HRV metrics, phase dynamics, and movement classification.")
        sys.exit(1)

    input_path = Path(sys.argv[1])

    if not input_path.exists():
        print(f"Error: File not found: {input_path}")
        sys.exit(1)

    output_path = process_session(input_path)
    print(f"\nDone. Processed session: {output_path}")


if __name__ == '__main__':
    main()
