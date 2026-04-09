//! Movement-preserving classification for EarthianBioSense.
//!
//! Implements soft membership, hysteresis-aware state transitions,
//! and movement annotation. The key insight: threshold cuts discard movement.
//! "Heightened alertness from settling" is fundamentally different from
//! "heightened alertness from threat capture" but hard thresholds give them
//! the same label.
//!
//! Ported from `src/processing/movement.py` (v1.1.0).

use serde::Serialize;
use std::collections::HashMap;

// =============================================================================
// Constants
// =============================================================================

/// Feature order: [entrainment, breath_steady_score, amp_norm, inverse_volatility]
const FEATURE_WEIGHTS: [f64; 4] = [0.4, 0.3, 0.2, 0.1];

/// Mode names in canonical order (used as index into centroid arrays).
const MODE_NAMES: [&str; 6] = [
    "heightened alertness",
    "subtle alertness",
    "transitional",
    "settling",
    "rhythmic settling",
    "settled presence",
];

/// Centroid feature vectors, same order as [`MODE_NAMES`].
/// Each row: [entrainment, breath_steady_score, amp_norm, inverse_volatility].
const MODE_CENTROID_VALUES: [[f64; 4]; 6] = [
    [0.1, 0.3, 0.2, 0.2],   // heightened alertness
    [0.25, 0.3, 0.35, 0.4],  // subtle alertness
    [0.4, 0.3, 0.45, 0.6],   // transitional
    [0.55, 1.0, 0.55, 0.75], // settling
    [0.65, 1.0, 0.65, 0.85], // rhythmic settling
    [0.8, 1.0, 0.75, 0.95],  // settled presence
];

/// Movement annotation thresholds.
const VELOCITY_THRESHOLD: f64 = 0.03;
const ACCELERATION_THRESHOLD: f64 = 0.01;
const SETTLED_THRESHOLD: f64 = 5.0;
const RECENT_TRANSITION_WINDOW: f64 = 3.0;

/// Rupture oscillation detection.
const OSCILLATION_WINDOW: usize = 10;
const MIN_OSCILLATION_TRANSITIONS: usize = 4;

// =============================================================================
// Data Structures
// =============================================================================

/// Weighted membership across modes.
///
/// Replaces hard thresholds with probability-like weights. State changes
/// are inferred from distribution shifts, not single threshold crossings.
#[derive(Debug, Clone, Serialize)]
pub struct SoftModeInference {
    /// Mode name -> weight, all values sum to 1.0.
    pub membership: HashMap<String, f64>,
    /// Mode with highest membership weight.
    pub primary_mode: String,
    /// Mode with second-highest weight (if within margin).
    pub secondary_mode: Option<String>,
    /// 1 - (max_weight - second_weight). High = uncertain.
    pub ambiguity: f64,
    /// KL divergence from previous timestep (if available).
    pub distribution_shift: Option<f64>,
}

/// Per-mode entry/exit threshold configuration.
///
/// Entry thresholds are lower than exit thresholds, making it easier
/// to enter a state than to leave it.
#[derive(Debug, Clone)]
pub struct HysteresisConfig {
    pub mode_name: String,
    pub entry_threshold: f64,
    pub exit_threshold: f64,
    pub provisional_samples: u32,
    pub established_samples: u32,
    pub entry_penalty: f64,
    pub settled_bonus: f64,
}

impl Default for HysteresisConfig {
    fn default() -> Self {
        Self {
            mode_name: "unknown".to_string(),
            entry_threshold: 0.3,
            exit_threshold: 0.4,
            provisional_samples: 3,
            established_samples: 10,
            entry_penalty: 0.7,
            settled_bonus: 1.1,
        }
    }
}

impl HysteresisConfig {
    fn new(mode_name: &str) -> Self {
        Self {
            mode_name: mode_name.to_string(),
            ..Default::default()
        }
    }
}

/// Tracks mode sequence for hysteresis-aware detection.
#[derive(Debug, Clone)]
pub struct ModeHistory {
    max_history: usize,
    history: Vec<(f64, String, f64)>,
    current_mode: Option<String>,
    previous_mode: Option<String>,
    mode_entry_time: f64,
    transition_count: u32,
    state_status: String,
    provisional_since: f64,
}

