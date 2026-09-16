/**
 * EarthianBioSense Desktop — Main Entry Point
 *
 * Adapted from viz/js/main.js for Tauri desktop app.
 * Replaces WebSocket live connection with Tauri IPC events.
 * Adds device scan/connect, session start/stop, and session loading.
 */

import { CONFIG, getModeColor } from './config.js';
import { createSketch2D } from './view2d.js';
import { createSketch3D, computeDwellDensity } from './view3d.js';
import { initModeSpace, setModeSpaceData } from './modespace.js';
import { initEegPanel, showEegPanel, hideEegPanel, onEegRaw, onCentral } from './eegpanel.js';
import { initBerger, setBergerEnabled, onCentralForBerger } from './berger.js';

// === Tauri API ===
const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;

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

  // Live mode state
  isLive: false,

  // Device state
  selectedDevice: null,
  isConnected: false,
  isReconnecting: false,
  isSessionActive: false,

  // SPEC-015 v0.1: Muse link state, independent of the H10 fields above.
  // Sessions are autonomic-first: session controls are tied to the H10 only,
  // so a Muse-only connection never shows Start/Stop.
  isMuseConnected: false,

  // Dyadic session state
  isDyadic: false,
  participants: null,
  dataA: [],
  dataB: [],

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

// === Logging ===
function log(msg) {
  const el = document.getElementById('log');
  if (!el) return;
  const time = new Date().toLocaleTimeString();
  el.innerHTML += `${time} — ${msg}\n`;
  el.scrollTop = el.scrollHeight;
}

// === Status ===
function setConnectionStatus(status) {
  const dot = document.getElementById('status-dot');
  if (dot) dot.className = `status-dot ${status}`;
}

// === Device Scanning & Connection ===
async function scanDevices() {
  const btn = document.getElementById('btn-scan');
  btn.disabled = true;
  btn.textContent = 'Scanning...';
  log('Scanning for devices (Polar H10, Muse S)...');

  try {
    const devices = await invoke('cmd_scan_devices', { timeoutSecs: 5 });
    const list = document.getElementById('device-list');
    list.innerHTML = '';
    state.selectedDevice = null;
    document.getElementById('btn-connect').classList.add('hidden');

    if (devices.length === 0) {
      log('No devices found. Is the strap on / the headband awake?');
    } else {
      devices.forEach(d => {
        const li = document.createElement('li');
        const isMuse = d.kind === 'muse';
        const label = isMuse
          ? ''
          : (d.registry_info
              ? `${d.registry_info.label}: ${d.registry_info.strap}`
              : 'Unregistered');
        li.innerHTML = `
          <span>
            <span class="device-name">${d.name}</span>
            ${isMuse ? '<span class="device-kind-tag">EEG</span>' : ''}
            <span class="device-label">${label}</span>
          </span>
        `;
        li.addEventListener('click', () => {
          list.querySelectorAll('li').forEach(el => el.classList.remove('selected'));
          li.classList.add('selected');
          state.selectedDevice = d;
          document.getElementById('btn-connect').classList.remove('hidden');
        });
        list.appendChild(li);
      });
      log(`Found ${devices.length} device(s)`);
    }
  } catch (e) {
    log(`Scan error: ${e}`);
  }

  btn.disabled = false;
  btn.textContent = 'Scan for devices';
}

// The scan-panel opener stays visible while either instrument is still
// unconnected, so the second device can be added after the first.
function updateOpenScanButton() {
  const btn = document.getElementById('btn-open-scan');
  if (state.isConnected && state.isMuseConnected) {
    btn.classList.add('hidden');
  } else {
    btn.classList.remove('hidden');
  }
}

function closeScanPanel() {
  document.getElementById('scan-panel').classList.add('hidden');
  document.getElementById('scan-panel-backdrop').classList.add('hidden');
}

async function connectDevice() {
  if (!state.selectedDevice) return;

  // Route by device kind (SPEC-015 v0.1). H10 path below is unchanged.
  if (state.selectedDevice.kind === 'muse') {
    return connectMuse();
  }

  const label = state.selectedDevice.registry_info?.label || 'A';
  log(`Connecting to ${state.selectedDevice.name} as ${label}...`);

  try {
    const status = await invoke('cmd_connect', {
      address: state.selectedDevice.address,
      label: label,
    });

    log(`Connected: ${status.name} (battery: ${status.battery ?? '?'}%)`);
    setConnectionStatus('connected');
    state.isConnected = true;

    // Show session controls, hide scan panel + backdrop
    closeScanPanel();
    document.getElementById('session-controls').classList.remove('hidden');
    document.getElementById('btn-disconnect').classList.remove('hidden');
    updateOpenScanButton();

    if (status.battery != null) {
      document.getElementById('battery-value').textContent = `${status.battery}%`;
    }
  } catch (e) {
    log(`Connection error: ${e}`);
    setConnectionStatus('error');
  }
}

