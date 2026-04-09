//! Phase-space trajectory tracking for HRV analysis.
//!
//! Ported from `src/processing/phase.py`. Maps HRV metrics into a 3D phase
//! space (entrainment, breath_norm, amplitude_norm) and tracks dynamics —
//! velocity, curvature, stability, history signature — over a rolling window.

use std::collections::VecDeque;

use serde::Serialize;

use super::HRVMetrics;
use super::movement::{
    ModeHistory, SoftModeInference, compose_movement_aware_label,
    compute_soft_mode_membership, detect_mode_with_hysteresis,
    generate_movement_annotation,
};

// ---------------------------------------------------------------------------
// Data structures
// ---------------------------------------------------------------------------

/// A single snapshot in the 3D phase space.
#[derive(Debug, Clone)]
pub struct PhaseState {
    pub timestamp: f64,
    /// [entrainment, breath_norm, amplitude_norm]
    pub position: [f64; 3],
}

/// Full dynamics output for one time-step.
#[derive(Debug, Clone, Serialize)]
pub struct PhaseDynamics {
    pub timestamp: f64,
    pub position: [f64; 3],
    pub velocity: [f64; 3],
    pub velocity_magnitude: f64,
    pub curvature: f64,
    pub stability: f64,
    pub transition_proximity: f64,
    pub history_signature: f64,
    pub phase_label: String,
    pub mode_score: f64,
    pub soft_mode: Option<SoftModeInference>,
    pub movement_annotation: String,
    pub movement_aware_label: String,
    pub mode_status: String,
    pub dwell_time: f64,
    pub mode_score_acceleration: f64,
}

// ---------------------------------------------------------------------------
// PhaseTrajectory — rolling buffer with dynamics computation
// ---------------------------------------------------------------------------

pub struct PhaseTrajectory {
    states: VecDeque<PhaseState>,
    window_size: usize,
    cumulative_path_length: f64,
    last_velocity: [f64; 3],
    mode_history: ModeHistory,
    last_soft_inference: Option<SoftModeInference>,
    last_mode_score: f64,
    mode_score_velocity: f64,
}

impl PhaseTrajectory {
    pub fn new(window_size: usize) -> Self {
        Self {
            states: VecDeque::with_capacity(window_size),
            window_size,
            cumulative_path_length: 0.0,
            last_velocity: [0.0; 3],
            mode_history: ModeHistory::new(100),
            last_soft_inference: None,
            last_mode_score: 0.0,
            mode_score_velocity: 0.0,
        }
    }

    pub fn append(&mut self, metrics: &HRVMetrics, timestamp: f64) -> PhaseDynamics {
        let position = Self::metrics_to_position(metrics);
        let new_state = PhaseState { timestamp, position };
        let dynamics = self.compute_dynamics(&new_state, metrics);

        if let Some(prev) = self.states.back() {
            self.cumulative_path_length +=
                euclidean_distance(&prev.position, &new_state.position);
        }

        if self.states.len() >= self.window_size {
            self.states.pop_front();
        }
        self.states.push_back(new_state);

        dynamics
    }

    pub fn metrics_to_position(m: &HRVMetrics) -> [f64; 3] {
        let entrainment = m.entrainment;
        let breath_norm = match m.breath_rate {
            Some(rate) => ((rate - 4.0) / 16.0).clamp(0.0, 1.0),
            None => 0.5,
        };
        let amplitude_norm = (m.amplitude as f64 / 200.0).min(1.0);
        [entrainment, breath_norm, amplitude_norm]
    }

