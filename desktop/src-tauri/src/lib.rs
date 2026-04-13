//! EarthianBioSense Desktop — Tauri v2 app.
//!
//! Rust backend for BLE acquisition from Polar H10, HRV processing,
//! and IPC event emission to the webview frontend.

mod ble;
pub mod hrv;
pub mod session;

use ble::registry::DeviceRegistry;
use ble::{connect_and_stream, create_adapter, scan_devices, DeviceStatus, DiscoveredDevice};
use btleplug::platform::Adapter;
use hrv::phase::PhaseTrajectory;
use hrv::compute_hrv_metrics;
use session::{SessionFileInfo, SessionLogger, SessionSummary};
use serde::Serialize;
use std::collections::VecDeque;
use std::path::PathBuf;
use tauri::{Emitter, Manager, State};
use tokio::sync::{mpsc, Mutex};

/// RR interval buffer size (matching Python RR_WINDOW_SIZE)
const RR_BUFFER_SIZE: usize = 20;

/// Shared application state.
pub struct AppState {
    adapter: Mutex<Option<Adapter>>,
    registry: DeviceRegistry,
    stop_tx: Mutex<Option<tokio::sync::oneshot::Sender<()>>>,
    active: Mutex<bool>,
    session_logger: Mutex<SessionLogger>,
    sessions_dir: PathBuf,
}

impl AppState {
    async fn get_adapter(&self) -> Result<tokio::sync::MutexGuard<'_, Option<Adapter>>, String> {
        let mut guard = self.adapter.lock().await;
        if guard.is_none() {
            let adapter = create_adapter().await?;
            *guard = Some(adapter);
        }
        Ok(guard)
    }
}

/// Path to the EBS project root
fn project_root() -> PathBuf {
    let manifest_dir = env!("CARGO_MANIFEST_DIR");
    PathBuf::from(manifest_dir)
        .parent() // desktop/ -> Earthian-BioSense/
        .unwrap_or_else(|| std::path::Path::new(manifest_dir))
        .to_path_buf()
}

/// Phase dynamics event emitted to the frontend at 1Hz.
/// Matches the `ebs:phase` contract from SPEC-009.
#[derive(Debug, Serialize)]
struct PhaseEvent {
    ts: String,
    hr: u16,
    rr: Vec<u16>,
    participant: String,
    // Metrics
    amplitude: u16,
    entrainment: f64,
    entrainment_label: String,
    breath_rate: Option<f64>,
    mode: String,
    mode_score: f64,
    volatility: f64,
    // Phase dynamics
    position: [f64; 3],
    velocity: [f64; 3],
    velocity_magnitude: f64,
    curvature: f64,
    stability: f64,
    history_signature: f64,
    phase_label: String,
    coherence: f64,
    // Movement-preserving classification
    movement_annotation: String,
    movement_aware_label: String,
    mode_status: String,
    dwell_time: f64,
    acceleration_mag: f64,
    // Soft mode (optional)
    soft_mode: Option<SoftModeEvent>,
}

#[derive(Debug, Serialize)]
struct SoftModeEvent {
    primary: String,
    secondary: Option<String>,
    ambiguity: f64,
    membership: std::collections::HashMap<String, f64>,
}

// === Tauri Commands ===

#[tauri::command]
async fn cmd_scan_devices(
    state: State<'_, AppState>,
    timeout_secs: Option<u64>,
) -> Result<Vec<DiscoveredDevice>, String> {
    let timeout = timeout_secs.unwrap_or(5);
    let guard = state.get_adapter().await?;
    let adapter = guard.as_ref().unwrap();
    scan_devices(adapter, &state.registry, timeout).await
}

