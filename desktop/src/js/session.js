/**
 * Session Data Management
 *
 * Handles loading, parsing, and derived computations
 * from session JSONL files.
 */

import { CONFIG } from './config.js';

export class Session {
  constructor() {
    this.data = [];
    this.filename = null;
    this.dwellDensity = [];
  }

  /**
   * Load session from JSONL text
   */
  load(text, filename) {
    const lines = text.trim().split('\n');
    this.data = lines.map(line => JSON.parse(line));
    this.filename = filename;
    this.computeDwellDensity();
    return this;
  }

  /**
   * Load session from File object
   */
  async loadFile(file) {
    const text = await file.text();
    return this.load(text, file.name);
  }

  get length() {
    return this.data.length;
  }

  get duration() {
    if (this.data.length < 2) return 0;
    const start = new Date(this.data[0].ts);
    const end = new Date(this.data[this.data.length - 1].ts);
    return (end - start) / 1000; // seconds
  }

  getSample(index) {
    return this.data[Math.floor(Math.max(0, Math.min(index, this.data.length - 1)))];
  }

  getTimeAtIndex(index) {
    if (this.data.length === 0) return 0;
    const start = new Date(this.data[0].ts);
    const current = new Date(this.getSample(index).ts);
    return (current - start) / 1000;
  }

  /**
   * Compute 3D dwell density grid
   *
   * Epistemic note: This aggregation loses temporal information —
   * we see where the ANS dwelt, but not when or in what order.
   */
  computeDwellDensity() {
    const gridSize = CONFIG.density.gridSize;

    // Initialize 3D grid
    this.dwellDensity = [];
    for (let x = 0; x < gridSize; x++) {
      this.dwellDensity[x] = [];
      for (let y = 0; y < gridSize; y++) {
        this.dwellDensity[x][y] = [];
        for (let z = 0; z < gridSize; z++) {
          this.dwellDensity[x][y][z] = 0;
        }
      }
    }

    // Accumulate dwell time
    for (const sample of this.data) {
      const coh = sample.metrics.coh || 0;
      const stability = sample.phase.stability || 0.5;
      const ampPos = sample.phase.position[2] || 0.5;

      let xi = Math.floor(coh * (gridSize - 1));
      let yi = Math.floor(stability * (gridSize - 1));
      let zi = Math.floor(ampPos * (gridSize - 1));

      xi = Math.max(0, Math.min(gridSize - 1, xi));
      yi = Math.max(0, Math.min(gridSize - 1, yi));
      zi = Math.max(0, Math.min(gridSize - 1, zi));

      this.dwellDensity[xi][yi][zi]++;
    }
  }

  getMaxDensity() {
    let max = 0;
    const gridSize = CONFIG.density.gridSize;
    for (let x = 0; x < gridSize; x++) {
      for (let y = 0; y < gridSize; y++) {
        for (let z = 0; z < gridSize; z++) {
          if (this.dwellDensity[x][y][z] > max) {
            max = this.dwellDensity[x][y][z];
          }
        }
      }
    }
    return max;
  }
}