async function disconnectDevice() {
  try {
    if (state.isSessionActive) {
      await stopSession();
    }
    await invoke('cmd_disconnect');
    log('Disconnected');
    setConnectionStatus('idle');
    state.isConnected = false;
    state.isReconnecting = false;
    state.isLive = false;

    document.getElementById('session-controls').classList.add('hidden');
    document.getElementById('btn-disconnect').classList.add('hidden');
    updateOpenScanButton();
    document.getElementById('battery-value').textContent = '';

    // Reset live HR display
    document.getElementById('live-hr').textContent = '--';
  } catch (e) {
    log(`Disconnect error: ${e}`);
  }
}

// === Muse S (SPEC-015 v0.1) ===
// The Muse link is independent of the H10 link: connecting or dropping it
// never touches session controls, the status dot, or the H10 segment.
const MUSE_CHANNELS = ['TP9', 'AF7', 'AF8', 'TP10'];

function showMuseSegment(status) {
  state.isMuseConnected = true;
  const seg = document.getElementById('muse-segment');
  seg.classList.remove('hidden');
  document.getElementById('muse-name').textContent = shortMuseName(status.name);
  document.getElementById('muse-battery').textContent =
    status.battery != null ? `${status.battery}%` : '';
  showEegPanel();
  updateOpenScanButton();
  setBergerEnabled(state.isSessionActive, state.isMuseConnected);   // SPEC-015 v0.3
}

function hideMuseSegment() {
  state.isMuseConnected = false;
  document.getElementById('muse-segment').classList.add('hidden');
  document.getElementById('muse-name').textContent = '';
  document.getElementById('muse-battery').textContent = '';
  document.getElementById('rel-alpha').textContent = 'α --';
  MUSE_CHANNELS.forEach(ch => setContactChip(ch, 'poor'));
  hideEegPanel();
  updateOpenScanButton();
  setBergerEnabled(state.isSessionActive, state.isMuseConnected);   // SPEC-015 v0.3
}

// "MuseS-7A3B" -> "7A3B"; anything else passes through.
function shortMuseName(name) {
  if (!name) return 'Muse';
  return name.startsWith('MuseS-') ? name.slice('MuseS-'.length) : name;
}

function setContactChip(channel, quality) {
  const el = document.getElementById(`contact-${channel}`);
  if (!el) return;
  const q = ['good', 'marginal', 'poor'].includes(quality) ? quality : 'poor';
  el.className = `contact-chip contact-${q}`;
}

async function connectMuse() {
  if (!state.selectedDevice) return;
  log(`Connecting to ${state.selectedDevice.name} (EEG)...`);

  try {
    const status = await invoke('cmd_connect_muse', {
      address: state.selectedDevice.address,
    });
    log(`Connected EEG: ${status.name} (battery: ${status.battery ?? '?'}%)`);
    closeScanPanel();
    showMuseSegment(status);
  } catch (e) {
    log(`EEG connection error: ${e}`);
  }
}

async function disconnectMuse() {
  try {
    await invoke('cmd_disconnect_muse');
    log('EEG disconnected');
  } catch (e) {
    log(`EEG disconnect error: ${e}`);
  }
  hideMuseSegment();
}

