//! SPEC-015 spike: does btleplug sustain BOTH peripherals in ONE process?
//!
//! The 2026-09-10 probe answered the platform question (two processes, two
//! peripherals: clean). This answers the one the spec actually asks: one
//! client, one adapter, two different peripherals, notifications on both.
//!
//! Bypasses the app entirely so nothing in EBS has to change to learn the
//! answer. Prints per-source notification counts and worst gaps.
//!
//! Run: `cargo run --release --example dual_ble_spike` with the H10 released
//! by the desktop app (a connected peripheral stops advertising) and the Muse
//! awake (it sleeps on idle and then advertises nothing).
//!
//! Result 2026-09-10, 90 s: h10 90 notifications @ 1.00 Hz, worst gap 1.05 s;
//! muse 3495 notifications @ 38.83 Hz, worst gap 0.08 s. NOTE those are BLE
//! notifications, i.e. multiplexed packets, NOT decoded samples -- this spike
//! never decodes a byte.

use std::collections::HashMap;
use std::time::{Duration, Instant};

use btleplug::api::{Central, Manager as _, Peripheral as _, ScanFilter, WriteType};
use btleplug::platform::{Adapter, Manager, Peripheral};
use futures::StreamExt;
use uuid::Uuid;

const HR_MEASUREMENT: Uuid = uuid::uuid!("00002a37-0000-1000-8000-00805f9b34fb");
const RUN_SECS: u64 = 90;

/// Muse protocol-v4 control framing: length-prefixed, newline-terminated.
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

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let manager = Manager::new().await?;
    let adapter = manager.adapters().await?.into_iter().next().ok_or("no BLE adapter")?;

    println!("scanning 10s...");
    adapter.start_scan(ScanFilter::default()).await?;
    tokio::time::sleep(Duration::from_secs(10)).await;
    adapter.stop_scan().await?;

    let h10 = find(&adapter, "Polar").await.ok_or("no Polar H10 found (is EBS still holding it?)")?;
    let muse = find(&adapter, "MuseS-").await.ok_or("no MuseS- found")?;
    println!("found both peripherals");

    // --- H10 first: it is the substrate that must never degrade (REQ-015-3).
    h10.connect().await?;
    h10.discover_services().await?;
    let hr_char = h10.characteristics().into_iter()
        .find(|c| c.uuid == HR_MEASUREMENT).ok_or("no HR measurement characteristic")?;
    h10.subscribe(&hr_char).await?;
    println!("h10 connected + subscribed");

    // --- Muse second, on the SAME adapter, while the H10 link is live.
    muse.connect().await?;
    muse.discover_services().await?;
    let chars = muse.characteristics();
    let ctrl = chars.iter().find(|c| c.uuid.to_string().starts_with("273e0001"))
        .ok_or("no Muse control characteristic")?.clone();
    let data = chars.iter().find(|c| c.uuid.to_string().starts_with("273e0013"))
        .ok_or("no Muse data characteristic")?.clone();
    muse.subscribe(&data).await?;
    // Handshake: halt, preset, start (dc001 sent twice), write-WITHOUT-response.
    for cmd in ["h", "p1035", "dc001", "dc001"] {
        muse.write(&ctrl, &frame(cmd), WriteType::WithoutResponse).await?;
        tokio::time::sleep(Duration::from_millis(300)).await;
    }
    println!("muse connected + streaming\n");

    let mut h10_stream = h10.notifications().await?;
    let mut muse_stream = muse.notifications().await?;

    let start = Instant::now();
    let deadline = start + Duration::from_secs(RUN_SECS);
    let mut counts: HashMap<&str, u64> = HashMap::new();
    let mut last: HashMap<&str, Instant> = HashMap::new();
    let mut worst: HashMap<&str, f64> = HashMap::new();
    let mut tick = tokio::time::interval(Duration::from_secs(15));
    tick.tick().await;

    let mut note = |src: &'static str,
                    counts: &mut HashMap<&str, u64>,
                    last: &mut HashMap<&str, Instant>,
                    worst: &mut HashMap<&str, f64>| {
        let now = Instant::now();
        *counts.entry(src).or_insert(0) += 1;
        if let Some(prev) = last.insert(src, now) {
            let gap = now.duration_since(prev).as_secs_f64();
            let w = worst.entry(src).or_insert(0.0);
            if gap > *w { *w = gap; }
        }
    };

    while Instant::now() < deadline {
        tokio::select! {
            Some(_) = h10_stream.next()  => note("h10",  &mut counts, &mut last, &mut worst),
            Some(_) = muse_stream.next() => note("muse", &mut counts, &mut last, &mut worst),
            _ = tick.tick() => {
                let el = start.elapsed().as_secs_f64();
                println!("  {:>5.0}s  h10 {:>4} ({:.2} Hz)   muse {:>6} ({:.1} Hz)",
                    el,
                    counts.get("h10").copied().unwrap_or(0),
                    counts.get("h10").copied().unwrap_or(0) as f64 / el,
                    counts.get("muse").copied().unwrap_or(0),
                    counts.get("muse").copied().unwrap_or(0) as f64 / el);
            }
            else => break,
        }
    }

    let el = start.elapsed().as_secs_f64();
    println!("\n--- one process, one adapter, two peripherals, {:.0}s ---", el);
    for src in ["h10", "muse"] {
        println!("{:<5} notifications {:>6}   {:>7.2} Hz   worst gap {:.2}s",
            src,
            counts.get(src).copied().unwrap_or(0),
            counts.get(src).copied().unwrap_or(0) as f64 / el,
            worst.get(src).copied().unwrap_or(0.0));
    }
    println!("\nh10 nominal 1 Hz. A sustained h10 rate at nominal with muse streaming");
    println!("is the pass condition (REQ-015-3: autonomic must not degrade).");

    let _ = muse.write(&ctrl, &frame("h"), WriteType::WithoutResponse).await;
    let _ = muse.disconnect().await;
    let _ = h10.disconnect().await;
    Ok(())
}
