//! BLE layer — Polar H10 discovery, connection, and notification streaming.
//!
//! Uses btleplug for CoreBluetooth access on macOS.
//! The Adapter must be shared across scan and connect — peripherals are
//! tied to the adapter instance that discovered them.

pub mod parser;
pub mod registry;

use btleplug::api::{Central, Manager as _, Peripheral as _, ScanFilter};
use btleplug::platform::{Adapter, Manager, Peripheral};
use futures::StreamExt;
use serde::Serialize;
use std::time::Duration;
use tokio::sync::mpsc;
use uuid::Uuid;

use parser::{parse_heart_rate_measurement, HeartRateData};
use registry::{DeviceInfo, DeviceRegistry};

/// Heart Rate Measurement Characteristic UUID
const HR_MEASUREMENT_UUID: Uuid = uuid::uuid!("00002a37-0000-1000-8000-00805f9b34fb");
/// Battery Level Characteristic UUID
const BATTERY_LEVEL_UUID: Uuid = uuid::uuid!("00002a19-0000-1000-8000-00805f9b34fb");

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
            }
        }
        log::info!("Notification stream ended for {}", label);
    });

    Ok(status)
}
