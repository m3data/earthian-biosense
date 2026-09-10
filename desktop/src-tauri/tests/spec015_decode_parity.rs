//! SPEC-015 TEST-015-2a / 2b / 2c — offline decode parity, two layers plus
//! the negative controls that prove the layers bite.
//!
//! No device, no BLE, no Python, no brainflow. Inputs are two committed
//! fixtures in tests/fixtures/muse_athena/:
//!   golden_eyes_closed.bin   raw 273e0013 packets, self-framing (byte[0] = len),
//!                            header bytes 2..9 zeroed, eyes-closed window
//!   golden_reference_uv.bin  frozen µV vector produced ONCE by muse-rs
//!                            (examples/gen_muse_reference.rs) — a reviewed act
//!
//! A missing fixture FAILS these tests. It does not skip. A guard that skips
//! silently is not a guard (SPEC-015 §Open questions, fixture inclusion).

use std::path::PathBuf;

use muse_rs::parse::{athena_payload_len, parse_athena_notification};
use muse_rs::types::MuseEvent;

const FS: f64 = 256.0;
const MIDRAIL: u16 = 8192;
const CH: [&str; 4] = ["TP9", "AF7", "AF8", "TP10"];

// REQ-015-5a tolerance.
const PARITY_TOL_UV: f64 = 0.1;
// REQ-015-5b anchors.
const DRL_TOL_LSB: i32 = 256;
const ALPHA_RMS_MIN_UV: f64 = 0.5; // was 2.0, set from a 4.55×-inflated witness — see SPEC-015 REQ-015-5b correction 2026-09-10 (▢ ratify)
const ALPHA_RMS_MAX_UV: f64 = 60.0;

fn fixture(name: &str) -> Vec<u8> {
    let p: PathBuf = [env!("CARGO_MANIFEST_DIR"), "..", "..", "tests", "fixtures", "muse_athena", name].iter().collect();
    std::fs::read(&p).unwrap_or_else(|e| panic!(
        "SPEC-015 golden fixture missing: {} ({e}). \
         The parity guard cannot run without it — see tests/fixtures/muse_athena/README.md.", p.display()))
}

fn packets(slice: &[u8]) -> Vec<&[u8]> {
    let mut out = Vec::new();
    let mut i = 0;
    while i < slice.len() {
        let len = slice[i] as usize;
        assert!(len >= 10 && i + len <= slice.len(), "slice not self-framing at byte {i}");
        out.push(&slice[i..i + len]);
        i += len;
    }
    out
}

/// Reference decoder path (muse-rs). Channel-major µV.
fn decode_reference(slice: &[u8]) -> Vec<Vec<f64>> {
    let mut ch = vec![Vec::new(); 4];
    for pkt in packets(slice) {
        for ev in parse_athena_notification(pkt) {
            if let MuseEvent::Eeg(r) = ev {
                if r.electrode < 4 { ch[r.electrode].extend(r.samples); }
            }
        }
    }
    ch
}

/// Walk sub-frames ourselves (needed for 0x53, which muse-rs discards, and
/// for the negative-control decoders). Yields (tag, payload).
fn subframes(pkt: &[u8]) -> Vec<(u8, &[u8])> {
    let mut out = Vec::new();
    let pkt_len = pkt[0] as usize;
    let mut idx = 9;
    while idx < pkt.len() {
        let tag = pkt[idx];
        let start = idx + 5;
        match athena_payload_len(tag) {
            Some(len) if start + len <= pkt.len() => { out.push((tag, &pkt[start..start + len])); idx = start + len; }
            Some(_) => { idx += 1; }
            None if tag == 0x88 => { idx = pkt_len.min(pkt.len()); }
            None => { idx += 1; }
        }
    }
    out
}

/// Little-endian bit-packed unsigned values of `bits` width (the Athena layout).
fn unpack_le(bytes: &[u8], bits: u32) -> Vec<u32> {
    let n = bytes.len() * 8 / bits as usize;
    let mut out = Vec::with_capacity(n);
    let mut acc: u64 = 0; let mut nacc = 0u32; let mut bi = 0usize;
    for _ in 0..n {
        while nacc < bits { acc |= (bytes[bi] as u64) << nacc; nacc += 8; bi += 1; }
        out.push((acc & ((1u64 << bits) - 1)) as u32);
        acc >>= bits; nacc -= bits;
    }
    out
}

