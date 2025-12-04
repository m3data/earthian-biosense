/**
 * Session Replay - Main Entry Point
 *
 * Wires together all modules and manages application state.
 */

import { CONFIG } from './config.js';
import { createSketch2D } from './view2d.js';
import { createSketch3D, computeDwellDensity } from './view3d.js';

// === Application State ===
const state = {
  sessionData: [],
  currentIndex: 0,
  isPlaying: false,
  playbackSpeed: 1,
  lastFrameTime: 0,
  currentView: '2d',
  p5Instance: null,
  dwellDensity: [],

  cam3D: {
    rotX: CONFIG.camera3D.initialRotX,
    rotY: CONFIG.camera3D.initialRotY,
    rotZ: 0,
    zoom: CONFIG.camera3D.zoom,
    autoRotate: true,
    dragging: false,
    lastMouseX: 0,
    lastMouseY: 0
  }
};

// === Playback Handler ===
function handlePlayback() {
  if (state.isPlaying) {
    let now = performance.now();
    let elapsed = now - state.lastFrameTime;
    let msPerSample = CONFIG.playback.msPerSample / state.playbackSpeed;

    if (elapsed > msPerSample / 60) {
      if (state.currentIndex < state.sessionData.length - 1) {
        state.currentIndex += (elapsed / msPerSample);
        state.currentIndex = Math.min(state.currentIndex, state.sessionData.length - 1);
        updateUI();
      } else {
        state.isPlaying = false;
        document.getElementById('play-btn').textContent = 'Play';
      }
      state.lastFrameTime = now;
    }
  }
}

// === UI Update ===
function updateUI() {
  if (state.sessionData.length === 0) return;

  let idx = Math.floor(state.currentIndex);
  let sample = state.sessionData[idx];

  document.getElementById('m-hr').textContent = sample.hr || '—';
  let coh = sample.phase.coherence || 0;
  document.getElementById('m-coh').textContent = coh.toFixed(2);
  document.getElementById('m-coh-label').textContent = sample.metrics.ent_label || '—';
  document.getElementById('m-breath').textContent = sample.metrics.breath ? sample.metrics.breath.toFixed(1) : '—';
  document.getElementById('m-stability').textContent = sample.phase.stability ? sample.phase.stability.toFixed(2) : '—';
  document.getElementById('m-mode').textContent = sample.metrics.mode || '—';

  document.getElementById('phase-label').textContent = sample.phase.phase_label || '—';
  document.getElementById('timeline').value = (state.currentIndex / (state.sessionData.length - 1)) * 100;

  let startTime = new Date(state.sessionData[0].ts);
  let currentTime = new Date(sample.ts);
  let elapsed = (currentTime - startTime) / 1000;
  let total = (new Date(state.sessionData[state.sessionData.length - 1].ts) - startTime) / 1000;

  document.getElementById('time-current').textContent = formatTime(elapsed);
  document.getElementById('time-total').textContent = formatTime(total);
}

function formatTime(seconds) {
  let mins = Math.floor(seconds / 60);
  let secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

// === p5 Initialization ===
function initP5(mode) {
  if (state.p5Instance) {
    state.p5Instance.remove();
  }

  let sketch;
  if (mode === '3d') {
    sketch = createSketch3D(state, handlePlayback);
  } else {
    sketch = createSketch2D(state, handlePlayback, updateUI);
  }

  state.p5Instance = new p5(sketch, 'canvas-container');
  state.currentView = mode;

  // Update hint
  let hint = document.getElementById('view-hint');
  if (mode === '3d') {
    hint.textContent = 'drag to rotate · scroll to zoom';
  } else {
    hint.textContent = '';
  }
}

// === Event Handlers ===
function setupEventHandlers() {
  // Tab switching
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      initP5(tab.dataset.view);
    });
  });

  // File input
  document.getElementById('file-input').addEventListener('change', async (e) => {
    let file = e.target.files[0];
    if (!file) return;

    let text = await file.text();
    let lines = text.trim().split('\n');
    let parsed = lines.map(line => JSON.parse(line));

    // Filter out header records
    state.sessionData = parsed.filter(record => record.phase && record.metrics);

    state.currentIndex = 0;
    state.isPlaying = false;
    state.dwellDensity = computeDwellDensity(state.sessionData);

    document.getElementById('play-btn').textContent = 'Play';
    document.getElementById('session-name').textContent = file.name;
    document.getElementById('phase-label').textContent = '— ready —';

    updateUI();
  });

  // Play/Pause
  document.getElementById('play-btn').addEventListener('click', () => {
    if (state.sessionData.length === 0) return;

    state.isPlaying = !state.isPlaying;
    document.getElementById('play-btn').textContent = state.isPlaying ? 'Pause' : 'Play';
    state.lastFrameTime = performance.now();

    if (state.currentIndex >= state.sessionData.length - 1) {
      state.currentIndex = 0;
    }
  });

  // Timeline scrub
  document.getElementById('timeline').addEventListener('input', (e) => {
    if (state.sessionData.length === 0) return;
    state.currentIndex = (e.target.value / 100) * (state.sessionData.length - 1);
    updateUI();
  });

  // Speed buttons
  ['05', '1', '2', '4'].forEach(speed => {
    document.getElementById(`speed-${speed}`).addEventListener('click', (e) => {
      state.playbackSpeed = speed === '05' ? 0.5 : parseInt(speed);
      document.querySelectorAll('#controls button').forEach(btn => {
        if (btn.id.startsWith('speed-')) btn.classList.remove('active');
      });
      e.target.classList.add('active');
    });
  });

  // Keyboard shortcuts
  document.addEventListener('keydown', (e) => {
    if (e.code === 'Space') {
      e.preventDefault();
      document.getElementById('play-btn').click();
    }
    if (e.code === 'ArrowLeft') {
      state.currentIndex = Math.max(0, state.currentIndex - 10);
      updateUI();
    }
    if (e.code === 'ArrowRight') {
      state.currentIndex = Math.min(state.sessionData.length - 1, state.currentIndex + 10);
      updateUI();
    }
  });
}

// === Initialize ===
setupEventHandlers();
initP5('2d');
