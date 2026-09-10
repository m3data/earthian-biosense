---
id: SPEC-015
title: Central Nervous Substrate — Muse S Athena EEG (schema 1.6.0)
status: draft (clean-context reviewed; REQ-015-5 amended after empirical falsification)
version: 0.3
created: 2026-07-25
updated: 2026-07-27
author: Mat Mytka & Kairos
delivers-schema: 1.6.0 (Rust desktop lineage; unconditional bump — see ADR-015-5)
---

# SPEC-015 — Central Nervous Substrate (Muse S Athena EEG)

**Status:** v0.3 draft — interface contract, ahead of implementation. Clean-context adversarial review run 2026-07-25 (findings folded in, §Clean-context review). **Amended 2026-07-27 after the first live capture falsified REQ-015-5's mechanism** — see §Amendment record. (USDD gate: SPEC + review before build.)
**Scope:** Add a central-nervous-system substrate to EBS by capturing EEG from a Muse S **Athena** headband, and define the schema-1.6.0 record format that carries it. The EEG substrate is represented as its own phase space **alongside** the existing autonomic (HRV) substrate — never fused at the substrate level. This spec defines the *acquisition path, the decode-sharing decision, the data tiers, and the on-disk contract*; the microstate/phase-space analysis layer that gives EEG research meaning is defined in shape here but deferred to a later build, gated on pilot data.

Companion documents: `concepts/muse-s-integration-concept.md` (research frame, hypotheses, ethics — the *why*); `concepts/muse-athena-first-contact.md` (the verified BLE handshake and decode landscape — the *how*, validated live 2026-07-25).

---

## Background — why this matters

Every EBS dimension to date is derived from the **RR-interval series alone** (the autonomic substrate) — with the accelerometer (SPEC-013) added as a confound channel, not a new observable of state. The instrument sees the autonomic nervous system and infers from it.

A central-nervous channel adds a substrate that is **empirically distinct** from the autonomic one. EEG resolves coordinated cortical activity on a timescale (tens to hundreds of milliseconds) that HRV cannot reach, and the *relationship between* cortical and autonomic dynamics becomes an observable rather than an assumption. That relationship — brain–ANS coupling, and how it tracks or leads semantic coupling-mode transitions — is the object of the multi-year programme the concept note lays out (H1–H4). None of it is askable without the central substrate instrumented.

The Muse S Athena is the pragmatic entry point: four (or eight) electrodes, wireless, ~5 h battery, 256 Hz. First contact is done — the device's protocol-v4 BLE interface has been reverse-engineered and validated live, and the packet framing has since been confirmed against 1,806 captured packets (see the first-contact note). *(The 1.54× Berger figure once cited here is withdrawn as a validation number — the metric behind it is biased for the eyes-open/closed contrast; see §CON-015-3. Signal reality is not in doubt — it rests on decoded µV landing in physiological range and the reference channel sitting at 14-bit mid-rail, REQ-015-5b — but the ratio is not a calibrated result.)* This spec turns that validated capture into a durable schema and a capture path in the apps.

**Connection to the research frame:** RQ4 (embodied/affective/relational dynamics — a second body substrate), RQ3 (coherence/entrainment durability — cross-substrate now observable), RQ5 (sensing/stewarding adaptive capacity — richer instrument). The tri-substrate form-discovery direction (`Action-Research/research/tri-substrate-form-discovery.md`) is gated on exactly this.

---

## Goal

When Muse EEG capture is enabled, an EBS session records:

1. a **full-rate raw EEG stream** (256 Hz, per channel, in µV) to a side-file — the research payload;
2. a **1 Hz central-substrate summary** in the primary session JSONL (per-channel band powers, contact quality, aggregated later with microstate occupancy) — a block named `central`, structurally parallel to the existing autonomic `metrics`/`phase` blocks and never merged with them;
3. an explicit **substrate/capability declaration** in *every* session-start record (EEG or not), so consumers detect features by capability, not by sniffing a version string.

The schema bumps to **1.6.0 unconditionally** on the Rust desktop lineage: every session a 1.6.0 build writes carries the `substrates`/`capabilities` declaration, so the header identifies the writer and capability-detection works for autonomic-only sessions too (ADR-015-5). Additions are **additive** — no existing autonomic field changes, and readers that ignore unknown keys parse 1.6.0 sessions unchanged — but an autonomic-only 1.6.0 session is *not* byte-identical to a 1.5.0 one: it gains the two declaration keys. Pre-1.6.0 sessions remain valid and simply lack the declaration.

## Non-goals (v0.1 of this feature)

- **Microstate analysis / central phase-space classification.** The `central_phase` block is defined in shape (RESERVED) but not computed here — it needs device-specific reference templates (weeks of methodological work per the concept note) and pilot data. Capturing raw EEG is the prerequisite; analysing it is the next build.
- **Substrate fusion.** No combined "somatic index" that merges EEG and HRV. Their coupling is a *research output*, computed in retrospective analysis or at the application layer (VibeHarness), never crystallised into the capture schema. (Concept note: "you cannot study the coupling between two things if you have already collapsed them into one.")
- **iOS implementation in this build.** The schema is cross-platform by design and iOS is specified below, but desktop lands first (see Implementation Surfaces). iOS follows once desktop is stable.
- **Compressed-preset EEG.** v0.1 uses an uncompressed preset (p1035/p1041 family). The Athena's Golomb-compressed presets are out of scope until a golden-vector decoder is proven for them.
- **Live EEG into Claude context.** That is the live-coupling thread, tracked separately.
- **Optics/PPG-derived HRV from the Muse.** The Athena streams optics; deriving a second HRV source from it is a later, separate decision (the Polar H10 remains the autonomic source).

---

## BLE acquisition (Athena, protocol v4)

The full verified handshake, GATT map, packet framing, and preset table live in `concepts/muse-athena-first-contact.md` and are not duplicated here. The load-bearing facts for implementation:

- **Control is write-*without*-response** on char `273e0001`; data is multiplexed on `273e0013`.
- **Handshake:** `h` → `p<preset>` → `dc001` (send `dc001` **twice** — the community-confirmed requirement; a single send half-worked on-head in testing but twice is the robust form).
- **Concurrency (assumed, pending the dual-BLE test — §Open questions):** the Muse is intended to connect as a **second BLE peripheral alongside the Polar H10.** Both apps currently manage a single peripheral; a two-device connection state machine is genuinely new work (§Implementation). This rests on btleplug sustaining two concurrent peripherals on macOS without dropping notifications on either — **not yet verified.** Fallback if it proves unstable: EEG capture is disabled and the autonomic (H10) capture runs alone. The transport layer must never be allowed to degrade autonomic capture in pursuit of EEG (REQ-015-3); the Muse link otherwise degrades gracefully and independently — EEG is additive, its loss must never take down the autonomic capture.
- **Preset / channel count is a decision (see ADR-015-4):** `p1035` (EEG4: the 4 scalp channels TP9/AF7/AF8/TP10 — validated) vs `p1041`/`p1045` (EEG8: the same 4 scalp channels **plus 4 amplified auxiliary/reference rows** — *not* additional scalp locations). The schema is **channel-count-agnostic** (§CON-015-2) so the preset can be chosen/changed without a schema break.

## Decode & the shared-core decision

The architectural spine of this feature: **BLE transport is platform-specific and small; EEG decode is pure, fiddly, and must be single-source-of-truth.**

- Transport: `btleplug` (desktop, Rust) / CoreBluetooth (iOS, Swift) — irreducibly per-platform.
- Decode (bytes → µV + tag demux + scaling): the part where a wrong constant is a silent, hard-to-catch error, and the part worth sharing.

