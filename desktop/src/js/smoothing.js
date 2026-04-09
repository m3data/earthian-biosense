/**
 * Curve Smoothing Utilities
 *
 * Provides Catmull-Rom spline interpolation for
 * smoothing jittery sample-to-sample transitions.
 *
 * Epistemic note: Smoothing is a choice — it removes
 * high-frequency variation, privileging the "trend"
 * over moment-to-moment fluctuation. What do we lose?
 */

import { CONFIG } from './config.js';

/**
 * Catmull-Rom spline interpolation for a single dimension
 */
function catmullRom(p0, p1, p2, p3, t) {
  const t2 = t * t;
  const t3 = t2 * t;

  return 0.5 * (
    (2 * p1) +
    (-p0 + p2) * t +
    (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
    (-p0 + 3 * p1 - 3 * p2 + p3) * t3
  );
}

/**
 * Interpolate a 3D point using Catmull-Rom
 */
function interpolatePoint3D(p0, p1, p2, p3, t) {
  return {
    x: catmullRom(p0.x, p1.x, p2.x, p3.x, t),
    y: catmullRom(p0.y, p1.y, p2.y, p3.y, t),
    z: catmullRom(p0.z, p1.z, p2.z, p3.z, t)
  };
}

/**
 * Interpolate a 2D point using Catmull-Rom
 */
function interpolatePoint2D(p0, p1, p2, p3, t) {
  return {
    x: catmullRom(p0.x, p1.x, p2.x, p3.x, t),
    y: catmullRom(p0.y, p1.y, p2.y, p3.y, t)
  };
}

/**
 * Smooth an array of 3D points using Catmull-Rom interpolation
 *
 * @param {Array} points - Array of {x, y, z, ...metadata}
 * @param {number} subdivisions - Points to insert between each original
 * @returns {Array} Smoothed points with interpolated positions
 */
export function smoothPath3D(points, subdivisions = CONFIG.trail.subdivisions) {
  if (points.length < 3) return points;

  const smoothed = [];

  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[Math.max(0, i - 1)];
    const p1 = points[i];
    const p2 = points[Math.min(i + 1, points.length - 1)];
    const p3 = points[Math.min(i + 2, points.length - 1)];

    for (let t = 0; t < subdivisions; t++) {
      const tNorm = t / subdivisions;
      const interpolated = interpolatePoint3D(p0, p1, p2, p3, tNorm);

      smoothed.push({
        ...interpolated,
        // Carry forward metadata from source point
        mode: p1.mode,
        stability: p1.stability,
        originalIndex: i
      });
    }
  }

  // Add final point
  const last = points[points.length - 1];
  smoothed.push({
    x: last.x,
    y: last.y,
    z: last.z,
    mode: last.mode,
    stability: last.stability,
    originalIndex: points.length - 1
  });

  return smoothed;
}

/**
 * Smooth an array of 2D points using Catmull-Rom interpolation
 *
 * @param {Array} points - Array of {x, y, ...metadata}
 * @param {number} subdivisions - Points to insert between each original
 * @returns {Array} Smoothed points with interpolated positions
 */
export function smoothPath2D(points, subdivisions = CONFIG.trail.subdivisions) {
  if (points.length < 3) return points;

  const smoothed = [];

  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[Math.max(0, i - 1)];
    const p1 = points[i];
    const p2 = points[Math.min(i + 1, points.length - 1)];
    const p3 = points[Math.min(i + 2, points.length - 1)];

    for (let t = 0; t < subdivisions; t++) {
      const tNorm = t / subdivisions;
      const interpolated = interpolatePoint2D(p0, p1, p2, p3, tNorm);

      smoothed.push({
        ...interpolated,
        mode: p1.mode,
        stability: p1.stability,
        z: p1.z, // Carry forward z for depth effects
        originalIndex: i
      });
    }
  }

  // Add final point
  const last = points[points.length - 1];
  smoothed.push({
    x: last.x,
    y: last.y,
    z: last.z,
    mode: last.mode,
    stability: last.stability,
    originalIndex: points.length - 1
  });

  return smoothed;
}

/**
 * Apply exponential moving average smoothing
 * Alternative to spline — preserves temporal causality
 *
 * @param {Array} values - Array of numbers
 * @param {number} alpha - Smoothing factor (0-1, higher = less smooth)
 */
export function exponentialSmooth(values, alpha = 0.3) {
  if (values.length === 0) return [];

  const smoothed = [values[0]];
  for (let i = 1; i < values.length; i++) {
    smoothed.push(alpha * values[i] + (1 - alpha) * smoothed[i - 1]);
  }
  return smoothed;
}