#[tauri::command]
async fn cmd_connect(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
    address: String,
    label: Option<String>,
) -> Result<DeviceStatus, String> {
    let mut active = state.active.lock().await;
    if *active {
        return Err("A device is already connected".to_string());
    }

    let device_label = label.unwrap_or_else(|| "A".to_string());
    let (tx, mut rx) = mpsc::unbounded_channel();

    let guard = state.get_adapter().await?;
    let adapter = guard.as_ref().unwrap();
    let mut status =
        connect_and_stream(adapter, address, tx, device_label.clone()).await?;
    drop(guard);

    if let Some(info) = state.registry.identify(&status.name) {
        status.strap = Some(info.strap.clone());
    }

    app.emit("ebs:device-status", &status).ok();

    *active = true;
    drop(active);

    let (stop_tx, mut stop_rx) = tokio::sync::oneshot::channel::<()>();
    *state.stop_tx.lock().await = Some(stop_tx);

    // Spawn the processing pipeline:
    // BLE HR data → RR buffer → HRV metrics → phase dynamics → emit + log
    let handle = app.clone();
    tokio::spawn(async move {
        let mut rr_buffer: VecDeque<u16> = VecDeque::with_capacity(RR_BUFFER_SIZE);
        let mut trajectory = PhaseTrajectory::new(30);
        let mut _tick_count: u64 = 0;

        loop {
            tokio::select! {
                Some((label, hr_data)) = rx.recv() => {
                    // Add RR intervals to buffer
                    for rr in &hr_data.rr_intervals {
                        rr_buffer.push_back(*rr);
                        if rr_buffer.len() > RR_BUFFER_SIZE {
                            rr_buffer.pop_front();
                        }
                    }

                    // Compute HRV metrics from buffer
                    let rr_vec: Vec<u16> = rr_buffer.iter().copied().collect();
                    let metrics = compute_hrv_metrics(&rr_vec);

                    // Compute phase dynamics (1Hz — every tick since BLE notifies ~1Hz)
                    let now = std::time::SystemTime::now()
                        .duration_since(std::time::UNIX_EPOCH)
                        .unwrap_or_default()
                        .as_secs_f64();
                    let dynamics = trajectory.append(&metrics, now);
                    let coherence = trajectory.compute_trajectory_coherence(5);

                    let ts = chrono::Local::now().to_rfc3339_opts(
                        chrono::SecondsFormat::Millis,
                        false,
                    );

                    // Build soft mode event
                    let soft_mode_event = dynamics.soft_mode.as_ref().map(|sm| {
                        // Top 3 membership weights
                        let mut sorted: Vec<_> = sm.membership.iter().collect();
                        sorted.sort_by(|a, b| b.1.partial_cmp(a.1).unwrap_or(std::cmp::Ordering::Equal));
                        let top3: std::collections::HashMap<String, f64> = sorted
                            .into_iter()
                            .take(3)
                            .map(|(k, v)| (k.clone(), (*v * 10000.0).round() / 10000.0))
                            .collect();

                        SoftModeEvent {
                            primary: sm.primary_mode.clone(),
                            secondary: sm.secondary_mode.clone(),
                            ambiguity: sm.ambiguity,
                            membership: top3,
                        }
                    });

                    // Emit phase event to frontend
                    let event = PhaseEvent {
                        ts: ts.clone(),
                        hr: hr_data.heart_rate,
                        rr: hr_data.rr_intervals.clone(),
                        participant: label.clone(),
                        amplitude: metrics.amplitude,
                        entrainment: metrics.entrainment,
                        entrainment_label: metrics.entrainment_label.clone(),
                        breath_rate: metrics.breath_rate,
                        mode: metrics.mode_label.clone(),
                        mode_score: metrics.mode_score,
                        volatility: metrics.rr_volatility,
                        position: dynamics.position,
                        velocity: dynamics.velocity,
                        velocity_magnitude: dynamics.velocity_magnitude,
                        curvature: dynamics.curvature,
                        stability: dynamics.stability,
                        history_signature: dynamics.history_signature,
                        phase_label: dynamics.phase_label.clone(),
                        coherence,
                        movement_annotation: dynamics.movement_annotation.clone(),
                        movement_aware_label: dynamics.movement_aware_label.clone(),
                        mode_status: dynamics.mode_status.clone(),
                        dwell_time: dynamics.dwell_time,
                        acceleration_mag: dynamics.mode_score_acceleration,
                        soft_mode: soft_mode_event,
                    };
                    handle.emit("ebs:phase", &event).ok();

                    // Also emit raw HR for the session bar display
                    handle.emit("ebs:hr", &serde_json::json!({
                        "hr": hr_data.heart_rate,
                        "rr": hr_data.rr_intervals,
                        "sensor_contact": hr_data.sensor_contact,
                    })).ok();

                    // Persist sample to JSONL if a session is recording
                    {
                        let state = handle.state::<AppState>();
                        let mut logger = state.session_logger.lock().await;
                        if logger.is_active() {
                            logger.log(
                                &ts,
                                hr_data.heart_rate,
                                &hr_data.rr_intervals,
                                &metrics,
                                &dynamics,
                                coherence,
                            );
                        }
                    }

                    _tick_count += 1;
                }
                _ = &mut stop_rx => {
                    log::info!("Stop signal received, ending data relay");
                    break;
                }
            }
        }
    });

    Ok(status)
}

