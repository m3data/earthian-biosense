#!/usr/bin/env python3
"""Quick dyadic phase space visualization.

Loads a dyadic session and plots both participants in 3D phase space.
"""

import json
import sys
sys.path.insert(0, 'src')

import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from pathlib import Path
from processing.hrv import compute_hrv_metrics

def load_dyadic_session(filepath):
    """Load and separate dyadic session data."""
    records = []
    with open(filepath) as f:
        for line in f:
            records.append(json.loads(line))

    header = records[0]
    data = [r for r in records[1:] if r.get('participant')]

    a_records = [r for r in data if r.get('participant') == 'A']
    b_records = [r for r in data if r.get('participant') == 'B']

    return header, a_records, b_records

def extract_rr_series(records):
    """Extract continuous RR series from records."""
    rr_all = []
    for r in records:
        rr_list = r.get('rr', [])
        # Filter valid RR intervals (300-1500ms)
        for rr in rr_list:
            if 300 < rr < 1500:
                rr_all.append(rr)
    return rr_all

def compute_phase_trajectory(rr_series, window_size=20):
    """Compute phase space trajectory from RR series.

    Returns arrays of (entrainment, breath_proxy, amplitude) over time.
    """
    if len(rr_series) < window_size:
        return [], [], []

    entrainments = []
    breath_proxies = []
    amplitudes = []

    for i in range(window_size, len(rr_series)):
        window = rr_series[i-window_size:i]
        metrics = compute_hrv_metrics(window)

        entrainments.append(metrics.entrainment)
        breath_proxies.append(metrics.breath_rate if metrics.breath_rate else 12.0)
        amplitudes.append(metrics.amplitude)

    return entrainments, breath_proxies, amplitudes

def plot_dyadic_phase_space(filepath, output_path=None):
    """Create 3D phase space plot for dyadic session."""

    print(f"Loading {filepath}...")
    header, a_records, b_records = load_dyadic_session(filepath)

    print(f"  A records: {len(a_records)}")
    print(f"  B records: {len(b_records)}")

    # Extract RR series
    a_rr = extract_rr_series(a_records)
    b_rr = extract_rr_series(b_records)

    print(f"  A RR intervals: {len(a_rr)}")
    print(f"  B RR intervals: {len(b_rr)}")

    # Compute phase trajectories
    print("Computing phase trajectories...")
    a_ent, a_breath, a_amp = compute_phase_trajectory(a_rr)
    b_ent, b_breath, b_amp = compute_phase_trajectory(b_rr)

    print(f"  A trajectory points: {len(a_ent)}")
    print(f"  B trajectory points: {len(b_ent)}")

    # Create figure
    fig = plt.figure(figsize=(14, 6))

    # 3D phase space plot
    ax1 = fig.add_subplot(121, projection='3d')

    # Normalize breath rate to 0-1 for visualization
    a_breath_norm = [(b - 8) / 12 for b in a_breath]  # Assuming 8-20 breaths/min range
    b_breath_norm = [(b - 8) / 12 for b in b_breath]

    # Normalize amplitude to 0-1
    max_amp = max(max(a_amp) if a_amp else 1, max(b_amp) if b_amp else 1, 1)
    a_amp_norm = [a / max_amp for a in a_amp]
    b_amp_norm = [a / max_amp for a in b_amp]

    # Plot trajectories with color gradient for time
    if a_ent:
        colors_a = plt.cm.Oranges(np.linspace(0.3, 1, len(a_ent)))
        ax1.scatter(a_ent, a_breath_norm, a_amp_norm, c=colors_a, s=10, alpha=0.6, label='A (Son)')
        # Connect with lines
        ax1.plot(a_ent, a_breath_norm, a_amp_norm, color='#d95f02', alpha=0.3, linewidth=0.5)

    if b_ent:
        colors_b = plt.cm.Blues(np.linspace(0.3, 1, len(b_ent)))
        ax1.scatter(b_ent, b_breath_norm, b_amp_norm, c=colors_b, s=10, alpha=0.6, label='B (Mat)')
        ax1.plot(b_ent, b_breath_norm, b_amp_norm, color='#1b9e77', alpha=0.3, linewidth=0.5)

    ax1.set_xlabel('Entrainment')
    ax1.set_ylabel('Breath Rate (norm)')
    ax1.set_zlabel('Amplitude (norm)')
    ax1.set_title('Dyadic Phase Space\nFather & Son')
    ax1.legend()

    # 2D entrainment over time
    ax2 = fig.add_subplot(122)

    if a_ent:
        ax2.plot(a_ent, color='#d95f02', alpha=0.7, label='A (Son)', linewidth=1)
    if b_ent:
        ax2.plot(b_ent, color='#1b9e77', alpha=0.7, label='B (Mat)', linewidth=1)

    ax2.set_xlabel('Sample')
    ax2.set_ylabel('Entrainment')
    ax2.set_title('Entrainment Over Time')
    ax2.legend()
    ax2.set_ylim(0, 1)
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()

    # Save or show
    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"Saved to {output_path}")
    else:
        plt.show()

    return fig

if __name__ == "__main__":
    # Default to latest dyadic session
    session_file = Path("sessions/dyadic_2025-12-13_122906.jsonl")
    output_file = Path("viz/dyadic_phase_space.png")

    if len(sys.argv) > 1:
        session_file = Path(sys.argv[1])

    plot_dyadic_phase_space(session_file, output_file)
    print(f"\nOpen {output_file} to view the visualization.")
