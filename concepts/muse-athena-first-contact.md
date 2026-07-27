# Muse S Athena — First Contact & Working Handshake

**Status:** Reference recipe (verified live)
**Authors:** Mat Mytka & Kairos
**Date:** 2026-07-25
**Scope:** How to actually get decoded EEG off a Muse S *Athena* headband. Companion to `muse-s-integration-concept.md`, which sets the research frame; this note is the "here's how you talk to her" that unblocks it.

---

## TL;DR

The Muse S **Athena** (2025 model) speaks a **new BLE protocol (version 4)** that the classic Muse tooling cannot drive. Two working paths, both validated live on device `MuseS-XXXX`:

1. **brainflow** (recommended for getting signal now) — `BoardIds.MUSE_S_ATHENA_BOARD` (id `67`), added in brainflow ≥ 5.22.0. Decodes to microvolts, handles the twice-sent start command, exposes presets. *No fork needed.*
2. **Hand-rolled `bleak`** (for owning the raw protocol) — handshake `h → p1035 → dc001`, data multiplexed on characteristic `273e0013`.

Validated with a clean **Berger effect** (eyes-closed posterior alpha ↑ 1.54×) — the signal is real and calibrated, not decode noise.

---

## Why the stock tooling fails

The Athena rewrote its BLE interface. Symptoms and root causes we confirmed:

- **brainflow's legacy `MUSE_S_BOARD` (id 39) connects but streams 0 samples.** Its log shows `failed to send command h to device`. Cause: the Athena's control characteristic is **write-*without*-response**; the legacy board writes *with* response, so every command silently fails.
- **The classic `d` "start streaming" command is rejected** — the device replies `{"rc":255}`. Protocol v4 replaced it with `dc001`.
- The old **per-electrode characteristics (`273e0003`–`0007`) are gone.** All sensors are multiplexed onto one notify characteristic.

## Device facts (this unit)

```
name: MuseS-XXXX     serial: <redacted — persistent device identifier>
fw: 3.1.23           hw: sp=Athena_RevE / hb=Athena_RevF_NW
protocol version: 4
service UUID: 0000fe8d-0000-1000-8000-00805f9b34fb
```

The advertised name is `MuseS-` plus the last four of the unit's serial. Substitute your
own throughout — nothing here depends on which physical unit it is. Serials and BLE
addresses are persistent identifiers and stay out of this public repo.

## GATT map (Athena — only 4 characteristics)

| Characteristic | Properties | Role |
|---|---|---|
| `273e0001-…` | write-without-response, notify | **Control** (commands out, JSON replies in) |
| `273e0013-…` | notify | **Multiplexed data stream** (EEG/IMU/optics) |
| `273e0014-…` | indicate, write | (control/aux — unused by us) |
| `273e0015-…` | write-without-response, notify | secondary data/notify |

## Control command framing

Each command is length-prefixed and newline-terminated, written **without response**:

```python
def frame(cmd: str) -> bytearray:
    b = bytearray([len(cmd) + 1]); b.extend(cmd.encode()); b.append(0x0A); return b
# await client.write_gatt_char(CTRL, frame("dc001"), response=False)
```

Useful control queries (reply as JSON on `273e0001`):
- `v6` → firmware/hardware version block
- `s`  → status (serial, battery `bp`, preset state `ps`)
- `h`  → halt streaming (`{"rc":0}`)

## The handshake

```
h          # halt / reset
p1035      # preset (see table) — accepted: {"rc":0}
dc001      # START. Send TWICE (community + brainflow both confirm; one send
           #   worked for us on-head but twice is the robust form)
```

Data then flows on `273e0013`: ~39 packets/s, ~4 KB/s.

### Packet structure (validated 2026-07-27 against 1,806 captured packets)

```
byte[0]       = packet length
byte[1]       = packet index (monotonic, watch for drops)
bytes[2:6]    = device clock;  bytes[5:9] constant per session
byte[9]       = FIRST sub-frame tag
bytes[10:14]  = 4-byte sub-frame metadata
bytes[14:]    = first payload, then further [TAG][META4][PAYLOAD] triples
```