/// Negative control A — the CLASSIC Muse layout: 12-bit BIG-endian packed,
/// mid 2048, 0.488 µV/LSB. The confusion the spec names.
fn decode_wrong_12bit_be(slice: &[u8]) -> Vec<Vec<f64>> {
    let mut ch = vec![Vec::new(); 4];
    for pkt in packets(slice) {
        for (tag, pl) in subframes(pkt) {
            if tag != 0x11 { continue; }
            // 28 B → 18 twelve-bit values big-endian (last 8 bits unused); take 16.
            let mut vals = Vec::new();
            let mut acc: u64 = 0; let mut nacc = 0u32;
            for &b in pl { acc = (acc << 8) | b as u64; nacc += 8;
                while nacc >= 12 { vals.push(((acc >> (nacc - 12)) & 0xFFF) as u32); nacc -= 12; } }
            for ch_i in 0..4 {
                for s in 0..4 {
                    if let Some(&v) = vals.get(s * 4 + ch_i) { ch[ch_i].push((v as f64 - 2048.0) * 0.488); }
                }
            }
        }
    }
    ch
}

/// Negative control B — right unpacking (14-bit LE), WRONG gain (0.488).
fn decode_wrong_gain(slice: &[u8]) -> Vec<Vec<f64>> {
    let mut ch = vec![Vec::new(); 4];
    for pkt in packets(slice) {
        for (tag, pl) in subframes(pkt) {
            if tag != 0x11 { continue; }
            let raw = unpack_le(pl, 14);
            for ch_i in 0..4 {
                for s in 0..4 { ch[ch_i].push((raw[s * 4 + ch_i] as f64 - 8192.0) * 0.488); }
            }
        }
    }
    ch
}

fn load_reference() -> Vec<Vec<f64>> {
    let b = fixture("golden_reference_uv.bin");
    assert_eq!(&b[..7], b"EBSREF1", "reference header");
    let n_ch = b[7] as usize;
    let n = u32::from_le_bytes([b[8], b[9], b[10], b[11]]) as usize;
    assert_eq!(n_ch, 4);
    let mut ch = vec![Vec::with_capacity(n); n_ch];
    let mut i = 12;
    for c in 0..n_ch { for _ in 0..n {
        ch[c].push(f32::from_le_bytes([b[i], b[i+1], b[i+2], b[i+3]]) as f64); i += 4; } }
    ch
}

/// Max |a−b| over all samples; None if lengths differ.
fn max_abs_diff(a: &[Vec<f64>], b: &[Vec<f64>]) -> Option<f64> {
    if a.len() != b.len() { return None; }
    let mut m = 0.0f64;
    for (x, y) in a.iter().zip(b) {
        if x.len() != y.len() { return None; }
        for (p, q) in x.iter().zip(y) { m = m.max((p - q).abs()); }
    }
    Some(m)
}

/// Band RMS (µV) via Hann-windowed DFT, mean removed. O(N²) is fine here.
fn band_rms(x: &[f64], lo: f64, hi: f64) -> f64 {
    let n = x.len();
    let mean = x.iter().sum::<f64>() / n as f64;
    let w: Vec<f64> = (0..n).map(|i| 0.5 - 0.5 * (2.0 * std::f64::consts::PI * i as f64 / n as f64).cos()).collect();
    let wpow = w.iter().map(|v| v * v).sum::<f64>();
    let xw: Vec<f64> = x.iter().zip(&w).map(|(v, w)| (v - mean) * w).collect();
    let df = FS / n as f64;
    let (k_lo, k_hi) = ((lo / df).ceil() as usize, ((hi / df).floor() as usize).min(n / 2));
    let mut power = 0.0;
    for k in k_lo..=k_hi {
        let step = 2.0 * std::f64::consts::PI * k as f64 / n as f64;
        let (mut re, mut im) = (0.0, 0.0);
        for (i, v) in xw.iter().enumerate() { let (s, c) = (step * i as f64).sin_cos(); re += v * c; im -= v * s; }
        power += 2.0 * (re * re + im * im) / (wpow * n as f64);
    }
    power.sqrt()
}

fn alpha_rms_per_channel(ch: &[Vec<f64>]) -> Vec<f64> {
    ch.iter().map(|c| band_rms(c, 8.0, 13.0)).collect()
}

// ───────────────────────────── TEST-015-2a ─────────────────────────────

#[test]
fn test_015_2a_relative_parity_against_frozen_reference() {
    let slice = fixture("golden_eyes_closed.bin");
    let decoded = decode_reference(&slice);
    let reference = load_reference();
    assert!(decoded[0].len() >= 256 * 5, "slice too short to be a guard: {} samples", decoded[0].len());
    let d = max_abs_diff(&decoded, &reference).expect("decoded and reference differ in shape");
    assert!(d <= PARITY_TOL_UV, "REQ-015-5a: max |decoded − reference| = {d:.4} µV > {PARITY_TOL_UV}");
}

// ───────────────────────────── TEST-015-2b ─────────────────────────────