impl ModeHistory {
    pub fn new(max_history: usize) -> Self {
        Self {
            max_history,
            history: Vec::new(),
            current_mode: None,
            previous_mode: None,
            mode_entry_time: 0.0,
            transition_count: 0,
            state_status: "unknown".to_string(),
            provisional_since: 0.0,
        }
    }

    pub fn append(&mut self, mode: &str, confidence: f64, timestamp: f64) {
        if let Some(ref current) = self.current_mode {
            if mode != current {
                self.previous_mode = Some(current.clone());
                self.mode_entry_time = timestamp;
                self.transition_count += 1;
                self.state_status = "unknown".to_string();
            }
        } else {
            self.mode_entry_time = timestamp;
        }

        self.current_mode = Some(mode.to_string());
        self.history.push((timestamp, mode.to_string(), confidence));

        if self.history.len() > self.max_history {
            let start = self.history.len() - self.max_history;
            self.history = self.history[start..].to_vec();
        }
    }

    pub fn get_current_mode(&self) -> Option<&str> {
        self.current_mode.as_deref()
    }

    pub fn get_previous_mode(&self) -> Option<&str> {
        self.previous_mode.as_deref()
    }

    pub fn get_dwell_time(&self, current_timestamp: f64) -> f64 {
        if self.current_mode.is_none() {
            return 0.0;
        }
        current_timestamp - self.mode_entry_time
    }

    pub fn get_transition_count(&self) -> u32 {
        self.transition_count
    }

    pub fn get_mode_sequence(&self, n: Option<usize>) -> Vec<&str> {
        match n {
            Some(n) => {
                let start = self.history.len().saturating_sub(n);
                self.history[start..]
                    .iter()
                    .map(|(_, mode, _)| mode.as_str())
                    .collect()
            }
            None => self.history.iter().map(|(_, mode, _)| mode.as_str()).collect(),
        }
    }

    pub fn get_state_status(&self) -> &str {
        &self.state_status
    }

    pub fn set_state_status(&mut self, status: &str, timestamp: f64) {
        assert!(
            matches!(status, "unknown" | "provisional" | "established"),
            "Invalid state status: {status}"
        );

        if status == "provisional" && self.state_status != "provisional" {
            self.provisional_since = timestamp;
        }
        self.state_status = status.to_string();
    }

    pub fn get_provisional_duration(&self, current_timestamp: f64) -> f64 {
        if self.state_status != "provisional" {
            return 0.0;
        }
        current_timestamp - self.provisional_since
    }

    pub fn clear(&mut self) {
        self.history.clear();
        self.current_mode = None;
        self.previous_mode = None;
        self.mode_entry_time = 0.0;
        self.transition_count = 0;
        self.state_status = "unknown".to_string();
        self.provisional_since = 0.0;
    }
}

// =============================================================================
// Default Hysteresis Configurations
// =============================================================================

fn default_hysteresis_config(mode: &str) -> HysteresisConfig {
    match mode {
        "heightened alertness" | "subtle alertness" => HysteresisConfig {
            mode_name: mode.to_string(),
            entry_threshold: 0.18,
            exit_threshold: 0.24,
            provisional_samples: 3,
            established_samples: 8,
            entry_penalty: 0.85,
            settled_bonus: 1.05,
        },
        "transitional" => HysteresisConfig {
            mode_name: mode.to_string(),
            entry_threshold: 0.17,
            exit_threshold: 0.22,
            provisional_samples: 2,
            established_samples: 5,
            entry_penalty: 0.9,
            settled_bonus: 1.0,
        },
        "settling" => HysteresisConfig {
            mode_name: mode.to_string(),
            entry_threshold: 0.19,
            exit_threshold: 0.25,
            provisional_samples: 3,
            established_samples: 10,
            entry_penalty: 0.8,
            settled_bonus: 1.1,
        },
        "rhythmic settling" => HysteresisConfig {
            mode_name: mode.to_string(),
            entry_threshold: 0.20,
            exit_threshold: 0.26,
            provisional_samples: 3,
            established_samples: 10,
            entry_penalty: 0.8,
            settled_bonus: 1.1,
        },
        "settled presence" => HysteresisConfig {
            mode_name: mode.to_string(),
            entry_threshold: 0.22,
            exit_threshold: 0.28,
            provisional_samples: 5,
            established_samples: 15,
            entry_penalty: 0.75,
            settled_bonus: 1.15,
        },
        _ => HysteresisConfig::new(mode),
    }
}

