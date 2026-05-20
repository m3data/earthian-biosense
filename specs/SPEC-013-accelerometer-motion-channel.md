# SPEC-013 — Accelerometer / Motion Channel (Polar PMD)

**Status:** v0.1 draft
**Created:** 2026-05-20
**Author:** Mat Mytka + Kairos
**Scope:** Capture the Polar H10's onboard 3-axis accelerometer via the proprietary PMD service, derive a motion channel, and use it to (a) flag motion-confounded mode classifications and (b) act as a leading indicator of BLE range egress. Adds the first non-cardiac signal dimension to EBS.

---

## Background — why this matters

Every EBS dimension to date — entrainment, breath, amplitude, all six phase modes — is derived from the **RR-interval time series alone**. The H10 client (both `src/ble/h10_client.py` and the Rust `desktop/src-tauri` backend) subscribes only to the standard Heart Rate Service (`0x180D` / char `0x2A37`).

Consequence: EBS cannot distinguish *HR elevated by physical exertion* (kettlebell, walking, fidget) from *HR elevated by affective/cognitive arousal*. They are near-identical in cardiac features. The mode taxonomy is therefore **valid in stationary work and confounded the instant the body moves** — and we have no signal that tells us which regime a given sample is in.

The H10 carries a 3-axis accelerometer exposed on Polar's PMD (Polar Measurement Data) service. It is currently unused. Adding it gives EBS the one thing that disambiguates the confound: ground truth on whether the body is moving.

Two distinct payoffs:

1. **Confound correction.** A `motion_confounded` flag lets the mode classifier annotate (or downweight) readings taken during movement, drawing the boundary of validity explicitly rather than silently mislabelling exercise tachycardia as "heightened alertness."
2. **Range-egress leading indicator.** Motion *precedes* BLE signal loss. A sustained motion signature (e.g. standing, walking toward the kitchen) is detectable seconds before the link degrades — turning an abrupt dropout into a predictable, annotatable transition. Movement away from the desk becomes a labelled event rather than a data gap of unknown cause.

A third, downstream payoff (see §Calibration): known activities become **labelled ground truth** for validating how well the mode taxonomy represents nervous-system state.

---

## Goal

When ACC capture is enabled, an EBS session records a per-tick motion summary alongside the existing cardiac/phase fields, and the pipeline exposes:
- `motion_mag` — scalar motion intensity over the tick window
- `motion_state` — `still | moving` (gated)
- `motion_confounded` — boolean attached to the mode classification
- a `range_egress_warning` event when sustained motion suggests imminent dropout

The raw ~Hz ACC stream is aggregated to the existing 1 Hz sample cadence. Full-rate raw ACC is **not** stored by default (bloat); an optional raw side-log is gated behind a flag.

## Non-goals (v0.1 of this feature)

- Activity *classification* (walking vs lifting vs typing) — only still/moving gating
- Gait analysis, step counting, posture estimation
- Storing full-rate raw ACC in the primary session JSONL by default
- iOS PMD capture (separate surface; the iOS app has its own acquisition path)
- Real-time feed of motion into Claude context (that is the live-coupling thread, tracked separately)
- ECG capture (also on PMD; out of scope here)

---

## BLE — PMD ACC acquisition

The H10 supports concurrent HR (`0x180D`) **and** PMD notifications. ACC capture is added alongside the existing HR subscription, not in place of it.

**Service / characteristics:**

| Role | UUID |
|------|------|
| PMD Service | `FB005C80-02E7-F387-1CAD-8ACD2D8DF0C8` |
| PMD Control Point (write + indicate) | `FB005C81-02E7-F387-1CAD-8ACD2D8DF0C8` |
| PMD Data (notify) | `FB005C82-02E7-F387-1CAD-8ACD2D8DF0C8` |

**Start sequence:**

