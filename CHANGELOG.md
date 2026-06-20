# Changelog

All notable changes to EarthianBioSense are documented here.
Versioning is semantic; dates are ISO-8601.

## [0.5.0] — 2026-06-20

### Added — Two-axis mode classification (SPEC-014)

A second, orthogonal classification axis. Until now the six autonomic modes were
bins along a single scalar (`calm_score` — stillness/entrainment); the project's
own key distinction, *coherence is not entrainment*, was absent from the
classifier. `trajectory_coherence` was computed, logged, and streamed every tick
but never reached the mode decision — despite being empirically orthogonal to
`calm_score` (corr +0.001 across 36 sessions / 15,909 records). This release adds
soft membership over a 2-D (stillness × trajectory-coherence) plane as an
additive field; the existing 1-D mode is untouched.

- **2-D classifier** (Python `src/processing/movement.py`, Rust `desktop/src-tauri/src/hrv/movement.rs`) — `compute_2d_mode_membership(calm, coherence)` over five provisional modes (reactive, engaged, transitional, constrained stillness, settled presence); softmax on equal-weighted plane distance. Centroids/temperature mirrored across both engines.
- **Wiring** — computed right after `trajectory_coherence` (consuming the same canonical value that is logged and streamed), in `src/app.py` and `desktop/src-tauri/src/lib.rs`.
- **Replay viz** — a "two-axis field" panel (opt-in, delayed-revelation) in both frontends: ambiguity rendered as marker softness, no evaluative encoding, a fading trajectory trail, a breathing marker. Live channels (Python WebSocket `phase` message, Rust `ebs:phase` event) carry `mode_score` + `soft_mode_2d`.
- **Schema** — additive `phase.soft_mode_2d` object (primary/secondary/ambiguity/distribution_shift/membership). Python **1.2.0 → 1.4.0**; Rust desktop **1.4.0 → 1.5.0** (independent lineages — same feature, different version string; detect by the field, not the version). Pre-feature sessions omit it and remain valid.

Tests: Python 135 passed (incl. the WebSocket wire contract), Rust 62 passed.

**Validated** on replay over 15,909 real records: the ambiguity field de-saturates
(1-D pinned at 0.996 → 2-D 0.336–1.000); old "subtle alertness" splits 50% reactive
/ 45% transitional / 5% engaged; 21% of old "settling" is actually `constrained
stillness` (settled but brittle) — a cut the 1-D ladder could not make.

A clean-context adversarial review (USDD P12) caught two bugs the build missed,
both fixed in this release: a cross-session `distribution_shift` state-leak in
both engines' `reset()`, and a warm-up mislabel in the replay fallback. Provisional
label set and a single-source-of-truth dedupe for the duplicated centroids are
tracked in SPEC-014.

## [0.4.0] — 2026-05-20

### Added — Accelerometer / motion channel (SPEC-013)

The first non-cardiac signal dimension. Until now every EBS metric was derived
from the RR-interval series alone, so the mode classifier could not distinguish
HR elevated by *movement* from HR elevated by *arousal*. This release reads the
Polar H10's onboard accelerometer over the proprietary PMD service and derives a
motion channel to disambiguate the two.

- **PMD ACC decoder** (Python `src/ble/parser.py`, Rust `desktop/src-tauri/src/ble/parser.rs`) — decodes uncompressed 16-bit XYZ frames; format confirmed empirically against real device capture (see `tests/fixtures/pmd_acc/`).
- **Motion processor** (Python `src/processing/motion.py`, Rust `desktop/src-tauri/src/motion/`) — per-tick gravity removal (EMA), RMS magnitude, debounced still/moving gate, and a range-egress warning (sustained motion as a leading indicator of BLE dropout).
- **Desktop app** now negotiates and streams ACC alongside HR (additive; degrades to HR-only if PMD is unavailable). Motion folds into the 1 Hz phase event and JSONL; emits `ebs:range_egress_warning`.
- **Capture tool** `scripts/capture_pmd_acc.py` for pulling raw golden frames.
- **Schema 1.3.0** — per-tick `motion` object (`mag`, `state`, `confounded`, `n_samples`) plus `phase.motion_confounded`. All fields optional; ACC-disabled and pre-1.3.0 sessions remain valid.

Tests: Python 112 passed, Rust 50 passed (both decoders verified; Python against real device bytes).

**Live-validated** 2026-05-20 (`desktop/sessions/2026-05-20_182805.jsonl`): a desk → handpan → desk session produced schema-1.3.0 records with motion on every tick, `state` tracking still/moving across the real movement, `motion_confounded` flipping accordingly, and `range_egress_warning` firing on both sustained-movement episodes (and correctly not on a 2-tick blip).

### Maintenance
- Aligned desktop app version (Cargo + Tauri config) to the project version (was 0.1.0).
- Refreshed CITATION.cff and .zenodo.json to 0.4.0.

## [0.3.2] — 2026-04-13
- fix(hrv): stop clobbering `state_status` on mode transitions.

## [0.3.1] — 2026-04-13
- fix(desktop): write HRV samples to session JSONL during recording.

## [0.3.0] — 2026-04-09
- feat: Tauri v2 macOS desktop app for long-duration HRV collection (Rust port of the Python pipeline).

## [0.2.2] — 2026-03-14
- Add `.zenodo.json` for Zenodo DOI minting.

[0.4.0]: https://github.com/m3data/earthian-biosense/releases/tag/v0.4.0
[0.3.2]: https://github.com/m3data/earthian-biosense/releases/tag/v0.3.2
[0.3.1]: https://github.com/m3data/earthian-biosense/releases/tag/v0.3.1
[0.3.0]: https://github.com/m3data/earthian-biosense/releases/tag/v0.3.0
[0.2.2]: https://github.com/m3data/earthian-biosense/releases/tag/v0.2.2
