//! SPEC-015 spike 2: decode under dual load + live contact quality.
//!
//! The 2026-09-10 `dual_ble_spike` showed btleplug holds H10 + Muse in one
//! process at nominal H10 rate -- but it decoded nothing and measured no
//! contact. This spike keeps the same transport shape and adds:
//!
//!   * EEG decode via `muse_rs::parse::parse_athena_notification` (the
//!     reference decoder named in ADR-015-1), so the Muse figure is SAMPLES.
//!   * DRL/REF (`0x53`) read from the raw bytes, since muse-rs discards it.
//!     Its mid-rail (8192) position is the REQ-015-5b(1) anchor.
//!   * Per-channel contact classification each second per CON-015-5
//!     (1-40 Hz bandpass, std + range, pinned thresholds).
//!   * A 10 s report: H10 rate, per-channel sample rate, contact, delta/alpha
//!     RMS, relative alpha 8-13 / 4-40 (the corrected Berger metric).
//!   * Raw packets + per-second summaries written to the gitignored fixture
//!     dir. Serials/addresses are never written.
//!
//! It still bypasses the app (AppState, generation counter, reconnect
//! supervisor). Throwaway by design. H10 is optional: if EBS desktop is
//! holding it, or it is not worn, the Muse still runs and the report says so.
//!
//! Run: `cargo run --release --example dual_ble_decode_spike [seconds]`
//! (default 600). Muse must be awake (button) -- it sleeps on idle.

use std::collections::HashMap;
use std::fs::File;
use std::io::{BufWriter, Write as _};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use btleplug::api::{Central, Manager as _, Peripheral as _, ScanFilter, WriteType};
use btleplug::platform::{Adapter, Manager, Peripheral};
use futures::StreamExt;
use muse_rs::parse::{athena_payload_len, parse_athena_notification};
use muse_rs::types::MuseEvent;
use uuid::Uuid;

const HR_MEASUREMENT: Uuid = uuid::uuid!("00002a37-0000-1000-8000-00805f9b34fb");
const FS: f64 = 256.0;
const CH_NAMES: [&str; 4] = ["TP9", "AF7", "AF8", "TP10"];
const MIDRAIL: f64 = 8192.0;

// CON-015-5 pinned thresholds (provisional).
const CONTACT_STD_GOOD_MIN: f64 = 5.0;
const CONTACT_STD_GOOD_MAX: f64 = 40.0;
const CONTACT_RANGE_GOOD_MAX: f64 = 400.0;
const CONTACT_STD_MARGINAL_MAX: f64 = 80.0;
const CONTACT_RANGE_MARGINAL_MAX: f64 = 2000.0;

fn frame(cmd: &str) -> Vec<u8> {
    let mut b = vec![(cmd.len() + 1) as u8];
    b.extend_from_slice(cmd.as_bytes());
    b.push(0x0A);
    b
}

async fn find(adapter: &Adapter, prefix: &str) -> Option<Peripheral> {
    for p in adapter.peripherals().await.ok()? {
        if let Ok(Some(props)) = p.properties().await {
            if props.local_name.as_deref().unwrap_or("").starts_with(prefix) {
                return Some(p);
            }
        }
    }
    None
}

fn unix_now() -> f64 {
    SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs_f64()
}

// ── Biquad (RBJ cookbook), Butterworth Q. Two cascaded 2nd-order sections
// per edge give a 4th-order response; not a true 4th-order Butterworth
// polynomial but the spike-grade equivalent of CON-015-5's filter.
#[derive(Clone)]
struct Biquad { b0: f64, b1: f64, b2: f64, a1: f64, a2: f64, z1: f64, z2: f64 }

