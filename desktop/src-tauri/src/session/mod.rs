//! JSONL session logger for EarthianBioSense.
//!
//! Writes one JSON object per line to timestamped session files.
//! Format matches the Python `session_logger.py` output exactly
//! so downstream tools (viz, replay, analysis) work unchanged.

use serde::Serialize;
use serde_json::{json, Value};
use std::fs::{self, File};
use std::io::{BufWriter, Write};
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::time::{Instant, SystemTime};

use chrono::Local;

use crate::eeg::{central_tick_json, CentralTick, Contact};
use crate::hrv::HRVMetrics;
use crate::hrv::movement::SoftModeInference;
use crate::hrv::phase::PhaseDynamics;
use crate::motion::MotionState;

/// Read `~/.ebs-bridge/current-session.json` and return `claude_session_id`
/// iff the file exists, parses, and is fresh (within the liveness window).
///
/// SPEC-010 v0.2 (2026-07-04): the freshness window was 300s, which assumed the
/// operator straps in within 5 min of the Claude session starting. In a long
/// think-with the strap goes on when the work turns, so the file was stale and
/// the link dropped. The `ebs-bridge-keepalive.sh` UserPromptSubmit hook now
/// re-touches the file on every prompt, so an *active* conversation keeps it
/// fresh; this window is widened to 900s only as a fallback covering pauses
/// between prompts. SessionEnd still clears the file, so an ended session
/// positively expires regardless of the window.
///
/// See `Earthian-BioSense/specs/SPEC-010-vibe-harness-bridge.md`.
fn read_bridge_claude_session_id() -> Option<String> {
    let home = std::env::var("HOME").ok()?;
    let path = PathBuf::from(home).join(".ebs-bridge").join("current-session.json");

    let meta = fs::metadata(&path).ok()?;
    let modified = meta.modified().ok()?;
    let age = SystemTime::now().duration_since(modified).ok()?;
    if age.as_secs() > 900 {
        return None;
    }

    let contents = fs::read_to_string(&path).ok()?;
    let value: Value = serde_json::from_str(&contents).ok()?;
    if !value.get("enabled").and_then(Value::as_bool).unwrap_or(false) {
        return None;
    }
    value
        .get("claude_session_id")
        .and_then(Value::as_str)
        .map(String::from)
        .filter(|s| !s.is_empty())
}

// ---------------------------------------------------------------------------
// Data structures
// ---------------------------------------------------------------------------

pub struct SessionLogger {
    session_dir: PathBuf,
    writer: Option<BufWriter<File>>,
    session_file: Option<PathBuf>,
    sample_count: u32,
    started_at: Option<String>,
    /// SPEC-015: the instant at which `host_mono` was 0 (app start). Set by
    /// `run()` via [`set_mono_epoch`]; defaults to logger creation.
    mono_epoch: Instant,
    /// SPEC-015: the open central window, if any. The logger is the single
    /// writer of the central lifecycle (`central_start` … `central_end`).
    central: Option<CentralFile>,
    /// SPEC-015: central windows opened in this session. A Muse reconnect
    /// inside one session opens a NEW side-file; earlier windows are never
    /// truncated (Codex review 2026-09-11, high).
    central_windows: u32,
}

/// SPEC-015 CON-015-4 `central_meta`, minus `raw_file` (the logger fills it).
#[derive(Debug, Clone)]
pub struct CentralMeta {
    pub device: String,
    pub preset: String,
    pub channels: Vec<String>,
    pub scalp_channels: Vec<String>,
    pub sample_rate_hz: u32,
}

/// The raw EEG side-file (`<session>_eeg.jsonl`) and the counters that
/// `central_end` declares for truncation detection.
struct CentralFile {
    writer: BufWriter<File>,
    raw_file: String,
    /// Last packet `seq` written; `None` until the first batch.
    last_seq: Option<u64>,
    /// Samples written, counted per record as the longest channel's length.
    n_samples: u64,
}

#[derive(Debug, Clone, Serialize)]
pub struct SessionSummary {
    pub duration_secs: f64,
    pub sample_count: u32,
    pub file_path: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct SessionFileInfo {
    pub filename: String,
    pub size_bytes: u64,
    pub date: String,
}

// ---------------------------------------------------------------------------
// Rounding helpers
// ---------------------------------------------------------------------------

fn r1(v: f64) -> f64 {
    (v * 10.0).round() / 10.0
}

fn r2(v: f64) -> f64 {
    (v * 100.0).round() / 100.0
}

fn r3(v: f64) -> f64 {
    (v * 1000.0).round() / 1000.0
}

fn r4(v: f64) -> f64 {
    (v * 10000.0).round() / 10000.0
}

// ---------------------------------------------------------------------------
// SessionLogger implementation
// ---------------------------------------------------------------------------

impl SessionLogger {
    pub fn new(session_dir: &Path) -> Self {
        if !session_dir.exists() {
            fs::create_dir_all(session_dir).ok();
        }
        Self {
            session_dir: session_dir.to_path_buf(),
            writer: None,
            session_file: None,
            sample_count: 0,
            started_at: None,
            mono_epoch: Instant::now(),
            central: None,
            central_windows: 0,
        }
    }

    /// SPEC-015: anchor `host_mono` to the app's monotonic epoch.
    pub fn set_mono_epoch(&mut self, epoch: Instant) {
        self.mono_epoch = epoch;
    }

    /// Seconds since the monotonic epoch (the `host_mono` the logger itself
    /// stamps when it closes the central window on session stop).
    pub fn host_mono_now(&self) -> f64 {
        self.mono_epoch.elapsed().as_secs_f64()
    }

