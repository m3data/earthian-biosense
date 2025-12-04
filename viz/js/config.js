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
  }
};

/**
 * Mode Color Palette — Earth-Warm
 *
 * Maps autonomic mode labels to RGB values.
 *
 * Design principle: Colors differentiate without ranking.
 * No state is "better" — just different textures of becoming.
 * Warm earth tones invite settling rather than striving.
 *
 * Palette: ochres, ambers, terracottas, clay, sandstone
 */
export const MODE_COLORS = {
  'heightened vigilance': [190, 120, 90],   // terracotta — active, present
  'subtle vigilance': [175, 145, 110],      // warm sand — attending
  'transitional': [165, 135, 115],          // clay — moving between
  'settling': [155, 140, 120],              // soft umber — easing
  'emerging coherence': [180, 155, 125],    // amber — gathering
  'coherent presence': [170, 150, 130],     // sandstone — dwelling
  'coherent': [170, 150, 130],              // sandstone (alias)
  'deep coherence': [160, 145, 125]         // deep ochre — resting
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