// =============================================================================
// Soft Mode Inference
// =============================================================================

/// Compute weighted membership across all modes.
///
/// Uses softmax on negative squared distances to mode centroids.
/// This replaces hard threshold cuts with probability-like weights,
/// preserving ambiguity at boundaries.
pub fn compute_soft_mode_membership(
    entrainment: f64,
    breath_steady: bool,
    amp_norm: f64,
    volatility: f64,
    temperature: f64,
    previous_inference: Option<&SoftModeInference>,
) -> SoftModeInference {
    let breath_steady_score = if breath_steady { 1.0 } else { 0.3 };
    let inverse_volatility = (1.0 - volatility * 5.0).clamp(0.0, 1.0);
    let position = [entrainment, breath_steady_score, amp_norm, inverse_volatility];

    // Weighted squared distances to each centroid.
    let mut neg_dists = [0.0_f64; 6];
    for (i, centroid) in MODE_CENTROID_VALUES.iter().enumerate() {
        let mut dist_sq = 0.0;
        for j in 0..4 {
            let diff = position[j] - centroid[j];
            dist_sq += FEATURE_WEIGHTS[j] * diff * diff;
        }
        neg_dists[i] = -dist_sq;
    }

    // Softmax with numerical stability.
    let max_val = neg_dists.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    let mut exp_weights = [0.0_f64; 6];
    let mut total = 0.0;
    for (i, &nd) in neg_dists.iter().enumerate() {
        let w = ((nd - max_val) / temperature).exp();
        exp_weights[i] = w;
        total += w;
    }

    let mut membership = HashMap::with_capacity(6);
    let mut best_idx = 0;
    let mut best_weight = 0.0_f64;
    let mut second_idx = 0;
    let mut second_weight = 0.0_f64;

    for (i, &w) in exp_weights.iter().enumerate() {
        let normed = w / total;
        membership.insert(MODE_NAMES[i].to_string(), normed);
        if normed > best_weight {
            second_idx = best_idx;
            second_weight = best_weight;
            best_idx = i;
            best_weight = normed;
        } else if normed > second_weight {
            second_idx = i;
            second_weight = normed;
        }
    }

    let ambiguity = 1.0 - (best_weight - second_weight);

    let distribution_shift = previous_inference.map(|prev| {
        let epsilon = 1e-10;
        let mut kl = 0.0;
        for name in &MODE_NAMES {
            let p = *membership.get(*name).unwrap_or(&epsilon);
            let q = prev.membership.get(*name).copied().unwrap_or(epsilon);
            if p > epsilon {
                kl += p * ((p + epsilon) / (q + epsilon)).ln();
            }
        }
        kl
    });

    SoftModeInference {
        membership,
        primary_mode: MODE_NAMES[best_idx].to_string(),
        secondary_mode: Some(MODE_NAMES[second_idx].to_string()),
        ambiguity,
        distribution_shift,
    }
}

// =============================================================================
// Hysteresis-Aware Detection
// =============================================================================