    fn now_ts() -> String {
        Local::now().format("%Y-%m-%dT%H:%M:%S%.3f%:z").to_string()
    }

    pub fn start_session(&mut self, session_type: &str) -> Result<PathBuf, String> {
        let now = Local::now();
        let ts = now.format("%Y-%m-%dT%H:%M:%S%.3f%:z").to_string();
        let filename = now.format("%Y-%m-%d_%H%M%S.jsonl").to_string();
        let path = self.session_dir.join(&filename);

        let file = File::create(&path)
            .map_err(|e| format!("Failed to create session file: {e}"))?;
        let mut writer = BufWriter::new(file);

        // SPEC-015 ADR-015-5: the wall-clock instant at which host_mono was 0,
        // so a reader can place every host_mono stamp on the wall clock.
        let host_mono_epoch = (now - chrono::Duration::from_std(self.mono_epoch.elapsed()).unwrap_or_default())
            .format("%Y-%m-%dT%H:%M:%S%.3f%:z")
            .to_string();

        let mut header = json!({
            "type": "session_start",
            "ts": ts,
            // 1.5.0: additive phase.soft_mode_2d (stillness × coherence membership).
            // 1.6.0 (SPEC-015): additive substrate/capability declaration +
            // host_mono_epoch, unconditional (ADR-015-5). Central records are
            // separate record types (ADR-015-7); the HR sample is unchanged.
            // Rust lineage is independent of Python's (see Python schema.py note).
            "schema_version": "1.6.0",
            "host_mono_epoch": host_mono_epoch,
            "substrates": ["autonomic"],
            "capabilities": ["hrv", "motion"],
            "session_type": session_type,
            "note": "ent=entrainment (breath-heart sync), coherence=trajectory integrity"
        });
        if let Some(cid) = read_bridge_claude_session_id() {
            header["claude_session_id"] = json!(cid);
        }

        writeln!(writer, "{}", serde_json::to_string(&header).unwrap())
            .map_err(|e| format!("Failed to write header: {e}"))?;
        writer.flush().map_err(|e| format!("Failed to flush: {e}"))?;

        self.writer = Some(writer);
        self.session_file = Some(path.clone());
        self.sample_count = 0;
        self.central_windows = 0;
        self.started_at = Some(ts);

        Ok(path)
    }

    pub fn log(
        &mut self,
        ts: &str,
        hr: u16,
        rr: &[u16],
        metrics: &HRVMetrics,
        dynamics: &PhaseDynamics,
        coherence: f64,
        soft_mode_2d: Option<&SoftModeInference>,
        motion: &MotionState,
    ) {
        let writer = match self.writer.as_mut() {
            Some(w) => w,
            None => return,
        };

        // Build soft_mode_2d object (stillness × coherence). Full membership —
        // the 2-D set is small (5 modes). Additive; null on pre-1.5.0 callers.
        let soft_mode_2d_json = match soft_mode_2d {
            Some(sm) => {
                let mut entries: Vec<(&String, &f64)> = sm.membership.iter().collect();
                entries.sort_by(|a, b| b.1.partial_cmp(a.1).unwrap_or(std::cmp::Ordering::Equal));
                let membership: serde_json::Map<String, serde_json::Value> = entries
                    .iter()
                    .map(|(k, v)| ((*k).clone(), json!(r4(**v))))
                    .collect();
                json!({
                    "primary": sm.primary_mode,
                    "secondary": sm.secondary_mode,
                    "ambiguity": r4(sm.ambiguity),
                    "distribution_shift": sm.distribution_shift.map(|v| r4(v)),
                    "membership": membership
                })
            }
            None => json!(null),
        };

        // Build soft_mode object
        let soft_mode_json = match &dynamics.soft_mode {
            Some(sm) => {
                // Top 3 modes by weight, sorted descending
                let mut entries: Vec<(&String, &f64)> = sm.membership.iter().collect();
                entries.sort_by(|a, b| b.1.partial_cmp(a.1).unwrap_or(std::cmp::Ordering::Equal));
                let top3: serde_json::Map<String, serde_json::Value> = entries
                    .iter()
                    .take(3)
                    .map(|(k, v)| ((*k).clone(), json!(r4(**v))))
                    .collect();

                json!({
                    "primary": sm.primary_mode,
                    "secondary": sm.secondary_mode,
                    "ambiguity": r4(sm.ambiguity),
                    "distribution_shift": sm.distribution_shift.map(|v| r4(v)),
                    "membership": top3
                })
            }
            None => json!(null),
        };

        let record = json!({
            "ts": ts,
            "hr": hr,
            "rr": rr,
            "metrics": {
                "amp": metrics.amplitude,
                "ent": r3(metrics.entrainment),
                "ent_label": metrics.entrainment_label,
                "breath": metrics.breath_rate.map(|v| r1(v)),
                "volatility": r4(metrics.rr_volatility),
                "mode": metrics.mode_label,
                "mode_score": r3(metrics.mode_score)
            },
            "phase": {
                "position": [r4(dynamics.position[0]), r4(dynamics.position[1]), r4(dynamics.position[2])],
                "velocity": [r4(dynamics.velocity[0]), r4(dynamics.velocity[1]), r4(dynamics.velocity[2])],
                "velocity_mag": r4(dynamics.velocity_magnitude),
                "curvature": r4(dynamics.curvature),
                "stability": r4(dynamics.stability),
                "history_signature": r4(dynamics.history_signature),
                "phase_label": dynamics.phase_label,
                "coherence": r4(coherence),
                "movement_annotation": dynamics.movement_annotation,
                "movement_aware_label": dynamics.movement_aware_label,
                "mode_status": dynamics.mode_status,
                "dwell_time": r2(dynamics.dwell_time),
                "acceleration_mag": r4(dynamics.mode_score_acceleration),
                "soft_mode": soft_mode_json,
                "soft_mode_2d": soft_mode_2d_json,
                "motion_confounded": motion.confounded
            },
            "motion": {
                "mag": r2(motion.motion_mag),
                "state": motion.state,
                "confounded": motion.confounded,
                "n_samples": motion.n_samples
            }
        });

        if let Ok(line) = serde_json::to_string(&record) {
            writeln!(writer, "{}", line).ok();
            writer.flush().ok();
        }

        self.sample_count += 1;
    }

