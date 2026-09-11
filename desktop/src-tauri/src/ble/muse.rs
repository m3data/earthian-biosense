//! Muse S Athena transport (SPEC-015 v0.1) — connect, handshake, forward raw
//! `273e0013` notifications. Independent of the H10 link: nothing here touches
//! `connect_and_stream`, the HR channel or the reconnect supervisor.
//!
//! The listener forwards `(bytes, host_mono, gen)`; decoding is the EEG
//! task's job (lib.rs) with muse-rs. No reconnect supervision in v0.1.

use btleplug::api::{Characteristic, Peripheral as _, WriteType};
use btleplug::platform::{Adapter, Peripheral};
use futures::StreamExt;
use serde::Serialize;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::mpsc;

use super::{find_peripheral, StreamAlive};
use crate::eeg::{frame, MUSE_CONTROL_PREFIX, MUSE_DATA_PREFIX, MUSE_HANDSHAKE};

/// Spacing between handshake writes (matches the working spike).
const HANDSHAKE_GAP: Duration = Duration::from_millis(300);

/// `ebs:muse-status` payload. Additive; never touches `ebs:device-status`.
#[derive(Debug, Clone, Serialize)]
pub struct MuseStatus {
    pub name: String,
    pub address: String,
    pub connected: bool,
    /// Battery from the telemetry sub-frame (%); `None` until the first one.
    pub battery: Option<f32>,
}

/// One raw data notification: bytes, `host_mono` at receipt, listener generation.
pub type MuseMessage = (Vec<u8>, f64, u64);

/// Connect to a Muse by address, subscribe to the data characteristic, run the
/// handshake and spawn a listener that forwards every notification stamped
/// with `mono_epoch.elapsed()`. The listener exits when `alive` is false.
///
/// Returns the status, the listener's generation flag, the peripheral and
/// its control characteristic (for [`halt_muse`]).
pub async fn connect_muse(
    adapter: &Adapter,
    address: String,
    tx: mpsc::UnboundedSender<MuseMessage>,
    mono_epoch: Instant,
    gen: u64,
) -> Result<(MuseStatus, StreamAlive, Peripheral, Characteristic), String> {
    let peripheral = find_peripheral(adapter, &address).await?;

    peripheral
        .connect()
        .await
        .map_err(|e| format!("Failed to connect to Muse: {}", e))?;
    peripheral
        .discover_services()
        .await
        .map_err(|e| format!("Failed to discover Muse services: {}", e))?;

    let chars = peripheral.characteristics();
    let ctrl = chars
        .iter()
        .find(|c| c.uuid.to_string().starts_with(MUSE_CONTROL_PREFIX))
        .cloned()
        .ok_or_else(|| "Muse control characteristic (273e0001) not found".to_string())?;
    let data = chars
        .iter()
        .find(|c| c.uuid.to_string().starts_with(MUSE_DATA_PREFIX))
        .cloned()
        .ok_or_else(|| "Muse data characteristic (273e0013) not found".to_string())?;

    peripheral
        .subscribe(&data)
        .await
        .map_err(|e| format!("Failed to subscribe to Muse data: {}", e))?;

    let mut notifications = peripheral
        .notifications()
        .await
        .map_err(|e| format!("Failed to get Muse notification stream: {}", e))?;

    // Handshake: h → p1035 → dc001 → dc001, write-without-response, 300 ms apart.
    for cmd in MUSE_HANDSHAKE {
        peripheral
            .write(&ctrl, &frame(cmd), WriteType::WithoutResponse)
            .await
            .map_err(|e| format!("Muse handshake write '{}' failed: {}", cmd, e))?;
        tokio::time::sleep(HANDSHAKE_GAP).await;
    }

    let name = peripheral
        .properties()
        .await
        .ok()
        .flatten()
        .and_then(|p| p.local_name)
        .unwrap_or_else(|| address.clone());

    let status = MuseStatus {
        name,
        address,
        connected: true,
        battery: None,
    };

    let alive: StreamAlive = Arc::new(AtomicBool::new(true));
    let listener_alive = alive.clone();
    let data_uuid = data.uuid;
    tokio::spawn(async move {
        while let Some(n) = notifications.next().await {
            if !listener_alive.load(Ordering::Relaxed) {
                log::info!("Muse listener gen {} retired; exiting", gen);
                break;
            }
            if n.uuid != data_uuid {
                continue;
            }
            let host_mono = mono_epoch.elapsed().as_secs_f64();
            if tx.send((n.value, host_mono, gen)).is_err() {
                log::info!("Muse data channel closed; stopping listener");
                break;
            }
        }
        log::info!("Muse notification stream ended (gen {})", gen);
    });

    Ok((status, alive, peripheral, ctrl))
}

/// Best-effort halt: write `h` (stop streaming) then disconnect. Every error
/// is logged and swallowed; the whole thing is capped at 3 s.
pub async fn halt_muse(peripheral: &Peripheral, ctrl: &Characteristic) {
    let fut = async {
        if let Err(e) = peripheral
            .write(ctrl, &frame("h"), WriteType::WithoutResponse)
            .await
        {
            log::warn!("Muse halt write failed: {}", e);
        }
        if let Err(e) = peripheral.disconnect().await {
            log::warn!("Muse disconnect failed: {}", e);
        }
    };
    if tokio::time::timeout(Duration::from_secs(3), fut).await.is_err() {
        log::warn!("Muse halt timed out");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn muse_status_serialises_the_additive_event_shape() {
        let st = MuseStatus {
            name: "MuseS-TEST".into(),
            address: "addr".into(),
            connected: false,
            battery: Some(81.5),
        };
        let v: serde_json::Value = serde_json::to_value(&st).unwrap();
        let mut keys: Vec<&String> = v.as_object().unwrap().keys().collect();
        keys.sort();
        assert_eq!(keys, ["address", "battery", "connected", "name"]);
        assert_eq!(v["connected"], serde_json::json!(false));
    }
}
