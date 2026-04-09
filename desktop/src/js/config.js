/**
 * Visualization Configuration
 *
 * Central configuration for the session replay visualization.
 * Ontological note: These parameters encode assumptions about
 * what matters in the data and how it should be perceived.
 */

export const CONFIG = {
  // Canvas dimensions
  canvas: {
    width: 800,
    height: 500,
    margin: 60
  },

  // Trail rendering
  trail: {
    length: 80,           // Samples to show — temporal window
    subdivisions: 3,      // Catmull-Rom interpolation points between samples
    smoothingTension: 0.5 // Spline tension (0 = sharp, 1 = loose)
  },

  // 2D perspective depth effect
  perspective2D: {
    vanishPointY: 0.35,   // Horizon line (fraction of height)
    vanishPointX: 0.5,    // Center (fraction of width)
    depthScale: 0.6       // How much age affects depth
  },

  // 3D camera
  camera3D: {
    initialRotX: -0.4,
    initialRotY: 0.3,
    zoom: 1,
    autoRotateSpeed: 0.002
  },

  // Dwell density grid
  density: {
    gridSize: 20,
    minDwellThreshold: 2  // Minimum samples to render
  },

  // Playback
  playback: {
    msPerSample: 2000,    // Real-time: ~2s between samples
    speeds: [0.5, 1, 2, 4]
  },

  // Dyadic session rendering
  dyadic: {
    trailLength: 60       // Shorter trails for clarity with two trajectories
  }
};

/**
 * Participant Color Palette — Dyadic Sessions
 *
 * Distinct hues for two participants that remain earth-warm.
 * A: warm orange-terracotta spectrum
 * B: cool teal-blue spectrum
 *
 * Each participant has base color and mode-modulated variants.
 */
export const PARTICIPANT_COLORS = {
  A: {
    base: [217, 95, 2],       // burnt orange — matches phase plot
    glow: [235, 140, 60],     // lighter orange for glow
    trail: [205, 110, 70]     // terracotta trail
  },
  B: {
    base: [27, 158, 119],     // soft teal — matches phase plot
    glow: [80, 180, 150],     // lighter teal for glow
    trail: [100, 140, 160]    // slate blue trail
  }
};

/**
 * Mode Color Palette — Earth-Warm (Extended Range)
 *
 * Maps autonomic mode labels to RGB values.
 *
 * Design principle: Colors differentiate without ranking.
 * No state is "better" — just different textures of becoming.
 *
 * Wider hue range for legibility while staying grounded:
 * - Alertness: warm oranges/terracotta
 * - Transitional: muted rose/mauve
 * - Settling: sage/moss greens
 * - Coherence: soft teals/slate blues
 */
export const MODE_COLORS = {
  'heightened alertness': [205, 110, 70],   // burnt orange — active, alert
  'subtle alertness': [195, 140, 95],       // amber ochre — attending
  'transitional': [175, 130, 140],          // dusty rose — moving between
  'settling': [130, 155, 130],              // sage moss — easing down
  'rhythmic settling': [115, 155, 155],     // soft teal — gathering
  'settled presence': [100, 140, 160],      // slate blue — dwelling
  'coherent': [100, 140, 160],              // slate blue (alias)
  'deep coherence': [95, 130, 150]          // deep slate — resting
};

/**
 * Get color for a mode string
 */
export function getModeColor(mode) {
  for (let key in MODE_COLORS) {
    if (mode && mode.includes(key.split(' ')[0])) {
      return MODE_COLORS[key];
    }
  }
  return [160, 145, 130]; // Default: warm neutral earth tone
}

/**
 * Lerp between two RGB colors
 */
export function lerpColor(c1, c2, t) {
  return [
    c1[0] + (c2[0] - c1[0]) * t,
    c1[1] + (c2[1] - c1[1]) * t,
    c1[2] + (c2[2] - c1[2]) * t
  ];
}