    pub fn log_field_event(&mut self, event: &str, note: &str) {
        self.log_field_event_with(event, note, &json!({}));
    }

    /// Like [`log_field_event`] but merges `extra` (an object) into the record,
    /// so structured facts (e.g. `gap_ms`) travel beside the human `note`.
    /// SPEC-009 REQ-005. Keys owned by the logger (`type`, `ts`, `event`,
    /// `note`) are never overridden by `extra`.
    pub fn log_field_event_with(&mut self, event: &str, note: &str, extra: &Value) {
        let ts = Local::now().format("%Y-%m-%dT%H:%M:%S%.3f%:z").to_string();
        self.log_field_event_at(&ts, event, note, extra);
    }

    /// SPEC-015 v0.3 — a cue mark (e.g. `berger_cue` / `eyes_closed`) written
    /// as a plain `field_event` with `host_mono` (seconds since the app's
    /// monotonic epoch, 3 dp) so it joins the `central` ticks by the same clock
    /// the raw side-file uses. Returns whether a session was active: with no
    /// writer nothing is written and the caller must refuse, not pretend.
    pub fn log_cue(&mut self, event: &str, note: &str, host_mono: f64) -> bool {
        if self.writer.is_none() {
            return false;
        }
        self.log_field_event_with(event, note, &json!({"host_mono": r3(host_mono)}));
        true
    }

    /// Like [`log_field_event_with`] but with an explicit `ts`. Events raised
    /// *from a tick* (ble_reconnect, range_egress_warning) must carry that
    /// tick's `ts`: a fresh `Local::now()` lands a few ms later than the sample
    /// the event precedes in the file, and a downstream reader sees a backward
    /// clock step (observed 2026-09-04 14:05:13.051 → .050). SPEC-009 REQ-005.
    pub fn log_field_event_at(&mut self, ts: &str, event: &str, note: &str, extra: &Value) {
        let writer = match self.writer.as_mut() {
            Some(w) => w,
            None => return,
        };

        let mut record = serde_json::Map::new();
        if let Some(obj) = extra.as_object() {
            for (k, v) in obj {
                if matches!(k.as_str(), "type" | "ts" | "event" | "note") {
                    continue;
                }
                record.insert(k.clone(), v.clone());
            }
        }
        // Logger-owned keys are written last so they always win.
        record.insert("type".into(), json!("field_event"));
        record.insert("ts".into(), json!(ts));
        record.insert("event".into(), json!(event));
        record.insert("note".into(), json!(note));

        if let Ok(line) = serde_json::to_string(&Value::Object(record)) {
            writeln!(writer, "{}", line).ok();
            writer.flush().ok();
        }
    }

    // -----------------------------------------------------------------------
    // SPEC-015 central lifecycle — single writer
    // -----------------------------------------------------------------------

    /// Open the central window: write `central_start` and open the raw
    /// side-file beside the session file. No-op `Ok` if no session is active
    /// or a window is already open (REQ-015-3: never declares what is not there).
    pub fn central_start(&mut self, meta: CentralMeta, host_mono: f64) -> Result<(), String> {
        if self.central.is_some() {
            return Ok(());
        }
        let session_file = match &self.session_file {
            Some(p) if self.writer.is_some() => p.clone(),
            _ => return Ok(()),
        };
        let stem = session_file
            .file_stem()
            .map(|s| s.to_string_lossy().to_string())
            .unwrap_or_else(|| "session".to_string());
        // One side-file per central window: the first is `<stem>_eeg.jsonl`,
        // a reconnect within the same session gets `<stem>_eeg_2.jsonl`, ...
        // Exclusive creation so an existing file is never truncated.
        let window = self.central_windows + 1;
        let raw_file = if window == 1 {
            format!("{stem}_eeg.jsonl")
        } else {
            format!("{stem}_eeg_{window}.jsonl")
        };
        let raw_path = self.session_dir.join(&raw_file);
        let file = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&raw_path)
            .map_err(|e| format!("Failed to create raw EEG file {}: {e}", raw_path.display()))?;
        self.central_windows = window;
        let raw_writer = BufWriter::new(file);

        let record = json!({
            "type": "central_start",
            "ts": Self::now_ts(),
            "host_mono": r3(host_mono),
            "substrates_add": ["central"],
            "capabilities_add": ["eeg_raw", "eeg_bands"],
            "central_meta": {
                "device": meta.device,
                "preset": meta.preset,
                "channels": meta.channels,
                "scalp_channels": meta.scalp_channels,
                "sample_rate_hz": meta.sample_rate_hz,
                "raw_file": raw_file,
            }
        });
        // The declaration is written before the window is considered open,
        // so a failed write never leaves a side-file without a raw_file link.
        let writer = self.writer.as_mut().expect("checked above");
        let line = serde_json::to_string(&record).map_err(|e| e.to_string())?;
        writeln!(writer, "{}", line).map_err(|e| format!("Failed to write central_start: {e}"))?;
        writer.flush().ok();

