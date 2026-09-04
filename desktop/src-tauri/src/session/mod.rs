//! JSONL session logger for EarthianBioSense.
//!
//! Writes one JSON object per line to timestamped session files.
//! Format matches the Python `session_logger.py` output exactly
//! so downstream tools (viz, replay, analysis) work unchanged.

use serde::Serialize;
use serde_json::{json, Value};
use std::fs::{self, File};
use std::io::{BufWriter, Write};
use std::path::{Path, PathBuf};
use std::time::SystemTime;

use chrono::Local;

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
        }
    }

    pub fn start_session(&mut self, session_type: &str) -> Result<PathBuf, String> {
        let now = Local::now();
        let ts = now.format("%Y-%m-%dT%H:%M:%S%.3f%:z").to_string();
        let filename = now.format("%Y-%m-%d_%H%M%S.jsonl").to_string();
        let path = self.session_dir.join(&filename);

        let file = File::create(&path)
            .map_err(|e| format!("Failed to create session file: {e}"))?;
        let mut writer = BufWriter::new(file);

        let mut header = json!({
            "type": "session_start",
            "ts": ts,
            // 1.5.0: additive phase.soft_mode_2d (stillness × coherence membership).
            // Rust lineage is independent of Python's (see Python schema.py note).
            "schema_version": "1.5.0",
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
        let writer = match self.writer.as_mut() {
            Some(w) => w,
            None => return,
        };

        let ts = Local::now().format("%Y-%m-%dT%H:%M:%S%.3f%:z").to_string();
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

    pub fn stop_session(&mut self) -> SessionSummary {
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
            if !filename.ends_with(".jsonl") {
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

    #[test]
    fn structured_field_event_is_a_noop_without_active_session() {
        let dir = tmp_dir("inactive");
        let mut logger = SessionLogger::new(&dir);
        logger.log_field_event_with("ble_link_lost", "x", &json!({"a": 1}));
        assert_eq!(fs::read_dir(&dir).unwrap().count(), 0);
        let _ = fs::remove_dir_all(&dir);
    }
}