impl Biquad {
    fn lowpass(fc: f64) -> Self {
        let w = 2.0 * std::f64::consts::PI * fc / FS;
        let (s, c) = w.sin_cos();
        let alpha = s / (2.0 * std::f64::consts::FRAC_1_SQRT_2);
        let a0 = 1.0 + alpha;
        Self { b0: (1.0 - c) / 2.0 / a0, b1: (1.0 - c) / a0, b2: (1.0 - c) / 2.0 / a0,
               a1: -2.0 * c / a0, a2: (1.0 - alpha) / a0, z1: 0.0, z2: 0.0 }
    }
    fn highpass(fc: f64) -> Self {
        let w = 2.0 * std::f64::consts::PI * fc / FS;
        let (s, c) = w.sin_cos();
        let alpha = s / (2.0 * std::f64::consts::FRAC_1_SQRT_2);
        let a0 = 1.0 + alpha;
        Self { b0: (1.0 + c) / 2.0 / a0, b1: -(1.0 + c) / a0, b2: (1.0 + c) / 2.0 / a0,
               a1: -2.0 * c / a0, a2: (1.0 - alpha) / a0, z1: 0.0, z2: 0.0 }
    }
    fn run(&mut self, x: f64) -> f64 {
        let y = self.b0 * x + self.z1;
        self.z1 = self.b1 * x - self.a1 * y + self.z2;
        self.z2 = self.b2 * x - self.a2 * y;
        y
    }
}

struct Channel {
    filt: Vec<Biquad>,      // hp1, hp1, lp40, lp40
    sec: Vec<f64>,          // filtered samples this 1 s tick
    win: Vec<f64>,          // filtered samples this 10 s report window
    total: u64,
    classes: HashMap<&'static str, u64>,
}

impl Channel {
    fn new() -> Self {
        Self {
            filt: vec![Biquad::highpass(1.0), Biquad::highpass(1.0), Biquad::lowpass(40.0), Biquad::lowpass(40.0)],
            sec: Vec::with_capacity(300), win: Vec::with_capacity(3000), total: 0, classes: HashMap::new(),
        }
    }
    fn push(&mut self, uv: f64) {
        let mut y = uv;
        for f in self.filt.iter_mut() { y = f.run(y); }
        self.sec.push(y);
        self.win.push(y);
        self.total += 1;
    }
}

fn std_range(x: &[f64]) -> (f64, f64) {
    if x.is_empty() { return (0.0, 0.0); }
    let n = x.len() as f64;
    let mean = x.iter().sum::<f64>() / n;
    let var = x.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / n;
    let (mn, mx) = x.iter().fold((f64::INFINITY, f64::NEG_INFINITY), |(a, b), &v| (a.min(v), b.max(v)));
    (var.sqrt(), mx - mn)
}

fn contact(std: f64, range: f64) -> &'static str {
    if (CONTACT_STD_GOOD_MIN..=CONTACT_STD_GOOD_MAX).contains(&std) && range < CONTACT_RANGE_GOOD_MAX { "good" }
    else if std <= CONTACT_STD_MARGINAL_MAX && range < CONTACT_RANGE_MARGINAL_MAX { "marginal" }
    else { "poor" }
}

/// Band RMS (µV) from a naive DFT over the window, Hann-windowed, mean-removed.
/// O(N²) but N ≈ 2560 per channel per 10 s: negligible.
fn band_rms(x: &[f64], lo: f64, hi: f64) -> f64 {
    let n = x.len();
    if n < 64 { return 0.0; }
    let mean = x.iter().sum::<f64>() / n as f64;
    let w: Vec<f64> = (0..n).map(|i| 0.5 - 0.5 * (2.0 * std::f64::consts::PI * i as f64 / n as f64).cos()).collect();
    let wpow = w.iter().map(|v| v * v).sum::<f64>();
    let xw: Vec<f64> = x.iter().zip(&w).map(|(v, w)| (v - mean) * w).collect();
    let df = FS / n as f64;
    let k_lo = (lo / df).ceil() as usize;
    let k_hi = ((hi / df).floor() as usize).min(n / 2);
    let mut power = 0.0;
    for k in k_lo..=k_hi {
        let (mut re, mut im) = (0.0, 0.0);
        let step = 2.0 * std::f64::consts::PI * k as f64 / n as f64;
        for (i, v) in xw.iter().enumerate() {
            let (s, c) = (step * i as f64).sin_cos();
            re += v * c; im -= v * s;
        }
        // one-sided power, normalised so sum over all bins ≈ variance
        power += 2.0 * (re * re + im * im) / (wpow * n as f64);
    }
    power.sqrt()
}

