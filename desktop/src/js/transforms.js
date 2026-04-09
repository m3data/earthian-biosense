/**
 * Coordinate Transforms
 *
 * Maps session data to canvas/3D coordinates.
 *
 * Ontological note: These transforms encode our model of the
 * phase space. The choice of axes, scaling, and perspective
 * all shape what becomes visible and what remains hidden.
 */

import { CONFIG } from './config.js';

const { width: WIDTH, height: HEIGHT, margin: MARGIN } = CONFIG.canvas;

/**
 * Transform a session sample to 2D canvas coordinates
 *
 * X-axis: Coherence (0-1)
 * Y-axis: Breath rhythm / phase.position[1]
 */
export function sampleToCanvas2D(sample) {
  const coh = sample.metrics.coh || 0;
  const breathPos = sample.phase.position[1] || 0.5;
  const zPhase = sample.phase.position[2] || 0.5;

  return {
    x: MARGIN + coh * (WIDTH - 2 * MARGIN),
    y: HEIGHT - MARGIN - breathPos * (HEIGHT - 2 * MARGIN),
    z: zPhase, // Carried for depth effects
    mode: sample.metrics.mode,
    stability: sample.phase.stability || 0.5
  };
}

/**
 * Transform a session sample to 3D coordinates
 *
 * X-axis: Coherence (0-1) -> -100 to 100
 * Y-axis: Stability (0-1) -> 80 to -80 (inverted: high = up)
 * Z-axis: Amplitude / phase.position[2] -> -100 to 100
 */
export function sampleToCanvas3D(sample) {
  const coh = sample.metrics.coh || 0;
  const stability = sample.phase.stability || 0.5;
  const ampPos = sample.phase.position[2] || 0.5;

  return {
    x: (coh - 0.5) * 200,
    y: (0.5 - stability) * 160,
    z: (ampPos - 0.5) * 200,
    mode: sample.metrics.mode,
    stability: stability
  };
}

/**
 * Apply 2D perspective transform based on age
 *
 * Older points recede toward a vanishing point,
 * creating depth illusion in the 2D view.
 */
export function applyPerspective2D(point, age) {
  const { vanishPointX, vanishPointY, depthScale } = CONFIG.perspective2D;

  const vanishX = WIDTH * vanishPointX;
  const vanishY = HEIGHT * vanishPointY;

  // Age 0 = present (front), age 1 = past (back)
  let depth = age * depthScale;

  // Z-phase also contributes to depth
  const zContrib = (1 - point.z) * 0.15;
  depth += zContrib;

  // Lerp toward vanishing point
  const x = point.x + (vanishX - point.x) * depth * 0.4;
  const y = point.y + (vanishY - point.y) * depth * 0.5;

  // Scale shrinks with depth
  const scale = 1 - depth * 0.7;

  return { x, y, scale, depth };
}

/**
 * Map a grid cell to 3D world coordinates
 * Used for dwell density visualization
 */
export function gridToWorld3D(xi, yi, zi, gridSize) {
  return {
    x: (xi / gridSize - 0.5) * 200,
    y: ((gridSize - yi) / gridSize - 0.5) * 160, // Inverted Y
    z: (zi / gridSize - 0.5) * 200
  };
}