        self.central = Some(CentralFile {
            writer: raw_writer,
            raw_file,
            last_seq: None,
            n_samples: 0,
        });
        Ok(())
    }

    /// True while a central window is open (`central_start` written, no
    /// `central_end` yet).
    pub fn central_active(&self) -> bool {
        self.central.is_some()
    }

    /// Name of the open raw side-file, if any.
    pub fn central_raw_file(&self) -> Option<&str> {
        self.central.as_ref().map(|c| c.raw_file.as_str())
    }

    /// One BLE notification's decoded samples → one raw record. Dropped
    /// silently outside the central window (they belong to no session).
    pub fn log_raw_batch(
        &mut self,
        ts: &str,
        host_mono: f64,
        seq: u64,
        eeg: &BTreeMap<String, Vec<f64>>,
        contact: Option<&BTreeMap<String, Contact>>,
    ) {
        let central = match self.central.as_mut() {
            Some(c) => c,
            None => return,
        };
        let eeg_json: serde_json::Map<String, Value> = eeg
            .iter()
            .map(|(k, v)| (k.clone(), json!(v.iter().map(|x| r2(*x)).collect::<Vec<f64>>())))
            .collect();
        let contact_json = match contact {
            Some(c) => {
                let m: serde_json::Map<String, Value> =
                    c.iter().map(|(k, v)| (k.clone(), json!(v.as_str()))).collect();
                Value::Object(m)
            }
            None => Value::Null,
        };
        let record = json!({
            "ts": ts,
            "host_mono": r3(host_mono),
            "seq": seq,
            "eeg": Value::Object(eeg_json),
            "contact": contact_json,
        });
        if let Ok(line) = serde_json::to_string(&record) {
            writeln!(central.writer, "{}", line).ok();
        }
        central.last_seq = Some(seq);
        central.n_samples += eeg.values().map(|v| v.len() as u64).max().unwrap_or(0);
    }

    /// One 1 Hz `central` record (ADR-015-7). Dropped silently outside the
    /// central window.
    pub fn log_central_tick(&mut self, ts: &str, tick: &CentralTick) {
        if self.central.is_none() {
            return;
        }
        let writer = match self.writer.as_mut() {
            Some(w) => w,
            None => return,
        };
        let record = json!({
            "type": "central",
            "ts": ts,
            "host_mono": r3(tick.host_mono),
            "central": central_tick_json(tick),
        });
        if let Ok(line) = serde_json::to_string(&record) {
            writeln!(writer, "{}", line).ok();
            writer.flush().ok();
        }
    }

    /// Close the central window: write `central_end` (final `seq` + sample
    /// count, for truncation detection) once and close the side-file.
    /// Idempotent; a no-op when no window is open.
    pub fn central_end(&mut self, host_mono: f64) {
        let mut central = match self.central.take() {
            Some(c) => c,
            None => return,
        };
        central.writer.flush().ok();
        drop(central.writer);
        if let Some(writer) = self.writer.as_mut() {
            let record = json!({
                "type": "central_end",
                "ts": Self::now_ts(),
                "host_mono": r3(host_mono),
                "final_seq": central.last_seq,
                "n_samples": central.n_samples,
            });
            if let Ok(line) = serde_json::to_string(&record) {
                writeln!(writer, "{}", line).ok();
                writer.flush().ok();
            }
        }
    }

    pub fn stop_session(&mut self) -> SessionSummary {
        // SPEC-015: session stop is one of the three closers of the central
        // window (stop, Muse disconnect, Muse link lost) — first one wins.
        if self.central.is_some() {
            let host_mono = self.host_mono_now();
            self.central_end(host_mono);
        }

        // Calculate duration
        let duration_secs = match &self.started_at {
            Some(start_ts) => {
                let now = Local::now().format("%Y-%m-%dT%H:%M:%S%.3f%:z").to_string();
                // Parse start and compute difference
                match chrono::DateTime::parse_from_str(start_ts, "%Y-%m-%dT%H:%M:%S%.3f%:z") {
                    Ok(start) => {
                        match chrono::DateTime::parse_from_str(&now, "%Y-%m-%dT%H:%M:%S%.3f%:z") {
                            Ok(end) => (end - start).num_milliseconds() as f64 / 1000.0,
                            Err(_) => 0.0,
                        }
                    }
                    Err(_) => 0.0,
                }
            }
            None => 0.0,
        };

        let file_path = self
            .session_file
            .as_ref()
            .map(|p| p.display().to_string())
            .unwrap_or_default();

        let summary = SessionSummary {
            duration_secs,
            sample_count: self.sample_count,
            file_path,
        };

        // Drop the writer to close the file
        self.writer = None;
        self.session_file = None;
        self.sample_count = 0;
        self.started_at = None;

        summary
    }

    pub fn is_active(&self) -> bool {
        self.writer.is_some()
    }
}

// ---------------------------------------------------------------------------
// Free functions
// ---------------------------------------------------------------------------

/// List all .jsonl session files, most recent first.
pub fn list_sessions(session_dir: &Path) -> Vec<SessionFileInfo> {
    let entries = match fs::read_dir(session_dir) {
        Ok(e) => e,
        Err(_) => return Vec::new(),
    };

    let mut files: Vec<SessionFileInfo> = entries
        .filter_map(|entry| {
            let entry = entry.ok()?;
            let filename = entry.file_name().to_string_lossy().to_string();
            // SPEC-015: the raw EEG side-file is not a session.
            if !filename.ends_with(".jsonl") || filename.ends_with("_eeg.jsonl") {
                return None;
            }
            let meta = entry.metadata().ok()?;
            // Extract date from filename: YYYY-MM-DD_HHMMSS.jsonl
            let date = filename.get(..10).unwrap_or("").to_string();
            Some(SessionFileInfo {
                filename,
                size_bytes: meta.len(),
                date,
            })
        })
        .collect();

    // Sort by filename descending (most recent first)
    files.sort_by(|a, b| b.filename.cmp(&a.filename));
    files
}