/// Walk the packet for `0x53` DRL/REF sub-frames (muse-rs discards them).
/// Returns raw u16 LE values (12 per sub-frame: 2 ch × 6 samples interleaved).
fn drl_values(data: &[u8]) -> Vec<u16> {
    let mut out = Vec::new();
    if data.len() < 10 { return out; }
    let pkt_len = data[0] as usize;
    let mut idx = 9usize;
    while idx < data.len() {
        let tag = data[idx];
        let start = idx + 5;
        match athena_payload_len(tag) {
            Some(len) => {
                let end = start + len;
                if end > data.len() { idx += 1; continue; }
                if tag == 0x53 {
                    out.extend(data[start..end].chunks_exact(2).map(|c| u16::from_le_bytes([c[0], c[1]])));
                }
                idx = end;
            }
            None if tag == 0x88 => { idx = pkt_len.min(data.len()); }
            None => { idx += 1; }
        }
    }
    out
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let run_secs: u64 = std::env::args().nth(1).and_then(|s| s.parse().ok()).unwrap_or(600);

    let manager = Manager::new().await?;
    let adapter = manager.adapters().await?.into_iter().next().ok_or("no BLE adapter")?;
    println!("scanning 10s...");
    adapter.start_scan(ScanFilter::default()).await?;
    tokio::time::sleep(Duration::from_secs(10)).await;
    adapter.stop_scan().await?;

    let h10 = find(&adapter, "Polar").await;
    let muse = find(&adapter, "MuseS-").await.ok_or("no MuseS- found (awake? button)")?;
    println!("muse found; h10 {}", if h10.is_some() { "found" } else { "NOT found -- running Muse only" });

    // H10 first (REQ-015-3: the substrate that must not degrade).
    let mut h10_stream = None;
    if let Some(h) = &h10 {
        h.connect().await?;
        h.discover_services().await?;
        let c = h.characteristics().into_iter().find(|c| c.uuid == HR_MEASUREMENT).ok_or("no HR char")?;
        h.subscribe(&c).await?;
        h10_stream = Some(h.notifications().await?);
        println!("h10 connected + subscribed");
    }

    muse.connect().await?;
    muse.discover_services().await?;
    let chars = muse.characteristics();
    let ctrl = chars.iter().find(|c| c.uuid.to_string().starts_with("273e0001")).ok_or("no ctrl char")?.clone();
    let data = chars.iter().find(|c| c.uuid.to_string().starts_with("273e0013")).ok_or("no data char")?.clone();
    muse.subscribe(&data).await?;
    let mut muse_stream = muse.notifications().await?;
    for cmd in ["h", "p1035", "dc001", "dc001"] {
        muse.write(&ctrl, &frame(cmd), WriteType::WithoutResponse).await?;
        tokio::time::sleep(Duration::from_millis(300)).await;
    }
    println!("muse streaming (p1035 / EEG4)\n");

    // Outputs: gitignored fixture dir (biometric policy). No identifiers written.
    let stamp = chrono_like_stamp();
    let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/muse_athena");
    std::fs::create_dir_all(&dir)?;
    let mut raw_out = BufWriter::new(File::create(dir.join(format!("dual_raw_{stamp}.jsonl")))?);
    let mut sum_out = BufWriter::new(File::create(dir.join(format!("dual_summary_{stamp}.jsonl")))?);
    writeln!(raw_out, "{{\"_meta\":{{\"preset\":\"p1035\",\"channels\":[\"TP9\",\"AF7\",\"AF8\",\"TP10\"],\"fs\":256,\"h10\":{},\"run_secs\":{},\"note\":\"hex = one 273e0013 notification; t_unix = host arrival\"}}}}",
        h10.is_some(), run_secs)?;

    let mut chans: Vec<Channel> = (0..4).map(|_| Channel::new()).collect();
    let mut h10_sec = 0u64; let mut h10_win = 0u64; let mut h10_total = 0u64;
    let mut h10_last: Option<Instant> = None; let mut h10_worst = 0.0f64;
    let mut pkts = 0u64; let mut pkt_win = 0u64;
    let mut drl_sec: Vec<u16> = Vec::new(); let mut drl_win: Vec<u16> = Vec::new();
    let mut battery: Option<f32> = None;
    let mut first_idx: Option<u8> = None; let mut last_idx: Option<u8> = None; let mut idx_drops = 0u64;

    let start = Instant::now();
    let deadline = start + Duration::from_secs(run_secs);
    let mut sec_tick = tokio::time::interval(Duration::from_secs(1));
    let mut rep_tick = tokio::time::interval(Duration::from_secs(10));
    sec_tick.tick().await; rep_tick.tick().await;
    let mut win_start = Instant::now();

    println!("{:>5}  {:>7}  {:<6}  {}", "t", "h10Hz", "musePk", "per-channel: Hz  contact  std  Δrms  αrms  relα(8-13/4-40)");

    while Instant::now() < deadline {
        tokio::select! {
            Some(_) = async { match h10_stream.as_mut() { Some(s) => s.next().await, None => std::future::pending().await } } => {
                let now = Instant::now();
                if let Some(p) = h10_last { h10_worst = h10_worst.max(now.duration_since(p).as_secs_f64()); }
                h10_last = Some(now);
                h10_sec += 1; h10_win += 1; h10_total += 1;
            }
            Some(n) = muse_stream.next() => {
                pkts += 1; pkt_win += 1;
                let bytes = &n.value;
                writeln!(raw_out, "{{\"t_unix\":{:.6},\"hex\":\"{}\"}}", unix_now(), hex(bytes))?;
                if bytes.len() > 1 {
                    let i = bytes[1];
                    if let Some(p) = last_idx { if i != p.wrapping_add(1) { idx_drops += 1; } }
                    if first_idx.is_none() { first_idx = Some(i); }
                    last_idx = Some(i);
                }
                for ev in parse_athena_notification(bytes) {
                    match ev {
                        MuseEvent::Eeg(r) if r.electrode < 4 => {
                            for s in r.samples { chans[r.electrode].push(s); }
                        }
                        MuseEvent::Telemetry(t) => { battery = Some(t.battery_level); }
                        _ => {}
                    }
                }
                let d = drl_values(bytes);
                drl_sec.extend_from_slice(&d); drl_win.extend_from_slice(&d);
            }
            _ = sec_tick.tick() => {
                // 1 Hz contact tick (CON-015-5 window)
                let t = start.elapsed().as_secs_f64();
                let mut rec = format!("{{\"t\":{:.1},\"t_unix\":{:.3},\"h10_beats\":{},\"pkts\":{},\"battery\":{}",
                    t, unix_now(), h10_sec, pkts, battery.map(|b| format!("{b:.1}")).unwrap_or("null".into()));
                rec.push_str(",\"ch\":{");
                for (i, ch) in chans.iter_mut().enumerate() {
                    let (sd, rg) = std_range(&ch.sec);
                    let cls = contact(sd, rg);
                    *ch.classes.entry(cls).or_insert(0) += 1;
                    if i > 0 { rec.push(','); }
                    rec.push_str(&format!("\"{}\":{{\"n\":{},\"std\":{:.2},\"range\":{:.1},\"contact\":\"{}\"}}", CH_NAMES[i], ch.sec.len(), sd, rg, cls));
                    ch.sec.clear();
                }
                let drl_mean = if drl_sec.is_empty() { f64::NAN } else { drl_sec.iter().map(|&v| v as f64).sum::<f64>() / drl_sec.len() as f64 };
                rec.push_str(&format!("}},\"drl_mean_lsb\":{:.1},\"drl_n\":{}}}", drl_mean, drl_sec.len()));
                writeln!(sum_out, "{rec}")?;
                h10_sec = 0; drl_sec.clear();
            }
            _ = rep_tick.tick() => {
                let el = win_start.elapsed().as_secs_f64();
                let t = start.elapsed().as_secs_f64();
                let h10_rate = if h10.is_some() { format!("{:.2}", h10_win as f64 / el) } else { "  --".into() };
                print!("{:>5.0}  {:>7}  {:<6}", t, h10_rate, pkt_win);
                for (i, ch) in chans.iter_mut().enumerate() {
                    let (sd, rg) = std_range(&ch.win);
                    let d = band_rms(&ch.win, 1.0, 4.0);
                    let a = band_rms(&ch.win, 8.0, 13.0);
                    let b = band_rms(&ch.win, 4.0, 40.0);
                    let rel = if b > 0.0 { (a * a) / (b * b) } else { 0.0 };
                    print!("  {} {:>5.1}Hz {:<8} {:>6.1} {:>6.1} {:>5.1} {:.3}",
                        CH_NAMES[i], ch.win.len() as f64 / el, contact(sd, rg), sd, d, a, rel);
                    ch.win.clear();
                }
                let drl = if drl_win.is_empty() { f64::NAN } else { drl_win.iter().map(|&v| v as f64).sum::<f64>() / drl_win.len() as f64 };
                println!("  drl {:.0} ({:+.0} vs mid)  bat {}", drl, drl - MIDRAIL, battery.map(|b| format!("{b:.0}%")).unwrap_or("?".into()));
                drl_win.clear(); h10_win = 0; pkt_win = 0; win_start = Instant::now();
            }
            else => break,
        }
    }

    let el = start.elapsed().as_secs_f64();
    println!("\n--- {:.0}s, one process, one adapter, {} ---", el, if h10.is_some() { "two peripherals" } else { "Muse only" });
    if h10.is_some() {
        println!("h10   beats {:>6}   {:.2} Hz   worst gap {:.2}s", h10_total, h10_total as f64 / el, h10_worst);
    }
    println!("muse  packets {:>6}   {:.2} pk/s   index drops {}", pkts, pkts as f64 / el, idx_drops);
    for (i, ch) in chans.iter().enumerate() {
        let g = ch.classes.get("good").copied().unwrap_or(0);
        let m = ch.classes.get("marginal").copied().unwrap_or(0);
        let p = ch.classes.get("poor").copied().unwrap_or(0);
        let n = (g + m + p).max(1) as f64;
        println!("{:<4} samples {:>7}   {:.2} Hz   contact good {:.0}%  marginal {:.0}%  poor {:.0}%",
            CH_NAMES[i], ch.total, ch.total as f64 / el, 100.0 * g as f64 / n, 100.0 * m as f64 / n, 100.0 * p as f64 / n);
    }
    println!("battery end {}", battery.map(|b| format!("{b:.0}%")).unwrap_or("?".into()));
    println!("\nfiles: {}", dir.display());

    let _ = muse.write(&ctrl, &frame("h"), WriteType::WithoutResponse).await;
    let _ = muse.disconnect().await;
    if let Some(h) = &h10 { let _ = h.disconnect().await; }
    raw_out.flush()?; sum_out.flush()?;
    Ok(())
}

fn hex(b: &[u8]) -> String {
    let mut s = String::with_capacity(b.len() * 2);
    for x in b { s.push_str(&format!("{x:02x}")); }
    s
}

/// YYYYMMDDTHHMMSS in local-ish UTC without pulling in chrono.
fn chrono_like_stamp() -> String {
    let secs = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs();
    let days = secs / 86400; let rem = secs % 86400;
    let (h, m, s) = (rem / 3600, (rem % 3600) / 60, rem % 60);
    // civil from days (Howard Hinnant)
    let z = days as i64 + 719468;
    let era = z.div_euclid(146097);
    let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let mo = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = if mo <= 2 { y + 1 } else { y };
    format!("{y:04}{mo:02}{d:02}T{h:02}{m:02}{s:02}Z")
}