**A packet carries several sub-frames, not one.** Each subsequent sub-frame repeats the
1-byte tag + 4-byte metadata header before its payload. Counting `byte[9]` alone — the
obvious first move, and the one we made — sees only the first sub-frame and undercounts
by up to 3.7×.

| Tag | Sensor | Payload | Layout | Nominal |
|---|---|---|---|---|
| `0x11` | EEG 4ch | 28 B | 14-bit LE packed, 4 samples × 4 ch, sample-major | 256 Hz |
| `0x12` | EEG 8ch | 28 B | 8 ch, 2 samples | 256 Hz |
| `0x34` | Optics 4ch | 30 B | 20-bit LE, 3 samples × 4 ch | 64 Hz |
| `0x35` / `0x36` | Optics 8/16ch | 40 B | | 64 Hz |
| `0x47` | IMU | 36 B | i16 LE, accel + gyro, 3 samples × 6 ch | 52 Hz |
| `0x53` | **DRL/REF** | 24 B | 12 × u16 LE = 2 ch × 6 samples | ~32 Hz |
| `0x88` | Battery (new fw) | rest of packet | u16 LE ÷ 256 = % | ~0.2 Hz |
| `0x98` | Battery (old fw) | 20 B | | 1 Hz |

Verification that these lengths are right: under this rule **all 1,806 packets tile with
zero resyncs**, and three tags independently land on their documented rate — EEG 63.55
frames/s × 4 = 254.2 Hz, optics 21.13 × 3 = 63.4 Hz, IMU 17.32 × 3 = 52.0 Hz. A wrong
payload length desynchronises immediately, so clean tiling is a real check, not a
formality. Source for the tag table: `muse-rs` 0.1.0 `src/parse.rs`, crediting OpenMuse's
`decode.py`.

### `0x53` — DRL/REF, and why it matters

The reference/driven-electrode channel. 24 B = 12 × u16 LE; per-position means alternate
exactly (even 8242.8, odd 8261.8), so it is two interleaved channels of six samples.
Both are extremely quiet — std 1.35 and 0.75 LSB, i.e. 0.12 and 0.07 µV — and do not
drift across a session.

**They park at 14-bit mid-rail.** Mid-scale for 14 bits is 8192, the constant muse-rs
subtracts before scaling; the two channels sit 51 and 70 LSB above it (4.5 and 6.2 µV).
A reference electrode resting at mid-scale is what a 14-bit ADC predicts and is not
producible by a 12-bit reading — so this channel corroborates the resolution *on its own*,
without trusting any decoder.

**muse-rs discards `0x53`** (advances the cursor, emits no event). Adopting it under
SPEC-015 ADR-015-1 therefore silently drops the reference. Whether that costs anything is
**untested**: in the 2026-07-27 capture DRL/REF stayed flat to within 0.12 µV during the
same window in which TP9 threw 200 µV of delta artifact, so it did *not* track the
artifact and is not a ready-made regressor for it. It may be a driven setpoint rather
than a measurement. Retaining it is free; using it needs its own experiment.

### Preset table (verified against brainflow / OpenMuse / muse-rs)

| Preset | EEG | Optics | ACC/GYRO | LED | Notes |
|---|---|---|---|---|---|
| `p21`, `p50`, `p60`… | EEG4 | — | yes | off | EEG-only |
| `p1035` | EEG4 | Optics4 | yes | dim | **what we used** |
| `p1041` | EEG8 | Optics16 | yes | bright | OpenMuse/brainflow default "all channels" |
| `p1045` | EEG8 | Optics4 | yes | dim | muse-rs default |
| `p1034`,`p1043`,`p1044` | EEG8 | Optics8 | yes | bright/dim | |

## Path 1 — brainflow (get signal now)