#[tauri::command]
async fn cmd_disconnect(state: State<'_, AppState>) -> Result<(), String> {
    // Stop BLE stream
    let stop_tx = state.stop_tx.lock().await.take();
    if let Some(tx) = stop_tx {
        tx.send(()).ok();
    }
    // Stop session if active
    let mut logger = state.session_logger.lock().await;
    if logger.is_active() {
        logger.stop_session();
    }
    *state.active.lock().await = false;
    Ok(())
}

#[tauri::command]
async fn cmd_start_session(
    state: State<'_, AppState>,
    session_type: Option<String>,
) -> Result<String, String> {
    let mut logger = state.session_logger.lock().await;
    if logger.is_active() {
        return Err("Session already active".to_string());
    }
    let st = session_type.as_deref().unwrap_or("solo");
    let path = logger.start_session(st)?;
    Ok(path.to_string_lossy().to_string())
}

#[tauri::command]
async fn cmd_stop_session(state: State<'_, AppState>) -> Result<SessionSummary, String> {
    let mut logger = state.session_logger.lock().await;
    if !logger.is_active() {
        return Err("No active session".to_string());
    }
    Ok(logger.stop_session())
}

#[tauri::command]
async fn cmd_list_sessions(state: State<'_, AppState>) -> Result<Vec<SessionFileInfo>, String> {
    Ok(session::list_sessions(&state.sessions_dir))
}

#[tauri::command]
async fn cmd_load_session(
    state: State<'_, AppState>,
    filename: String,
) -> Result<String, String> {
    let path = state.sessions_dir.join(&filename);
    std::fs::read_to_string(&path)
        .map_err(|e| format!("Failed to read session file: {}", e))
}

#[tauri::command]
async fn cmd_get_registry(
    state: State<'_, AppState>,
) -> Result<Vec<ble::registry::DeviceInfo>, String> {
    Ok(state.registry.all_devices().into_iter().cloned().collect())
}

// === App Setup ===

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let root = project_root();
    let config_path = root.join("config").join("devices.json");
    let sessions_dir = root.join("sessions");

    let registry = DeviceRegistry::load(&config_path).unwrap_or_else(|e| {
        eprintln!("Could not load device registry: {}. Using empty registry.", e);
        DeviceRegistry::empty()
    });

    let session_logger = SessionLogger::new(&sessions_dir);

    tauri::Builder::default()
        .manage(AppState {
            adapter: Mutex::new(None),
            registry,
            stop_tx: Mutex::new(None),
            active: Mutex::new(false),
            session_logger: Mutex::new(session_logger),
            sessions_dir,
        })
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            cmd_scan_devices,
            cmd_connect,
            cmd_disconnect,
            cmd_start_session,
            cmd_stop_session,
            cmd_list_sessions,
            cmd_load_session,
            cmd_get_registry,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
