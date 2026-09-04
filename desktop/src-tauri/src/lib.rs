//! EarthianBioSense Desktop — Tauri v2 app.
//!
//! Rust backend for BLE acquisition from Polar H10, HRV processing,
//! and IPC event emission to the webview frontend.

mod ble;
pub mod hrv;
pub mod motion;
pub mod session;

use ble::registry::DeviceRegistry;
use ble::reconnect::{self, backoff_for_attempt, gap_ms, supervision_deadline, LINK_WATCHDOG};
use ble::{
    connect_and_stream, create_adapter, reconnect_and_stream, scan_devices, teardown_peripheral,
    AccBuffer, DeviceStatus, DiscoveredDevice, HrMessage, StreamAlive,
};
use btleplug::platform::Adapter;
use hrv::phase::PhaseTrajectory;
use hrv::compute_hrv_metrics;
use motion::{MotionProcessor, MotionState};
use session::{SessionFileInfo, SessionLogger, SessionSummary};
use serde::Serialize;
use std::collections::VecDeque;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex as StdMutex};
use std::time::{Duration, Instant};
use tauri::{Emitter, Manager, State};
use tokio::sync::{mpsc, Mutex};

/// RR interval buffer size (matching Python RR_WINDOW_SIZE)
const RR_BUFFER_SIZE: usize = 20;

/// Rescan window used within a reconnect attempt when the adapter no longer
/// lists the device (SPEC-009 REQ-005 §5).
const RECONNECT_RESCAN: Duration = Duration::from_secs(2);
/// Upper bound on one reconnect attempt (lookup + optional rescan + connect + subscribe).
const RECONNECT_ATTEMPT_TIMEOUT: Duration = Duration::from_secs(20);
/// How long `cmd_disconnect` waits for the processing task to exit (§10).
const DISCONNECT_JOIN_TIMEOUT: Duration = Duration::from_secs(5);

/// Shared application state.
pub struct AppState {
    adapter: Mutex<Option<Adapter>>,
    registry: DeviceRegistry,
    stop_tx: Mutex<Option<tokio::sync::oneshot::Sender<()>>>,
    /// Connection generation (REQ-005 §9): minted by every `cmd_connect`. A
    /// processing task acts on shared UI state only while it owns the
    /// current generation.
    generation: AtomicU64,
    /// The live processing task; `cmd_disconnect` awaits it (§10).
    task: Mutex<Option<tokio::task::JoinHandle<()>>>,
    /// Lifecycle mutex (§10): `cmd_connect` and `cmd_disconnect` hold this for
    /// their whole body so two lifecycle commands never interleave (a second
    /// concurrent disconnect waits for the first to finish its join).
    lifecycle: Mutex<()>,
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
    /// Signed breath-band coupling (−1..1); entrainment's positive part, with
    /// anti-phase preserved distinct from decoupled.
    phase_coupling: f64,
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
    // Two-axis mode field (stillness × coherence). None until coherence wired.
    soft_mode_2d: Option<SoftModeEvent>,
    // Motion channel (SPEC-013)
    motion: MotionState,
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
    // §10: held for the whole command body (named so it is not dropped early).
    let _lifecycle = state.lifecycle.lock().await;
    let mut active = state.active.lock().await;
    if *active {
        return Err("A device is already connected".to_string());
    }

    let device_label = label.unwrap_or_else(|| "A".to_string());
    let (tx, mut rx) = mpsc::unbounded_channel::<HrMessage>();
    let acc_buffer: AccBuffer = Arc::new(StdMutex::new(Vec::new()));

    // Connection generation (§9): this task owns `conn_gen` until the next
    // cmd_connect mints a newer one. Stream sub-generation starts at 1 and
    // increments on every successful reconnect; channel messages carry it.
    let conn_gen = state.generation.fetch_add(1, Ordering::SeqCst) + 1;
    let first_stream_gen: u64 = 1;

    let guard = state.get_adapter().await?;
    let adapter = guard.as_ref().unwrap();
    let (mut status, first_alive) = connect_and_stream(
        adapter,
        address.clone(),
        tx.clone(),
        device_label.clone(),
        acc_buffer.clone(),
        first_stream_gen,
    )
    .await?;
    drop(guard);

