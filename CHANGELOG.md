# Changelog

All notable changes to EarthianBioSense are documented here.
Versioning is semantic; dates are ISO-8601.

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

**Status:** implementation complete and unit-tested on both engines. Live on-device validation (still/moving during real activity; egress firing before dropout) pending a paired session with the strap.

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
