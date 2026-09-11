//! Central-nervous substrate (SPEC-015 v0.1): Muse S Athena EEG on the desktop.
//!
//! Pure signal code — no BLE, no I/O. The Muse transport lives in
//! `ble::muse`; the record writer is `session::SessionLogger` (single writer
//! for the central lifecycle). This module owns:
//!
//!   * the pinned constants (CON-015-3 band edges, CON-015-5 contact
//!     thresholds, the handshake and characteristic prefixes),
//!   * the 1–40 Hz contact filter and the contact classifier (CON-015-5),
//!   * Hann-windowed periodogram band powers + `rel_alpha` (CON-015-3),
//!   * the 1 Hz `CentralTicker` that turns decoded samples into a
//!     `CentralTick`, and the allowlisted JSON shape of that tick (REQ-015-1),
//!   * the consumer-side helpers: capability fold (REQ-015-6) and raw-file
//!     truncation detection.
//!
//! The decode itself is muse-rs (ADR-015-1); the `0x53` DRL/REF walk is here
//! because muse-rs discards that sub-frame (ADR-015-6).

use serde::Serialize;
use serde_json::{json, Value};
use std::collections::BTreeMap;

// ---------------------------------------------------------------------------
// Pinned constants
// ---------------------------------------------------------------------------

/// The four scalp electrodes of the p1035 / EEG4 preset, in muse-rs
/// electrode-index order (ADR-015-4).
pub const CH_SCALP: [&str; 4] = ["TP9", "AF7", "AF8", "TP10"];
/// Nominal EEG sample rate (Hz). The measured rate is a residue (`fs_measured`).
pub const FS_NOMINAL: f64 = 256.0;

// CON-015-5 contact thresholds (µV), provisional, identical in every engine.
pub const CONTACT_STD_GOOD_MIN: f64 = 5.0;
pub const CONTACT_STD_GOOD_MAX: f64 = 40.0;
pub const CONTACT_RANGE_GOOD_MAX: f64 = 400.0;
pub const CONTACT_STD_MARGINAL_MAX: f64 = 80.0;
pub const CONTACT_RANGE_MARGINAL_MAX: f64 = 2000.0;

// CON-015-3 band edges (Hz). Gamma is capped at 40 so it sits inside the
// `rel_alpha` denominator.
pub const BAND_DELTA: (f64, f64) = (1.0, 4.0);
pub const BAND_THETA: (f64, f64) = (4.0, 8.0);
pub const BAND_ALPHA: (f64, f64) = (8.0, 13.0);
pub const BAND_BETA: (f64, f64) = (13.0, 30.0);
pub const BAND_GAMMA: (f64, f64) = (30.0, 40.0);
/// Denominator of `rel_alpha`: total 1–40 Hz.
pub const BAND_TOTAL: (f64, f64) = (1.0, 40.0);

/// A tick shorter than this writes `bands: null`, `rel_alpha: null` (too
/// short to resolve 1 Hz). Contact is still classified.
pub const TICK_MIN_SAMPLES_FOR_BANDS: usize = 64;
/// CON-015-3 drop handling: a tick with fewer samples than this floor MUST
/// set `contact_ok = false` (packet loss, not physiology).
pub const TICK_CONTACT_OK_FLOOR: usize = 128;

/// Muse preset (ADR-015-4: p1035 / EEG4).
pub const MUSE_PRESET: &str = "p1035";
/// Handshake written to the control characteristic, 300 ms apart,
/// write-without-response.
pub const MUSE_HANDSHAKE: [&str; 4] = ["h", "p1035", "dc001", "dc001"];
/// Control characteristic UUID prefix (`273e0001-…`).
pub const MUSE_CONTROL_PREFIX: &str = "273e0001";
/// Data (EEG + telemetry) characteristic UUID prefix (`273e0013-…`).
pub const MUSE_DATA_PREFIX: &str = "273e0013";

/// REQ-015-1 allowlist: every key the `central` object may carry.
pub const CENTRAL_ALLOWLIST: [&str; 7] = [
    "host_mono",
    "bands",
    "rel_alpha",
    "contact",
    "contact_ok",
    "n_samples",
    "central_phase",
];

/// Length-prefixed, newline-terminated Muse control command.
pub fn frame(cmd: &str) -> Vec<u8> {
    let mut b = vec![(cmd.len() + 1) as u8];
    b.extend_from_slice(cmd.as_bytes());
    b.push(0x0A);
    b
}

// ---------------------------------------------------------------------------
// Contact filter (RBJ biquads, Butterworth Q) — CON-015-5
// ---------------------------------------------------------------------------

/// One RBJ-cookbook second-order section. Two cascaded per edge give a
/// 4th-order response (the spike-grade equivalent of CON-015-5's filter).
#[derive(Clone, Debug)]
pub struct Biquad {
    b0: f64,
    b1: f64,
    b2: f64,
    a1: f64,
    a2: f64,
    z1: f64,
    z2: f64,
}

