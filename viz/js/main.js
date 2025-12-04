/**
 * Session Replay - Main Entry Point
 *
 * Wires together all modules and manages application state.
 */

import { CONFIG, getModeColor } from './config.js';
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
  detailsRevealed: false,
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
        document.getElementById('play-btn').innerHTML = '<i class="ph ph-play"></i>';
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

  // Update phase label with mode-colored border
  const phaseLabel = document.getElementById('phase-label');
  phaseLabel.textContent = sample.phase.phase_label || '—';
  const modeColor = getModeColor(sample.metrics.mode);
  phaseLabel.style.borderColor = `rgb(${modeColor[0]}, ${modeColor[1]}, ${modeColor[2]})`;
  phaseLabel.style.color = `rgb(${modeColor[0]}, ${modeColor[1]}, ${modeColor[2]})`;

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
  let legend = document.getElementById('legend');
  if (mode === '3d') {
    hint.textContent = 'drag to rotate · scroll to zoom';
    legend.classList.remove('hidden');
  } else {
    hint.textContent = '';
    legend.classList.add('hidden');
  }
}

// === Details Reveal ===
function toggleDetails() {
  state.detailsRevealed = !state.detailsRevealed;

  const toggle = document.getElementById('details-toggle');
  const revealables = document.querySelectorAll('.revealable');

  if (state.detailsRevealed) {
    toggle.textContent = 'Hide details';
    toggle.classList.add('active');
    revealables.forEach(el => {
      el.classList.remove('hidden');
      el.classList.add('revealed');
    });
  } else {
    toggle.textContent = 'Show details';
    toggle.classList.remove('active');
    revealables.forEach(el => {
      el.classList.add('hidden');
      el.classList.remove('revealed');
    });
  }
}

// === Info Panel Toggle ===
function setupInfoPanel() {
  const toggle = document.getElementById('info-toggle');
  const content = document.getElementById('info-content');

  toggle.addEventListener('click', () => {
    const isOpen = !content.classList.contains('hidden');
    if (isOpen) {
      content.classList.add('hidden');
      toggle.classList.remove('active');
      toggle.setAttribute('aria-expanded', 'false');
    } else {
      content.classList.remove('hidden');
      toggle.classList.add('active');
      toggle.setAttribute('aria-expanded', 'true');
    }
  });
}

// === Metrics Info Toggle ===
function setupMetricsInfo() {
  const toggle = document.getElementById('metrics-info-toggle');
  const content = document.getElementById('metrics-info-content');

  toggle.addEventListener('click', () => {
    const isOpen = !content.classList.contains('hidden');
    if (isOpen) {
      content.classList.add('hidden');
      toggle.innerHTML = '<i class="ph ph-question"></i>What do these mean?';
    } else {
      content.classList.remove('hidden');
      toggle.innerHTML = '<i class="ph ph-caret-up"></i>Hide explanations';
    }
  });
}

// === Sidebar Toggle ===
function setupSidebar() {
  const sidebar = document.getElementById('sidebar');
  const toggle = document.getElementById('sidebar-toggle');

  toggle.addEventListener('click', () => {
    const isOpen = sidebar.classList.contains('open');
    if (isOpen) {
      sidebar.classList.remove('open');
      sidebar.classList.add('closed');
      toggle.innerHTML = '<i class="ph ph-book-open"></i>';
    } else {
      sidebar.classList.remove('closed');
      sidebar.classList.add('open');
      toggle.innerHTML = '<i class="ph ph-x"></i>';
    }
  });
}

// === Event Handlers ===
function setupEventHandlers() {
  // Details toggle
  document.getElementById('details-toggle').addEventListener('click', toggleDetails);

  // Info panel
  setupInfoPanel();

  // Metrics info panel
  setupMetricsInfo();

  // Sidebar
  setupSidebar();

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

    document.getElementById('play-btn').innerHTML = '<i class="ph ph-play"></i>';
    document.getElementById('session-name').textContent = file.name;
    document.getElementById('phase-label').textContent = '— ready —';

    updateUI();
  });

  // Play/Pause
  document.getElementById('play-btn').addEventListener('click', () => {
    if (state.sessionData.length === 0) return;

    state.isPlaying = !state.isPlaying;
    document.getElementById('play-btn').innerHTML = state.isPlaying ? '<i class="ph ph-pause"></i>' : '<i class="ph ph-play"></i>';
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