    fn compute_dynamics(
        &mut self,
        new_state: &PhaseState,
        metrics: &HRVMetrics,
    ) -> PhaseDynamics {
        let amp_norm = (metrics.amplitude as f64 / 200.0).min(1.0);

        // Soft mode — always computed
        let soft_mode = compute_soft_mode_membership(
            metrics.entrainment,
            metrics.breath_steady,
            amp_norm,
            metrics.rr_volatility,
            0.2, // temperature
            self.last_soft_inference.as_ref(),
        );

        if self.states.len() < 2 {
            // Warming up — not enough history for derivatives
            let (detected_mode, _confidence, meta) = detect_mode_with_hysteresis(
                &soft_mode,
                &mut self.mode_history,
                new_state.timestamp,
            );

            let previous_mode = meta.get("previous_mode").map(|s| s.as_str());
            let dwell_time: f64 = meta
                .get("dwell_time")
                .and_then(|s| s.parse().ok())
                .unwrap_or(0.0);
            let mode_status = meta
                .get("state_status")
                .cloned()
                .unwrap_or_else(|| "unknown".to_string());

            let movement_annotation = generate_movement_annotation(
                None, // no velocity yet
                None,
                previous_mode,
                dwell_time,
            );

            let movement_aware_label =
                compose_movement_aware_label(&detected_mode, &movement_annotation);

            self.mode_history
                .append(&detected_mode, soft_mode.membership[&soft_mode.primary_mode], new_state.timestamp);
            self.last_soft_inference = Some(soft_mode.clone());
            self.last_mode_score = metrics.mode_score;

            return PhaseDynamics {
                timestamp: new_state.timestamp,
                position: new_state.position,
                velocity: [0.0; 3],
                velocity_magnitude: 0.0,
                curvature: 0.0,
                stability: 0.5,
                transition_proximity: 0.0,
                history_signature: 0.0,
                phase_label: "warming up".to_string(),
                mode_score: metrics.mode_score,
                soft_mode: Some(soft_mode),
                movement_annotation,
                movement_aware_label,
                mode_status,
                dwell_time: 0.0,
                mode_score_acceleration: 0.0,
            };
        }

        // --- Velocity (finite difference) ---
        let prev = &self.states[self.states.len() - 1];
        let dt = (new_state.timestamp - prev.timestamp).max(0.001);

        let velocity = [
            (new_state.position[0] - prev.position[0]) / dt,
            (new_state.position[1] - prev.position[1]) / dt,
            (new_state.position[2] - prev.position[2]) / dt,
        ];
        let velocity_mag = vector_magnitude(&velocity);

        // --- Curvature (magnitude of acceleration) ---
        let acceleration = [
            (velocity[0] - self.last_velocity[0]) / dt,
            (velocity[1] - self.last_velocity[1]) / dt,
            (velocity[2] - self.last_velocity[2]) / dt,
        ];
        let curvature = vector_magnitude(&acceleration);

        // --- Stability ---
        let stability =
            (1.0 / (1.0 + (velocity_mag + curvature * 0.5) * 2.0)).clamp(0.0, 1.0);

        // --- History signature (rolling window only — RAA-EBS-001 fix) ---
        let history_signature = self.compute_rolling_path_signature(new_state);

        // --- Phase label ---
        let phase_label = infer_phase_label(
            &new_state.position,
            velocity_mag,
            curvature,
            stability,
        );

        let transition_proximity = 1.0 - stability;

        // --- Mode dynamics ---
        let (detected_mode, _confidence, meta) = detect_mode_with_hysteresis(
            &soft_mode,
            &mut self.mode_history,
            new_state.timestamp,
        );

        let previous_mode = meta.get("previous_mode").map(|s| s.as_str());
        let dwell_time: f64 = meta
            .get("dwell_time")
            .and_then(|s| s.parse().ok())
            .unwrap_or(0.0);
        let mode_status = meta
            .get("state_status")
            .cloned()
            .unwrap_or_else(|| "unknown".to_string());

        // --- Mode score acceleration ---
        let prev_mode_score_velocity = self.mode_score_velocity;
        self.mode_score_velocity = (metrics.mode_score - self.last_mode_score) / dt;
        let mode_score_accel =
            ((self.mode_score_velocity - prev_mode_score_velocity) / dt).abs();

        // --- Movement annotation ---
        let movement_annotation = generate_movement_annotation(
            Some(self.mode_score_velocity.abs()),
            Some(mode_score_accel),
            previous_mode,
            dwell_time,
        );

        let movement_aware_label =
            compose_movement_aware_label(&detected_mode, &movement_annotation);

        // --- Update internal state ---
        self.mode_history
            .append(&detected_mode, _confidence, new_state.timestamp);
        self.last_velocity = velocity;
        self.last_soft_inference = Some(soft_mode.clone());
        self.last_mode_score = metrics.mode_score;

        PhaseDynamics {
            timestamp: new_state.timestamp,
            position: new_state.position,
            velocity,
            velocity_magnitude: velocity_mag,
            curvature,
            stability,
            transition_proximity,
            history_signature,
            phase_label,
            mode_score: metrics.mode_score,
            soft_mode: Some(soft_mode),
            movement_annotation,
            movement_aware_label,
            mode_status,
            dwell_time,
            mode_score_acceleration: mode_score_accel,
        }
    }

