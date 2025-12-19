#!/usr/bin/env python3
"""
Demo script for Chimera Ecology.

Loads your seed vocabulary and demonstrates:
- Vocabulary loading with niche inference
- Sanctuary creation and initial seeding
- Chimera crystallization
- Evolution (drift, niche pressure, speciation)
- Threshold detection simulation
"""

from pathlib import Path

from .types import ChimeraState, Niche
from .vocabulary import load_seed_vocabulary, print_vocabulary_summary, create_sanctuary_from_seed
from .ecology import SanctuaryManager
from .evolution import evolve_sanctuary
from .threshold import detect_threshold, get_threshold_context
from .encounter import on_witnessed, on_refused, get_encounter_summary


def run_demo():
    """Run a demonstration of the Chimera ecology system."""

    print("=" * 60)
    print("CHIMERA ECOLOGY DEMO")
    print("Baradian poetry for rewilding the ANS")
    print("=" * 60)
    print()

    # Path to seed vocabulary
    seed_path = Path(__file__).parent.parent.parent.parent / "tools" / "species-browser" / "seed_vocabulary_2025-12-14.json"

    if not seed_path.exists():
        print(f"Seed vocabulary not found at: {seed_path}")
        print("Please export your vocabulary from the species-browser first.")
        return

    # Load vocabulary
    print("Loading seed vocabulary...")
    species_list, country = load_seed_vocabulary(seed_path)
    print(f"Country: {country.name}")
    print()

    print_vocabulary_summary(species_list)

    # Create sanctuary
    print("\n" + "=" * 60)
    print("CREATING SANCTUARY")
    print("=" * 60)

    sanctuary = create_sanctuary_from_seed(seed_path)
    manager = SanctuaryManager(sanctuary)

    print(f"Sanctuary created with {len(sanctuary.species_vocabulary)} species")
    print(f"Empty niches: {len(sanctuary.empty_niches)}")

    # Seed initial chimeras
    print("\nSeeding initial chimeras...")
    initial_chimeras = manager.seed_initial_chimeras(count=7)

    for chimera in initial_chimeras:
        display_name = manager.get_chimera_display_name(chimera)
        niche = chimera.niche.value if chimera.niche else "none"
        print(f"  - {display_name} [{niche}]")
        print(f"    Components: {chimera.components}")
        print(f"    Weights: {[f'{w:.2f}' for w in chimera.weights]}")

    print(f"\nNiche coverage: {len(sanctuary.niche_coverage)}/{len(Niche)} niches")

    # Simulate evolution
    print("\n" + "=" * 60)
    print("SIMULATING EVOLUTION (24 hours)")
    print("=" * 60)

    result = evolve_sanctuary(sanctuary, time_delta_hours=24)

    print(f"Chimeras drifted: {result['stats']['chimeras_drifted']}")
    print(f"Speciation events: {result['stats']['speciation_events']}")
    print(f"Niche pressure events: {result['stats']['niche_pressure_events']}")

    if result['events']:
        print("\nEvents:")
        for event in result['events'][:10]:
            print(f"  - {event}")

    # Simulate threshold detection
    print("\n" + "=" * 60)
    print("SIMULATING THRESHOLD DETECTION")
    print("=" * 60)

    # Simulate different phase states
    test_states = [
        {
            "name": "Alert stillness",
            "phase": {"phase_label": "alert stillness", "velocity_mag": 0.03, "curvature": 0.1, "stability": 0.7, "coherence": 0.4},
            "hrv": {"entrainment": 0.5}
        },
        {
            "name": "Active transition",
            "phase": {"phase_label": "active transition", "velocity_mag": 0.15, "curvature": 0.25, "stability": 0.3, "coherence": 0.3},
            "hrv": {"entrainment": 0.3}
        },
        {
            "name": "Coherent dwelling",
            "phase": {"phase_label": "coherent dwelling", "velocity_mag": 0.02, "curvature": 0.05, "stability": 0.8, "coherence": 0.6},
            "hrv": {"entrainment": 0.6}
        },
        {
            "name": "Inflection seeking",
            "phase": {"phase_label": "inflection (seeking)", "velocity_mag": 0.08, "curvature": 0.35, "stability": 0.35, "coherence": 0.25},
            "hrv": {"entrainment": 0.2}
        },
    ]

    for state in test_states:
        print(f"\nPhase state: {state['name']}")

        # Clear threshold history for demo
        sanctuary.threshold_history = []

        candidate = detect_threshold(
            state["phase"],
            state["hrv"],
            sanctuary,
            cooldown_minutes=0  # Disable cooldown for demo
        )

        if candidate:
            display_name = manager.get_chimera_display_name(candidate)
            niche = candidate.niche.value if candidate.niche else "none"
            print(f"  -> Threshold detected: {display_name} [{niche}]")

            # Simulate witness/refuse
            if state["name"] in ["Coherent dwelling", "Alert stillness"]:
                print("  -> [Simulating: Witnessed]")
                encounter = on_witnessed(candidate, sanctuary, state["phase"])
                print(f"     Chimera stabilized. Encounter count: {candidate.encounter_count}")
            else:
                print("  -> [Simulating: Refused]")
                threshold_event = on_refused(candidate, sanctuary, state["phase"])
                print(f"     Chimera returns to sanctuary. Drift rate: {candidate.drift_rate:.2f}")
        else:
            print("  -> No threshold detected")

    # Summary
    print("\n" + "=" * 60)
    print("SANCTUARY SUMMARY")
    print("=" * 60)

    summary = get_encounter_summary(sanctuary)
    print(f"Total thresholds: {summary['total_thresholds']}")
    print(f"Total witnessed: {summary['total_witnessed']}")
    print(f"Total refused: {summary['total_refused']}")
    print(f"Witness rate: {summary['witness_rate']:.1%}")

    print(f"\nChimeras by state:")
    for state in ChimeraState:
        count = sum(1 for c in sanctuary.chimeras if c.state == state)
        if count > 0:
            print(f"  {state.value}: {count}")

    print(f"\nDiversity index: {manager.compute_diversity_index():.2f}")

    # Save sanctuary
    save_path = Path(__file__).parent.parent.parent.parent / "sessions" / "sanctuary_demo.json"
    save_path.parent.mkdir(exist_ok=True)
    manager.save(save_path)
    print(f"\nSanctuary saved to: {save_path}")


if __name__ == "__main__":
    run_demo()