/// Hysteresis-aware mode detection.
///
/// State machine: UNKNOWN -> PROVISIONAL -> ESTABLISHED.
/// Entry thresholds are lower than exit thresholds, preventing oscillation
/// from noise at boundaries.
///
/// Returns `(mode_name, confidence, metadata)`.
pub fn detect_mode_with_hysteresis(
    soft_inference: &SoftModeInference,
    mode_history: &mut ModeHistory,
    timestamp: f64,
) -> (String, f64, HashMap<String, String>) {
    let proposed_mode = &soft_inference.primary_mode;
    let raw_confidence = *soft_inference
        .membership
        .get(proposed_mode.as_str())
        .unwrap_or(&0.0);

    let mut metadata = HashMap::new();
    metadata.insert("raw_confidence".into(), format!("{raw_confidence:.4}"));
    metadata.insert("dwell_time".into(), "0.0".into());

    if let Some(prev) = mode_history.get_previous_mode() {
        metadata.insert("previous_mode".into(), prev.to_string());
    }
    metadata.insert("state_status".into(), "unknown".into());

    let current_mode = mode_history.get_current_mode().map(|s| s.to_string());
    let state_status = mode_history.get_state_status().to_string();
    let dwell_time = mode_history.get_dwell_time(timestamp);

    metadata.insert("dwell_time".into(), format!("{dwell_time:.2}"));
    metadata.insert("state_status".into(), state_status.clone());

    let current_config = current_mode
        .as_deref()
        .map(default_hysteresis_config)
        .unwrap_or_else(|| HysteresisConfig::new("unknown"));
    let proposed_config = default_hysteresis_config(proposed_mode);

    let final_mode;
    let final_confidence;

    match current_mode.as_deref() {
        None => {
            // First entry.
            if raw_confidence >= proposed_config.entry_threshold {
                final_mode = proposed_mode.clone();
                final_confidence = raw_confidence * proposed_config.entry_penalty;
                mode_history.set_state_status("provisional", timestamp);
                metadata.insert("transition_type".into(), "entry".into());
                metadata.insert("state_status".into(), "provisional".into());
            } else {
                final_mode = "transitional".to_string();
                final_confidence = 0.3;
                metadata.insert("state_status".into(), "unknown".into());
            }
        }
        Some(current) if current == proposed_mode => {
            // Staying in same mode.
            final_mode = current.to_string();
            final_confidence = if state_status == "established"
                && dwell_time >= current_config.established_samples as f64
            {
                (raw_confidence * current_config.settled_bonus).min(1.0)
            } else {
                raw_confidence
            };

            if state_status == "provisional" {
                let prov_duration = mode_history.get_provisional_duration(timestamp);
                if prov_duration >= proposed_config.provisional_samples as f64 {
                    mode_history.set_state_status("established", timestamp);
                    metadata.insert("state_status".into(), "established".into());
                    metadata.insert("transition_type".into(), "sustained".into());
                }
            }
        }
        Some(current) => {
            // Potential transition to different mode.
            if state_status == "established" {
                if raw_confidence < current_config.exit_threshold {
                    // Can't exit yet.
                    final_mode = current.to_string();
                    final_confidence = current_config.exit_threshold * 0.9;
                } else {
                    // Crossing exit threshold.
                    final_mode = proposed_mode.clone();
                    final_confidence = raw_confidence * proposed_config.entry_penalty;
                    mode_history.set_state_status("provisional", timestamp);
                    metadata.insert("state_status".into(), "provisional".into());
                    metadata.insert("transition_type".into(), "exit".into());
                }
            } else {
                // Provisional or unknown — easier to transition.
                if raw_confidence >= proposed_config.entry_threshold {
                    final_mode = proposed_mode.clone();
                    final_confidence = raw_confidence * proposed_config.entry_penalty;
                    mode_history.set_state_status("provisional", timestamp);
                    metadata.insert("state_status".into(), "provisional".into());
                    metadata.insert("transition_type".into(), "entry".into());
                } else if !current.is_empty() {
                    final_mode = current.to_string();
                    final_confidence = raw_confidence;
                } else {
                    final_mode = "transitional".to_string();
                    final_confidence = 0.3;
                }
            }
        }
    }

    (final_mode, final_confidence, metadata)
}

// =============================================================================
// Movement Annotation
// =============================================================================

/// Generate human-readable movement annotation.
///
/// Encodes HOW you arrived at a state, not just WHERE you are.
pub fn generate_movement_annotation(
    velocity_magnitude: Option<f64>,
    mode_score_acceleration: Option<f64>,
    previous_mode: Option<&str>,
    dwell_time: f64,
) -> String {
    let velocity = match velocity_magnitude {
        Some(v) => v,
        None => return "insufficient data".to_string(),
    };

    let is_still = velocity < VELOCITY_THRESHOLD;
    let is_settled = is_still && dwell_time >= SETTLED_THRESHOLD;

    let mut parts: Vec<String> = Vec::new();

    if is_settled {
        parts.push("settled".to_string());
    } else if is_still {
        parts.push("still".to_string());
    } else if let Some(accel) = mode_score_acceleration {
        if accel > ACCELERATION_THRESHOLD {
            parts.push("accelerating".to_string());
        } else if accel < -ACCELERATION_THRESHOLD {
            parts.push("decelerating".to_string());
        } else {
            parts.push("moving".to_string());
        }
    } else {
        parts.push("moving".to_string());
    }

    if let Some(prev) = previous_mode {
        if dwell_time < RECENT_TRANSITION_WINDOW {
            parts.push(format!("from {prev}"));
        }
    }

    if parts.is_empty() {
        "unknown".to_string()
    } else {
        parts.join(" ")
    }
}

