//! Device registry for Polar H10 identification and role assignment.
//!
//! Port of `src/ble/device_registry.py`. Maps device serials to
//! participant labels (A/B) based on config/devices.json.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::Path;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceInfo {
    pub serial: String,
    pub label: String,
    pub strap: String,
    pub color: String,
    #[serde(default)]
    pub description: String,
}

#[derive(Debug, Deserialize)]
struct DeviceConfigEntry {
    label: String,
    strap: String,
    color: String,
    #[serde(default)]
    description: String,
}

#[derive(Debug, Deserialize)]
struct DeviceConfig {
    devices: HashMap<String, DeviceConfigEntry>,
}

pub struct DeviceRegistry {
    devices: HashMap<String, DeviceInfo>,
}

impl DeviceRegistry {
    pub fn load(config_path: &Path) -> Result<Self, String> {
        let content = std::fs::read_to_string(config_path)
            .map_err(|e| format!("Failed to read device config: {}", e))?;

        let config: DeviceConfig = serde_json::from_str(&content)
            .map_err(|e| format!("Failed to parse device config: {}", e))?;

        let devices = config
            .devices
            .into_iter()
            .map(|(serial, entry)| {
                let info = DeviceInfo {
                    serial: serial.clone(),
                    label: entry.label,
                    strap: entry.strap,
                    color: entry.color,
                    description: entry.description,
                };
                (serial, info)
            })
            .collect();

        Ok(Self { devices })
    }

    pub fn empty() -> Self {
        Self {
            devices: HashMap::new(),
        }
    }

    /// Extract serial from Polar H10 device name (e.g., "Polar H10 035E4C31" -> "035E4C31")
    pub fn extract_serial(device_name: &str) -> Option<&str> {
        device_name.strip_prefix("Polar H10 ")
    }

    /// Look up device by serial
    pub fn get_device(&self, serial: &str) -> Option<&DeviceInfo> {
        self.devices.get(serial)
    }

    /// Identify device from its BLE name
    pub fn identify(&self, device_name: &str) -> Option<&DeviceInfo> {
        Self::extract_serial(device_name).and_then(|s| self.get_device(s))
    }

    /// All registered devices
    pub fn all_devices(&self) -> Vec<&DeviceInfo> {
        self.devices.values().collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_serial() {
        assert_eq!(
            DeviceRegistry::extract_serial("Polar H10 035E4C31"),
            Some("035E4C31")
        );
        assert_eq!(DeviceRegistry::extract_serial("Other Device"), None);
        assert_eq!(DeviceRegistry::extract_serial(""), None);
    }
}