impl Biquad {
    pub fn lowpass(fc: f64, fs: f64) -> Self {
        let w = 2.0 * std::f64::consts::PI * fc / fs;
        let (s, c) = w.sin_cos();
        let alpha = s / (2.0 * std::f64::consts::FRAC_1_SQRT_2);
        let a0 = 1.0 + alpha;
        Self {
            b0: (1.0 - c) / 2.0 / a0,
            b1: (1.0 - c) / a0,
            b2: (1.0 - c) / 2.0 / a0,
            a1: -2.0 * c / a0,
            a2: (1.0 - alpha) / a0,
            z1: 0.0,
            z2: 0.0,
        }
    }

    pub fn highpass(fc: f64, fs: f64) -> Self {
        let w = 2.0 * std::f64::consts::PI * fc / fs;
        let (s, c) = w.sin_cos();
        let alpha = s / (2.0 * std::f64::consts::FRAC_1_SQRT_2);
        let a0 = 1.0 + alpha;
        Self {
            b0: (1.0 + c) / 2.0 / a0,
            b1: -(1.0 + c) / a0,
            b2: (1.0 + c) / 2.0 / a0,
            a1: -2.0 * c / a0,
            a2: (1.0 - alpha) / a0,
            z1: 0.0,
            z2: 0.0,
        }
    }

    pub fn run(&mut self, x: f64) -> f64 {
        let y = self.b0 * x + self.z1;
        self.z1 = self.b1 * x - self.a1 * y + self.z2;
        self.z2 = self.b2 * x - self.a2 * y;
        y
    }
}

/// The CON-015-5 contact filter: 2×HP 1 Hz then 2×LP 40 Hz, at `FS_NOMINAL`.
pub fn contact_filter() -> Vec<Biquad> {
    vec![
        Biquad::highpass(1.0, FS_NOMINAL),
        Biquad::highpass(1.0, FS_NOMINAL),
        Biquad::lowpass(40.0, FS_NOMINAL),
        Biquad::lowpass(40.0, FS_NOMINAL),
    ]
}

// ---------------------------------------------------------------------------
// Contact classification — CON-015-5
// ---------------------------------------------------------------------------

#[derive(Serialize, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Debug)]
#[serde(rename_all = "lowercase")]
pub enum Contact {
    Poor,
    Marginal,
    Good,
}

impl Contact {
    pub fn as_str(&self) -> &'static str {
        match self {
            Contact::Good => "good",
            Contact::Marginal => "marginal",
            Contact::Poor => "poor",
        }
    }
}

/// Population std (µV) and range (max−min, µV) of a segment. Empty → (0, 0).
pub fn std_range(x: &[f64]) -> (f64, f64) {
    if x.is_empty() {
        return (0.0, 0.0);
    }
    let n = x.len() as f64;
    let mean = x.iter().sum::<f64>() / n;
    let var = x.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / n;
    let (mn, mx) = x
        .iter()
        .fold((f64::INFINITY, f64::NEG_INFINITY), |(a, b), &v| (a.min(v), b.max(v)));
    (var.sqrt(), mx - mn)
}

/// CON-015-5, on the bandpassed + constant-detrended segment's std/range.
pub fn classify_contact(std: f64, range: f64) -> Contact {
    if (CONTACT_STD_GOOD_MIN..=CONTACT_STD_GOOD_MAX).contains(&std) && range < CONTACT_RANGE_GOOD_MAX {
        Contact::Good
    } else if std <= CONTACT_STD_MARGINAL_MAX && range < CONTACT_RANGE_MARGINAL_MAX {
        Contact::Marginal
    } else {
        Contact::Poor
    }
}

// ---------------------------------------------------------------------------
// Band powers — CON-015-3
// ---------------------------------------------------------------------------

/// Mean one-sided PSD over each band, µV²/Hz.
#[derive(Serialize, Clone, Copy, PartialEq, Debug, Default)]
pub struct Bands {
    pub delta: f64,
    pub theta: f64,
    pub alpha: f64,
    pub beta: f64,
    pub gamma: f64,
}

/// Hann-windowed, mean-removed, one-sided periodogram PSD:
/// `PSD_k = 2|X_k|² / (fs · Σw²)`, so `Σ PSD_k · df` ≈ variance. Naive DFT
/// (N ≤ 256 per tick). Returns `(df, psd)` with `psd[k]` for `k = 0..=N/2`.
fn periodogram(samples: &[f64], fs: f64) -> (f64, Vec<f64>) {
    let n = samples.len();
    let mean = samples.iter().sum::<f64>() / n as f64;
    let w: Vec<f64> = (0..n)
        .map(|i| 0.5 - 0.5 * (2.0 * std::f64::consts::PI * i as f64 / n as f64).cos())
        .collect();
    let wpow = w.iter().map(|v| v * v).sum::<f64>();
    let xw: Vec<f64> = samples.iter().zip(&w).map(|(v, w)| (v - mean) * w).collect();
    let df = fs / n as f64;
    let mut psd = Vec::with_capacity(n / 2 + 1);
    for k in 0..=n / 2 {
        let step = 2.0 * std::f64::consts::PI * k as f64 / n as f64;
        let (mut re, mut im) = (0.0, 0.0);
        for (i, v) in xw.iter().enumerate() {
            let (s, c) = (step * i as f64).sin_cos();
            re += v * c;
            im -= v * s;
        }
        psd.push(2.0 * (re * re + im * im) / (fs * wpow));
    }
    (df, psd)
}

