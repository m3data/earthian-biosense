# Muse S Athena golden capture — 2026-07-27

Capture for SPEC-015 §Tests-first step 1. Device `MuseS-XXXX`, preset **p1035** (EEG4),
4 scalp channels `TP9, AF7, AF8, TP10` @ 256 Hz. Wearer: Mat. Captured on the Mac Studio.

## ⚠️ The recordings are LOCAL-ONLY and are not in this repo

This repo is **public**. Mat's biosignal data does not enter it — see the biometric-data
block in `.gitignore`. The two capture files below exist **only on the Mac Studio** at
this path and are gitignored. This README, the derived findings, and the protocol facts
are committed; the recordings are not.

Anyone cloning this repo will find this directory empty apart from this file. That is
intended. To reproduce the findings you need your own capture — the method is fully
described in `concepts/muse-athena-first-contact.md`.

| File (local-only) | What | How |
|---|---|---|
| `raw_20260727T202132.jsonl` | 1806 raw `273e0013` notifications, unix-stamped | hand-rolled `bleak`, our own handshake `h → p1035 → dc001 ×2` |
| `uv_20260727T202132.npz` | 11,580 samples of brainflow-decoded µV + timestamps | `MUSE_S_ATHENA_BOARD` (id 67), brainflow 5.22.2 |

> **Open question for Mat:** the aggregate physiological numbers retained below (alpha RMS,
> contact std, Berger ratios) are derived from his body, even though they are summary
> statistics serving a *device* characterisation — they are the evidence that pins the
> scaling constant. They have been kept for that reason. Say the word and they come out,
> at the cost of the corroboration record.

Line 1 of the `.jsonl` is a `_meta` object (preset, cue marks, control-characteristic
replies — all five `{"rc":0}`). Every subsequent line is one packet: `{t_unix, hex}`.
The `.npz` carries `data, marks, eeg_channels, eeg_names, ts_channel, fs`.

## Packet framing (validated against this capture)

Source: `muse-rs` 0.1.0 `src/parse.rs`, which credits OpenMuse's `decode.py`.

```
byte[0]      packet length
byte[1]      packet index;  bytes[2..6] device clock;  bytes[5..9] constant
byte[9]      FIRST sub-frame tag
bytes[10..14] 4-byte sub-frame metadata
bytes[14..]  first payload, then further [TAG][META4][PAYLOAD] triples
```

**All 1806 packets tile cleanly under this rule with zero resyncs** — strong evidence
the payload lengths below are right; a wrong length would desynchronise immediately.

| Tag | Sensor | Payload | Frames | Measured | Nominal | Cross-check |
|---|---|---|---|---|---|---|
| `0x11` | EEG 4ch | 28 B | 2968 | 63.55/s | 64/s | ×4 samples = **254.2 Hz** ≈ 256 ✓ |
| `0x34` | Optics 4ch | 30 B | 987 | 21.13/s | — | ×3 samples = **63.4 Hz** ≈ 64 ✓ |
| `0x47` | IMU | 36 B | 809 | 17.32/s | — | ×3 samples = **52.0 Hz** ≈ 52 ✓ |
| `0x53` | **DRL/REF** | 24 B | 232 | 4.97/s | 32 Hz | ×6 samples = 29.8 Hz (~7% under) |
| `0x88` | Battery | rest of packet | 45 | 0.96/s | ~0.2 Hz | |

> ⚠️ An earlier count in this file histogrammed `byte[9]` only and so saw just the
> **first** sub-frame per packet. Those numbers (EEG 797, optics 474, IMU 462, DRL 61,
> battery 12) were low by up to 3.7× and are superseded by the table above.

### `0x53` = DRL/REF — identified 2026-07-27

24-byte payload = **12 × u16 little-endian**, high byte constant `0x20` across all
2,784 values. Per-position means alternate exactly, so it is **2 interleaved channels
× 6 samples**:

```
even positions  mean 8242.8   std 1.35 LSB  (0.12 µV)
odd  positions  mean 8261.8   std 0.75 LSB  (0.07 µV)
```