#[test]
fn test_015_2b_i_drl_ref_parks_at_14bit_midrail() {
    let slice = fixture("golden_eyes_closed.bin");
    let mut n = 0usize;
    let (mut lo, mut hi) = (u16::MAX, u16::MIN);
    for pkt in packets(&slice) {
        for (tag, pl) in subframes(pkt) {
            if tag != 0x53 { continue; }
            for c in pl.chunks_exact(2) {
                let v = u16::from_le_bytes([c[0], c[1]]);
                let off = v as i32 - MIDRAIL as i32;
                assert!(off.abs() <= DRL_TOL_LSB, "REQ-015-5b(i): DRL/REF value {v} is {off} LSB from mid-rail (tol ±{DRL_TOL_LSB})");
                lo = lo.min(v); hi = hi.max(v); n += 1;
            }
        }
    }
    assert!(n > 0, "no 0x53 DRL/REF sub-frames in the slice — the anchor cannot be checked");
    eprintln!("2b(i): {n} DRL/REF values in [{lo}, {hi}] around {MIDRAIL}");
}

#[test]
fn test_015_2b_ii_eyes_closed_alpha_rms_in_physiological_range() {
    let slice = fixture("golden_eyes_closed.bin");
    let decoded = decode_reference(&slice);
    let a = alpha_rms_per_channel(&decoded);
    for (i, v) in a.iter().enumerate() {
        assert!((ALPHA_RMS_MIN_UV..=ALPHA_RMS_MAX_UV).contains(v),
            "REQ-015-5b(ii): {} eyes-closed alpha RMS {v:.2} µV outside [{ALPHA_RMS_MIN_UV}, {ALPHA_RMS_MAX_UV}]", CH[i]);
    }
    eprintln!("2b(ii): alpha RMS µV {:?}", a.iter().map(|v| format!("{v:.2}")).collect::<Vec<_>>());
}

// ───────────────────────────── TEST-015-2c ─────────────────────────────

#[test]
fn test_015_2c_relative_layer_bites_on_12bit_be_unpacking() {
    let slice = fixture("golden_eyes_closed.bin");
    let wrong = decode_wrong_12bit_be(&slice);
    let reference = load_reference();
    match max_abs_diff(&wrong, &reference) {
        None => {} // shape differs: that is a failure of parity, i.e. the guard bit
        Some(d) => assert!(d > PARITY_TOL_UV, "2c: 12-bit BE decode passed parity (max diff {d:.4} µV) — the relative guard does not bite"),
    }
}

#[test]
fn test_015_2c_relative_layer_bites_on_wrong_gain() {
    let slice = fixture("golden_eyes_closed.bin");
    let wrong = decode_wrong_gain(&slice);
    let reference = load_reference();
    let d = max_abs_diff(&wrong, &reference).expect("same shape expected: only the gain differs");
    assert!(d > PARITY_TOL_UV, "2c: 0.488 gain passed parity (max diff {d:.4} µV) — the relative guard does not bite");
}

#[test]
fn test_015_2c_absolute_layer_bites_on_12bit_be_unpacking() {
    let slice = fixture("golden_eyes_closed.bin");
    let a = alpha_rms_per_channel(&decode_wrong_12bit_be(&slice));
    let out_of_range = a.iter().filter(|v| !(ALPHA_RMS_MIN_UV..=ALPHA_RMS_MAX_UV).contains(v)).count();
    assert!(out_of_range > 0, "2c: 12-bit BE decode kept every channel's alpha RMS in range {a:?} — the absolute guard does not bite");
}

/// The spec's own caveat, made explicit: the absolute layer is COARSE. A 5.5×
/// gain error moves 2–11 µV of alpha to 11–60 µV, which can sit inside the
/// [2, 60] bound. This test records what the layer can and cannot see; the
/// wrong-gain confusion is caught by the RELATIVE layer above, not this one.
#[test]
fn test_015_2c_absolute_layer_coverage_of_wrong_gain_is_recorded() {
    let slice = fixture("golden_eyes_closed.bin");
    let right = alpha_rms_per_channel(&decode_reference(&slice));
    let wrong = alpha_rms_per_channel(&decode_wrong_gain(&slice));
    let caught = wrong.iter().filter(|v| !(ALPHA_RMS_MIN_UV..=ALPHA_RMS_MAX_UV).contains(v)).count();
    eprintln!("2c coverage: right-gain alpha {:?}; wrong-gain alpha {:?}; channels caught by the absolute bound: {caught}/4",
        right.iter().map(|v| format!("{v:.1}")).collect::<Vec<_>>(),
        wrong.iter().map(|v| format!("{v:.1}")).collect::<Vec<_>>());
    // Invariant that must hold regardless: the wrong gain is exactly 0.488/0.0885 × right.
    for (r, w) in right.iter().zip(&wrong) {
        let ratio = w / r;
        assert!((ratio - 0.488 / 0.0885).abs() < 1e-6, "gain ratio {ratio}");
    }
}