```python
import time, numpy as np
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds

p = BrainFlowInputParams()
p.serial_number = "MuseS-XXXX"                 # disambiguate by advertised name
p.other_info    = "preset=p1035;low_latency=true"
b = BoardShim(BoardIds.MUSE_S_ATHENA_BOARD, p)  # id 67, needs brainflow >= 5.22.0
b.prepare_session(); b.start_stream()
time.sleep(8)
d = b.get_board_data(); b.stop_stream(); b.release_session()

eeg   = BoardShim.get_eeg_channels(BoardIds.MUSE_S_ATHENA_BOARD)   # rows for TP9,AF7,AF8,TP10
names = BoardShim.get_eeg_names(BoardIds.MUSE_S_ATHENA_BOARD)
fs    = BoardShim.get_sampling_rate(BoardIds.MUSE_S_ATHENA_BOARD)  # 256 Hz
```

Notes:
- Channels: `['TP9','AF7','AF8','TP10']` at 256 Hz. Optics/IMU come on AUXILIARY / ANCILLARY presets — see brainflow's Athena docs.
- The `BoardShim.__del__` `ImportError: sys.meta_path is None` at interpreter shutdown is harmless noise; capture completes before it.
- brainflow's pip enum name is `MUSE_S_ATHENA_BOARD` (their blog/docs typo it "Anthena" — the enum is spelled correctly).

## Path 2 — raw bleak (own the protocol)

Connect, `start_notify` on `273e0013`, write `h`/`p1035`/`dc001` (×2) via `frame()` above, collect notifications, demux by tag byte. EEG scaling for hand-decode (per `muse-rs`, **cross-check before trusting**): Athena `0x11/0x12` EEG = 14-bit LE packed, ~0.0885 µV/LSB (classic Muse was 12-bit BE, 0.488 µV/LSB). brainflow's decoder is the reference to validate any hand-rolled unpacking against.

## Contact quality — the fragile part

Behind-ear electrodes (**TP9/TP10**, on the mastoid) are the flaky ones; forehead (**AF7/AF8**) seat easily. The concept doc's "60–70% usable" is real.

- **Good contact ≈ 5–40 µV std** on a 1–40 Hz bandpassed channel, tight range. Drift/motion dumps huge energy into low bands and inflates std into the hundreds.
- Reseat fixes: push the arms down onto **bare skin behind the ear**, clear hair, snug forehead band ~1 cm above brows, lightly **dampen** the pads, let it settle ~30–60 s.
- **Use a drift-robust metric — but see the correction below.** Absolute band power is dominated by contact artifact. Relative alpha = `bandpower(8–13) / bandpower(1–40)` is invariant to *contact* drift and is what made the first Berger test read cleanly. Our first (absolute-power) run gave a *false null* — inverted ratios from an artifact-inflated eyes-open segment. Test the premise: a weak effect can be bad contact, not absent physiology.

> ### ⚠️ Correction (2026-07-27): relative alpha is biased for the eyes-open/closed contrast
>
> The recommendation above is right for **contact drift**, which is what it was validated
> against. It is **not** safe for the open-vs-closed comparison specifically, and the
> reason is structural: ocular artifact is condition-dependent *by construction* — blinks
> and saccades only happen with the eyes open. That energy lands in the 1–4 Hz band, which
> sits inside the `1–40` denominator, inflating it in the open condition only and
> inflating the ratio with it.
>
> Measured on the 2026-07-27 capture (`tests/fixtures/muse_athena/`), delta-band RMS
> open → closed: TP9 **201.8 → 11.0 µV**, TP10 73.1 → 11.8, AF8 27.2 → 5.6. An 18× drop is
> not physiology. Consequences on that file:
>
> - Relative alpha `8–13 / 1–40` reported posterior **9.75×**. Moving the denominator to
>   `4–40`, excluding the ocular band, dropped it to **3.04×**.
> - **Absolute** alpha power *decreased* from eyes-open to eyes-closed on all four
>   channels — anti-Berger. Blink energy had inflated the open condition across all bands.
>
> The two metrics disagreed in direction, so that capture cannot support a Berger claim
> either way. It is the mirror of the 25 July false null: that time absolute power lied
> and relative alpha rescued it; this time relative alpha was the flattering one.
>
> **The 1.54× recorded below carries the same bias** and should be read as directionally
> right, magnitude unverified.
>
> For future Berger runs: use `8–13 / 4–40`, report absolute alpha alongside it, and reject
> any epoch whose delta RMS exceeds the eyes-closed baseline by more than ~3×.