    fn compute_rolling_path_signature(&self, new_state: &PhaseState) -> f64 {
        if self.states.len() < 2 {
            return 0.0;
        }
        let mut path_length = 0.0;
        for i in 1..self.states.len() {
            path_length += euclidean_distance(
                &self.states[i - 1].position,
                &self.states[i].position,
            );
        }
        if let Some(last) = self.states.back() {
            path_length += euclidean_distance(&last.position, &new_state.position);
        }
        let window_time =
            (new_state.timestamp - self.states[0].timestamp).max(0.001);
        ((path_length / window_time) / 0.5).min(1.0)
    }

    pub fn compute_trajectory_coherence(&self, lag: usize) -> f64 {
        if self.states.len() < lag + 2 {
            return 0.0;
        }

        let n = self.states.len() - 1;
        let mut vel_mags: Vec<f64> = Vec::with_capacity(n);
        let mut vel_dirs: Vec<[f64; 3]> = Vec::with_capacity(n);

        for i in 0..n {
            let dt = (self.states[i + 1].timestamp - self.states[i].timestamp)
                .max(0.001);
            let v = [
                (self.states[i + 1].position[0] - self.states[i].position[0]) / dt,
                (self.states[i + 1].position[1] - self.states[i].position[1]) / dt,
                (self.states[i + 1].position[2] - self.states[i].position[2]) / dt,
            ];
            vel_mags.push(vector_magnitude(&v));
            vel_dirs.push(v);
        }

        let mean_mag: f64 = vel_mags.iter().sum::<f64>() / vel_mags.len() as f64;
        let variance: f64 = vel_mags
            .iter()
            .map(|m| (m - mean_mag).powi(2))
            .sum::<f64>()
            / vel_mags.len() as f64;

        if variance < 1e-10 {
            return 0.8;
        }

        // Autocorrelation with n as denominator
        let autocorr = {
            let mut num = 0.0;
            for i in 0..(vel_mags.len() - lag) {
                num += (vel_mags[i] - mean_mag) * (vel_mags[i + lag] - mean_mag);
            }
            num / (vel_mags.len() as f64 * variance)
        };

        // Direction consistency via cosine similarity
        let direction_coherence = {
            let mut cos_sum = 0.0;
            let mut count = 0usize;
            for i in 0..(vel_dirs.len() - lag) {
                let a = &vel_dirs[i];
                let b = &vel_dirs[i + lag];
                let mag_a = vector_magnitude(a);
                let mag_b = vector_magnitude(b);
                if mag_a > 1e-10 && mag_b > 1e-10 {
                    let dot = a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
                    cos_sum += (dot / (mag_a * mag_b) + 1.0) / 2.0;
                    count += 1;
                }
            }
            if count == 0 { 0.5 } else { cos_sum / count as f64 }
        };

        let coherence = 0.5 * autocorr.max(0.0) + 0.5 * direction_coherence;
        coherence.clamp(0.0, 1.0)
    }

    pub fn reset(&mut self) {
        self.states.clear();
        self.cumulative_path_length = 0.0;
        self.last_velocity = [0.0; 3];
        self.mode_history = ModeHistory::new(100);
        self.last_soft_inference = None;
        self.last_mode_score = 0.0;
        self.mode_score_velocity = 0.0;
    }
}

// ---------------------------------------------------------------------------
// Phase label inference
// ---------------------------------------------------------------------------

fn infer_phase_label(
    position: &[f64; 3],
    velocity_mag: f64,
    curvature: f64,
    stability: f64,
) -> String {
    let ent = position[0];

    if stability > 0.7 && ent > 0.6 {
        "entrained dwelling".to_string()
    } else if curvature > 0.3 && ent > 0.5 {
        "inflection (from entrainment)".to_string()
    } else if curvature > 0.3 {
        "inflection (seeking)".to_string()
    } else if velocity_mag > 0.1 && ent > 0.5 {
        "flowing (entrained)".to_string()
    } else if velocity_mag > 0.1 {
        "active transition".to_string()
    } else if stability > 0.6 && ent > 0.5 {
        "settling into entrainment".to_string()
    } else if stability > 0.6 && ent > 0.3 {
        "neutral dwelling".to_string()
    } else if stability > 0.6 {
        "alert stillness".to_string()
    } else {
        "transitional".to_string()
    }
}

// ---------------------------------------------------------------------------
// Helper functions
// ---------------------------------------------------------------------------

pub fn euclidean_distance(p1: &[f64; 3], p2: &[f64; 3]) -> f64 {
    let dx = p1[0] - p2[0];
    let dy = p1[1] - p2[1];
    let dz = p1[2] - p2[2];
    (dx * dx + dy * dy + dz * dz).sqrt()
}

