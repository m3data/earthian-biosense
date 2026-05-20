//! BLE layer — Polar H10 discovery, connection, and notification streaming.
//!
//! Uses btleplug for CoreBluetooth access on macOS.
//! The Adapter must be shared across scan and connect — peripherals are
//! tied to the adapter instance that discovered them.

pub mod parser;
pub mod registry;

use btleplug::api::{Central, Manager as _, Peripheral as _, ScanFilter, WriteType};
use btleplug::platform::{Adapter, Manager, Peripheral};
use futures::StreamExt;
use serde::Serialize;
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
pub async fn connect_and_stream(
    adapter: &Adapter,
    address: String,
    tx: mpsc::UnboundedSender<(String, HeartRateData)>,
    label: String,
    acc_buffer: AccBuffer,
) -> Result<DeviceStatus, String> {
    let peripheral = find_peripheral(adapter, &address).await?;

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
    };

    // Spawn notification listener
    let stream_label = label.clone();
    let mut notification_stream = peripheral
        .notifications()
        .await
        .map_err(|e| format!("Failed to get notification stream: {}", e))?;

    tokio::spawn(async move {
        while let Some(notification) = notification_stream.next().await {
            if notification.uuid == HR_MEASUREMENT_UUID {
                if let Some(hr_data) = parse_heart_rate_measurement(&notification.value) {
                    if tx.send((stream_label.clone(), hr_data)).is_err() {
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