14-bit mid-rail is **8192** — the value muse-rs subtracts before scaling EEG. Both
channels park 51 and 70 LSB above it (4.5 and 6.2 µV) and do not drift across the
session (start 8252.0, end 8252.2). **This independently corroborates the 14-bit
interpretation from the data itself**: a reference electrode should sit at mid-scale,
and it does, to within a few µV.

muse-rs **discards `0x53`** — it advances the cursor and emits no event. Adopting it
per ADR-015-1 therefore silently drops the reference channel. Whether that matters is
**open and untested**: DRL/REF stayed rock-stable (std ≤0.12 µV) through the same window
in which TP9 threw 200 µV of delta artifact, so in this session it did **not** co-vary
with the artifact and is not a ready-made artifact regressor. It may be a driven setpoint
rather than a measurement. Retaining it costs nothing; using it needs its own test.

## ⚠️ These two files are NOT sample-aligned

They are **sequential captures, ~40 s apart**, not one simultaneous session.

SPEC-015 REQ-015-5 assumes raw bytes and brainflow µV can be recorded from *one* live
capture. **Tested 2026-07-27 and that does not hold** with these tools on macOS:

- brainflow's trace logger dumps raw bytes for the **control** characteristic only
  (they decode to the firmware JSON); never for the `273e0013` data stream.
- Concurrent connection fails in **both orderings** — whichever client connects second
  cannot discover the peripheral, because a connected device stops advertising and both
  `bleak` and brainflow (SimpleBLE) find devices by scanning. Tested brainflow-first
  (bleak cannot find it) and bleak-first (brainflow `BOARD_NOT_READY_ERROR:7`).

So **sample-exact parity against brainflow is not available from this fixture.**
The decode-parity mechanism needs a decision — see the trace for the two-layer proposal.

## Physiological anchor (independent of any decoder)

Computed on the **eyes-closed** window, 1–40 Hz bandpassed. Alpha-band RMS:

```
TP9 9.7    AF7 3.7    AF8 4.1    TP10 10.7   µV
```

All within the plausible cortical-alpha range (~2–60 µV RMS). This **independently
corroborates brainflow's scaling** without trusting it: the classic 12-bit BE constant
(0.488 µV/LSB) versus 14-bit LE (~0.0885) differ by ~5.5×, which would put alpha RMS at
either ~0.7 or ~55 µV. Observed values sit where 14-bit LE predicts. Coarse — it would
not catch a 20% gain error — but it decisively rules out the specific confusion the spec
names, and it does so from physiology rather than from a second implementation.

## ⚠️ Do NOT use this capture as a Berger reference

The eyes-open baseline is artifact-contaminated. Delta-band (1–4 Hz) RMS, open → closed:
TP9 201.8 → 11.0, TP10 73.1 → 11.8, AF8 27.2 → 5.6. An 18× drop on TP9 is ocular/motion
artifact, not physiology.

Consequences, all measured on this file:

- Relative alpha (`8–13 / 1–40`, the metric the first-contact note recommends) reports
  posterior **9.75×**. Excluding delta from the denominator (`8–13 / 4–40`) drops it to
  **3.04×**. Most of the effect was a suppressed denominator.
- **Absolute** alpha power *decreased* eyes-open → eyes-closed on all four channels —
  anti-Berger. Blink/movement energy inflated the open condition across all bands.

The two metrics disagree in direction, so this capture cannot support a Berger claim
either way. The eyes-**closed** segment is clean and is the part used for the anchor above.

### Methodological correction to `muse-athena-first-contact.md`

That note recommends relative alpha as drift-robust. True for **contact** drift, which is
what it was validated against. But it is **biased for the eyes-open/closed contrast
specifically**, because ocular artifact is condition-dependent by construction — blinks
and saccades only occur with the eyes open — so the open denominator is systematically
inflated and the ratio with it. The 1.54× recorded on 2026-07-25 carries the same bias
and should be treated as directionally right, magnitude unverified.

For future Berger runs: use `8–13 / 4–40`, report absolute alpha alongside it, and reject
any epoch whose delta RMS exceeds the closed-condition baseline by more than ~3×.