`muse-rs` (Apache-2.0, on crates.io, **btleplug-based — the desktop's existing BLE crate**) supports the Athena, auto-selects the protocol, and separates its `parse` module from its transport (`muse_client.rs`). See ADR-015-1 for the decision: **use muse-rs on desktop now; extract a shared pure-decode core when iOS lands.** Its parse module is the seed for that core (Apache-2.0 permits it). Do **not** hand-roll a second decoder without golden-vector parity against the recorded reference µV (§Tests-first).

**Scaling constants are not asserted in this spec.** Sources disagree on the Athena EEG packing (14-bit LE vs the classic 12-bit BE; µV/LSB differs). Per the SPEC-013 lesson (*capture real frames first; the bit-unpacking is where the assumption hides*), the decoder owns scaling and the **golden-vector test pins whatever it actually is.**

> ### ⚠️ Amended 2026-07-27 — the v0.2 parity mechanism was not achievable
>
> v0.2 specified: *"during one live capture, record both the raw `273e0013` notification
> bytes and brainflow's decoded µV for the same session."* **That capture cannot be
> performed.** Tested on macOS 2026-07-27, both available routes fail:
>
> - brainflow's trace logger (`LEVEL_TRACE` + `enable_dev_board_logger()`) dumps raw bytes
>   for the **control** characteristic only — they decode to the firmware JSON. The
>   `273e0013` data stream is never dumped.
> - Concurrent connection fails in **both orderings**. brainflow first → `bleak` cannot
>   find the device. `bleak` first, connected and subscribed → brainflow returns
>   `BOARD_NOT_READY_ERROR:7`. A connected peripheral stops advertising and both stacks
>   discover by scanning, so whichever connects second is blind to it.
>
> The v0.2 mechanism was itself introduced to fix review finding **M3** ("golden-vector
> parity had no mechanism"). M3 was correctly identified; the fix was wrong. It replaced
> an absent mechanism with an unexecutable one, and neither state was detectable without
> putting a headband on and trying.

**The deeper defect: brainflow was the wrong reference.** Anchoring parity to brainflow
made an external, live-only, Python tool load-bearing for a Rust offline test. It also
guards the wrong thing — it can only show that *our decoder agrees with brainflow*, never
that the constant is **right**. If brainflow's own constant were wrong, the fixture goes
green over a shared error. The corrected guard is two layers with no shared failure mode
(ADR-015-6): a **relative** layer pinning implementation drift against a frozen reference
vector, and an **absolute** layer checking the decoded output against decoder-independent
physical facts. Tolerances in REQ-015-5a / REQ-015-5b.

## Data tiers — the raw/summary split

EEG is 256 Hz; the existing session JSONL is a ~1 Hz tick. Unlike SPEC-013's accelerometer (aggregated to 1 Hz and the raw discarded), **the full-rate EEG is the research payload** — microstates need it. So two tiers, both written when EEG is enabled:

| Tier | Rate | Where | Content |
|---|---|---|---|
| **Raw EEG** | 256 Hz | side-file `<session>_eeg.jsonl` (or binary — ADR-015-3) | per-channel µV samples, sequence, contact flags |
| **Central summary** | 1 Hz | primary session JSONL, `central` block | per-channel band powers, contact quality, (later) microstate occupancy |

The primary JSONL stays human-diffable and joinable with the autonomic tick; the raw side-file carries the volume. **The two files are linked at the file level by `central_meta.raw_file`, and joined at the sample level by a shared host-monotonic timestamp:** every raw batch and every `central` tick carries a `host_mono` value (seconds from a session-start monotonic reference, stamped at notification receipt). A `central` tick at `host_mono = t` summarises the raw samples with `host_mono ∈ [t, t+1s)`. This makes the EEG↔autonomic alignment explicit to within notification-receipt jitter — the seam H2 (brain–ANS lead/lag) depends on it. Absolute cross-*device* clock drift (H10 vs Muse) is a separate open question (§Open questions); the within-host association defined here does not depend on resolving it.

---

## Schema additions (1.6.0)

### Session-start record — substrate/capability declaration

The base `session_start` is written immediately and **always** carries the declaration (unconditional, ADR-015-5). For an autonomic-only session this is the whole story:

```json
{
  "type": "session_start",
  "schema_version": "1.6.0",
  "host_mono_epoch": "2026-07-25T15:30:11.900Z",
  "substrates": ["autonomic"],
  "capabilities": ["hrv", "motion"]
}
```

The **central declaration is deferred** to a separate `central_start` record, emitted **only after the Muse handshake succeeds** — so a failed or never-seated Muse never declares a substrate that isn't there, and `raw_file` never dangles:

```json
{
  "type": "central_start",
  "host_mono": 1.204,
  "substrates_add": ["central"],
  "capabilities_add": ["eeg_raw", "eeg_bands"],
  "central_meta": {
    "device": "MuseS-XXXX",
    "preset": "p1041",
    "channels": ["TP9", "AF7", "AF8", "TP10", "AUX1", "AUX2", "AUX3", "AUX4"],
    "scalp_channels": ["TP9", "AF7", "AF8", "TP10"],
    "sample_rate_hz": 256,
    "raw_file": "2026-07-25_153012_eeg.jsonl"
  }
}
```

`substrates`/`capabilities` are the **detection contract**: consumers form the effective set by folding `*_add` records over the base, and branch on capability presence, not on the version string. `scalp_channels` marks which of `channels` carry real scalp EEG (vs the amplified aux/reference rows an EEG8 preset adds, ADR-015-4); **all EEG semantics apply to `scalp_channels` only** (§CON-015-2). On clean stop a `central_end` record writes the final `seq` + total sample count, so a truncated/crashed raw file is detectable (last raw `seq` ≠ declared final `seq` ⇒ known-incomplete). This mechanism is Rust-only in this spec; see ADR-015-5 for the honest S2-1 scope.

### Central summary block (1 Hz, in primary JSONL)

Additive top-level `central` object, parallel to `metrics`/`phase` (which remain autonomic-only):

```json
"central": {
  "host_mono": 12.204,
  "bands": {
    "TP9":  { "delta": 12.1, "theta": 8.4, "alpha": 22.6, "beta": 9.1, "gamma": 3.0 },
    "AF7":  { "delta": 9.7,  "theta": 6.1, "alpha": 7.5,  "beta": 12.2, "gamma": 4.1 }
  },
  "rel_alpha": { "TP9": 0.31, "AF7": 0.12 },
  "contact": { "TP9": "good", "AF7": "good", "AF8": "marginal", "TP10": "poor" },
  "contact_ok": false,
  "n_samples": 256,
  "central_phase": null
}
```

- `host_mono` — the tick's monotonic timestamp; the join key to the raw side-file (§Data tiers).
- `bands` — per-**scalp-channel** band power as **mean PSD over the band (µV²/Hz), normalised by `n_samples`** (Welch — *not* a raw sum), so a short tick (packet loss → `n_samples` < 256) stays comparable to a full one. Band edges pinned in §CON-015-3. Computed on `scalp_channels` only; aux rows (EEG8) are stored raw but not band-analysed in v0.1.
- `rel_alpha` — per-scalp-channel alpha(8–13) / total(1–40 Hz) power. Robust to **contact drift**, which is what it was validated against. The 1–40 Hz denominator is fixed and **includes the whole gamma band (capped at 40 Hz, §CON-015-3)**, so `rel_alpha` is well-defined. **⚠️ Not safe for the eyes-open/closed contrast** — see the correction in §CON-015-3 and Acceptance 5.
- `contact` — per-channel `good | marginal | poor`, from the **pinned** classification in §CON-015-5 (named-constant thresholds, identical across engines — not a loose "≈"). Contact quality is a **first-class signal, not an afterthought** — the Athena's behind-ear electrodes are fragile and downstream MUST be able to gate on quality (§REQ-015-4).
- `contact_ok` — convenience boolean: all `scalp_channels` ≥ marginal.
- `n_samples` — samples in the tick window (≤ 256; < 256 signals packet loss — drop-handling in §CON-015-3).
- `central_phase` — **RESERVED** (null in v0.1). Reserved shape when computed: the microstate-trajectory phase space, mirroring the autonomic `phase` block's apparatus (position / velocity / curvature / stability / soft membership) over microstate space, on `scalp_channels`. Deferred to the analysis build (Non-goals).

### Raw EEG record (256 Hz, side-file)

```json
{ "ts": "2026-07-25T15:30:12.004Z", "host_mono": 12.204, "seq": 1041,
  "eeg": { "TP9": [ ...samples... ], "AF7": [...], "AF8": [...], "TP10": [...] },
  "contact": { "TP9": "good", "AF7": "good", "AF8": "marginal", "TP10": "poor" } }
```

Batched per BLE notification (not one record per sample) to keep the file tractable. `host_mono` is the join key to the 1 Hz `central` tick (§Data tiers). `seq` is the Athena packet sequence counter: a gap marks dropped packets and drops the affected tick's `n_samples` below 256 (drop-handling: §CON-015-3). The `central_end` record's final `seq`/count lets a reader detect a truncated file.

---

## Requirements

### REQ-015-1 — Substrate separation (non-fusion)
The `central` block MUST be represented as its own substrate, never merged into the autonomic `metrics`/`phase` values. **Enumerable invariant:** every key inside `central` is a function of EEG samples alone; no field combines an EEG-derived and an HRV-derived quantity. *Verified by* [[#TEST-015-8]] — a schema test enumerates `central`'s keys against an allowlist (`host_mono`, `bands`, `rel_alpha`, `contact`, `contact_ok`, `n_samples`, `central_phase`) and fails on any key outside it. (`host_mono` is a clock stamp, not an autonomic quantity.)

### REQ-015-2 — Additive, back-compatible
Adding EEG MUST NOT alter any existing **autonomic** field, and MUST NOT break parsing of pre-1.6.0 sessions (readers ignore unknown keys). A 1.6.0 session is **additive, not byte-identical** to 1.5.0: an autonomic-only 1.6.0 session adds exactly the `substrates`/`capabilities`/`host_mono_epoch` declaration keys (and no `central` block, no `central_start`) — every autonomic field unchanged. Pre-1.6.0 sessions remain valid and lack the declaration. *Verified by* [[#TEST-015-5]].

### REQ-015-3 — Graceful, independent degradation
Muse connection failure, mid-session Muse dropout, sustained poor contact, **or dual-BLE instability** MUST NOT interrupt autonomic (H10) capture. EEG is additive; its absence yields a valid autonomic-only session. The central declaration is emitted only after a successful Muse handshake (`central_start`), so a session that never connects the Muse never declares `central` and never dangles `raw_file`. *Verified by* [[#TEST-015-6]].

### REQ-015-4 — Contact quality is recorded and gate-able
Every central record (raw and summary) MUST carry per-channel contact quality, so no consumer mistakes artifact for signal. The classification rule is **pinned in §CON-015-5** (bandpass, std thresholds, range test — named constants, identical across engines), not a loose heuristic, and MUST classify the drift/motion regime that produced the first-contact false-null (behind-ear std in the hundreds) as `poor`. *Verified by* [[#TEST-015-3]].

### REQ-015-5a — Decode parity, relative (frozen reference vector, offline)
Any EEG decoder MUST reproduce, from the checked-in golden **raw bytes**, the checked-in **frozen reference µV vector**, to within **≤ 0.1 µV per sample**, offline in the test harness.

The reference vector is generated **once** by the reference decoder (muse-rs, ADR-015-1) from those same bytes and committed alongside them. It is a static array, not a live capture — no BLE, no device, no brainflow at test time. This is what makes the requirement executable where v0.2 was not, and it is the check that a **second** implementation (the iOS Swift port, or the extracted shared core per ADR-015-1) has not drifted from the first.

**What this layer cannot do:** it is silent on whether the shared constant is correct. Regenerating the reference from a wrong decoder makes it green over a wrong answer. That gap is REQ-015-5b's job. Regenerating the reference vector is therefore a **reviewed act**, never a convenience when a test goes red. *Verified by* [[#TEST-015-2a]].

### REQ-015-5b — Decode parity, absolute (decoder-independent physical anchors)
The decoded golden capture MUST satisfy both checks below. Neither consults any decoder, so neither can be satisfied by two implementations agreeing on a wrong constant:

1. **Reference-rail check.** DRL/REF (`0x53`) sub-frame values, read as `u16` LE, MUST fall within **±256 LSB of 8192** — the mid-rail of a 14-bit ADC. Observed 2026-07-27: two interleaved channels at 8242.8 and 8261.8, std ≤ 1.35 LSB, no drift across a session. A 12-bit reading cannot produce this. This is the sharpest anchor available and costs nothing: it is internal to a channel the decoder does not even emit.
2. **Physiological-amplitude check.** Alpha-band (8–13 Hz) RMS over the eyes-closed segment MUST fall within **0.5–60 µV ▢** per scalp channel. Observed 2026-07-27: 3.7–10.7 µV. The competing 12-bit BE constant (0.488 µV/LSB) differs from 14-bit LE (0.0885) by ~5.5× and would land near 55 µV or 0.7 µV.

**Deliberately coarse.** Layer (2) would not catch a 20 % gain error, and layer (1) has ±3 % headroom. They are not a substitute for 5a; they close the *specific* failure 5a is blind to — the wrong-packing confusion this spec was written to guard, which is a 5.5× error, not a subtle one. *Verified by* [[#TEST-015-2b]].

> **Correction 2026-09-10 (evening) — the alpha bound was set from a mis-scaled witness.** The
> 2–60 µV bound and the fixture README's "3.7–10.7 µV eyes-closed alpha" were computed on
> brainflow 5.22.2's µV, which applied the **12-bit** constant (1650/4095 = 0.4029 µV/LSB) to
> **14-bit** samples — upstream issue #854, fixed in PR #855/#856 on 2026-08-18 to 1450/16383
> (0.0885) with mid-rail 8192, i.e. exactly muse-rs's and OpenMuse's rule. Every brainflow-derived
> µV figure in this repo from July is therefore **4.55× too large**. On the correct scale the
> golden eyes-closed window gives alpha RMS **TP9 3.0 · AF7 0.9 · AF8 0.7 · TP10 3.2 µV** (10 s;
> the full 20 s window: 2.9 · 1.1 · 1.2 · 3.3), so the frontal channels fail the old bound and
> TEST-015-2b(ii) went red on the first run against the reference decoder. Lower bound moved to
> 0.5 µV (▢ Mat to ratify; 2 µV is defensible for the posterior pair only). **Honest scope of this
> layer:** it catches unpacking/bit-depth confusion (the 12-bit-BE control lands far outside the
> band); it does *not* catch a 4.5–5.5× gain error at these amplitudes (TEST-015-2c records
> 0/4 channels caught). Gain is guarded by the relative layer (5a) plus the three-lineage
> agreement on 1450/16383, which since 2026-08-18 is no longer one lineage. The "three independent
> ways" argument in the first-contact note was partly circular: its physiology witness was
> brainflow's own (mis-scaled) output.

### REQ-015-5c — No decoder ships without both layers green
Neither layer alone is sufficient: 5a catches implementation drift and is blind to a shared error; 5b catches a shared error and is blind to per-sample drift. A decoder ships only with both green.

### REQ-015-6 — Capability-based detection
Consumers MUST be able to determine a session's substrates/capabilities from the `session_start` declaration without inferring from the schema version string. *Verified by* [[#TEST-015-7]].

### NFR-015-1 — Raw volume bounded
The 256 Hz side-file MUST be written in batches (per-notification, not per-sample) and MUST NOT block the autonomic tick. A one-hour 4-channel session is the sizing target (§Open questions).

### NFR-015-2 — Reserved fields visibly reserved
`central_phase` MUST be present-and-null (not absent) in v0.1 and commented RESERVED, so its future shape is anticipated, not silently invented later.

---

## Contracts

### CON-015-1 — Decode core interface (transport-independent)
```
decode_athena_notification(bytes: &[u8]) -> Vec<MuseEvent>
// MuseEvent ∈ { Eeg{channel, samples_uV}, Imu{...}, Optics{...}, Battery{...} }
```
Pure, no I/O, no allocation beyond the returned vector. This is the surface shared (muse-rs now; extracted core when iOS lands) and the surface the golden-vector test drives.

### CON-015-2 — Channel-count-agnostic *storage*; scalp-scoped *semantics*
`central.contact` and raw `eeg` are **keyed by channel name**, not fixed to four; an EEG8 preset populates eight keys and storage iterates all keys. **But EEG semantics are scalp-only:** `bands`, `rel_alpha`, `contact_ok`, the Berger check, and (future) microstates are computed over `central_meta.scalp_channels` (the 4 real scalp electrodes). The aux/reference rows an EEG8 preset adds (ADR-015-4) are stored raw but **not interpreted as brain signal** in v0.1. "Iterate keys" is safe for storage, never for EEG interpretation. No schema change to move between p1035 (4 scalp) and p1041 (4 scalp + 4 aux).

### CON-015-3 — Central summary block (1 Hz)
Per **scalp** channel, `bands` = mean PSD over each band in **µV²/Hz**, normalised by `n_samples` (Welch; not a raw periodogram sum) so ticks of unequal length stay comparable. **Pinned band edges (single source of truth, both engines):**

| Band | Hz |
|---|---|
| delta | 1–4 |
| theta | 4–8 |
| alpha | 8–13 |
| beta  | 13–30 |
| gamma | 30–40 |

Gamma is **capped at 40 Hz** (not the conventional >40) so it sits inside the `rel_alpha` denominator; `rel_alpha` = alpha(8–13) / total(1–40).

> **⚠️ Correction 2026-07-27 — `rel_alpha` is biased for the eyes-open/closed contrast.**
> The 1–40 denominator includes delta (1–4), where ocular artifact lands. That artifact is
> **condition-dependent by construction** — blinks and saccades only occur with the eyes
> open — so the open denominator is systematically inflated and the ratio with it.
> Measured on the 2026-07-27 capture, delta RMS open → closed: TP9 **201.8 → 11.0 µV**,
> TP10 73.1 → 11.8. `rel_alpha` reported a posterior ratio of **9.75×**; an artifact-free
> `4–40` denominator gave **3.04×**; and *absolute* alpha moved the other way entirely.
>
> `rel_alpha` **stays** as the stored field — it is a sound general descriptor and is
> schema-visible. It must simply not be the statistic for an open/closed comparison. The
> de-biased ratio needs **no new field**: `alpha / (theta + alpha + beta + gamma)` is
> computable from the stored `bands`. Used in Acceptance 5.

`contact` per channel ∈ {good, marginal, poor} (§CON-015-5); `contact_ok` = all `scalp_channels` ≥ marginal; `host_mono` (join key); `n_samples` (≤ 256). **Drop handling:** a `seq` gap reduces the tick's `n_samples`; because `bands` is PSD-normalised the values stay comparable, but a tick with `n_samples` below a floor (default 128 = 0.5 s) MUST set `contact_ok=false` and SHOULD mark the tick low-confidence rather than report a physiological change that is actually packet loss. `central_phase` null (RESERVED).

### CON-015-4 — Capability declaration (base + deferred central)
The base `session_start` ALWAYS carries `substrates: string[]` + `capabilities: string[]` + `host_mono_epoch` (wall-clock anchor for the monotonic clock). A `central_start` record (emitted only after Muse handshake) carries `substrates_add`, `capabilities_add`, and `central_meta: {device, preset, channels[], scalp_channels[], sample_rate_hz, raw_file}`. A `central_end` record carries the final `seq` + sample count for truncation detection. Consumers fold `*_add` records over the base to get the effective set. This is the forward detection contract (REQ-015-6).

### CON-015-5 — Contact classification (pinned)
Per channel, over the 1 Hz tick window, on the signal **bandpassed 1–40 Hz** (4th-order Butterworth) then constant-detrended, compute `std` (µV) and `range` (max−min, µV):
- `good`: `5 ≤ std ≤ 40` **and** `range < 400`.
- `marginal`: `std ≤ 80` **and** `range < 2000` (and not `good`).
- `poor`: otherwise (the drift/motion regime — std in the hundreds — that caused the first-contact false-null).

Thresholds are **named constants** (`CONTACT_STD_GOOD_MAX=40`, `CONTACT_RANGE_GOOD_MAX=400`, `CONTACT_STD_MARGINAL_MAX=80`, `CONTACT_RANGE_MARGINAL_MAX=2000`), identical in every engine, **provisional** — calibrated on the first labelled sessions — and guarded by a fixture (mirrors SPEC-013's `MOTION_THRESHOLD`).

---

## Architecture decisions

### ADR-015-1 — muse-rs on desktop now; extract shared core when iOS lands
**Decision:** Depend on `muse-rs` for the desktop (Rust) decode immediately; defer extracting a platform-neutral `muse-athena-core` until iOS is actually built. **Rationale:** muse-rs is Apache-2.0, btleplug-based (the desktop's existing stack), Athena-native — near-zero-friction on desktop and the fastest path to capturing on the platform the concept note targets first. Extracting a shared core has real one-time cost (FFI/UniFFI toolchain) and is only justified once a *second* platform consumes it; by then we have golden captures to validate both bindings against, and know whether decoder divergence is really biting. **Consequence:** desktop leans on muse-rs's parse; the extraction is a tracked follow-up whose seed is muse-rs's `parse` module.

### ADR-015-2 — Non-fusion at the schema level (concept-note commitment)
**Decision:** EEG and HRV are separate substrates in the schema; no fused field. **Rationale:** the coupling between substrates is the research object; collapsing them into one index destroys the ability to study it, and pre-commits the system to an answer before the empirical work constrains its form. **Consequence:** `central` sits parallel to `metrics`/`phase`; any cross-substrate quantity is computed downstream (analysis / VibeHarness), never stored here.

### ADR-015-3 — Two-tier storage (raw side-file + 1 Hz summary)
**Decision:** Full-rate 256 Hz EEG to a side-file; 1 Hz summary in the primary JSONL. **Rationale:** the raw is the research payload (microstates need it) so it can't be discarded like SPEC-013's ACC; but 256 Hz in the primary tick would bloat it and break the 1 Hz join. **Open sub-decision:** side-file format — JSONL (diffable, consistent with the rest) vs a compact binary (smaller, faster). v0.1 leans JSONL for consistency; revisit on the one-hour sizing test (§Open questions). **Consequence:** session metadata links the two files; tooling that only wants summaries never touches the raw.

### ADR-015-4 — Preset / channel count (DECIDED 2026-07-25 — p1035 / EEG4)
**Premise correction (2026-07-25, Mat-prompted):** the Athena has **4 scalp EEG electrodes** (TP9/AF7/AF8/TP10 — identical to the classic Muse S) plus **FPz as reference** (CMS/DRL). The "EEG8" presets do **not** add scalp locations; they add 4 *amplified auxiliary/reference* rows (Interaxon's spec: "4 on-head + 4 auxiliary"; brainflow exposes the extra 4 as `other_channels`). So this is **not** a spatial-resolution decision — microstate topographies get 4 scalp channels either way (already methodologically marginal per the concept note; no preset changes it). The Athena's real upgrades over the classic Muse S are **14-bit resolution** and **fNIRS optics**, not more EEG.

**The actual choice:**
- `p1035` (EEG4, tag `0x11`): the 4 scalp channels. Matches the existing 4-electrode centroid work; simplest.
- `p1041`/`p1045` (EEG8, tag `0x12`): the 4 scalp channels + 4 amplified aux. The aux rows *may* aid artifact rejection / re-referencing, but that is **unproven** for this work.

The schema is channel-agnostic (CON-015-2) so this does not block the schema, **but it sets what the pilot captures.** **Decision (Mat, 2026-07-25): `p1035` / EEG4.** Capture the 4 scalp channels (TP9/AF7/AF8/TP10) that carry the brain signal and match the existing 4-electrode centroid work; `scalp_channels` == `channels` for this preset, so the aux/scalp distinction (§CON-015-2) is inert until a preset change. A one-off `p1041`/EEG8 characterisation run — to see what the 4 aux rows actually contain — is deferred, not required for v0.1. No spatial gains were ever on the table from EEG8. (fNIRS is a distinct future substrate — hemodynamic, not electrical — explicitly out of scope here; see Non-goals.)

### ADR-015-6 — Two-layer decode guard; brainflow is not the reference (2026-07-27)
**Decision:** Replace the single brainflow-anchored parity test with two layers — a **relative** check against a frozen reference vector generated once by muse-rs (REQ-015-5a), and an **absolute** check against decoder-independent physical anchors (REQ-015-5b). brainflow is demoted from *reference decoder* to *convenient live-capture tool*, used for exploration and never in the test path.

**Rationale.** Two independent reasons, and either alone would force the change.

*Executability.* The v0.2 mechanism required raw bytes and brainflow µV from one live session. That capture cannot be performed (§Decode). A requirement that cannot be satisfied is not a guard; it is a green light with a ceremony attached.

*Correctness of the target.* Even had it worked, it guarded the wrong proposition. "muse-rs agrees with brainflow" is not "the constant is right" — two implementations can share an error, and both trace to the same OpenMuse lineage, so they are **not** independent witnesses. The spec's own words were *"the golden-vector test pins whatever it actually is."* It did not. It pinned whatever brainflow says it is. That is a premise wearing the costume of setup: brainflow was installed as ground truth by the phrase "the reference decoder," and nothing established its correctness.

**What makes the new layers independent.** Layer 5a is implementation-vs-implementation, so it inherits any shared error. Layer 5b consults physics instead: a reference electrode must rest at the ADC's mid-rail, and cortical alpha must land in a known amplitude band. Neither fact comes from a decoder, so a shared decoder error cannot satisfy them.

**Consequence.** The test harness no longer depends on brainflow, Python, or a device. The fixture gains a frozen reference vector. Regenerating that vector is a reviewed act, not a red-test convenience (REQ-015-5a). Whether a genuinely simultaneous capture path exists remains open (§Open questions) — if one is found, sample-exact parity against a *third* witness can be added, but it is no longer load-bearing.

**Also noted (unresolved):** muse-rs **discards `0x53`** — it advances the cursor and emits no event. Adopting muse-rs under ADR-015-1 therefore silently drops DRL/REF. REQ-015-5b(1) reads that channel from the **raw bytes**, so the guard is unaffected; but if DRL/REF is ever wanted as a signal (re-referencing, artifact regression), muse-rs's parse needs extending. In the 2026-07-27 capture it stayed flat to within 0.12 µV while TP9 threw 200 µV of delta artifact, so it did *not* track the artifact and is **not** a ready-made regressor — it may be a driven setpoint rather than a measurement. Untested either way.

### ADR-015-5 — Capability declaration as the version contract
**Decision:** From 1.6.0, **every** session (EEG or not) declares `substrates` + `capabilities` in `session_start`; consumers detect by these, not by the version string. Unconditional, so the discriminator exists for autonomic-only sessions too — otherwise REQ-015-6 fails for the common case and the header no longer identifies the writer. **Rationale:** establishes a lineage-independent detection *mechanism* for SPEC-014 residue S2-1. **Honest scope (from the clean-context review):** this spec bumps and instruments **only the Rust desktop lineage.** Python remains at 1.4.0 with no declaration, so S2-1 is **not yet closed** — a Python session still needs version-sniffing. Closing it requires the Python lineage to also emit the declaration and the version numbers to reconcile; that is a **tracked follow-up** (§Clean-context review), not done here. This ADR establishes the mechanism; it does not by itself resolve the cross-engine divergence. **Consequence:** on Rust, feature detection is version-independent; the Python/Rust gap persists until Python adopts.

---

## Implementation surfaces

**Desktop (`desktop/src-tauri`, Rust) — primary, this build:**
- `Cargo.toml` — add `muse-rs`.
- `src/ble/mod.rs` — second concurrent peripheral: discover `MuseS-*`, connect, `start_notify` on `273e0013`, write `h`/`p<preset>`/`dc001×2` (write-without-response). Two-device connection state machine; Muse link independent of H10.
- new `src/eeg/mod.rs` — wrap muse-rs decode; per-tick band powers + rel_alpha (reuse a Welch/FFT util); contact-quality heuristic (std/range gate, mirrors the motion still/moving gate defensively).
- `src/session/mod.rs` — bump schema to **1.6.0** and emit the base `substrates`/`capabilities`/`host_mono_epoch` in every `session_start`; on Muse handshake emit `central_start` (with `central_meta` + `scalp_channels`); write the raw `_eeg.jsonl` side-file (batched, with `host_mono`) + fold the 1 Hz `central` block into the session log; emit `central_end` (final `seq` + count) on stop.
- webview — a live band-power / contact panel mirroring the phase-space viz (surfacing contact quality is the on-head UX that makes reseating obvious).

**iOS (`ios/EBSCapture`, SwiftUI) — later build (specified, not built here):**
- CoreBluetooth transport (`.withoutResponse` writes; same handshake).
- Decode via the extracted shared Rust core (ADR-015-1) through UniFFI/XCFramework, **or** a Swift port validated against the same golden vectors. Decide when iOS starts, with captures in hand.
- On-device band-power + contact feedback mirroring the existing HRV feedback.

**Python (`src/`) — parity/diagnostic, optional:**
- Not required for this build (desktop is primary and Python has been superseded for capture). If added, it MUST also adopt the 1.6.0 declaration (`substrates`/`capabilities`, and reconcile the Python schema number) — a Python client emitting `central` blocks into an undeclared 1.4.0 session would reproduce S2-1 (EEG present but invisible to capability-detection). Offline decode via brainflow (the reference decoder) is fine.

---

## Tests-first plan

Per project convention, failing tests precede implementation.

1. ~~**Capture golden Athena packets.**~~ **DONE 2026-07-27.** 1,806 raw `273e0013` notifications (preset `p1035`, 45 s, spoken eyes-open/eyes-closed cues) plus a separate brainflow µV capture. Provenance and findings: `tests/fixtures/muse_athena/README.md`. Packet framing validated against it — `[TAG][META4][PAYLOAD]` sub-frames, all 1,806 packets tiling with zero resyncs, three tags landing on their nominal rate. **⚠️ The recordings are local-only under the biometric-data policy** (§Open questions — fixture inclusion is an open decision).
2. **[TEST-015-2a] Decoder parity test — relative (offline, no device, no brainflow).** Decode the checked-in raw bytes and assert a match to the checked-in frozen reference µV vector, ≤ 0.1 µV/sample. Runs in the Rust harness with no BLE and no Python. Guards **REQ-015-5a**. *(Supersedes the v0.2 test, which required an unperformable capture.)*
2b. **[TEST-015-2b] Decoder parity test — absolute (offline, decoder-independent).** From the same raw bytes assert: (i) `0x53` DRL/REF values as `u16` LE within ±256 LSB of 8192; (ii) eyes-closed alpha RMS within 2–60 µV per scalp channel. Guards **REQ-015-5b**. Deliberately coarse — this is the layer that survives the reference decoder itself being wrong.
2c. **[TEST-015-2c] Negative controls for both layers (the tests that prove the tests bite).** Re-decode the golden bytes with the *wrong* constants and assert each layer fails: 12-bit BE unpacking, and the 0.488 µV/LSB gain. A guard nobody has watched fail is not known to be a guard.
3. **Contact-quality test.** Synthetic channel segments (clean ~20 µV; drift-inflated hundreds-of-µV; railed) → assert `good | marginal | poor` against the pinned §CON-015-5 thresholds, and that the first-contact false-null regime flags `poor`. Guards REQ-015-4.
4. **Band-power test.** Known synthetic signals (pure 10 Hz sinusoid → alpha dominates; broadband) → assert band powers (against the pinned §CON-015-3 edges) and rel_alpha land where expected, and that PSD-normalisation makes a half-length window comparable to a full one.
5. **Schema tests.** Autonomic-only 1.6.0 session = 1.5.0 + declaration keys only (no autonomic field changed); EEG-enabled session validates against 1.6.0; `central_phase` present-and-null; pre-1.6.0 sessions still load. Guards REQ-015-2 / NFR-015-2.
6. **Graceful-degradation test.** Muse absent / mid-session dropout / sustained poor contact / simulated dual-BLE instability → autonomic capture uninterrupted, valid autonomic-only session, no `central_start` emitted, no dangling `raw_file`. Guards REQ-015-3.
7. **Capability-detection test.** A consumer folds `central_start`'s `*_add` over the base and branches correctly without touching `schema_version`; a raw file whose last `seq` ≠ `central_end`'s final `seq` is flagged incomplete. Guards REQ-015-6.
8. **Non-fusion invariant test.** Enumerate every key in `central` against the allowlist (§REQ-015-1); fail on any key outside it. Guards REQ-015-1.

A live **Berger acceptance** (below) is the end-to-end proof, echoing the first-contact validation.

---

## Open questions

- ~~**Preset / channel count**~~ — DECIDED 2026-07-25: `p1035` / EEG4 (ADR-015-4).
- **Raw side-file format** — JSONL vs binary; decide on the one-hour sizing test. 4 ch × 256 Hz × ~8 h battery is the worst case to bound.
- **Dual-BLE stability on macOS — ANSWERED 2026-09-10 for a short session; long-session behaviour still open.** Original question: does btleplug sustain H10 + Muse concurrently over a long session without dropping notifications on either? (SPEC-013 raised the same question for concurrent PMD+HR; now two *devices*, not two characteristics.) **⚠️ Still fully open — the 2026-07-27 concurrency test does NOT bear on this.** That test was *two client stacks contending for one peripheral* (brainflow and bleak both wanting the Muse), which failed on **discovery**: a connected peripheral stops advertising. This question is *one client holding two different peripherals*, where each is discoverable when the other is connected and no contention exists. Different mechanism, different answer. **Do not read the 2026-07-27 result as evidence either way.**

  **Partial result 2026-09-10 — the platform layer is clear; the question is not closed.** A third
  configuration was measured: *two clients, two peripherals* (EBS desktop holding the H10 via
  btleplug, brainflow holding the Muse in a separate Python process), 60 s baseline / 120 s dual /
  45 s recovery on the Studio. H10 **1.000 → 0.999 → 1.000 Hz**, max inter-sample gap **1.05 s in
  all three phases**, identical to the hundredth — no measurable degradation. Muse **30,914 samples
  in 120.7 s = 256.2 Hz** against a nominal 256; rate *at* nominal means no loss, and the 0.211 s
  max gap is arrival jitter (loss would read *below* nominal). So CoreBluetooth on this host
  sustains two concurrent peripheral links at full rate, and REQ-015-3 is satisfiable here.
  **What it does NOT establish:** btleplug holding *both* peripherals inside *one* process, which is
  what the desktop app would do — the configuration this bullet actually asks about. Also untested:
  long sessions (2 min only), contact quality (the probe counted samples and timestamps, discarding
  the voltage channels), and battery/thermal. Repro: `scripts/probe_dual_ble.py`.

  **Spike result 2026-09-10 — one client, one adapter, two peripherals: PASS.** The configuration
  this bullet actually asks about, run outside the app (`desktop/src-tauri/examples/dual_ble_spike.rs`,
  `cargo run --release --example dual_ble_spike`). H10 connected and subscribed first, Muse connected
  second on the same adapter and handshaked (`h → p1035 → dc001 → dc001`, write-without-response),
  then 90 s holding both:

  | source | notifications | rate | worst gap |
  |---|---|---|---|
  | H10 | 90 | 1.00 Hz (nominal 1) | 1.05 s |
  | Muse | 3495 | 38.83 Hz | 0.08 s |

  The H10 held exactly nominal for the full 90 s with the Muse streaming, and its worst gap (1.05 s)
  is identical to the two-process probe and to solo capture — **REQ-015-3 is satisfied at the
  transport layer.** ⚠️ **The Muse figure is BLE notifications — multiplexed packets — NOT samples.**
  This spike decodes nothing; a packet carries several sub-frames, so packet rate and sample rate are
  different quantities (brainflow reported 256 Hz of decoded EEG over the same link earlier the same
  day). **Still open:** long sessions (90 s only), decode under dual load, contact quality,
  battery/thermal, and the app-level state machine — the spike bypasses `AppState`, the generation
  counter and the reconnect supervisor entirely, and those are where the remaining work is.

  **Spike 2 result 2026-09-10 (evening) — decode under dual load, 600 s, contact measured: PASS with
  two findings.** `desktop/src-tauri/examples/dual_ble_decode_spike.rs` (muse-rs 0.1.0 as a
  dev-dependency for `parse_athena_notification`; DRL/REF read from raw bytes since muse-rs discards
  `0x53`; CON-015-5 contact per 1 s tick; raw packets + per-second summaries to the gitignored
  fixture dir). One process, one adapter, H10 first then Muse, wearer seated at the desk:

  | source | 600 s | rate | note |
  |---|---|---|---|
  | H10 | 602 beats | 1.00 Hz | worst gap 1.74 s (one late notification; solo/spike-1 was 1.05 s) |
  | Muse packets | 23,312 | 38.85 pk/s | 5 packet-index discontinuities |
  | Muse EEG, each channel | 152,248 samples | **253.7 Hz** | decoded µV, all four channels equal |
  | DRL/REF | — | 8241–8263 LSB | +49…+71 above mid-rail 8192, never left the band |
  | Battery | 71 % → 68 % | | |

  Contact (share of 1 s ticks): TP9 good 55 / marginal 42 / poor 3 %; AF7 79 / 13 / 8; AF8 58 / 25 / 17;
  TP10 33 / 58 / 9. Alpha RMS 1–8 µV in good windows (REQ-015-5b range). Poor windows arrived in
  bursts on both channels of a pair at once (both mastoids, or both forehead), i.e. movement/band
  contact, not one bad electrode.

  **Finding A — the EEG sample rate is ~254 Hz, not 256, and it is the device.** 253.7 Hz here over
  600 s and 254.2 Hz in the 2026-07-27 capture, on different tooling. The 5 index drops cannot account
  for it (≈ 1,400 samples short vs ≤ 5 × 16). Consequence for the join with the H10 and the transcript
  clock: **never build EEG time from sample count × 1/256** — 0.9 % drift is ~5 s per 10 min. Time from
  host arrival per packet (SPEC-010's clock), samples interpolated within the packet. Worth pinning
  `fs` as a measured per-session value in `central_meta`, not the nominal.

  **Finding B — contact is a pair-wise, bursty state, so a per-channel 1 s label under-describes it.**
  The 1 s tick is right for the record (CON-015-5 stands) but the consumer wants a run-length view:
  most of the session is usable (good+marginal 83–97 % per channel), the unusable part is a handful
  of 10–30 s bursts. Still open: whether contact should be gated per-pair.

  **Still open after this spike:** long sessions (> 10 min), battery/thermal, the app-level state
  machine, and the CON-015-5 thresholds themselves (provisional; this is the first labelled data).

- ~~**Second-process capture as a fallback transport**~~ — **REJECTED 2026-09-10 (Mat).** The probe
  incidentally demonstrated it (Muse held by a separate process writing its own wall-clock-stamped
  stream, joined post-hoc), and it is consistent with ADR-015-2. Rejected on **UX grounds: the
  cerebral signal is managed by EBS, in one app.** ADR-015-1 stands. Recorded so it is not
  rediscovered and re-proposed.

- **Where the one-client two-peripheral constraint actually lives (2026-09-10).** The spec says
  "both apps currently manage a single peripheral" and calls a two-device connection state machine
  genuinely new work. True at the app level, but narrower than it reads: the BLE layer is already
  device-parameterised — `connect_and_stream(adapter, address, tx, label, …)`, `teardown_peripheral(
  adapter, address)`, and `DeviceRegistry` already maps serials to A/B participant labels for dyad
  capture. The single-device constraint is one `active: bool` guard in `cmd_connect` ("A device is
  already connected") plus an `AppState` shaped for one connection, one generation counter and one
  channel. So the work is in the **connection state machine**, not the transport. Not yet verified:
  that btleplug sustains both peripherals on one adapter in one process — the spike that answers it
  can bypass the app entirely.

- **Is a genuinely simultaneous raw+reference capture possible at all?** Unresolved. Both routes tried on macOS failed (§Decode). A single client that decodes *and* retains raw bytes — a muse-rs harness emitting both, or OpenMuse instrumented at its notification callback — would sidestep the contention entirely, since it never needs two connections. Worth an hour if sample-exact parity against a third witness is ever wanted; **not on the critical path** now that ADR-015-6 removes it from the guard.

- **Fixture inclusion under the biometric-data policy — DECISION NEEDED (Mat).** *Update 2026-09-10: option (i) is built and waiting on the word — `golden_eyes_closed.bin` (41 KB, 389 packets, 10 s eyes-closed, header bytes 2..9 zeroed) + `golden_reference_uv.bin` (muse-rs, hashes in the fixture README). Both are on the Studio, untracked. TEST-015-2a/2b/2c pass locally against them (7/7); on a fresh clone the suite fails loudly until they are committed.* REQ-015-5a/5b need golden raw bytes and a frozen reference vector *in the repo*, or the guard cannot run in CI or on a fresh clone; a test that silently skips is not a guard. But `m3data/earthian-biosense` is **public** and the raw bytes are EEG. Three options: **(i)** commit a decimated slice — the minimum packets to satisfy both layers, likely a few seconds plus one eyes-closed window, stripped of session context and identifiers, as a narrow well-scoped inclusion; **(ii)** commit the full capture; **(iii)** keep fixtures local and accept that the guard runs only on Mat's machines. Leaning **(i)**. Serials and BLE addresses stay out under all three.
- **Battery / thermal** — two concurrent BLE peripherals + FFT per tick; quantify on a long session.
- **Timestamp alignment across substrates** — the H10 tick and the Muse stream have independent clocks; the join for cross-substrate analysis needs a shared reference (monotonic host clock at notification receipt is the v0.1 default; assess drift). This is the seam H2 (lead/lag) depends on.
- **Extraction trigger** — at what point does ADR-015-1's shared core get extracted: when iOS starts, or earlier if a Python parity client is wanted?

---

## Acceptance for v0.1 (desktop)

1. Golden Athena capture (raw `273e0013` bytes + a frozen reference µV vector) available to the harness — scope of what is *committed* vs local pending the fixture-inclusion decision (§Open questions).
2. Both parity layers green: muse-rs decodes the golden bytes to the frozen reference within ≤ 0.1 µV/sample (REQ-015-5a), **and** the decoder-independent anchors hold — DRL/REF within ±256 LSB of 8192, eyes-closed alpha RMS 2–60 µV (REQ-015-5b) — **and** both negative controls fail as expected (Tests 2c).
3. A live desktop session with a connected Muse writes: a 256 Hz `_eeg.jsonl` side-file (with `host_mono`), a 1 Hz `central` block in the primary JSONL, a base `session_start` declaration, a `central_start` (after handshake) and a `central_end` (final `seq`+count) — schema-1.6.0 valid, and the raw↔central join by `host_mono` resolves.
4. Contact quality reads `good` on seated forehead channels and flags `poor`/`marginal` on unseated behind-ear channels per the pinned §CON-015-5 thresholds, visible in the webview panel.
5. A **Berger check** end-to-end, read from the recorded `central` block (not a separate script). Amended 2026-07-27 — the v0.2 form used `rel_alpha` and **could have passed on ocular artifact alone**. All three conditions must hold:
   - **(a) De-biased ratio.** Eyes-closed posterior (TP9/TP10) mean `alpha / (theta+alpha+beta+gamma)` ≥ **1.3×** eyes-open. Computed from stored `bands`; no new field.
   - **(b) Artifact gate.** Mean eyes-open `delta` band power MUST NOT exceed mean eyes-closed `delta` by more than **3×**. Above that the baseline is ocular-contaminated and the run is void, not failed — reseat and repeat. On the 2026-07-27 capture TP9 was ~18×, so that session would correctly have been rejected rather than scored.
   - **(c) Direction agreement.** *Absolute* alpha band power must also rise eyes-open → eyes-closed. If the relative and absolute metrics disagree in direction, the result is **void**. This is the check that would have caught the 2026-07-27 false positive, and the mirror of the 2026-07-25 false null where absolute power lied and relative rescued it. Neither metric is trusted alone.

   The first-contact **1.54×** this criterion once echoed carries the same bias and is *not* a validated target — directionally right, magnitude unverified.
6. Muse disabled / dropped / poor-contact / dual-BLE-unstable → autonomic (H10) capture is a valid autonomic-only 1.6.0 session (base declaration only, no `central_start`, no `central` block); no crash, graceful log.

Once these hold on one live session, v0.1 is done. Microstate templates, the `central_phase` trajectory, cross-substrate coupling analysis, and iOS are downstream builds.

---

## Clean-context review (2026-07-25)

A fresh-context adversarial reviewer — given only the v0.1 draft + its cited sources and mandated to find defects (USDD P12 gate) — returned **2 critical, 7 major, 5 minor**. All verified legitimate against the sources/codebase. Folded in at v0.2:

**Fixed (this revision):**
- **C1 — over-claimed S2-1 closure.** The discriminator was added to the Rust lineage only; the claim "resolves S2-1" was false (Python stays 1.4.0, undeclared). Scoped honestly: Rust establishes the mechanism; Python adoption + number reconciliation tracked (ADR-015-5, Provenance, §heading).
- **C2 — REQ-015-2 self-contradiction** ("byte-identical to 1.5.0" *and* carrying declaration keys). Resolved by the unconditional-declaration decision: 1.6.0 is additive, not byte-identical (Goal, REQ-015-2, ADR-015-5).
- **M3 — golden-vector parity had no mechanism** (brainflow decodes live-only and is Python). *v0.2 fix:* record raw bytes + brainflow µV once into the fixture; assert muse-rs against it in-harness. **⚠️ SUPERSEDED at v0.3 — that fix was unexecutable** (the joint capture cannot be performed) *and* aimed at the wrong reference. Replaced by the two-layer guard, REQ-015-5a/5b + ADR-015-6. The finding was right; the remedy was not.
- **M4 — 256 Hz↔1 Hz join hand-waved.** Now a shared `host_mono` on every raw batch and central tick; association rule `[t, t+1s)` (Data tiers, central block, raw record, CON-015-3).
- **M5 — session_start written before Muse outcome; `raw_file` could dangle.** Now: base declaration always; `central_start` only after handshake; `central_end` finalises `seq`/count for truncation detection (session_start §, REQ-015-3, CON-015-4).
- **M6 — CON-015-2 "iterate keys" collided with the aux-vs-scalp correction.** Now: storage is channel-agnostic, EEG *semantics* are `scalp_channels`-only (CON-015-2, `central_meta.scalp_channels`, central block).
- **M7 — contact heuristic under-specified for cross-engine parity.** Now pinned as CON-015-5 (bandpass + std/range thresholds as named constants + fixture).
- **M8 — band edges unpinned; gamma vs `rel_alpha` denominator inconsistent.** Now a pinned band table; gamma capped 30–40 Hz inside the 1–40 denominator (CON-015-3).
- **M9 — subjective thresholds.** Berger now **≥ 1.3×** numeric (Acceptance 5); non-fusion now an enumerable allowlist invariant (REQ-015-1, TEST-8).
- **m10 — dual-BLE asserted as fact** while unverified. Demoted to "assumed pending test" + fallback (disable EEG, protect autonomic) (BLE §, REQ-015-3).
- **m11 — decode tolerance unspecified.** Now ≤ 0.1 µV/sample (REQ-015-5a at v0.3).
- **m12 — conditional bump.** Resolved by unconditional 1.6.0 (frontmatter, Goal).
- **m13 — `n_samples` made band power incomparable across ticks.** Now PSD-normalised (µV²/Hz) + a drop-handling floor (CON-015-3).
- **m14 — optional Python surface would reproduce S2-1.** Now requires Python to adopt the declaration first (Implementation surfaces).

**Deferred (tracked residue — for Mat / later builds):**
- **Full S2-1 closure** — the Python lineage adopting the 1.6.0 declaration + cross-engine version-number reconciliation.
- **Cross-*device* clock drift** (H10 vs Muse absolute alignment) — the within-host `host_mono` join is defined; absolute drift assessment is an Open Question, needed before H2 lead/lag claims.
- ~~**Preset decision (ADR-015-4)**~~ — DECIDED: `p1035` / EEG4. (Optional `p1041` aux-characterisation run deferred.)
- **Raw side-file format** (JSONL vs binary) — decide on the sizing test.
- **CON-015-5 thresholds are provisional** — calibrate on the first labelled sessions.

---

## Amendment record — v0.3 (2026-07-27)

Driven by the first live capture against this spec. Nothing here came from re-reading the
document; all four changes came from trying to execute it.

| # | Change | Why |
|---|---|---|
| A1 | **REQ-015-5 split into 5a/5b/5c**; brainflow demoted from reference decoder to exploration tool (ADR-015-6) | The v0.2 mechanism was **unexecutable** — raw bytes and brainflow µV cannot be captured from one session (both routes tested and failed). It also guarded the wrong proposition: agreement between two same-lineage decoders is not correctness. |
| A2 | **Acceptance 5 (Berger) hardened** — de-biased denominator, artifact gate, direction agreement | The v0.2 criterion used `rel_alpha`, whose 1–40 denominator carries condition-dependent ocular artifact. It **could have passed on blinks alone**; the 2026-07-27 capture scored 9.75× and was in fact void. |
| A3 | **`rel_alpha` scope narrowed** in CON-015-3 and the central-block description | Same root cause; the field stays, its use for open/closed contrasts does not. Propagated to every site the correction reaches. |
| A4 | **Packet framing + `0x53` recorded**; Tests-first step 1 closed; negative-control tests added (2c) | Framing validated empirically (zero resyncs over 1,806 packets). `0x53` = DRL/REF now does load-bearing work in REQ-015-5b(1). |

**Two things this amendment deliberately does not do.** It does not claim the dual-BLE
question was answered — the 2026-07-27 test was two clients contending for one peripheral,
not one client holding two, and conflating them would retire an open question on evidence
that does not address it. And it does not decide fixture inclusion, which is Mat's call
under the biometric-data policy.

**Pattern worth naming for the next reviewer.** M3 in the 2026-07-25 clean-context review
correctly found that golden-vector parity had no mechanism. The v0.2 fix supplied one that
could not be run. A reviewer reading only the document could not have caught that — the
mechanism was plausible on the page and failed only against hardware. *Some defects are
reachable only by execution.* The USDD clean-context gate catches what can be read; it
does not catch what must be run.

---

## Provenance

- Research frame, hypotheses (H1–H4), ethics: `concepts/muse-s-integration-concept.md`.
- Verified BLE handshake, GATT map, packet framing, decode landscape: `concepts/muse-athena-first-contact.md` (first contact 2026-07-25; framing validated, `0x53` identified, relative-alpha correction and the concurrency finding added 2026-07-27).
- Golden capture provenance, measured anchors, and the physiological numbers behind REQ-015-5b: `tests/fixtures/muse_athena/README.md` (2026-07-27). Recordings local-only pending the fixture-inclusion decision.
- Tag table and decode constants (`ATHENA_EEG_SCALE = 0.0885`, 14-bit LE, mid-rail 8192): `muse-rs` 0.1.0 `src/parse.rs` / `src/protocol.rs`, crediting OpenMuse's `decode.py`. **Note these are one lineage, not independent witnesses** — the reason REQ-015-5b exists.
- Additive-channel pattern + golden-vector / tests-first discipline: [[SPEC-013-accelerometer-motion-channel]].
- Substrate/version-discriminator residue this spec **partially addresses (Rust mechanism only; Python adoption tracked)**: [[SPEC-014-two-axis-mode-classification]] §Residue S2-1.
- Tri-substrate research direction this unblocks: `Action-Research/research/tri-substrate-form-discovery.md`.