/// Mean PSD over the bins whose centre frequency lies in `[lo, hi)`.
fn band_mean(psd: &[f64], df: f64, band: (f64, f64)) -> f64 {
    let k_lo = (band.0 / df).ceil() as usize;
    let mut k_hi = (band.1 / df).ceil() as usize; // exclusive
    if k_hi > psd.len() {
        k_hi = psd.len();
    }
    if k_hi <= k_lo {
        return 0.0;
    }
    psd[k_lo..k_hi].iter().sum::<f64>() / (k_hi - k_lo) as f64
}

/// CON-015-3 band powers for one tick. `None` when the tick is shorter than
/// `TICK_MIN_SAMPLES_FOR_BANDS`.
pub fn band_powers(samples: &[f64], fs: f64) -> Option<Bands> {
    if samples.len() < TICK_MIN_SAMPLES_FOR_BANDS {
        return None;
    }
    let (df, psd) = periodogram(samples, fs);
    Some(Bands {
        delta: band_mean(&psd, df, BAND_DELTA),
        theta: band_mean(&psd, df, BAND_THETA),
        alpha: band_mean(&psd, df, BAND_ALPHA),
        beta: band_mean(&psd, df, BAND_BETA),
        gamma: band_mean(&psd, df, BAND_GAMMA),
    })
}

fn bw(b: (f64, f64)) -> f64 {
    b.1 - b.0
}

/// `rel_alpha` = alpha power / total(1–40) power, power = mean PSD × bandwidth.
/// Computable from the stored `bands` alone (CON-015-3). 0 when total is 0.
pub fn rel_alpha(b: &Bands) -> f64 {
    let alpha = b.alpha * bw(BAND_ALPHA);
    let total = b.delta * bw(BAND_DELTA)
        + b.theta * bw(BAND_THETA)
        + alpha
        + b.beta * bw(BAND_BETA)
        + b.gamma * bw(BAND_GAMMA);
    if total > 0.0 {
        alpha / total
    } else {
        0.0
    }
}

// ---------------------------------------------------------------------------
// DRL/REF walk — ADR-015-6 (muse-rs discards 0x53)
// ---------------------------------------------------------------------------

/// Walk one `273e0013` packet for `0x53` DRL/REF sub-frames and return the raw
/// u16 LE values (12 per sub-frame: 2 ch × 6 samples interleaved).
pub fn drl_values(packet: &[u8]) -> Vec<u16> {
    let mut out = Vec::new();
    if packet.len() < 10 {
        return out;
    }
    let pkt_len = packet[0] as usize;
    let mut idx = 9usize;
    while idx < packet.len() {
        let tag = packet[idx];
        let start = idx + 5;
        match muse_rs::parse::athena_payload_len(tag) {
            Some(len) => {
                let end = start + len;
                if end > packet.len() {
                    idx += 1;
                    continue;
                }
                if tag == 0x53 {
                    out.extend(
                        packet[start..end]
                            .chunks_exact(2)
                            .map(|c| u16::from_le_bytes([c[0], c[1]])),
                    );
                }
                idx = end;
            }
            None if tag == 0x88 => {
                idx = pkt_len.min(packet.len());
            }
            None => {
                idx += 1;
            }
        }
    }
    out
}

// ---------------------------------------------------------------------------
// Packet sequence — byte[1] wraps at 256; extend to a monotonic u64
// ---------------------------------------------------------------------------

#[derive(Debug, Default, Clone)]
pub struct SeqExtender {
    last: Option<u8>,
    base: u64,
}

impl SeqExtender {
    pub fn new() -> Self {
        Self::default()
    }

    /// Extend the packet's u8 index into a monotonically increasing u64.
    pub fn extend(&mut self, idx: u8) -> u64 {
        if let Some(prev) = self.last {
            if idx < prev {
                self.base += 256;
            }
        }
        self.last = Some(idx);
        self.base + idx as u64
    }
}

// ---------------------------------------------------------------------------
// The 1 Hz ticker
// ---------------------------------------------------------------------------

/// Per-channel state across ticks: the contact filter (stateful), this tick's
/// raw and filtered samples, and the last completed tick's contact class.
pub struct ChannelState {
    filter: Vec<Biquad>,
    raw: Vec<f64>,
    filtered: Vec<f64>,
    last_contact: Option<Contact>,
}