// === Session Controls ===
async function startSession() {
  const typeSelect = document.getElementById('session-type');
  const sessionType = typeSelect ? typeSelect.value : 'solo';

  try {
    await invoke('cmd_start_session', { sessionType });
    state.isSessionActive = true;
    state.isLive = true;
    state.sessionData = [];
    state.currentIndex = 0;
    state.isDyadic = false;

    document.getElementById('btn-start-session').classList.add('hidden');
    document.getElementById('btn-stop-session').classList.remove('hidden');
    document.getElementById('session-name').textContent = 'live session';
    document.getElementById('phase-label').textContent = '— waiting for data —';

    // Auto-reveal details
    if (!state.detailsRevealed) {
      toggleDetails();
    }

    log(`Session started (${sessionType})`);
    setBergerEnabled(state.isSessionActive, state.isMuseConnected);   // SPEC-015 v0.3
  } catch (e) {
    // Session commands may not be implemented yet — fall back to live HR display
    log(`Session start: ${e} — using live HR display mode`);
    state.isLive = true;
    state.isSessionActive = true;
    document.getElementById('btn-start-session').classList.add('hidden');
    document.getElementById('btn-stop-session').classList.remove('hidden');
    document.getElementById('session-name').textContent = 'live (HR only)';
    setBergerEnabled(state.isSessionActive, state.isMuseConnected);   // SPEC-015 v0.3
  }
}

async function stopSession() {
  try {
    const summary = await invoke('cmd_stop_session');
    log(`Session stopped. Duration: ${summary?.duration ?? 'unknown'}`);
  } catch (e) {
    log(`Session stop: ${e}`);
  }

  state.isSessionActive = false;
  state.isLive = false;
  document.getElementById('btn-start-session').classList.remove('hidden');
  document.getElementById('btn-stop-session').classList.add('hidden');
  setBergerEnabled(state.isSessionActive, state.isMuseConnected);   // SPEC-015 v0.3
}

// === Session Loading (File or Tauri Command) ===
async function loadSessionList() {
  const list = document.getElementById('session-list');
  if (!list) return;

  try {
    const sessions = await invoke('cmd_list_sessions');
    list.innerHTML = '';
    sessions.forEach(s => {
      const opt = document.createElement('option');
      opt.value = s.filename;
      opt.textContent = `${s.filename} (${s.duration ?? '?'})`;
      list.appendChild(opt);
    });
    if (sessions.length > 0) {
      document.getElementById('btn-load-session').classList.remove('hidden');
    }
  } catch (e) {
    // cmd_list_sessions not implemented yet — hide the session list
    list.innerHTML = '<option disabled>No stored sessions</option>';
  }
}

async function loadSessionFromBackend(filename) {
  try {
    const content = await invoke('cmd_load_session', { filename });
    const lines = content.trim().split('\n');
    const parsed = lines.map(line => JSON.parse(line));

    loadParsedSession(parsed, filename);
  } catch (e) {
    log(`Load error: ${e}`);
  }
}