/// Compose full movement-aware label.
///
/// If annotation is trivial, return just the mode name.
pub fn compose_movement_aware_label(mode: &str, movement_annotation: &str) -> String {
    match movement_annotation {
        "insufficient data" | "unknown" | "settled" => mode.to_string(),
        _ => format!("{mode} ({movement_annotation})"),
    }
}

// =============================================================================
// Rupture Oscillation Detection
// =============================================================================

/// ABAB oscillation pattern detected in mode history.
#[derive(Debug, Clone, Serialize)]
pub struct RuptureOscillation {
    pub pattern: Vec<String>,
    pub modes: (String, String),
    pub transition_count: usize,
    pub onset_index: usize,
}

/// Detect ABAB patterns in mode transitions.
///
/// Rapid oscillation between two modes may indicate rupture or
/// boundary instability that warrants attention.
pub fn detect_rupture_oscillation(
    mode_history: &ModeHistory,
    window: Option<usize>,
    min_transitions: Option<usize>,
) -> Option<RuptureOscillation> {
    let window = window.unwrap_or(OSCILLATION_WINDOW);
    let min_transitions = min_transitions.unwrap_or(MIN_OSCILLATION_TRANSITIONS);

    let sequence = mode_history.get_mode_sequence(Some(window));

    if sequence.len() < min_transitions + 1 {
        return None;
    }

    // Count transitions.
    let mut transitions = 0;
    for i in 1..sequence.len() {
        if sequence[i] != sequence[i - 1] {
            transitions += 1;
        }
    }

    if transitions < min_transitions {
        return None;
    }

    // Check for exactly 2 unique modes.
    let mut unique: Vec<&str> = Vec::new();
    for s in &sequence {
        if !unique.contains(s) {
            unique.push(s);
        }
    }
    if unique.len() != 2 {
        return None;
    }

    // Verify strictly alternating.
    for i in 1..sequence.len() {
        if sequence[i] == sequence[i - 1] {
            return None;
        }
    }

    let total_len = mode_history.get_mode_sequence(None).len();
    Some(RuptureOscillation {
        pattern: sequence.iter().map(|s| s.to_string()).collect(),
        modes: (unique[0].to_string(), unique[1].to_string()),
        transition_count: transitions,
        onset_index: total_len - sequence.len(),
    })
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_soft_mode_membership_settled() {
        let result = compute_soft_mode_membership(
            0.75, // high entrainment
            true, // breath steady
            0.7,  // decent amplitude
            0.05, // low volatility
            0.2,
            None,
        );

        // High entrainment + steady breath should yield settling/rhythmic/presence.
        let primary = result.primary_mode.as_str();
        assert!(
            ["settling", "rhythmic settling", "settled presence"].contains(&primary),
            "Expected a settling-family mode, got: {primary}"
        );

        // Membership should sum to ~1.0.
        let sum: f64 = result.membership.values().sum();
        assert!(
            (sum - 1.0).abs() < 1e-6,
            "Membership should sum to 1.0, got {sum}"
        );
    }

    #[test]
    fn test_soft_mode_membership_alert() {
        let result = compute_soft_mode_membership(
            0.05, // very low entrainment
            false, // breath not steady
            0.15, // low amplitude
            0.4,  // high volatility
            0.2,
            None,
        );

        assert_eq!(
            result.primary_mode, "heightened alertness",
            "Low entrainment + high volatility should be heightened alertness"
        );
    }

    #[test]
    fn test_hysteresis_prevents_oscillation() {
        let mut history = ModeHistory::new(100);

        // Establish a mode by feeding consistent signals for 20 iterations.
        let mut established_mode = String::new();
        for i in 0..20 {
            let inf = compute_soft_mode_membership(0.6, true, 0.6, 0.05, 0.2, None);
            let (mode, conf, _meta) =
                detect_mode_with_hysteresis(&inf, &mut history, i as f64);
            history.append(&mode, conf, i as f64);
            established_mode = mode;
        }

        // Now send a mildly different signal — should resist leaving.
        // Use values close to settling but slightly shifted.
        let nudge = compute_soft_mode_membership(0.45, true, 0.5, 0.08, 0.2, None);
        let (mode, _conf, _meta) =
            detect_mode_with_hysteresis(&nudge, &mut history, 20.0);

        // Should stay in established mode, not jump to whatever nudge proposes.
        assert_eq!(
            mode, established_mode,
            "Hysteresis should keep '{}' instead of jumping to '{}'",
            established_mode, nudge.primary_mode
        );
    }

    #[test]
    fn test_movement_annotation_settled() {
        let annotation = generate_movement_annotation(
            Some(0.01), // low velocity
            Some(0.0),
            None,
            10.0, // high dwell
        );
        assert_eq!(annotation, "settled");
    }

    #[test]
    fn test_movement_annotation_moving() {
        let annotation = generate_movement_annotation(
            Some(0.1), // high velocity
            Some(0.05), // positive acceleration
            None,
            1.0,
        );
        assert!(
            annotation == "accelerating" || annotation == "moving",
            "High velocity should yield accelerating or moving, got: {annotation}"
        );
    }

    #[test]
    fn test_compose_label_trivial() {
        assert_eq!(
            compose_movement_aware_label("settling", "settled"),
            "settling"
        );
        assert_eq!(
            compose_movement_aware_label("settling", "unknown"),
            "settling"
        );
    }

    #[test]
    fn test_compose_label_with_annotation() {
        assert_eq!(
            compose_movement_aware_label("settling", "still from heightened alertness"),
            "settling (still from heightened alertness)"
        );
    }

    #[test]
    fn test_rupture_detection() {
        let mut history = ModeHistory::new(100);

        // Build a strict ABABAB pattern — 6 entries, 5 transitions.
        let modes = ["settling", "heightened alertness"];
        for i in 0..6 {
            history.append(modes[i % 2], 0.5, i as f64);
        }

        let result = detect_rupture_oscillation(&history, Some(6), Some(4));
        assert!(result.is_some(), "ABAB pattern should be detected");
        let osc = result.unwrap();
        assert_eq!(osc.transition_count, 5);
    }

    #[test]
    fn test_no_rupture_for_stable() {
        let mut history = ModeHistory::new(100);
        for i in 0..10 {
            history.append("settling", 0.8, i as f64);
        }
        let result = detect_rupture_oscillation(&history, None, None);
        assert!(result.is_none(), "Stable mode should not flag rupture");
    }

    #[test]
    fn test_mode_history_basics() {
        let mut h = ModeHistory::new(5);
        assert!(h.get_current_mode().is_none());
        assert_eq!(h.get_transition_count(), 0);

        h.append("settling", 0.8, 1.0);
        assert_eq!(h.get_current_mode(), Some("settling"));
        assert_eq!(h.get_dwell_time(3.0), 2.0);

        h.append("transitional", 0.5, 4.0);
        assert_eq!(h.get_current_mode(), Some("transitional"));
        assert_eq!(h.get_previous_mode(), Some("settling"));
        assert_eq!(h.get_transition_count(), 1);

        h.clear();
        assert!(h.get_current_mode().is_none());
        assert_eq!(h.get_transition_count(), 0);
    }

    #[test]
    fn test_distribution_shift() {
        let first = compute_soft_mode_membership(0.1, false, 0.2, 0.4, 0.2, None);
        assert!(first.distribution_shift.is_none());

        let second = compute_soft_mode_membership(0.7, true, 0.7, 0.05, 0.2, Some(&first));
        assert!(second.distribution_shift.is_some());
        assert!(
            second.distribution_shift.unwrap() > 0.0,
            "Large input change should produce positive KL divergence"
        );
    }
}