impl ChannelState {
    fn new() -> Self {
        Self {
            filter: contact_filter(),
            raw: Vec::with_capacity(300),
            filtered: Vec::with_capacity(300),
            last_contact: None,
        }
    }

    fn push(&mut self, uv: f64) {
        let mut y = uv;
        for f in self.filter.iter_mut() {
            y = f.run(y);
        }
        self.raw.push(uv);
        self.filtered.push(y);
    }
}

/// One closed 1 s tick (CON-015-3). `contact` is keyed by scalp channel.
#[derive(Serialize, Clone, Debug)]
pub struct CentralTick {
    pub host_mono: f64,
    /// Min over scalp channels of samples in the window (≤ 256).
    pub n_samples: usize,
    pub contact: BTreeMap<String, Contact>,
    pub contact_ok: bool,
    pub rel_alpha: Option<BTreeMap<String, f64>>,
    pub bands: Option<BTreeMap<String, Bands>>,
}

/// Accepts decoded EEG samples per scalp channel and closes a tick on demand.
pub struct CentralTicker {
    channels: Vec<ChannelState>,
    fs: f64,
}

impl Default for CentralTicker {
    fn default() -> Self {
        Self::new()
    }
}

impl CentralTicker {
    pub fn new() -> Self {
        Self {
            channels: CH_SCALP.iter().map(|_| ChannelState::new()).collect(),
            fs: FS_NOMINAL,
        }
    }

    /// Feed samples for scalp channel `ch` (index into `CH_SCALP`); others ignored.
    pub fn push(&mut self, ch: usize, samples: &[f64]) {
        if let Some(state) = self.channels.get_mut(ch) {
            for &s in samples {
                state.push(s);
            }
        }
    }

    /// Contact of the most recently completed tick; `None` until one closes.
    pub fn last_contact(&self) -> Option<BTreeMap<String, Contact>> {
        let mut m = BTreeMap::new();
        for (i, ch) in self.channels.iter().enumerate() {
            m.insert(CH_SCALP[i].to_string(), ch.last_contact?);
        }
        Some(m)
    }

    /// Close the current window: classify contact, compute bands, clear buffers.
    pub fn close_tick(&mut self, host_mono: f64) -> CentralTick {
        let mut contact = BTreeMap::new();
        let mut rel = BTreeMap::new();
        let mut bands = BTreeMap::new();
        let mut n_samples = usize::MAX;
        let mut all_bands = true;
        for (i, ch) in self.channels.iter_mut().enumerate() {
            let name = CH_SCALP[i].to_string();
            let (sd, rg) = std_range(&ch.filtered);
            let cls = classify_contact(sd, rg);
            ch.last_contact = Some(cls);
            contact.insert(name.clone(), cls);
            n_samples = n_samples.min(ch.raw.len());
            match band_powers(&ch.raw, self.fs) {
                Some(b) => {
                    rel.insert(name.clone(), rel_alpha(&b));
                    bands.insert(name, b);
                }
                None => all_bands = false,
            }
            ch.raw.clear();
            ch.filtered.clear();
        }
        if n_samples == usize::MAX {
            n_samples = 0;
        }
        let contact_ok = n_samples >= TICK_CONTACT_OK_FLOOR
            && contact.values().all(|c| *c >= Contact::Marginal);
        CentralTick {
            host_mono,
            n_samples,
            contact,
            contact_ok,
            rel_alpha: if all_bands { Some(rel) } else { None },
            bands: if all_bands { Some(bands) } else { None },
        }
    }
}

fn r3(v: f64) -> f64 {
    (v * 1000.0).round() / 1000.0
}

/// The `central` object as written to the session file and emitted to the
/// webview: exactly `CENTRAL_ALLOWLIST`'s keys (REQ-015-1), floats at 3 dp,
/// `central_phase` present-and-null (NFR-015-2, RESERVED).
pub fn central_tick_json(tick: &CentralTick) -> Value {
    let bands = match &tick.bands {
        Some(b) => {
            let m: serde_json::Map<String, Value> = b
                .iter()
                .map(|(k, v)| {
                    (
                        k.clone(),
                        json!({
                            "delta": r3(v.delta),
                            "theta": r3(v.theta),
                            "alpha": r3(v.alpha),
                            "beta": r3(v.beta),
                            "gamma": r3(v.gamma),
                        }),
                    )
                })
                .collect();
            Value::Object(m)
        }
        None => Value::Null,
    };
    let rel = match &tick.rel_alpha {
        Some(r) => {
            let m: serde_json::Map<String, Value> =
                r.iter().map(|(k, v)| (k.clone(), json!(r3(*v)))).collect();
            Value::Object(m)
        }
        None => Value::Null,
    };
    let contact: serde_json::Map<String, Value> = tick
        .contact
        .iter()
        .map(|(k, v)| (k.clone(), json!(v.as_str())))
        .collect();
    json!({
        "host_mono": r3(tick.host_mono),
        "bands": bands,
        "rel_alpha": rel,
        "contact": Value::Object(contact),
        "contact_ok": tick.contact_ok,
        "n_samples": tick.n_samples,
        "central_phase": Value::Null,
    })
}