function loadParsedSession(parsed, name) {
  // Find header and detect session type
  const header = parsed.find(r => r.type === 'session_start');

  // Filter out header records - keep only data records with phase/metrics
  state.sessionData = parsed.filter(record => record.phase && record.metrics);

  // Detect dyadic session
  if (header && header.session_type === 'dyadic' && header.processed) {
    state.isDyadic = true;
    state.participants = header.participants || { A: {}, B: {} };
    state.dataA = state.sessionData.filter(r => r.participant === 'A');
    state.dataB = state.sessionData.filter(r => r.participant === 'B');
    log(`Dyadic session loaded: A=${state.dataA.length}, B=${state.dataB.length}`);
  } else {
    state.isDyadic = false;
    state.participants = null;
    state.dataA = [];
    state.dataB = [];
  }

  state.currentIndex = 0;
  state.isPlaying = false;
  state.isLive = false;
  state.dwellDensity = computeDwellDensity(state.sessionData);

  document.getElementById('play-btn').innerHTML = '<i class="ph ph-play"></i>';
  document.getElementById('session-name').textContent = name + (state.isDyadic ? ' (dyadic)' : '');
  document.getElementById('phase-label').textContent = '— ready —';

  updateUI();
  log(`Loaded ${state.sessionData.length} samples from ${name}`);
}

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

  if (state.isDyadic) {
    let participant = sample.participant || '?';
    document.getElementById('m-hr').textContent = `${sample.hr || '—'} (${participant})`;
  } else {
    document.getElementById('m-hr').textContent = sample.hr || '—';
  }

  let coh = sample.phase.coherence || 0;
  document.getElementById('m-coh').textContent = coh.toFixed(2);
  document.getElementById('m-coh-label').textContent = sample.metrics.ent_label || '—';
  document.getElementById('m-breath').textContent = sample.metrics.breath ? sample.metrics.breath.toFixed(1) : '—';
  document.getElementById('m-stability').textContent = sample.phase.stability ? sample.phase.stability.toFixed(2) : '—';
  document.getElementById('m-mode').textContent = sample.metrics.mode || '—';

  // Update phase label with mode-colored border
  const phaseLabel = document.getElementById('phase-label');
  if (state.isDyadic) {
    let currentTs = new Date(sample.ts).getTime();
    let sampleA = null, sampleB = null;
    for (let i = state.dataA.length - 1; i >= 0; i--) {
      if (new Date(state.dataA[i].ts).getTime() <= currentTs) { sampleA = state.dataA[i]; break; }
    }
    for (let i = state.dataB.length - 1; i >= 0; i--) {
      if (new Date(state.dataB[i].ts).getTime() <= currentTs) { sampleB = state.dataB[i]; break; }
    }
    let labelA = sampleA ? sampleA.phase.phase_label : '—';
    let labelB = sampleB ? sampleB.phase.phase_label : '—';
    phaseLabel.innerHTML = `<span style="color: rgb(217, 95, 2)">A:</span> ${labelA} · <span style="color: rgb(27, 158, 119)">B:</span> ${labelB}`;
    phaseLabel.style.borderColor = 'rgb(80, 80, 90)';
    phaseLabel.style.color = 'rgb(160, 160, 160)';
  } else {
    phaseLabel.textContent = sample.phase.phase_label || '—';
    const modeColor = getModeColor(sample.metrics.mode);
    phaseLabel.style.borderColor = `rgb(${modeColor[0]}, ${modeColor[1]}, ${modeColor[2]})`;
    phaseLabel.style.color = `rgb(${modeColor[0]}, ${modeColor[1]}, ${modeColor[2]})`;
  }

  document.getElementById('timeline').value = (state.currentIndex / (state.sessionData.length - 1)) * 100;

  let startTime = new Date(state.sessionData[0].ts);
  let currentTime = new Date(sample.ts);
  let elapsed = (currentTime - startTime) / 1000;
  let total = (new Date(state.sessionData[state.sessionData.length - 1].ts) - startTime) / 1000;

  document.getElementById('time-current').textContent = formatTime(elapsed);
  document.getElementById('time-total').textContent = formatTime(total);

  // Two-axis mode field: current position + a recent trail (flows over points).
  const trailStart = Math.max(0, idx - CONFIG.trail.length + 1);
  setModeSpaceData(sample, state.sessionData.slice(trailStart, idx + 1));
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
  // SPEC-015 v0.2: #eeg-panel shares the revealable mechanics but is owned by
  // the Muse link (show/hide on connect/disconnect), not by the details toggle.
  const revealables = document.querySelectorAll('.revealable:not(#eeg-panel)');

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