    if let Some(info) = state.registry.identify(&status.name) {
        status.strap = Some(info.strap.clone());
    }

    app.emit("ebs:device-status", &status).ok();

    *active = true;
    drop(active);

    let (stop_tx, stop_rx) = tokio::sync::oneshot::channel::<()>();
    *state.stop_tx.lock().await = Some(stop_tx);

    // Spawn the processing pipeline:
    // BLE HR data → RR buffer → HRV metrics → phase dynamics → emit + log
    let handle = app.clone();
    let acc_buffer_loop = acc_buffer.clone();
    let loop_status = status.clone();
    let loop_address = address.clone();
    let loop_label = device_label.clone();
    let task = tokio::spawn(async move {
        // Held for the life of the loop so `rx.recv()` never yields `None`
        // when a notification task exits (peripheral dropped). Reconnects
        // hand clones of this sender to the new stream (SPEC-009 REQ-005).
        let tx = tx;
        let mut stop_rx = stop_rx;
        let address = loop_address;
        let device_label = loop_label;
        let mut current_status = loop_status;
        // Generation flag of the live notification listener (REQ-005 §6).
        let mut current_alive: StreamAlive = first_alive;
        // Stream sub-generation (§9): messages with any other value are stale.
        let mut stream_gen: u64 = first_stream_gen;

        let mut rr_buffer: VecDeque<u16> = VecDeque::with_capacity(RR_BUFFER_SIZE);
        let mut trajectory = PhaseTrajectory::new(30);
        let mut motion_proc = MotionProcessor::new();
        let mut _tick_count: u64 = 0;

        // Link supervision (SPEC-009 REQ-005 §1, §8, §11). One deadline:
        //   sample exists            → last sample + LINK_WATCHDOG (link lost)
        //   no sample, after reconn. → reconnected_at + ESTABLISH_TIMEOUT
        //   neither (initial connect)→ unarmed (residue)
        // `ble_link_lost` is only ever written from a real sample; a failed
        // establishment after a reconnect resumes the cycle silently.
        let mut last_sample: Option<(Instant, String)> = None;
        let mut reconnected_at: Option<Instant> = None;
        // The departure on record: (last sample instant, its ts). Set when the
        // link is declared lost; cleared by the next real sample. Reused for
        // `since_ts` and `gap_ms` if establishment fails and the cycle resumes.
        let mut loss: Option<(Instant, String)> = None;
        // Attempt counter for the current departure; reset by a real sample so
        // "the cycle resumes with the next back-off" (§11) holds.
        let mut attempt: u32 = 0;

        loop {
            let deadline = supervision_deadline(last_sample.as_ref().map(|(t, _)| *t), reconnected_at);
            tokio::select! {
                Some((label, hr_data, msg_gen)) = rx.recv() => {
                    if msg_gen != stream_gen {
                        // Queued by a retired listener (§9): never fresh.
                        continue;
                    }
                    let seen_at = Instant::now();
                    // Drain accelerometer samples accumulated since the last tick
                    // and derive this tick's motion state (SPEC-013).
                    let acc_samples: Vec<[i16; 3]> = match acc_buffer_loop.lock() {
                        Ok(mut b) => b.drain(..).collect(),
                        Err(_) => Vec::new(),
                    };
                    let motion_state = motion_proc.update(&acc_samples);
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
                    // Two-axis classification: feed the (now-available) coherence
                    // into the 2-D scheme alongside the calm scalar. Additive —
                    // the 1-D soft_mode above is untouched.
                    let soft_mode_2d_inf =
                        trajectory.compute_2d_mode(metrics.mode_score, coherence);

                    let ts = chrono::Local::now().to_rfc3339_opts(
                        chrono::SecondsFormat::Millis,
                        false,
                    );
                    last_sample = Some((seen_at, ts.clone()));
                    reconnected_at = None;

                    // First real sample of a restored stream: the reconnect is
                    // confirmed here, not at connect() (§2). Exactly one
                    // ble_reconnect per ble_link_lost; an attempt that connected
                    // but never produced a sample writes nothing.
                    if let Some((lost_at, _)) = loss.take() {
                        let gap = gap_ms(lost_at, seen_at);
                        log::info!("BLE link restored after {} ms ({} attempts)", gap, attempt);
                        // §3: the UI goes green only now — a connect() that never
                        // produced a sample must never have shown connected:true.
                        current_status.connected = true;
                        current_status.reconnecting = false;
                        handle.emit("ebs:device-status", &current_status).ok();
                        handle.emit("ble:reconnected", &serde_json::json!({
                            "gap_ms": gap,
                            "attempts": attempt,
                        })).ok();
                        let state = handle.state::<AppState>();
                        let mut logger = state.session_logger.lock().await;
                        if logger.is_active() {
                            logger.log_field_event_at(
                                &ts,
                                "ble_reconnect",
                                &format!("link restored after {} ms ({} attempts)", gap, attempt),
                                &reconnect::reconnect_fields(gap, attempt),
                            );
                        }
                    }
                    attempt = 0;

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

                    // Build 2-D mode event (full membership — only 5 modes).
                    let soft_mode_2d_event = {
                        let membership: std::collections::HashMap<String, f64> = soft_mode_2d_inf
                            .membership
                            .iter()
                            .map(|(k, v)| (k.clone(), (*v * 10000.0).round() / 10000.0))
                            .collect();
                        Some(SoftModeEvent {
                            primary: soft_mode_2d_inf.primary_mode.clone(),
                            secondary: soft_mode_2d_inf.secondary_mode.clone(),
                            ambiguity: soft_mode_2d_inf.ambiguity,
                            membership,
                        })
                    };

                    // Emit phase event to frontend
                    let event = PhaseEvent {
                        ts: ts.clone(),
                        hr: hr_data.heart_rate,
                        rr: hr_data.rr_intervals.clone(),
                        participant: label.clone(),
                        amplitude: metrics.amplitude,
                        entrainment: metrics.entrainment,
                        entrainment_label: metrics.entrainment_label.clone(),
                        phase_coupling: metrics.phase_coupling,
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
                        soft_mode_2d: soft_mode_2d_event,
                        motion: motion_state.clone(),
                    };
                    handle.emit("ebs:phase", &event).ok();

                    // Range-egress warning: sustained motion before a likely dropout.
                    if motion_state.range_egress_warning {
                        handle.emit("ebs:range_egress_warning", &serde_json::json!({
                            "ts": ts.clone(),
                            "motion_mag": motion_state.motion_mag,
                            "sustained_ticks": motion_state.sustained_moving_ticks,
                        })).ok();
                    }

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
                                Some(&soft_mode_2d_inf),
                                &motion_state,
                            );
                            if motion_state.range_egress_warning {
                                logger.log_field_event_at(
                                    &ts,
                                    "range_egress_warning",
                                    &format!(
                                        "motion_mag={:.1} sustained_ticks={}",
                                        motion_state.motion_mag,
                                        motion_state.sustained_moving_ticks
                                    ),
                                    &serde_json::json!({}),
                                );
                            }
                        }
                    }

                    _tick_count += 1;
                }
                _ = tokio::time::sleep_until(tokio::time::Instant::from_std(deadline.unwrap_or_else(Instant::now))), if deadline.is_some() => {
                    let now = Instant::now();
                    if deadline.map(|d| now < d).unwrap_or(true) {
                        continue; // early wake; re-derive and sleep again
                    }

                    match last_sample.take() {
                        Some((sample_at, sample_ts)) => {
                            // --- Link lost (§1): a real sample went quiet ------
                            log::warn!(
                                "BLE link lost: no HR notification for {:?} (last sample {})",
                                LINK_WATCHDOG, sample_ts
                            );
                            // Retire the listener generation (§6) before any attempt.
                            current_alive.store(false, Ordering::Relaxed);
                            current_status.connected = false;
                            current_status.reconnecting = true;
                            handle.emit("ebs:device-status", &current_status).ok();
                            {
                                let state = handle.state::<AppState>();
                                let mut logger = state.session_logger.lock().await;
                                if logger.is_active() {
                                    logger.log_field_event_with(
                                        "ble_link_lost",
                                        &format!(
                                            "no HR notification for {}s; reconnecting",
                                            LINK_WATCHDOG.as_secs()
                                        ),
                                        &reconnect::link_lost_fields(&sample_ts, LINK_WATCHDOG.as_secs()),
                                    );
                                }
                            }
                            loss = Some((sample_at, sample_ts));
                        }
                        None => {
                            // --- Establishment timeout after a reconnect (§11) ---
                            // The attempt is deemed failed after the fact. No
                            // second ble_link_lost (departure already on record),
                            // no new connected:false (UI is already amber).
                            log::warn!(
                                "Reconnected stream produced no HR sample within {:?}; resuming reconnect cycle",
                                reconnect::ESTABLISH_TIMEOUT
                            );
                            current_alive.store(false, Ordering::Relaxed);
                            // Status is already connected:false/reconnecting:true
                            // (never flipped at connect()); nothing to emit.
                        }
                    }
                    reconnected_at = None;
                    let since_ts = match &loss {
                        Some((_, ts)) => ts.clone(),
                        None => String::new(), // unreachable: loss is set on every path into the cycle
                    };

                    // --- Reconnect cycle: back off, attempt, repeat; stop wins ---
                    let mut stopped = false;
                    loop {
                        attempt += 1;
                        let delay = backoff_for_attempt(attempt);
                        handle.emit("ble:reconnecting", &serde_json::json!({
                            "attempt": attempt,
                            "delay_secs": delay.as_secs(),
                            "since_ts": since_ts,
                        })).ok();

                        tokio::select! {
                            _ = tokio::time::sleep(delay) => {}
                            _ = &mut stop_rx => {
                                log::info!("Stop signal received during reconnect back-off");
                                stopped = true;
                                break;
                            }
                        }

                        // Clone the adapter out and release the AppState lock
                        // BEFORE any BLE await (§7) so scan/connect commands
                        // are never starved by a long attempt.
                        let adapter_res: Result<Option<Adapter>, String> = {
                            let state = handle.state::<AppState>();
                            // Bound to a local so the guard is dropped before `state`.
                            let r = state.get_adapter().await.map(|guard| guard.as_ref().cloned());
                            r
                        };
                        let adapter: Adapter = match adapter_res {
                            Ok(Some(a)) => a,
                            Ok(None) => {
                                log::warn!("Reconnect attempt {}: no adapter", attempt);
                                continue;
                            }
                            Err(e) => {
                                log::warn!("Reconnect attempt {}: adapter unavailable: {}", attempt, e);
                                continue;
                            }
                        };

                        // A single attempt may not hang the cycle: btleplug's
                        // connect() has no deadline of its own on CoreBluetooth.
                        // On expiry a bounded teardown runs (§7).
                        let next_stream_gen = stream_gen + 1;
                        let attempt_fut = tokio::time::timeout(
                            RECONNECT_ATTEMPT_TIMEOUT,
                            reconnect_and_stream(
                                &adapter,
                                address.clone(),
                                tx.clone(),
                                device_label.clone(),
                                acc_buffer_loop.clone(),
                                RECONNECT_RESCAN,
                                next_stream_gen,
                            ),
                        );

                        let mut timed_out = false;
                        let result = tokio::select! {
                            r = attempt_fut => match r {
                                Ok(inner) => inner,
                                Err(_elapsed) => {
                                    timed_out = true;
                                    Err(format!("attempt timed out after {:?}", RECONNECT_ATTEMPT_TIMEOUT))
                                }
                            },
                            _ = &mut stop_rx => {
                                log::info!("Stop signal received during reconnect attempt");
                                stopped = true;
                                break;
                            }
                        };

                        if timed_out {
                            // Bounded teardown (§7), only while this task still
                            // owns the connection generation (§9/§10), and
                            // abandoned the moment stop fires.
                            let owns = handle.state::<AppState>().generation.load(Ordering::SeqCst) == conn_gen;
                            if owns {
                                log::warn!("Reconnect attempt {} timed out; tearing down peripheral", attempt);
                                tokio::select! {
                                    _ = teardown_peripheral(&adapter, &address) => {}
                                    _ = &mut stop_rx => {
                                        log::info!("Stop signal received during timeout teardown; abandoning");
                                        stopped = true;
                                        break;
                                    }
                                }
                            } else {
                                log::warn!("Reconnect attempt {} timed out; generation superseded, skipping teardown", attempt);
                            }
                        }

                        match result {
                            Ok((fresh, fresh_alive)) => {
                                let connected_at = Instant::now();
                                log::info!(
                                    "BLE connect() succeeded on attempt {}; awaiting first HR sample to confirm",
                                    attempt
                                );
                                // §3: status stays connected:false/reconnecting:true
                                // (amber, truthful) until the first generation-valid
                                // HR sample. Only the non-connection fields refresh
                                // here; connected:true, ble:reconnected and the
                                // ble_reconnect field event fire in the tick branch.
                                // `loss` and `attempt` stay set.
                                current_status.name = fresh.name;
                                current_status.battery = fresh.battery;
                                current_status.device = fresh.device;
                                {
                                    let state = handle.state::<AppState>();
                                    current_status.strap = state
                                        .registry
                                        .identify(&current_status.name)
                                        .map(|info| info.strap.clone());
                                }
                                current_status.connected = false;
                                current_status.reconnecting = true;
                                current_alive = fresh_alive;
                                stream_gen = next_stream_gen;
                                // Anything the retired stream left behind is not this link's motion.
                                if let Ok(mut b) = acc_buffer_loop.lock() {
                                    b.clear();
                                }
                                // §11: do NOT fabricate a sample. The sample watchdog
                                // stays unarmed; establishment is supervised instead.
                                last_sample = None;
                                reconnected_at = Some(connected_at);
                                break;
                            }
                            Err(e) => {
                                log::warn!("Reconnect attempt {} failed: {}", attempt, e);
                            }
                        }
                    }

                    if stopped {
                        break;
                    }
                }
                _ = &mut stop_rx => {
                    log::info!("Stop signal received, ending data relay");
                    break;
                }
            }
        }

        // Task exit (stop): retire the live listener so a lingering stream
        // is discarded, and publish the terminal status (CON-002:
        // connected:false, reconnecting:false on user disconnect) — but only
        // while this task still owns the connection generation (§9), so an
        // old task can never overwrite a newer connection's UI state.
        current_alive.store(false, Ordering::Relaxed);
        let owns = handle.state::<AppState>().generation.load(Ordering::SeqCst) == conn_gen;
        if owns {
            current_status.connected = false;
            current_status.reconnecting = false;
            handle.emit("ebs:device-status", &current_status).ok();
        } else {
            log::info!("Processing task gen {} exiting; generation superseded, no terminal status emit", conn_gen);
        }
    });
    *state.task.lock().await = Some(task);

    Ok(status)
}

#[tauri::command]
async fn cmd_disconnect(state: State<'_, AppState>) -> Result<(), String> {
    // §10: held for the whole command body (named so it is not dropped early).
    // A second concurrent disconnect waits here, then finds stop_tx/task empty
    // and active=false, and returns Ok.
    let _lifecycle = state.lifecycle.lock().await;
    // Stop BLE stream
    let stop_tx = state.stop_tx.lock().await.take();
    if let Some(tx) = stop_tx {
        tx.send(()).ok();
    }
    // Await the processing task (§10, bounded) so a following cmd_connect
    // cannot overlap a task that is still tearing down.
    let task = state.task.lock().await.take();
    if let Some(task) = task {
        match tokio::time::timeout(DISCONNECT_JOIN_TIMEOUT, task).await {
            Ok(Ok(())) => {}
            Ok(Err(e)) => log::warn!("Processing task ended with error on disconnect: {}", e),
            Err(_) => log::warn!(
                "Processing task did not exit within {:?} of stop; continuing disconnect",
                DISCONNECT_JOIN_TIMEOUT
            ),
        }
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
            generation: AtomicU64::new(0),
            task: Mutex::new(None),
            lifecycle: Mutex::new(()),
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
