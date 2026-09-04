# Changelog

All notable changes to EarthianBioSense are documented here.
Versioning is semantic; dates are ISO-8601.

## [0.6.1] — 2026-09-04

### Fixed — tick-raised field events carry the tick's timestamp (SPEC-009 REQ-005 v0.3)

`ble_reconnect` and `range_egress_warning` were stamped with a fresh `Local::now()`
a few ms after the sample they precede in the file (observed: event 14:05:13.051
before sample 14:05:13.050). A downstream monotonic reader (vibe-harness-mcp
SPEC-003) saw a 1 ms backward clock step at every reconnect. Both events now use
the tick's own `ts` via `SessionLogger::log_field_event_at`. `ble_link_lost`
keeps detection time. Tests: Rust 80.

## [0.6.0] — 2026-09-04

### Added — BLE auto-reconnect (SPEC-009 REQ-005)

REQ-005 had been carried unimplemented from the Python client into the Tauri
port. Observed live 2026-09-04: the operator walked out of range with the strap
on, the last sample landed at 12:54:25, and the session file stayed silent after
they returned because nothing attempted to reconnect. This release closes that.

- **Detection by watchdog** (`desktop/src-tauri/src/ble/reconnect.rs`) — the H10 notifies HR at ~1 Hz; no HR notification for `LINK_WATCHDOG = 5 s` ⇒ link lost. Independent of CoreBluetooth's own disconnect signalling, which can lag by many seconds.
- **Reconnect cycle** (`lib.rs`) — exponential back-off 1, 2, 4, 8, 16 s then every 30 s; each attempt clones the adapter handle out of `AppState` and releases the lock before any BLE await, re-looks-up the peripheral, rescans for 2 s if the adapter no longer lists it, tears down a stale CoreBluetooth link if the OS still believes it connected, and re-subscribes HR + PMD ACC. One attempt is bounded at 20 s; on expiry a bounded (3 s) best-effort `disconnect()` teardown runs. `cmd_disconnect` cancels the cycle immediately — stop wins mid-back-off and mid-attempt; no attempt runs after stop.
- **One live stream at a time** — every notification listener carries a generation flag (`StreamAlive`, an `Arc<AtomicBool>`). The previous generation is retired at link-lost detection, before any attempt; a retired listener discards anything it still receives (HR and ACC) and exits, so a stale link can neither duplicate samples nor keep the watchdog alive.
- **Connection generations** — `cmd_connect` mints a monotonically increasing generation in `AppState`; the processing task emits its terminal `ebs:device-status` and runs attempt-timeout teardown only while it still owns the current generation, so an old task can never overwrite a newer connection's UI state or disconnect its peripheral. Every channel message carries a per-stream sub-generation (incremented on each successful reconnect); the loop discards messages from any other generation, so a notification queued by a retired listener is never consumed as fresh. The shared ACC buffer is cleared on reconnect success.
- **Disconnect awaits the task** — `cmd_disconnect` sends stop, then awaits the processing task's `JoinHandle` (bounded, 5 s) before clearing `active`, so disconnect→immediate connect never overlaps a task still tearing down. `cmd_connect` and `cmd_disconnect` hold a lifecycle mutex for their whole body, so concurrent lifecycle commands serialise (a second disconnect waits, finds nothing to stop, returns Ok). Attempt-timeout teardown is `select!`ed against stop and abandoned once stop fires.
- **Supervision** — a single deadline `supervision_deadline(last_sample_at, reconnected_at)`: last sample + 5 s when a sample exists (link lost → `ble_link_lost`, cycle); reconnect + `ESTABLISH_TIMEOUT` 10 s when a reconnected stream has produced no HR sample yet (attempt deemed failed after the fact, cycle resumes with the next back-off, **no second `ble_link_lost`**, no new `connected:false`); unarmed on the initial connect before the first sample (pre-existing behaviour, residue). Reconnect success never re-arms the sample watchdog with a fabricated sample.
- **Two JSONL `field_event`s, written to the same session file** — `ble_link_lost` at detection with `last_sample_ts` (RFC 3339 of the last HR sample) and `watchdog_secs`; `ble_reconnect` on the first HR sample of the restored stream (not at `connect()`) with `gap_ms` (last sample → that first sample) and `attempts` — exactly one per `ble_link_lost`; an attempt that connected but never produced a sample writes nothing. `ble:reconnected` fires at the same moment. The session continues across the gap; no new file, no `stop_session`/`start_session`. `SessionLogger::log_field_event_with` merges structured fields beside `note` and never lets them override `type`/`ts`/`event`/`note`.
- **IPC** — `ebs:device-status` gains an additive boolean `reconnecting` (CON-002): `connected:false, reconnecting:true` at detection, `connected:true, reconnecting:false` only on the first HR sample of the new stream (never at `connect()`, so a reconnect that never produces a sample never shows green), `connected:false, reconnecting:false` when the relay stops on user disconnect. The UI derives the status dot from this one event (amber = `!connected && reconnecting`); `ble:reconnecting {attempt, delay_secs, since_ts}` and `ble:reconnected {gap_ms, attempts}` are informational log lines.
- **Schema** — unchanged at **1.5.0** (additive: two new `event` names; readers that know only `type`/`event`/`note` still parse them; detect by `event`, not version).

Tests: Rust 79 passed (62 + 17 new: TEST-005a–g). The btleplug wiring is exercised live (walk to the kitchen and back), not by unit test.

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
