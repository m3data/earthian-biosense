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

/**
 * Two-Axis Mode Palette — stillness × trajectory coherence
 *
 * Earth-warm, differentiate-without-ranking. No region is a goal: there is no
 * "good state to achieve" (DESIGN_PRINCIPLES). reactive/engaged/constrained are
 * not better or worse than settled presence — just different textures.
 */
export const MODE_COLORS_2D = {
  'reactive':              [200, 120, 85],   // warm terracotta — activated, scattered
  'engaged':               [200, 165, 95],   // amber gold — activated with integrity
  'transitional':          [175, 130, 140],  // dusty rose — moving between
  'constrained stillness': [150, 135, 125],  // muted clay — still but held/brittle
  'settled presence':      [100, 140, 160]   // slate blue — settled, permeable
};

/**
 * 2-D mode centroids in the (calm/stillness × coherence) plane.
 * MIRRORS src/processing/movement.py MODE_CENTROIDS_2D — keep in sync.
 */
export const MODE_CENTROIDS_2D = {
  'reactive':              { calm: 0.15, coherence: 0.12 },
  'engaged':               { calm: 0.30, coherence: 0.62 },
  'transitional':          { calm: 0.45, coherence: 0.35 },
  'constrained stillness': { calm: 0.72, coherence: 0.15 },
  'settled presence':      { calm: 0.78, coherence: 0.68 }
};

/**
 * Faithful JS twin of compute_2d_mode_membership (movement.py).
 *
 * Used as a FALLBACK only — when a loaded session predates schema 1.4.0 and so
 * carries no logged soft_mode_2d. When the authoritative Python field is present
 * the viz uses it directly. Same constants, same softmax, same ambiguity.
 *
 * Returns { membership: {mode: weight}, primary, ambiguity } or null if inputs
 * are unavailable.
 */
export function compute2DMembership(calmScore, coherence, temperature = 0.15) {
  if (calmScore == null || coherence == null) return null;
  const calm = Math.max(0, Math.min(1, calmScore));
  const coh = Math.max(0, Math.min(1, coherence));

  const dist = {};
  for (const [name, c] of Object.entries(MODE_CENTROIDS_2D)) {
    const dc = calm - c.calm;
    const dh = coh - c.coherence;
    dist[name] = dc * dc + dh * dh;
  }
  const maxNeg = Math.max(...Object.values(dist).map(d => -d));
  const expW = {};
  let total = 0;
  for (const [name, d] of Object.entries(dist)) {
    const w = Math.exp((-d - maxNeg) / temperature);
    expW[name] = w;
    total += w;
  }
  const membership = {};
  for (const name of Object.keys(expW)) membership[name] = expW[name] / total;

  const sorted = Object.entries(membership).sort((a, b) => b[1] - a[1]);
  const ambiguity = 1 - (sorted[0][1] - (sorted[1] ? sorted[1][1] : 0));
  return { membership, primary: sorted[0][0], ambiguity };
}

/**
 * Read the 2-D membership for a sample: prefer the logged authoritative field
 * (soft_mode_2d), fall back to the JS twin from mode_score + coherence.
 */
export function getModeSpace2D(sample) {
  if (!sample || !sample.phase) return null;
  const logged = sample.phase.soft_mode_2d;
  if (logged && logged.membership) {
    return {
      membership: logged.membership,
      primary: logged.primary,
      ambiguity: logged.ambiguity != null ? logged.ambiguity : null
    };
  }
  const calm = sample.metrics ? sample.metrics.mode_score : null;
  const coh = sample.phase.coherence;
  return compute2DMembership(calm, coh);
}

/**
 * Blend mode colors by membership weights → a single RGB.
 * The current marker's hue IS the soft membership (honest, not a hard label).
 */
export function blendModeColor2D(membership) {
  let r = 0, g = 0, b = 0, sum = 0;
  for (const [name, w] of Object.entries(membership || {})) {
    const c = MODE_COLORS_2D[name];
    if (!c) continue;
    r += c[0] * w; g += c[1] * w; b += c[2] * w; sum += w;
  }
  if (sum === 0) return [160, 145, 130];
  return [r / sum, g / sum, b / sum];
}
