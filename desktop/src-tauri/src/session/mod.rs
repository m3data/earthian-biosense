//! JSONL session logger for EarthianBioSense.
//!
//! Writes one JSON object per line to timestamped session files.
//! Format matches the Python `session_logger.py` output exactly
//! so downstream tools (viz, replay, analysis) work unchanged.

use serde::Serialize;
use serde_json::json;
use std::fs::{self, File};
use std::io::{BufWriter, Write};
use std::path::{Path, PathBuf};

use chrono::Local;

use crate::hrv::HRVMetrics;
use crate::hrv::phase::PhaseDynamics;

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
        let ts = now.format("%Y-%m-%dT%H:%M:%S%.3f").to_string();
        let filename = now.format("%Y-%m-%d_%H%M%S.jsonl").to_string();
        let path = self.session_dir.join(&filename);

        let file = File::create(&path)
            .map_err(|e| format!("Failed to create session file: {e}"))?;
        let mut writer = BufWriter::new(file);

        let header = json!({
            "type": "session_start",
            "ts": ts,
            "schema_version": "1.1.0",
            "session_type": session_type,
            "note": "ent=entrainment (breath-heart sync), coherence=trajectory integrity"
        });

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
    ) {
        let writer = match self.writer.as_mut() {
            Some(w) => w,
            None => return,
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
                "soft_mode": soft_mode_json
            }
        });

        if let Ok(line) = serde_json::to_string(&record) {
            writeln!(writer, "{}", line).ok();
            writer.flush().ok();
        }

        self.sample_count += 1;
    }

    pub fn log_field_event(&mut self, event: &str, note: &str) {
        let writer = match self.writer.as_mut() {
            Some(w) => w,
            None => return,
        };

        let ts = Local::now().format("%Y-%m-%dT%H:%M:%S%.3f").to_string();
        let record = json!({
            "type": "field_event",
            "ts": ts,
            "event": event,
            "note": note
        });

        if let Ok(line) = serde_json::to_string(&record) {
            writeln!(writer, "{}", line).ok();
            writer.flush().ok();
        }
    }

    pub fn stop_session(&mut self) -> SessionSummary {
        // Calculate duration
        let duration_secs = match &self.started_at {
            Some(start_ts) => {
                let now = Local::now().format("%Y-%m-%dT%H:%M:%S%.3f").to_string();
                // Parse start and compute difference
                match chrono::NaiveDateTime::parse_from_str(start_ts, "%Y-%m-%dT%H:%M:%S%.3f") {
                    Ok(start) => {
                        match chrono::NaiveDateTime::parse_from_str(&now, "%Y-%m-%dT%H:%M:%S%.3f") {
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