// === Tauri Event Listeners ===
function setupTauriListeners() {
  // Listen for phase events (from processing pipeline — future)
  listen('ebs:phase', (event) => {
    const data = event.payload;

    const sample = {
      ts: data.ts,
      hr: data.hr,
      metrics: {
        mode: data.mode || '',
        mode_score: data.mode_score != null ? data.mode_score : null,
        amp: data.amplitude || 50,
        breath: data.breath_rate || null,
        ent_label: data.entrainment_label || '',
        coh: data.coherence || 0
      },
      phase: {
        coherence: data.coherence || 0,
        stability: data.stability || 0.5,
        position: data.position || [0, 0.5, 0.5],
        phase_label: data.phase_label || '',
        velocity_mag: data.velocity_magnitude || 0,
        movement_annotation: data.movement_annotation || '',
        movement_aware_label: data.movement_aware_label || '',
        mode_status: data.mode_status || 'unknown',
        soft_mode_2d: data.soft_mode_2d || null,
      }
    };

    state.sessionData.push(sample);

    // Keep buffer bounded (10 min at 1Hz = 600 samples)
    if (state.sessionData.length > 600) {
      state.sessionData.shift();
    }

    // Always show latest in live mode
    state.currentIndex = state.sessionData.length - 1;
    state.isLive = true;
    updateUI();
  });

  // Listen for HR data events (raw, from BLE)
  listen('ebs:hr', (event) => {
    const data = event.payload;

    // Update live HR display
    const hrEl = document.getElementById('live-hr');
    if (hrEl) hrEl.textContent = data.hr;

    const contactEl = document.getElementById('live-contact');
    if (contactEl) contactEl.textContent = data.sensor_contact ? 'Yes' : 'No';
  });

  // Listen for device status events. This is the single authority for the
  // status dot (SPEC-009 REQ-005 v0.2 §3 / CON-002): amber iff
  // `!connected && reconnecting`; never derived from the ordering of two events.
  listen('ebs:device-status', (event) => {
    const data = event.payload;
    state.isReconnecting = !data.connected && !!data.reconnecting;
    setConnectionStatus(
      data.connected ? 'connected' : (data.reconnecting ? 'reconnecting' : 'idle')
    );
    log(`Device ${data.device}: ${data.connected ? 'connected' : (data.reconnecting ? 'link lost, reconnecting' : 'disconnected')}`);
  });

  // BLE auto-reconnect (SPEC-009 REQ-005) — informational log lines only;
  // the dot is owned by `ebs:device-status` above.
  listen('ble:reconnecting', (event) => {
    const { attempt, delay_secs } = event.payload;
    log(`Link lost — reconnecting (attempt ${attempt}, next in ${delay_secs}s)`);
  });

  listen('ble:reconnected', (event) => {
    const { gap_ms, attempts } = event.payload;
    log(`Reconnected after ${gap_ms} ms (${attempts} attempts)`);
  });

  // SPEC-015 v0.1: Muse link status. Additive — never touches the H10
  // status dot or `ebs:device-status`. On link lost the backend emits
  // connected:false and the task exits; the user reconnects by hand.
  listen('ebs:muse-status', (event) => {
    const data = event.payload;
    if (data.connected) {
      showMuseSegment(data);
      log(`EEG ${data.name}: connected`);
    } else {
      hideMuseSegment();
      log(`EEG ${data.name ?? ''}: disconnected`);
    }
  });

  // SPEC-015 v0.1: 1 Hz central tick. Chips + posterior rel-alpha only;
  // no history, no charts.
  listen('ebs:central', (event) => {
    const data = event.payload;
    const contact = data.contact || {};
    MUSE_CHANNELS.forEach(ch => setContactChip(ch, contact[ch]));
    onCentral(data);   // SPEC-015 v0.2: band row + contact fallback for the strip
    onCentralForBerger(data);   // SPEC-015 v0.3: collected only during a Berger run

    const ra = data.rel_alpha;
    const el = document.getElementById('rel-alpha');
    if (!el) return;
    if (ra && ra.TP9 != null && ra.TP10 != null) {
      const posterior = (ra.TP9 + ra.TP10) / 2;
      el.textContent = `α ${posterior.toFixed(2)}`;
    } else {
      el.textContent = 'α --';
    }
  });

  // SPEC-015 v0.2: raw EEG packets (~21/s, ~12 unfiltered µV samples per
  // channel). Display only — the panel filters for the eye; the record is
  // what the Rust side logged before emitting.
  listen('ebs:eeg-raw', (event) => {
    onEegRaw(event.payload);
  });
}

// === Event Handlers ===
function setupEventHandlers() {
  // Device controls
  document.getElementById('btn-scan').addEventListener('click', scanDevices);
  document.getElementById('btn-connect').addEventListener('click', connectDevice);
  document.getElementById('btn-disconnect').addEventListener('click', disconnectDevice);
  document.getElementById('btn-disconnect-muse').addEventListener('click', disconnectMuse);

  // Session controls
  document.getElementById('btn-start-session').addEventListener('click', startSession);
  document.getElementById('btn-stop-session').addEventListener('click', stopSession);

  // Load session from file
  const loadBtn = document.getElementById('btn-load-session');
  if (loadBtn) {
    loadBtn.addEventListener('click', () => {
      const list = document.getElementById('session-list');
      if (list && list.value) {
        loadSessionFromBackend(list.value);
      }
    });
  }

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

  // File input (local file loading — always available)
  document.getElementById('file-input').addEventListener('change', async (e) => {
    let file = e.target.files[0];
    if (!file) return;

    let text = await file.text();
    let lines = text.trim().split('\n');
    let parsed = lines.map(line => JSON.parse(line));

    loadParsedSession(parsed, file.name);
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
setupTauriListeners();
setupEventHandlers();
initP5('2d');
initModeSpace('modespace-canvas');
initEegPanel();
initBerger({ invoke });   // SPEC-015 v0.3: Berger run controls inside #eeg-panel
loadSessionList();

log('EarthianBioSense Desktop v0.1.0');
log('Scan for a device or load a session file.');
