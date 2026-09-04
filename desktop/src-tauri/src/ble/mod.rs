//! BLE layer — Polar H10 discovery, connection, and notification streaming.
//!
//! Uses btleplug for CoreBluetooth access on macOS.
//! The Adapter must be shared across scan and connect — peripherals are
//! tied to the adapter instance that discovered them.

pub mod parser;
pub mod reconnect;
pub mod registry;

use btleplug::api::{Central, Manager as _, Peripheral as _, ScanFilter, WriteType};
use btleplug::platform::{Adapter, Manager, Peripheral};
use futures::StreamExt;
use serde::Serialize;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tokio::sync::mpsc;
use uuid::Uuid;

use parser::{parse_heart_rate_measurement, parse_pmd_acc_frame, HeartRateData};
use registry::{DeviceInfo, DeviceRegistry};

/// Heart Rate Measurement Characteristic UUID
const HR_MEASUREMENT_UUID: Uuid = uuid::uuid!("00002a37-0000-1000-8000-00805f9b34fb");
/// Battery Level Characteristic UUID
const BATTERY_LEVEL_UUID: Uuid = uuid::uuid!("00002a19-0000-1000-8000-00805f9b34fb");
/// PMD (Polar Measurement Data) Control Point — write start/stop, indicate.
const PMD_CONTROL_UUID: Uuid = uuid::uuid!("fb005c81-02e7-f387-1cad-8acd2d8df0c8");
/// PMD Data — notify (ACC frames).
const PMD_DATA_UUID: Uuid = uuid::uuid!("fb005c82-02e7-f387-1cad-8acd2d8df0c8");

/// Control-point command to start ACC at 50Hz / 16-bit / +-4g (SPEC-013).
const PMD_START_ACC: [u8; 14] = [
    0x02, 0x02, // op=start, type=ACC
    0x00, 0x01, 0x32, 0x00, // sample rate = 50
    0x01, 0x01, 0x10, 0x00, // resolution = 16
    0x02, 0x01, 0x04, 0x00, // range = 4g
];

/// Shared accumulator of decoded ACC samples ([x, y, z] milli-g), drained per
/// HR tick by the processing loop in lib.rs.
pub type AccBuffer = Arc<Mutex<Vec<[i16; 3]>>>;

/// One HR notification as delivered to the processing loop: participant
/// label, parsed data, and the *stream generation* of the listener that
/// produced it (REQ-005 §9). The loop discards messages whose generation is
/// not its current one.
pub type HrMessage = (String, HeartRateData, u64);

/// Generation flag for a notification listener (SPEC-009 REQ-005 §6). The
/// owner stores `false` to retire the listener; a retired listener discards
/// everything it still receives and exits, so a stale link can neither
/// duplicate samples nor keep the watchdog alive.
pub type StreamAlive = Arc<AtomicBool>;

#[derive(Debug, Clone, Serialize)]
pub struct DiscoveredDevice {
    pub name: String,
    pub address: String,
    pub registry_info: Option<DeviceInfo>,
}

#[derive(Debug, Clone, Serialize)]
pub struct DeviceStatus {
    pub device: String, // label ("A", "B") or address
    pub name: String,
    pub connected: bool,
    pub battery: Option<u8>,
    pub strap: Option<String>,
    /// SPEC-009 REQ-005 v0.2 (CON-002, additive): true only while a reconnect
    /// cycle is running after a watchdog-detected link loss.
    pub reconnecting: bool,
}

/// Create and return the first available Bluetooth adapter.
/// Call once at app startup, then share via AppState.
pub async fn create_adapter() -> Result<Adapter, String> {
    let manager = Manager::new()
        .await
        .map_err(|e| format!("Failed to create BLE manager: {}", e))?;

    let adapters = manager
        .adapters()
        .await
        .map_err(|e| format!("Failed to get adapters: {}", e))?;

    adapters
        .into_iter()
        .next()
        .ok_or_else(|| "No Bluetooth adapters found".to_string())
}

/// Scan for Polar H10 devices using the shared adapter.
pub async fn scan_devices(
    adapter: &Adapter,
    registry: &DeviceRegistry,
    timeout_secs: u64,
) -> Result<Vec<DiscoveredDevice>, String> {
    adapter
        .start_scan(ScanFilter::default())
        .await
        .map_err(|e| format!("Failed to start scan: {}", e))?;

    tokio::time::sleep(Duration::from_secs(timeout_secs)).await;

    adapter
        .stop_scan()
        .await
        .map_err(|e| format!("Failed to stop scan: {}", e))?;

    let peripherals = adapter
        .peripherals()
        .await
        .map_err(|e| format!("Failed to get peripherals: {}", e))?;

    let mut devices = Vec::new();

    for peripheral in peripherals {
        if let Ok(Some(props)) = peripheral.properties().await {
            if let Some(name) = &props.local_name {
                if name.starts_with("Polar H10") {
                    let registry_info = registry.identify(name).cloned();
                    devices.push(DiscoveredDevice {
                        name: name.clone(),
                        address: peripheral.id().to_string(),
                        registry_info,
                    });
                }
            }
        }
    }

    Ok(devices)
}