## Berger calibration (the validation)

30 s protocol, 15 s eyes-open then 15 s eyes-closed, spoken cues via macOS `say`, relative-alpha metric:

```
ch     relα open   relα closed   ratio
TP9       0.061       0.092      1.51
AF7       0.027       0.075      2.76
AF8       0.032       0.051      1.58
TP10      0.057       0.089      1.56
posterior mean closed/open = 1.54×   → Berger confirmed
```

All four channels show eyes-closed alpha rise — physiologically correct, and it *moved when the body moved*, which is the point: calibrated signal, not decode noise.

## ⚠️ brainflow and a raw client cannot both hold the device (tested 2026-07-27)

SPEC-015 REQ-015-5 assumes raw `273e0013` bytes and brainflow's decoded µV can be recorded
from **one** live capture, to give sample-exact decode parity. **That does not hold** with
these tools on macOS. Both routes were tested and both fail:

- **brainflow's trace logger** (`set_log_level(LEVEL_TRACE)` + `enable_dev_board_logger()`)
  dumps raw bytes for the **control** characteristic only — they decode to the firmware
  JSON `{"fw":"3.1.23",…}`. The `273e0013` data stream is never dumped.
- **Concurrent connection fails in both orderings.** brainflow first → `bleak` cannot find
  the device. `bleak` first (connected and subscribed successfully) → brainflow returns
  `BOARD_NOT_READY_ERROR:7`. Cause: a connected peripheral stops advertising, and both
  `bleak` and brainflow (SimpleBLE) discover by scanning, so whichever connects second is
  blind to it. *Note the first negative result was confounded* — a failed scan is not a
  refused connection; the bleak-first ordering is what makes this conclusive.

Consequence: captures are **sequential and not sample-aligned**. Sample-exact parity
against brainflow is unavailable until someone finds a genuinely simultaneous path.

### The scaling constant is corroborated three independent ways

Sources disagreed on the Athena packing (14-bit LE ~0.0885 µV/LSB vs classic 12-bit BE
0.488 — a ~5.5× difference). All three lines below agree on **14-bit LE, 0.0885**, and no
two of them share a failure mode:

1. **Source.** `muse-rs` `protocol.rs`: `ATHENA_EEG_SCALE = 0.0885`, applied as
   `(raw − 8192) × SCALE` over 14-bit LE unsigned.
2. **Physiology.** Alpha RMS in a clean eyes-closed window measured 3.7–10.7 µV across
   channels — plausible cortical alpha. The 12-bit constant would put it near 55 µV, or
   ~0.7 µV the other way. Neither is what we see. Coarse (blind to a 20% gain error) but
   decisive for this 5.5× question, and it trusts no decoder.
3. **The reference channel.** DRL/REF parks at 14-bit mid-rail 8192 (see `0x53` above) —
   internal evidence of the bit depth from a channel nobody was decoding.

## Fork landscape (for when the pipeline gets built)

| Option | What | Best for | Verdict |
|---|---|---|---|
| **brainflow** `MUSE_S_ATHENA_BOARD` | C++ core, Python binding, decoded µV + DSP | Signal now; reference decoder | Use today |
| **OpenMuse** (D. Makowski, NeuroKit2 author) | Python, Athena-native, LSL + viz | Owning the Python *research* pipeline (microstate/phase-space) | **Fork base — when we commit** |
| **muse-rs** (eugenehp) | Rust, full Athena decode, exact scaling | The EBS *desktop* app (Tauri/Rust) | If EEG lands in desktop first |
| **amused** (nexon33) | First reverse-eng | — | Skip: author says decode "non-operational" |

Recommendation: **brainflow to play/validate; fork OpenMuse when committing to the Python research pipeline** (it's LSL-first and shares the NeuroKit2 stack). Forking before that commitment is premature — same "don't crystallise before the empirical work constrains the form" logic the concept doc applies to the fusion repo.

---

*Scripts from the session live in the session scratchpad (ephemeral); the essential code is embedded above so this note is self-contained.*
