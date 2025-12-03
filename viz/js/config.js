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
    subdivisions: 4,      // Catmull-Rom interpolation points
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
  }
};

/**
 * Mode Color Palette
 *
 * Maps autonomic mode labels to RGB values.
 * These colors encode interpretive meaning —
 * warm = vigilance, cool = settling, green = coherence.
 */
export const MODE_COLORS = {
  'heightened vigilance': [255, 120, 80],
  'subtle vigilance': [220, 180, 100],
  'settling': [100, 160, 200],
  'transitional': [180, 150, 200],
  'emerging coherence': [120, 200, 160],
  'coherent': [100, 220, 180],
  'deep coherence': [80, 240, 200]
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
  return [150, 150, 150]; // Default gray
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