1. Discover PMD service; subscribe (indicate) to the Control Point and (notify) to Data.
2. Write a **start-measurement** command to the Control Point:
   - `[0x02 (op=start), 0x02 (type=ACC), <settings TLV…>]`
   - Settings are `[setting_type(1), array_len(1), value(2·len, little-endian)]`:
     - `0x00` sample rate — H10 supports `25 | 50 | 100 | 200` Hz
     - `0x01` resolution — `16` bit
     - `0x02` range — `2 | 4 | 8` g
   - **v0.1 default: 50 Hz, 16-bit, ±4 g.** 50 Hz is ample for still/moving gating and range-egress detection while keeping decode/aggregation cheap.
3. Control Point replies via indication: `[0xF0, op, type, status, …]`. Treat non-zero status as a hard failure → log, fall back to HR-only (feature must degrade gracefully; ACC is additive).
4. On stop / session end: write `[0x03 (op=stop), 0x02 (type=ACC)]`.

**Data frame parsing (EMPIRICALLY CONFIRMED — see fixture `tests/fixtures/pmd_acc/pmd_acc_2026-05-20_170219.jsonl`):**

PMD Data notifications for ACC arrive as:
`[measurement_type(1)=0x02, timestamp(8, uint64 ns, LE), frame_type(1), payload…]`

At the v0.1 config (50 Hz / 16-bit / ±4 g) the H10 sends `frame_type = 0x01` with an **uncompressed payload**: contiguous signed 16-bit little-endian XYZ triples (6 bytes/sample) in **milli-g**. At 50 Hz the device batches **36 samples per frame** (226-byte frame: 10-byte header + 216-byte payload). Decode is `struct.unpack('<hhh', …)` per 6 bytes — no delta unpacking required.

> Earlier draft assumed delta-frame compression and flagged bit-unpacking as the risk. Capturing real frames first (tests-first) disproved that assumption for this config. **Caveat:** other resolutions/frame_types *may* use compressed formats; if we ever change resolution we re-capture and re-confirm. The golden-vector test guards this.

Validation from the captured fixture: 22 frames, 792 samples, rest magnitude min 926 / mean 991 / max 1068 mg — i.e. ≈ 1 g gravity vector, exactly as expected for a near-stationary strap.

---

## Motion feature derivation

Per ACC sample (XYZ, signed, in milli-g at the configured range):

1. **Gravity removal** — high-pass / running-mean subtraction to isolate dynamic acceleration from the static gravity vector.
2. **Magnitude** — `‖(x,y,z)_dynamic‖`.
3. **Tick aggregation** — RMS of per-sample magnitude over the 1 Hz tick window → `motion_mag`.
4. **Gating** — `motion_state = moving` when `motion_mag` exceeds a calibrated threshold for a minimum dwell (debounced to avoid single-sample flips); else `still`. Threshold is a named constant, calibrated empirically on first real sessions (mirrors how `ACCELERATION_THRESHOLD` is handled in `movement.py`).

**Confound flag.** `motion_confounded = (motion_state == moving)` is attached to each emitted phase/mode record. The classifier itself is unchanged in v0.1 — we *annotate*, we don't yet re-weight. Re-weighting/suppression is a v0.2 decision once we see real motion/mode co-occurrence.

**Range-egress warning.** Sustained `moving` (motion above threshold for N consecutive ticks) emits a `range_egress_warning` event. Optional enhancement: combine with BLE RSSI trend if exposed by the transport. v0.1 is motion-only; RSSI is an open question (§Open questions).

---

## Schema additions

Per-sample (`ebs:phase` / JSONL tick) record gains an optional `motion` object:

```json
{
  "motion": {
    "mag": 0.042,
    "state": "still",
    "confounded": false,
    "sample_rate_hz": 50,
    "n_samples": 50
  }
}
```

And the mode/phase block gains `motion_confounded: false` for join-friendly filtering.

New event record type:

```json
{ "type": "range_egress_warning", "ts": "…", "motion_mag": 0.31, "sustained_ticks": 4 }
```

**Schema version** bumps to `1.3.0` (movement-preserving 1.1.0 → SPEC-010 session_start 1.2.0 → motion 1.3.0). All new fields optional; sessions recorded with ACC disabled or unavailable are byte-for-byte unchanged and remain valid.

---

## Implementation surfaces (dual engine)