/// Find a specific peripheral by address on the shared adapter.
async fn find_peripheral(adapter: &Adapter, address: &str) -> Result<Peripheral, String> {
    let peripherals = adapter
        .peripherals()
        .await
        .map_err(|e| format!("Failed to get peripherals: {}", e))?;

    for peripheral in peripherals {
        if peripheral.id().to_string() == address {
            return Ok(peripheral);
        }
    }

    Err(format!("Device {} not found", address))
}

/// Read battery level from a connected peripheral
async fn read_battery(peripheral: &Peripheral) -> Option<u8> {
    let chars = peripheral.characteristics();
    for ch in &chars {
        if ch.uuid == BATTERY_LEVEL_UUID {
            if let Ok(data) = peripheral.read(ch).await {
                if !data.is_empty() {
                    return Some(data[0]);
                }
            }
        }
    }
    None
}

/// Connect to a Polar H10 and stream heart rate data.
///
/// Uses the shared adapter so the peripheral from the scan is still available.
/// Sends parsed HeartRateData through the provided channel.
///
/// Returns the status and the generation flag of the spawned listener; store
/// `false` into the flag to retire that listener (REQ-005 §6).
pub async fn connect_and_stream(
    adapter: &Adapter,
    address: String,
    tx: mpsc::UnboundedSender<HrMessage>,
    label: String,
    acc_buffer: AccBuffer,
    gen: u64,
) -> Result<(DeviceStatus, StreamAlive), String> {
    let peripheral = find_peripheral(adapter, &address).await?;
    let alive: StreamAlive = Arc::new(AtomicBool::new(true));
    let status =
        stream_from_peripheral(peripheral, address, tx, label, acc_buffer, alive.clone(), gen).await?;
    Ok((status, alive))
}

/// Best-effort, bounded teardown of a peripheral by address (REQ-005 §7):
/// used after a reconnect attempt times out so no half-connected peripheral
/// is left behind. Every error is swallowed; the whole thing is capped at 3 s.
pub async fn teardown_peripheral(adapter: &Adapter, address: &str) {
    let fut = async {
        if let Ok(p) = find_peripheral(adapter, address).await {
            if let Err(e) = p.disconnect().await {
                log::warn!("Teardown disconnect of {} failed: {}", address, e);
            }
        }
    };
    if tokio::time::timeout(Duration::from_secs(3), fut).await.is_err() {
        log::warn!("Teardown of {} timed out", address);
    }
}

/// Short rescan used when the adapter no longer lists a device we want to
/// reconnect to (SPEC-009 REQ-005 §5). Starts and stops the scan around a
/// fixed window, then looks the address up again.
pub async fn rescan_for_peripheral(
    adapter: &Adapter,
    address: &str,
    window: Duration,
) -> Result<Peripheral, String> {
    adapter
        .start_scan(ScanFilter::default())
        .await
        .map_err(|e| format!("Failed to start rescan: {}", e))?;
    tokio::time::sleep(window).await;
    adapter
        .stop_scan()
        .await
        .map_err(|e| format!("Failed to stop rescan: {}", e))?;
    find_peripheral(adapter, address).await
}

/// One reconnect attempt (SPEC-009 REQ-005). Differs from
/// [`connect_and_stream`] in two ways:
///
/// 1. If the adapter no longer lists the device, a short rescan (`rescan`)
///    is run and the lookup retried once within the same attempt.
/// 2. If CoreBluetooth still believes the peripheral is connected (the
///    watchdog fires well before the OS reports a disconnect), the stale
///    link is torn down first. A failure here is tolerated: the caller has
///    already retired the previous listener's generation flag (§6), so a
///    lingering stale stream is discarded rather than duplicated.
///
/// Returns the status and the new listener's generation flag.
pub async fn reconnect_and_stream(
    adapter: &Adapter,
    address: String,
    tx: mpsc::UnboundedSender<HrMessage>,
    label: String,
    acc_buffer: AccBuffer,
    rescan: Duration,
    gen: u64,
) -> Result<(DeviceStatus, StreamAlive), String> {
    let peripheral = match find_peripheral(adapter, &address).await {
        Ok(p) => p,
        Err(e) => {
            log::info!("{}; rescanning for {:?}", e, rescan);
            rescan_for_peripheral(adapter, &address, rescan).await?
        }
    };

    if peripheral.is_connected().await.unwrap_or(false) {
        log::info!("Peripheral {} still marked connected; tearing down stale link", address);
        if let Err(e) = peripheral.disconnect().await {
            log::warn!("Stale-link disconnect failed: {} (continuing)", e);
        }
    }

    let alive: StreamAlive = Arc::new(AtomicBool::new(true));
    let status =
        stream_from_peripheral(peripheral, address, tx, label, acc_buffer, alive.clone(), gen).await?;
    Ok((status, alive))
}