// ---------------------------------------------------------------------------
// Consumer-side helpers — REQ-015-6, truncation detection
// ---------------------------------------------------------------------------

fn str_list(v: &Value) -> Vec<String> {
    v.as_array()
        .map(|a| a.iter().filter_map(|x| x.as_str().map(String::from)).collect())
        .unwrap_or_default()
}

/// Effective `(substrates, capabilities)` of a session: the `session_start`
/// base, then every `central_start` record's `*_add` folded in (deduplicated,
/// in order of appearance). Never consults `schema_version`.
pub fn fold_capabilities(records: &[Value]) -> (Vec<String>, Vec<String>) {
    let mut substrates: Vec<String> = Vec::new();
    let mut capabilities: Vec<String> = Vec::new();
    let push_all = |dst: &mut Vec<String>, src: Vec<String>| {
        for s in src {
            if !dst.contains(&s) {
                dst.push(s);
            }
        }
    };
    for r in records {
        match r.get("type").and_then(Value::as_str) {
            Some("session_start") => {
                push_all(&mut substrates, str_list(&r["substrates"]));
                push_all(&mut capabilities, str_list(&r["capabilities"]));
            }
            Some("central_start") => {
                push_all(&mut substrates, str_list(&r["substrates_add"]));
                push_all(&mut capabilities, str_list(&r["capabilities_add"]));
            }
            _ => {}
        }
    }
    (substrates, capabilities)
}