pub fn vector_magnitude(v: &[f64; 3]) -> f64 {
    (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]).sqrt()
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::hrv::compute_hrv_metrics;

    fn make_metrics(
        entrainment: f64,
        breath_rate: Option<f64>,
        amplitude: u16,
        mode_score: f64,
    ) -> HRVMetrics {
        HRVMetrics {
            mean_rr: 800.0,
            min_rr: 750,
            max_rr: 750 + amplitude,
            amplitude,
            entrainment,
            entrainment_label: "[low]".to_string(),
            breath_rate,
            breath_steady: true,
            rr_volatility: 0.03,
            mode_label: "transitional".to_string(),
            mode_score,
        }
    }

    #[test]
    fn test_metrics_to_position() {
        let m = make_metrics(0.8, Some(12.0), 100, 0.5);
        let pos = PhaseTrajectory::metrics_to_position(&m);
        assert!((pos[0] - 0.8).abs() < 1e-9);
        assert!((pos[1] - 0.5).abs() < 1e-9); // (12-4)/16
        assert!((pos[2] - 0.5).abs() < 1e-9); // 100/200

        let m2 = make_metrics(0.3, None, 250, 0.0);
        let pos2 = PhaseTrajectory::metrics_to_position(&m2);
        assert!((pos2[1] - 0.5).abs() < 1e-9); // None -> 0.5
        assert!((pos2[2] - 1.0).abs() < 1e-9); // clamped
    }

    #[test]
    fn test_phase_trajectory_warmup() {
        let mut traj = PhaseTrajectory::new(30);
        let m = make_metrics(0.5, Some(10.0), 80, 0.4);
        let d1 = traj.append(&m, 1.0);
        assert_eq!(d1.phase_label, "warming up");
        let d2 = traj.append(&m, 2.0);
        assert_eq!(d2.phase_label, "warming up");
        // Third has 2 states in buffer — real label
        let d3 = traj.append(&m, 3.0);
        assert_ne!(d3.phase_label, "warming up");
    }

    #[test]
    fn test_velocity_computation() {
        let mut traj = PhaseTrajectory::new(30);
        let m1 = make_metrics(0.0, Some(4.0), 0, 0.0);
        traj.append(&m1, 0.0);
        traj.append(&m1, 1.0);
        let m2 = make_metrics(0.5, Some(4.0), 0, 0.0);
        let d = traj.append(&m2, 2.0);
        assert!(
            (d.velocity[0] - 0.5).abs() < 1e-6,
            "expected 0.5, got {}",
            d.velocity[0]
        );
    }

    #[test]
    fn test_stability_high_when_still() {
        let mut traj = PhaseTrajectory::new(30);
        let m = make_metrics(0.7, Some(10.0), 100, 0.5);
        for i in 0..10 {
            traj.append(&m, i as f64);
        }
        let d = traj.append(&m, 10.0);
        assert!(d.stability > 0.9, "got {}", d.stability);
    }

    #[test]
    fn test_coherence_insufficient_data() {
        let traj = PhaseTrajectory::new(30);
        assert!((traj.compute_trajectory_coherence(1)).abs() < 1e-9);
    }

    #[test]
    fn test_phase_labels() {
        assert_eq!(infer_phase_label(&[0.8, 0.5, 0.5], 0.0, 0.0, 0.9), "entrained dwelling");
        assert_eq!(infer_phase_label(&[0.6, 0.5, 0.5], 0.0, 0.5, 0.3), "inflection (from entrainment)");
        assert_eq!(infer_phase_label(&[0.3, 0.5, 0.5], 0.0, 0.5, 0.3), "inflection (seeking)");
        assert_eq!(infer_phase_label(&[0.6, 0.5, 0.5], 0.2, 0.1, 0.3), "flowing (entrained)");
        assert_eq!(infer_phase_label(&[0.3, 0.5, 0.5], 0.2, 0.1, 0.3), "active transition");
        assert_eq!(infer_phase_label(&[0.6, 0.5, 0.5], 0.05, 0.1, 0.65), "settling into entrainment");
        assert_eq!(infer_phase_label(&[0.4, 0.5, 0.5], 0.05, 0.1, 0.65), "neutral dwelling");
        assert_eq!(infer_phase_label(&[0.2, 0.5, 0.5], 0.05, 0.1, 0.65), "alert stillness");
        assert_eq!(infer_phase_label(&[0.4, 0.5, 0.5], 0.05, 0.1, 0.5), "transitional");
    }
}