#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn tmp_dir(tag: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("ebs-session-test-{}-{}", tag, std::process::id()));
        let _ = fs::remove_dir_all(&d);
        fs::create_dir_all(&d).unwrap();
        d
    }

    fn lines(path: &Path) -> Vec<Value> {
        fs::read_to_string(path)
            .unwrap()
            .lines()
            .filter(|l| !l.trim().is_empty())
            .map(|l| serde_json::from_str(l).unwrap())
            .collect()
    }

    // TEST-005e — the ble_reconnect field event lands in the SAME session
    // file (no new file), with structured fields beside the note.
    #[test]
    fn structured_field_event_is_written_to_the_active_session_file() {
        let dir = tmp_dir("reconnect");
        let mut logger = SessionLogger::new(&dir);
        let path = logger.start_session("solo").unwrap();

        logger.log_field_event_with(
            "ble_reconnect",
            "link restored after 3 attempts",
            &json!({"gap_ms": 4200, "attempts": 3}),
        );

        let recs = lines(&path);
        assert_eq!(recs.len(), 2, "header + one field event");
        let ev = &recs[1];
        assert_eq!(ev["type"], json!("field_event"));
        assert_eq!(ev["event"], json!("ble_reconnect"));
        assert_eq!(ev["note"], json!("link restored after 3 attempts"));
        assert_eq!(ev["gap_ms"], json!(4200));
        assert_eq!(ev["attempts"], json!(3));
        assert!(ev["ts"].is_string());
        assert!(logger.is_active(), "a link event must not end the session");
        assert_eq!(fs::read_dir(&dir).unwrap().count(), 1, "no second file");
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn structured_field_event_cannot_override_logger_owned_keys() {
        let dir = tmp_dir("owned");
        let mut logger = SessionLogger::new(&dir);
        let path = logger.start_session("solo").unwrap();
        logger.log_field_event_with(
            "ble_link_lost",
            "watchdog",
            &json!({"type": "sample", "event": "spoof", "note": "spoof", "ts": "1970", "x": 1}),
        );
        let ev = &lines(&path)[1];
        assert_eq!(ev["type"], json!("field_event"));
        assert_eq!(ev["event"], json!("ble_link_lost"));
        assert_eq!(ev["note"], json!("watchdog"));
        assert_ne!(ev["ts"], json!("1970"));
        assert_eq!(ev["x"], json!(1));
        let _ = fs::remove_dir_all(&dir);
    }

    // TEST-14 (SPEC-015 v0.3) — a Berger cue written via log_cue is a plain
    // field_event carrying host_mono (3 dp) so it joins the central ticks by
    // the same clock as the raw side-file; logger-owned keys still win; with
    // no active session nothing is written and the call reports false.
    #[test]
    fn cue_field_event_carries_host_mono_and_refuses_without_session() {
        let dir = tmp_dir("cue-inactive");
        let mut logger = SessionLogger::new(&dir);
        assert!(!logger.log_cue("berger_cue", "settle", 1.0), "no session → false");
        assert_eq!(fs::read_dir(&dir).unwrap().count(), 0, "nothing written");
        let _ = fs::remove_dir_all(&dir);

        let dir = tmp_dir("cue-active");
        let mut logger = SessionLogger::new(&dir);
        let path = logger.start_session("solo").unwrap();
        assert!(logger.log_cue("berger_cue", "eyes_closed", 12.3456));
        let recs = lines(&path);
        assert_eq!(recs.len(), 2, "header + one field event");
        let ev = &recs[1];
        assert_eq!(ev["type"], json!("field_event"));
        assert_eq!(ev["event"], json!("berger_cue"));
        assert_eq!(ev["note"], json!("eyes_closed"));
        assert_eq!(ev["host_mono"], json!(12.346));
        assert!(ev["ts"].is_string());
        assert!(logger.is_active(), "a cue must not end the session");
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn structured_field_event_is_a_noop_without_active_session() {
        let dir = tmp_dir("inactive");
        let mut logger = SessionLogger::new(&dir);
        logger.log_field_event_with("ble_link_lost", "x", &json!({"a": 1}));
        assert_eq!(fs::read_dir(&dir).unwrap().count(), 0);
        let _ = fs::remove_dir_all(&dir);
    }

    // TEST-005h — a field event written from a tick carries THAT tick's ts, so
    // the event can never be stamped later than the sample it precedes in the
    // file (observed 2026-09-04: ble_reconnect 14:05:13.051 before sample .050;
    // the harness read a 1 ms backward clock step).
    #[test]
    fn field_event_at_uses_the_given_timestamp() {
        let dir = tmp_dir("event-at");
        let mut logger = SessionLogger::new(&dir);
        let path = logger.start_session("solo").unwrap();
        logger.log_field_event_at(
            "2026-09-04T14:05:13.050+10:00",
            "ble_reconnect",
            "n",
            &json!({"gap_ms": 1}),
        );
        let ev = &lines(&path)[1];
        assert_eq!(ev["ts"], json!("2026-09-04T14:05:13.050+10:00"));
        assert_eq!(ev["event"], json!("ble_reconnect"));
        assert_eq!(ev["gap_ms"], json!(1));
        let _ = fs::remove_dir_all(&dir);
    }

    // ───────────────────────── SPEC-015 fixtures ─────────────────────────

    use crate::eeg::{CentralTicker, Contact, CENTRAL_ALLOWLIST};
    use crate::hrv::HRVMetrics;
    use crate::hrv::phase::PhaseDynamics;
    use crate::motion::MotionState;
    use std::collections::BTreeMap;

    fn sample_inputs() -> (HRVMetrics, PhaseDynamics, MotionState) {
        let rr: Vec<u16> = (0..20).map(|i| 800 + (i % 5) * 7).collect();
        let metrics = crate::hrv::compute_hrv_metrics(&rr);
        let mut traj = crate::hrv::phase::PhaseTrajectory::new(30);
        let dynamics = traj.append(&metrics, 1.0);
        let mut mp = crate::motion::MotionProcessor::new();
        let motion = mp.update(&[[0, 0, 1000]; 50]);
        (metrics, dynamics, motion)
    }

    fn meta() -> CentralMeta {
        CentralMeta {
            device: "MuseS-TEST".into(),
            preset: "p1035".into(),
            channels: crate::eeg::CH_SCALP.iter().map(|s| s.to_string()).collect(),
            scalp_channels: crate::eeg::CH_SCALP.iter().map(|s| s.to_string()).collect(),
            sample_rate_hz: 256,
        }
    }

    fn eeg_batch(v: f64) -> BTreeMap<String, Vec<f64>> {
        crate::eeg::CH_SCALP
            .iter()
            .map(|c| (c.to_string(), vec![v, v + 0.123456, -v]))
            .collect()
    }

    fn a_tick() -> crate::eeg::CentralTick {
        let mut t = CentralTicker::new();
        for ch in 0..4 {
            let x: Vec<f64> = (0..256)
                .map(|i| 20.0 * (2.0 * std::f64::consts::PI * 10.0 * i as f64 / 256.0).sin())
                .collect();
            t.push(ch, &x);
        }
        t.close_tick(3.5)
    }

    fn side_files(dir: &Path) -> Vec<String> {
        let mut v: Vec<String> = fs::read_dir(dir)
            .unwrap()
            .filter_map(|e| e.ok().map(|e| e.file_name().to_string_lossy().to_string()))
            .filter(|n| n.ends_with("_eeg.jsonl"))
            .collect();
        v.sort();
        v
    }

    // ───────────────────────── TEST-015-5 schema ─────────────────────────

    // REQ-015-2 / ADR-015-5: every session_start declares, at 1.6.0.
    #[test]
    fn test_015_5_session_start_carries_the_declaration_at_1_6_0() {
        let dir = tmp_dir("decl");
        let mut logger = SessionLogger::new(&dir);
        logger.set_mono_epoch(std::time::Instant::now());
        let path = logger.start_session("solo").unwrap();
        let hdr = &lines(&path)[0];
        assert_eq!(hdr["type"], json!("session_start"));
        assert_eq!(hdr["schema_version"], json!("1.6.0"));
        assert_eq!(hdr["substrates"], json!(["autonomic"]));
        assert_eq!(hdr["capabilities"], json!(["hrv", "motion"]));
        let epoch = hdr["host_mono_epoch"].as_str().expect("host_mono_epoch is a string");
        let parsed = chrono::DateTime::parse_from_rfc3339(epoch).expect("RFC3339");
        let ts = chrono::DateTime::parse_from_rfc3339(hdr["ts"].as_str().unwrap()).unwrap();
        let d = (ts - parsed).num_milliseconds();
        assert!((0..5000).contains(&d), "epoch {epoch} should be just before ts (Δ {d} ms)");
        // Pre-existing keys still there.
        assert_eq!(hdr["session_type"], json!("solo"));
        assert!(hdr["note"].is_string());
        logger.stop_session();
        let _ = fs::remove_dir_all(&dir);
    }

    // REQ-015-2 (literal, ADR-015-7): the HR sample record is unchanged —
    // no key beyond ts/hr/rr/metrics/phase/motion, and the nested key sets
    // are exactly the 1.5.0 ones.
    #[test]
    fn test_015_5_hr_sample_record_shape_is_unchanged() {
        let dir = tmp_dir("sample");
        let mut logger = SessionLogger::new(&dir);
        let path = logger.start_session("solo").unwrap();
        let (m, d, mo) = sample_inputs();
        let soft2d = crate::hrv::phase::PhaseTrajectory::new(30).compute_2d_mode(m.mode_score, 0.5);
        logger.log("2026-09-11T10:00:00.000+10:00", 72, &[820, 830], &m, &d, 0.5, Some(&soft2d), &mo);
        let rec = &lines(&path)[1];
        let keys = |v: &Value| -> Vec<String> { v.as_object().unwrap().keys().cloned().collect() };
        let mut top = keys(rec);
        top.sort();
        assert_eq!(top, ["hr", "metrics", "motion", "phase", "rr", "ts"]);
        let mut metrics = keys(&rec["metrics"]);
        metrics.sort();
        assert_eq!(metrics, ["amp", "breath", "ent", "ent_label", "mode", "mode_score", "volatility"]);
        let mut phase = keys(&rec["phase"]);
        phase.sort();
        assert_eq!(
            phase,
            [
                "acceleration_mag", "coherence", "curvature", "dwell_time", "history_signature",
                "mode_status", "motion_confounded", "movement_annotation", "movement_aware_label",
                "phase_label", "position", "soft_mode", "soft_mode_2d", "stability", "velocity",
                "velocity_mag"
            ]
        );
        let mut motion = keys(&rec["motion"]);
        motion.sort();
        assert_eq!(motion, ["confounded", "mag", "n_samples", "state"]);
        assert!(rec.get("central").is_none(), "ADR-015-7: no central in the HR record");
        let _ = fs::remove_dir_all(&dir);
    }

    // ───────────────────── TEST-015-6 degradation / lifecycle ─────────────

    #[test]
    fn test_015_6_session_without_central_start_writes_no_central_and_no_side_file() {
        let dir = tmp_dir("nocentral");
        let mut logger = SessionLogger::new(&dir);
        let path = logger.start_session("solo").unwrap();
        assert!(!logger.central_active());
        // Batches and ticks with no central open are dropped silently.
        logger.log_raw_batch("t", 0.5, 1, &eeg_batch(1.0), None);
        logger.log_central_tick("t", &a_tick());
        logger.central_end(0.9);
        let (m, d, mo) = sample_inputs();
        logger.log("t", 70, &[800], &m, &d, 0.5, None, &mo);
        let summary = logger.stop_session();
        assert_eq!(summary.sample_count, 1);
        let recs = lines(&path);
        assert_eq!(recs.len(), 2, "header + one HR sample: {recs:?}");
        assert!(recs.iter().all(|r| r["type"] != json!("central")
            && r["type"] != json!("central_start")
            && r["type"] != json!("central_end")));
        assert!(side_files(&dir).is_empty(), "no dangling raw_file");
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_015_6_central_lifecycle_start_records_end_and_side_file() {
        let dir = tmp_dir("lifecycle");
        let mut logger = SessionLogger::new(&dir);
        let path = logger.start_session("solo").unwrap();
        let stem = path.file_stem().unwrap().to_string_lossy().to_string();

        // Before central_start: dropped.
        logger.log_raw_batch("t0", 0.1, 7, &eeg_batch(1.0), None);
        logger.log_central_tick("t0", &a_tick());

        logger.central_start(meta(), 1.204).unwrap();
        assert!(logger.central_active());
        // Idempotent while open.
        logger.central_start(meta(), 1.9).unwrap();

        let mut contact = BTreeMap::new();
        for c in crate::eeg::CH_SCALP {
            contact.insert(c.to_string(), Contact::Good);
        }
        logger.log_raw_batch("t1", 1.3, 1040, &eeg_batch(12.345678), None);
        logger.log_raw_batch("t2", 1.4, 1041, &eeg_batch(-3.0), Some(&contact));
        logger.log_central_tick("t3", &a_tick());

        logger.central_end(2.5);
        assert!(!logger.central_active());
        logger.central_end(2.6); // idempotent
        // After central_end: dropped.
        logger.log_raw_batch("t4", 2.7, 1042, &eeg_batch(1.0), None);
        logger.log_central_tick("t4", &a_tick());
        assert!(logger.is_active(), "central_end does not end the session");
        logger.stop_session();

        let recs = lines(&path);
        let types: Vec<String> = recs.iter().map(|r| r["type"].as_str().unwrap_or("sample").to_string()).collect();
        assert_eq!(types, ["session_start", "central_start", "central", "central_end"], "{types:?}");

        let cs = &recs[1];
        assert_eq!(cs["host_mono"], json!(1.204));
        assert!(cs["ts"].is_string());
        assert_eq!(cs["substrates_add"], json!(["central"]));
        assert_eq!(cs["capabilities_add"], json!(["eeg_raw", "eeg_bands"]));
        let cm = &cs["central_meta"];
        assert_eq!(cm["device"], json!("MuseS-TEST"));
        assert_eq!(cm["preset"], json!("p1035"));
        assert_eq!(cm["channels"], json!(["TP9", "AF7", "AF8", "TP10"]));
        assert_eq!(cm["scalp_channels"], json!(["TP9", "AF7", "AF8", "TP10"]));
        assert_eq!(cm["sample_rate_hz"], json!(256));
        assert_eq!(cm["raw_file"], json!(format!("{stem}_eeg.jsonl")));
        let mut cm_keys: Vec<&String> = cm.as_object().unwrap().keys().collect();
        cm_keys.sort();
        assert_eq!(cm_keys, ["channels", "device", "preset", "raw_file", "sample_rate_hz", "scalp_channels"]);

        let tick = &recs[2];
        assert_eq!(tick["ts"], json!("t3"));
        assert_eq!(tick["host_mono"], json!(3.5));
        let central = tick["central"].as_object().unwrap();
        let mut keys: Vec<&str> = central.keys().map(String::as_str).collect();
        keys.sort();
        let mut allow: Vec<&str> = CENTRAL_ALLOWLIST.to_vec();
        allow.sort();
        assert_eq!(keys, allow, "TEST-015-8 on the tick the logger actually writes");
        assert!(central["central_phase"].is_null());
        assert_eq!(central["contact"]["TP9"], json!("good"));

        let end = &recs[3];
        assert_eq!(end["host_mono"], json!(2.5));
        assert_eq!(end["final_seq"], json!(1041));
        assert_eq!(end["n_samples"], json!(6), "3 samples/channel × 2 batches");
        assert!(end["ts"].is_string());

        // The raw side-file, beside the session file, with the declared name.
        let side = side_files(&dir);
        assert_eq!(side, [format!("{stem}_eeg.jsonl")]);
        let raw = lines(&dir.join(&side[0]));
        assert_eq!(raw.len(), 2, "only batches inside the window: {raw:?}");
        assert_eq!(raw[0]["ts"], json!("t1"));
        assert_eq!(raw[0]["host_mono"], json!(1.3));
        assert_eq!(raw[0]["seq"], json!(1040));
        assert_eq!(raw[0]["eeg"]["TP9"], json!([12.35, 12.47, -12.35]), "µV at 2 dp");
        assert!(raw[0]["contact"].is_null(), "first second of a link: contact null");
        assert_eq!(raw[1]["contact"]["AF7"], json!("good"));
        let mut rkeys: Vec<&String> = raw[1].as_object().unwrap().keys().collect();
        rkeys.sort();
        assert_eq!(rkeys, ["contact", "eeg", "host_mono", "seq", "ts"]);
        // Truncation check agrees with the consumer helper.
        assert!(crate::eeg::raw_file_complete(raw.last().unwrap()["seq"].as_u64(), end));
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_015_6_stop_session_closes_an_open_central_first() {
        let dir = tmp_dir("stopcloses");
        let mut logger = SessionLogger::new(&dir);
        logger.set_mono_epoch(std::time::Instant::now());
        let path = logger.start_session("solo").unwrap();
        logger.central_start(meta(), 0.5).unwrap();
        logger.log_raw_batch("t", 0.6, 9, &eeg_batch(1.0), None);
        logger.log_raw_batch("t", 0.7, 10, &eeg_batch(1.0), None);
        logger.stop_session();
        assert!(!logger.central_active());
        let recs = lines(&path);
        let last = recs.last().unwrap();
        assert_eq!(last["type"], json!("central_end"));
        assert_eq!(last["final_seq"], json!(10));
        assert_eq!(last["n_samples"], json!(6));
        assert!(last["host_mono"].as_f64().unwrap() >= 0.0);
        // Nothing written after stop.
        logger.central_end(9.0);
        logger.log_raw_batch("t", 9.1, 11, &eeg_batch(1.0), None);
        assert_eq!(lines(&path).len(), recs.len());
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_015_6_central_start_without_session_is_a_noop() {
        let dir = tmp_dir("nosession");
        let mut logger = SessionLogger::new(&dir);
        assert!(logger.central_start(meta(), 0.1).is_ok());
        assert!(!logger.central_active());
        logger.log_raw_batch("t", 0.2, 1, &eeg_batch(1.0), None);
        logger.central_end(0.3);
        assert_eq!(fs::read_dir(&dir).unwrap().count(), 0, "no files at all");
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_015_6_central_end_with_no_packets_declares_null_final_seq() {
        let dir = tmp_dir("nopackets");
        let mut logger = SessionLogger::new(&dir);
        let path = logger.start_session("solo").unwrap();
        logger.central_start(meta(), 0.5).unwrap();
        logger.central_end(0.8);
        let end = lines(&path).last().unwrap().clone();
        assert_eq!(end["type"], json!("central_end"));
        assert!(end["final_seq"].is_null());
        assert_eq!(end["n_samples"], json!(0));
        assert!(crate::eeg::raw_file_complete(None, &end));
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn raw_side_files_are_not_listed_as_sessions() {
        let dir = tmp_dir("listing");
        let mut logger = SessionLogger::new(&dir);
        logger.start_session("solo").unwrap();
        logger.central_start(meta(), 0.5).unwrap();
        logger.stop_session();
        assert_eq!(side_files(&dir).len(), 1);
        let listed = list_sessions(&dir);
        assert_eq!(listed.len(), 1);
        assert!(!listed[0].filename.ends_with("_eeg.jsonl"));
        let _ = fs::remove_dir_all(&dir);
    }

    /// Codex review 2026-09-11 (high): a Muse reconnect inside one session
    /// must open a NEW side-file; the first window's data must survive.
    #[test]
    fn test_central_reconnect_within_session_preserves_earlier_window() {
        let dir = tmp_dir("reconnect");
        let mut logger = SessionLogger::new(&dir);
        logger.start_session("solo").unwrap();
        let meta = || CentralMeta {
            device: "MuseS-TEST".into(), preset: "p1035".into(),
            channels: vec!["TP9".into()], scalp_channels: vec!["TP9".into()], sample_rate_hz: 256,
        };
        let mut eeg = BTreeMap::new();
        eeg.insert("TP9".to_string(), vec![1.0, 2.0]);

        logger.central_start(meta(), 1.0).unwrap();
        logger.log_raw_batch("t1", 1.1, 1, &eeg, None);
        logger.central_end(2.0);
        logger.central_start(meta(), 3.0).unwrap();
        logger.log_raw_batch("t2", 3.1, 7, &eeg, None);
        logger.central_end(4.0);
        let session_path = logger.session_file.clone().unwrap();
        logger.stop_session();

        let stem = session_path.file_stem().unwrap().to_string_lossy().to_string();
        let first = fs::read_to_string(dir.join(format!("{stem}_eeg.jsonl"))).unwrap();
        let second = fs::read_to_string(dir.join(format!("{stem}_eeg_2.jsonl"))).unwrap();
        assert!(first.contains("\"seq\":1"), "first window truncated: {first}");
        assert!(second.contains("\"seq\":7"));
        assert!(!second.contains("\"seq\":1,"));

        let log = fs::read_to_string(&session_path).unwrap();
        let starts: Vec<Value> = log.lines().map(|l| serde_json::from_str(l).unwrap())
            .filter(|v: &Value| v["type"] == "central_start").collect();
        assert_eq!(starts.len(), 2);
        assert_eq!(starts[0]["central_meta"]["raw_file"], json!(format!("{stem}_eeg.jsonl")));
        assert_eq!(starts[1]["central_meta"]["raw_file"], json!(format!("{stem}_eeg_2.jsonl")));
        let ends = log.lines().filter(|l| l.contains("\"type\":\"central_end\"")).count();
        assert_eq!(ends, 2);
    }
}