/// A raw side-file is complete iff its last `seq` equals `central_end.final_seq`
/// (both absent — nothing written, nothing declared — also counts as complete).
/// A `central_end` without a `final_seq` key never validates a file.
pub fn raw_file_complete(last_raw_seq: Option<u64>, central_end: &Value) -> bool {
    match central_end.get("final_seq") {
        None => false,
        Some(Value::Null) => last_raw_seq.is_none(),
        Some(v) => v.as_u64().is_some() && v.as_u64() == last_raw_seq,
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// Deterministic Gaussian-ish noise (sum of 12 uniforms) from an LCG.
    struct Noise(u64);
    impl Noise {
        fn uniform(&mut self) -> f64 {
            self.0 = self.0.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
            ((self.0 >> 11) as f64) / ((1u64 << 53) as f64)
        }
        fn gauss(&mut self, sd: f64) -> f64 {
            let s: f64 = (0..12).map(|_| self.uniform()).sum::<f64>() - 6.0;
            s * sd
        }
    }

    fn sinusoid(hz: f64, amp: f64, n: usize) -> Vec<f64> {
        (0..n)
            .map(|i| amp * (2.0 * std::f64::consts::PI * hz * i as f64 / FS_NOMINAL).sin())
            .collect()
    }

    fn run_filter(x: &[f64]) -> Vec<f64> {
        let mut f = contact_filter();
        x.iter()
            .map(|&v| {
                let mut y = v;
                for s in f.iter_mut() {
                    y = s.run(y);
                }
                y
            })
            .collect()
    }

    // ── constants pinned to the spec ──────────────────────────────────────
    #[test]
    fn pinned_constants_match_con_015_3_and_5() {
        assert_eq!(CONTACT_STD_GOOD_MIN, 5.0);
        assert_eq!(CONTACT_STD_GOOD_MAX, 40.0);
        assert_eq!(CONTACT_RANGE_GOOD_MAX, 400.0);
        assert_eq!(CONTACT_STD_MARGINAL_MAX, 80.0);
        assert_eq!(CONTACT_RANGE_MARGINAL_MAX, 2000.0);
        assert_eq!(BAND_DELTA, (1.0, 4.0));
        assert_eq!(BAND_THETA, (4.0, 8.0));
        assert_eq!(BAND_ALPHA, (8.0, 13.0));
        assert_eq!(BAND_BETA, (13.0, 30.0));
        assert_eq!(BAND_GAMMA, (30.0, 40.0));
        assert_eq!(CH_SCALP, ["TP9", "AF7", "AF8", "TP10"]);
        assert_eq!(MUSE_PRESET, "p1035");
        assert_eq!(MUSE_HANDSHAKE, ["h", "p1035", "dc001", "dc001"]);
        assert_eq!(frame("h"), vec![2, b'h', 0x0A]);
        assert_eq!(frame("p1035"), vec![6, b'p', b'1', b'0', b'3', b'5', 0x0A]);
    }

    // ── TEST-015-3 contact classes ────────────────────────────────────────
    #[test]
    fn test_015_3_contact_thresholds_on_std_range() {
        assert_eq!(classify_contact(20.0, 100.0), Contact::Good);
        assert_eq!(classify_contact(5.0, 399.0), Contact::Good); // inclusive std min
        assert_eq!(classify_contact(40.0, 399.0), Contact::Good); // inclusive std max
        assert_eq!(classify_contact(4.9, 100.0), Contact::Marginal); // flat line: not good
        assert_eq!(classify_contact(20.0, 400.0), Contact::Marginal); // range boundary
        assert_eq!(classify_contact(60.0, 1000.0), Contact::Marginal);
        assert_eq!(classify_contact(80.0, 1999.0), Contact::Marginal);
        assert_eq!(classify_contact(80.1, 100.0), Contact::Poor);
        assert_eq!(classify_contact(20.0, 2000.0), Contact::Poor);
        // REQ-015-4: the first-contact false-null regime (std in the hundreds).
        assert_eq!(classify_contact(250.0, 900.0), Contact::Poor);
        assert_eq!(classify_contact(600.0, 3000.0), Contact::Poor);
    }

    #[test]
    fn test_015_3_synthetic_segments_classify_as_expected() {
        let mut rng = Noise(7);
        // Clean ~20 µV segment: 10 Hz sinusoid + a little noise, 1 s.
        let clean: Vec<f64> = sinusoid(10.0, 20.0, 256)
            .iter()
            .map(|v| v + rng.gauss(2.0))
            .collect();
        let (sd, rg) = std_range(&run_filter(&clean)[..]);
        assert_eq!(classify_contact(sd, rg), Contact::Good, "clean std {sd:.1} range {rg:.1}");

        // Drift/motion regime: broadband noise with std in the hundreds.
        let drift: Vec<f64> = (0..256).map(|_| rng.gauss(300.0)).collect();
        let (sd, rg) = std_range(&run_filter(&drift)[..]);
        assert!(sd > 100.0, "drift std {sd:.1}");
        assert_eq!(classify_contact(sd, rg), Contact::Poor);

        // Railed segment: parked at the 14-bit rail, one step to the other
        // rail mid-window (the bandpass turns the step into a huge swing).
        let mut railed = vec![-725.0; 128];
        railed.extend(vec![725.0; 128]);
        let (sd, rg) = std_range(&run_filter(&railed)[..]);
        assert_eq!(classify_contact(sd, rg), Contact::Poor, "railed std {sd:.1} range {rg:.1}");

        // A flat line (no signal at all) is not `good`.
        let flat = vec![0.0; 256];
        let (sd, rg) = std_range(&run_filter(&flat)[..]);
        assert_ne!(classify_contact(sd, rg), Contact::Good);
    }

    #[test]
    fn contact_serialises_lowercase_and_orders_poor_lt_marginal_lt_good() {
        assert_eq!(serde_json::to_value(Contact::Good).unwrap(), json!("good"));
        assert_eq!(serde_json::to_value(Contact::Marginal).unwrap(), json!("marginal"));
        assert_eq!(serde_json::to_value(Contact::Poor).unwrap(), json!("poor"));
        assert!(Contact::Poor < Contact::Marginal && Contact::Marginal < Contact::Good);
    }

    // ── TEST-015-4 band powers ────────────────────────────────────────────
    #[test]
    fn test_015_4_pure_10hz_sinusoid_alpha_dominates_and_is_length_invariant() {
        let full = band_powers(&sinusoid(10.0, 20.0, 256), FS_NOMINAL).unwrap();
        let half = band_powers(&sinusoid(10.0, 20.0, 128), FS_NOMINAL).unwrap();
        for b in [&full, &half] {
            assert!(b.alpha > 10.0 * b.delta, "alpha {} delta {}", b.alpha, b.delta);
            assert!(b.alpha > 10.0 * b.theta, "alpha {} theta {}", b.alpha, b.theta);
            assert!(b.alpha > 10.0 * b.beta, "alpha {} beta {}", b.alpha, b.beta);
            assert!(b.alpha > 10.0 * b.gamma, "alpha {} gamma {}", b.alpha, b.gamma);
            assert!(rel_alpha(b) > 0.9, "rel_alpha {}", rel_alpha(b));
        }
        // Parseval: a 20 µV sinusoid carries 200 µV² over a 5 Hz band → 40 µV²/Hz.
        assert!((full.alpha - 40.0).abs() < 4.0, "alpha PSD {}", full.alpha);
        // PSD normalisation keeps a half-length tick comparable (within 25 %).
        let ratio = half.alpha / full.alpha;
        assert!((0.75..=1.25).contains(&ratio), "half/full alpha ratio {ratio}");
    }

    #[test]
    fn test_015_4_white_noise_is_roughly_flat_across_bands() {
        let mut rng = Noise(42);
        let mut acc = Bands::default();
        let ticks = 200;
        for _ in 0..ticks {
            let x: Vec<f64> = (0..256).map(|_| rng.gauss(10.0)).collect();
            let b = band_powers(&x, FS_NOMINAL).unwrap();
            acc.delta += b.delta;
            acc.theta += b.theta;
            acc.alpha += b.alpha;
            acc.beta += b.beta;
            acc.gamma += b.gamma;
        }
        let means = [acc.delta, acc.theta, acc.alpha, acc.beta, acc.gamma].map(|v| v / ticks as f64);
        let expect = 100.0 / (FS_NOMINAL / 2.0); // variance / Nyquist bandwidth
        for (i, m) in means.iter().enumerate() {
            assert!(
                (0.7 * expect..=1.3 * expect).contains(m),
                "band {i} mean PSD {m:.3} vs flat {expect:.3}"
            );
        }
        let r = rel_alpha(&Bands {
            delta: means[0],
            theta: means[1],
            alpha: means[2],
            beta: means[3],
            gamma: means[4],
        });
        assert!((r - 5.0 / 39.0).abs() < 0.04, "flat rel_alpha {r}");
    }

    #[test]
    fn band_powers_is_none_below_64_samples() {
        assert!(band_powers(&sinusoid(10.0, 20.0, 63), FS_NOMINAL).is_none());
        assert!(band_powers(&sinusoid(10.0, 20.0, 64), FS_NOMINAL).is_some());
    }

    // ── DRL walk + seq ────────────────────────────────────────────────────
    #[test]
    fn drl_values_reads_0x53_subframes_as_u16_le() {
        // 9-byte header, then one 0x53 sub-frame: tag + 4 bytes + 12-byte payload.
        let mut pkt = vec![0u8; 9];
        pkt.extend_from_slice(&[0x53, 0, 0, 0, 0]);
        let payload_len = muse_rs::parse::athena_payload_len(0x53).expect("0x53 known");
        let mut payload = Vec::new();
        for i in 0..(payload_len / 2) {
            let v: u16 = 8192 + i as u16;
            payload.extend_from_slice(&v.to_le_bytes());
        }
        pkt.extend_from_slice(&payload);
        pkt[0] = pkt.len() as u8;
        let vals = drl_values(&pkt);
        assert_eq!(vals.len(), payload_len / 2);
        assert_eq!(vals[0], 8192);
        assert_eq!(vals[1], 8193);
        assert!(drl_values(&[1, 2, 3]).is_empty());
    }

    #[test]
    fn seq_extender_wraps_at_256_monotonically() {
        let mut s = SeqExtender::new();
        assert_eq!(s.extend(250), 250);
        assert_eq!(s.extend(255), 255);
        assert_eq!(s.extend(0), 256);
        assert_eq!(s.extend(3), 259); // a gap does not break monotonicity
        assert_eq!(s.extend(255), 511);
        assert_eq!(s.extend(1), 513);
    }

    // ── ticker ────────────────────────────────────────────────────────────
    #[test]
    fn ticker_closes_a_full_tick_with_bands_and_contact() {
        let mut t = CentralTicker::new();
        assert!(t.last_contact().is_none(), "no completed tick yet");
        let mut rng = Noise(3);
        for ch in 0..4 {
            let x: Vec<f64> = sinusoid(10.0, 20.0, 256).iter().map(|v| v + rng.gauss(2.0)).collect();
            t.push(ch, &x);
        }
        let tick = t.close_tick(12.204);
        assert_eq!(tick.n_samples, 256);
        assert!(tick.contact_ok);
        assert_eq!(tick.contact.len(), 4);
        assert!(tick.contact.values().all(|c| *c == Contact::Good));
        let bands = tick.bands.as_ref().unwrap();
        assert_eq!(bands.keys().cloned().collect::<Vec<_>>(), ["AF7", "AF8", "TP10", "TP9"]);
        assert!(tick.rel_alpha.as_ref().unwrap()["TP9"] > 0.9);
        assert_eq!(t.last_contact().unwrap()["AF8"], Contact::Good);
        // Buffers cleared: an immediately following empty tick.
        let empty = t.close_tick(13.2);
        assert_eq!(empty.n_samples, 0);
        assert!(empty.bands.is_none() && empty.rel_alpha.is_none());
        assert!(!empty.contact_ok);
    }

    #[test]
    fn ticker_short_tick_has_null_bands_and_contact_ok_false_below_floor() {
        let mut t = CentralTicker::new();
        for ch in 0..4 {
            t.push(ch, &sinusoid(10.0, 20.0, 100));
        }
        let tick = t.close_tick(1.0);
        assert_eq!(tick.n_samples, 100);
        assert!(tick.bands.is_some(), "≥ 64 samples resolves bands");
        assert!(!tick.contact_ok, "CON-015-3: n_samples < 128 ⇒ contact_ok=false");
        for ch in 0..4 {
            t.push(ch, &sinusoid(10.0, 20.0, 40));
        }
        let tick = t.close_tick(2.0);
        assert!(tick.bands.is_none() && tick.rel_alpha.is_none());
        assert_eq!(tick.contact.len(), 4, "contact is still classified");
    }

    #[test]
    fn ticker_n_samples_is_the_min_channel_count_and_poor_channel_clears_contact_ok() {
        let mut t = CentralTicker::new();
        let mut rng = Noise(9);
        for ch in 0..3 {
            let x: Vec<f64> = sinusoid(10.0, 20.0, 256).iter().map(|v| v + rng.gauss(2.0)).collect();
            t.push(ch, &x);
        }
        let poor: Vec<f64> = (0..200).map(|_| rng.gauss(300.0)).collect();
        t.push(3, &poor);
        let tick = t.close_tick(5.0);
        assert_eq!(tick.n_samples, 200);
        assert_eq!(tick.contact["TP10"], Contact::Poor);
        assert!(!tick.contact_ok);
    }

    // ── TEST-015-8 allowlist ──────────────────────────────────────────────
    #[test]
    fn test_015_8_central_tick_json_has_exactly_the_allowlisted_keys() {
        let mut t = CentralTicker::new();
        for ch in 0..4 {
            t.push(ch, &sinusoid(10.0, 20.0, 256));
        }
        for tick in [t.close_tick(1.0), t.close_tick(2.0)] {
            let v = central_tick_json(&tick);
            let obj = v.as_object().expect("central is an object");
            let keys: Vec<&str> = obj.keys().map(String::as_str).collect();
            for k in &keys {
                assert!(CENTRAL_ALLOWLIST.contains(k), "REQ-015-1: key {k} is outside the allowlist");
            }
            for k in CENTRAL_ALLOWLIST {
                assert!(obj.contains_key(k), "allowlisted key {k} missing (must be present, null if unset)");
            }
            assert_eq!(obj.len(), CENTRAL_ALLOWLIST.len());
            assert!(obj["central_phase"].is_null(), "NFR-015-2: central_phase present-and-null");
        }
    }

    #[test]
    fn central_tick_json_rounds_to_3dp_and_serialises_contact_strings() {
        let mut t = CentralTicker::new();
        for ch in 0..4 {
            t.push(ch, &sinusoid(10.0, 20.0, 256));
        }
        let v = central_tick_json(&t.close_tick(12.2044444));
        assert_eq!(v["host_mono"], json!(12.204));
        assert_eq!(v["n_samples"], json!(256));
        assert_eq!(v["contact"]["TP9"], json!("good"));
        let a = v["bands"]["TP9"]["alpha"].as_f64().unwrap();
        assert_eq!(a, (a * 1000.0).round() / 1000.0);
        let r = v["rel_alpha"]["AF7"].as_f64().unwrap();
        assert_eq!(r, (r * 1000.0).round() / 1000.0);
        assert!(r > 0.9);
    }

    // ── TEST-015-7 capability fold + truncation ───────────────────────────
    #[test]
    fn test_015_7_fold_add_records_over_base_without_reading_schema_version() {
        let base = json!({"type":"session_start","schema_version":"9.9.9",
                          "substrates":["autonomic"],"capabilities":["hrv","motion"]});
        let (s, c) = fold_capabilities(&[base.clone()]);
        assert_eq!(s, ["autonomic"]);
        assert_eq!(c, ["hrv", "motion"]);

        let add = json!({"type":"central_start","substrates_add":["central"],
                         "capabilities_add":["eeg_raw","eeg_bands"]});
        let sample = json!({"ts":"x","hr":60});
        let (s, c) = fold_capabilities(&[base.clone(), sample, add.clone(), add]);
        assert_eq!(s, ["autonomic", "central"]);
        assert_eq!(c, ["hrv", "motion", "eeg_raw", "eeg_bands"]);
        assert!(c.contains(&"eeg_raw".to_string()), "consumer branches on capability presence");

        // Pre-1.6.0 session: no declaration → empty sets, never a panic.
        let old = json!({"type":"session_start","schema_version":"1.5.0"});
        assert_eq!(fold_capabilities(&[old]), (vec![], vec![]));
    }

    #[test]
    fn test_015_7_truncation_is_detected_from_last_seq_vs_final_seq() {
        let end = json!({"type":"central_end","final_seq":1041,"n_samples":30000});
        assert!(raw_file_complete(Some(1041), &end));
        assert!(!raw_file_complete(Some(1040), &end), "last raw seq ≠ final_seq ⇒ incomplete");
        assert!(!raw_file_complete(None, &end), "raw file empty but packets declared");
        let none = json!({"type":"central_end","final_seq":null,"n_samples":0});
        assert!(raw_file_complete(None, &none), "nothing written, nothing declared");
        assert!(!raw_file_complete(Some(3), &none));
        assert!(!raw_file_complete(Some(3), &json!({"type":"central_end"})), "missing final_seq never validates");
    }
}