/// Connect an already-located peripheral, subscribe to HR (+ PMD ACC), and
/// spawn the notification listener. Shared by first connect and reconnect.
/// The listener checks `alive` on every notification and exits once retired,
/// and tags every HR message with `gen` (REQ-005 §9).
#[allow(clippy::too_many_arguments)]
async fn stream_from_peripheral(
    peripheral: Peripheral,
    address: String,
    tx: mpsc::UnboundedSender<HrMessage>,
    label: String,
    acc_buffer: AccBuffer,
    alive: StreamAlive,
    gen: u64,
) -> Result<DeviceStatus, String> {
    peripheral
        .connect()
        .await
        .map_err(|e| format!("Failed to connect: {}", e))?;

    peripheral
        .discover_services()
        .await
        .map_err(|e| format!("Failed to discover services: {}", e))?;

    // Read battery
    let battery = read_battery(&peripheral).await;

    // Find HR measurement characteristic and subscribe
    let chars = peripheral.characteristics();
    let hr_char = chars
        .iter()
        .find(|c| c.uuid == HR_MEASUREMENT_UUID)
        .ok_or_else(|| "HR measurement characteristic not found".to_string())?
        .clone();

    peripheral
        .subscribe(&hr_char)
        .await
        .map_err(|e| format!("Failed to subscribe to HR notifications: {}", e))?;

    // Accelerometer via PMD (SPEC-013) — additive and best-effort. Any failure
    // here leaves the session HR-only; the motion channel simply stays empty.
    match (
        chars.iter().find(|c| c.uuid == PMD_CONTROL_UUID).cloned(),
        chars.iter().find(|c| c.uuid == PMD_DATA_UUID).cloned(),
    ) {
        (Some(ctrl), Some(data_char)) => {
            let _ = peripheral.subscribe(&ctrl).await;
            match peripheral.subscribe(&data_char).await {
                Ok(()) => match peripheral
                    .write(&ctrl, &PMD_START_ACC, WriteType::WithResponse)
                    .await
                {
                    Ok(()) => log::info!("PMD ACC stream started (50Hz/16-bit/+-4g)"),
                    Err(e) => log::warn!("PMD ACC start failed: {} (HR-only)", e),
                },
                Err(e) => log::warn!("PMD data subscribe failed: {} (HR-only)", e),
            }
        }
        _ => log::warn!("PMD service not found; motion channel disabled"),
    }

    let name = peripheral
        .properties()
        .await
        .ok()
        .flatten()
        .and_then(|p| p.local_name)
        .unwrap_or_else(|| address.clone());

    let status = DeviceStatus {
        device: label.clone(),
        name: name.clone(),
        connected: true,
        battery,
        strap: None, // filled by caller from registry
        reconnecting: false,
    };

    // Spawn notification listener
    let stream_label = label.clone();
    let mut notification_stream = peripheral
        .notifications()
        .await
        .map_err(|e| format!("Failed to get notification stream: {}", e))?;

    tokio::spawn(async move {
        while let Some(notification) = notification_stream.next().await {
            if !alive.load(Ordering::Relaxed) {
                // Retired generation (REQ-005 §6): discard HR and ACC, exit.
                log::info!("Notification listener for {} retired; exiting", label);
                break;
            }
            if notification.uuid == HR_MEASUREMENT_UUID {
                if let Some(hr_data) = parse_heart_rate_measurement(&notification.value) {
                    if tx.send((stream_label.clone(), hr_data, gen)).is_err() {
                        log::info!("HR data channel closed, stopping stream");
                        break;
                    }
                }
            } else if notification.uuid == PMD_DATA_UUID {
                if let Some(frame) = parse_pmd_acc_frame(&notification.value) {
                    if let Ok(mut buf) = acc_buffer.lock() {
                        for s in &frame.samples {
                            buf.push([s.x, s.y, s.z]);
                        }
                    }
                }
            }
        }
        log::info!("Notification stream ended for {}", label);
    });

    Ok(status)
}

#[cfg(test)]
mod status_tests {
    use super::*;

    // TEST-005f — CON-002 carries one authoritative `reconnecting` flag.
    #[test]
    fn device_status_serialises_reconnecting_flag_default_false() {
        let st = DeviceStatus {
            device: "A".into(),
            name: "Polar H10 TEST".into(),
            connected: false,
            battery: None,
            strap: None,
            reconnecting: false,
        };
        let v: serde_json::Value = serde_json::to_value(&st).unwrap();
        assert_eq!(v["reconnecting"], serde_json::json!(false));
        assert_eq!(v["connected"], serde_json::json!(false));
    }
}