Live sessions run on the **Rust** path; Python is the diagnostic/parity client. Both get the feature; Rust is primary.

**Rust (`desktop/src-tauri`) — primary:**
- `src/ble/mod.rs` — discover PMD, subscribe CP + Data, write start/stop commands
- `src/ble/parser.rs` — `parse_pmd_acc_frame` (delta-frame decode)
- new `src/motion/mod.rs` — gravity removal, magnitude, gating, range-egress detection
- `src/lib.rs` — fold `motion` into `PhaseEvent` (the 1 Hz emit) + session log; emit `ebs:range_egress_warning`

**Python (`src/`) — parity:**
- `src/ble/pmd_client.py` (or extend `h10_client.py`) — bleak PMD start/stop + notify
- `src/ble/parser.py` — `parse_pmd_acc_frame`
- `src/processing/motion.py` — feature derivation (mirror Rust)
- wire into the existing event-bus / session logger

The two decoders share **golden frame vectors** (captured once, checked into `tests/fixtures/pmd_acc/`) so Rust and Python provably decode identical bytes to identical samples.

---

## Tests-first plan

Per project convention, failing tests precede implementation.

1. **Capture golden frames.** A throwaway capture script subscribes to PMD ACC on a live H10 and dumps raw Data-characteristic bytes + the negotiated settings to `tests/fixtures/pmd_acc/`. (One-time, requires the strap — Mat at the Mac.)
2. **Decoder tests (both engines).** Feed golden frames → assert reconstructed XYZ matches hand-verified expected samples. This is the load-bearing test; the delta-frame bit-unpacking is where bugs hide.
3. **Motion-feature tests.** Synthetic XYZ sequences (still, steady motion, spike) → assert `motion_mag`, debounced `motion_state`, `range_egress_warning` firing.
4. **Schema tests.** ACC-disabled session is unchanged; ACC-enabled session validates against 1.3.0; old sessions still load.
5. **Graceful degradation.** PMD start failure / service absent → HR-only session, no crash, logged warning.

---

## Calibration (downstream use, not in this build)

Once motion is captured, run **labelled-activity sessions**: Mat performs known activities (stationary think-with, kettlebell, walking to the kitchen) with timestamps, against clock time now available in the JSONL. Then:
- Confirm the classifier mislabels exertion as arousal in the way we predict (the confound, made visible)
- Quantify how much of "heightened alertness" in real sessions is motion vs affect
- Establish where the mode taxonomy is trustworthy (still) vs annotated-suspect (moving)

This is the move that tells us *what the modes are actually worth*. The kettlebell flips from confound to instrument.

---

## Open questions

- **RSSI exposure.** Does btleplug (Rust) / bleak (Python) expose live RSSI on a connected peripheral on macOS? If yes, fuse with motion for a stronger range-egress predictor. If no, motion-only for v0.1.
- **Sample rate.** Is 50 Hz the right default, or is 25 Hz enough for gating (cheaper) / 100 Hz needed for clean gravity separation? Decide empirically on golden-frame capture.
- **Battery cost.** PMD streaming draws more power than HR-only. Quantify on a long session; may inform a "motion on demand" rather than always-on default.
- **Concurrent PMD + HR stability.** Confirm the H10 sustains both subscriptions over a long session without dropping HR notifications.
- **Gravity-removal method.** Running-mean vs Butterworth high-pass — pick on real data; running-mean is the simpler default.

---

## Acceptance for v0.1

1. Golden PMD ACC frames captured from a live H10 and checked into fixtures
2. Both Rust and Python decoders reconstruct identical XYZ from the golden frames (tests green)
3. A live session with ACC enabled writes `motion` fields at 1 Hz and is schema-1.3.0 valid
4. `motion_state` correctly reads `still` during stationary work and `moving` during a deliberate kettlebell/walk segment (eyeball + threshold check)
5. `range_egress_warning` fires before the link drops when Mat walks out of range
6. ACC-disabled sessions are byte-for-byte unchanged; degradation on PMD failure is graceful

Once these hold on one live session, v0.1 is done. Confound re-weighting and the full calibration study are downstream.
