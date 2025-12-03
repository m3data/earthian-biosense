/**
 * Playback Controller
 *
 * Manages timeline state, play/pause, speed, and scrubbing.
 */

import { CONFIG } from './config.js';

export class PlaybackController {
  constructor(session, onUpdate) {
    this.session = session;
    this.onUpdate = onUpdate;

    this.currentIndex = 0;
    this.isPlaying = false;
    this.speed = 1;
    this.lastFrameTime = 0;
  }

  play() {
    this.isPlaying = true;
    this.lastFrameTime = performance.now();

    // Reset if at end
    if (this.currentIndex >= this.session.length - 1) {
      this.currentIndex = 0;
    }
  }

  pause() {
    this.isPlaying = false;
  }

  toggle() {
    if (this.isPlaying) {
      this.pause();
    } else {
      this.play();
    }
    return this.isPlaying;
  }

  setSpeed(speed) {
    this.speed = speed;
  }

  seekTo(fraction) {
    this.currentIndex = fraction * (this.session.length - 1);
    this.onUpdate?.();
  }

  seekToIndex(index) {
    this.currentIndex = Math.max(0, Math.min(index, this.session.length - 1));
    this.onUpdate?.();
  }

  step(delta) {
    this.seekToIndex(this.currentIndex + delta);
  }

  /**
   * Call this each frame to advance playback
   */
  tick() {
    if (!this.isPlaying || this.session.length === 0) return;

    const now = performance.now();
    const elapsed = now - this.lastFrameTime;
    const msPerSample = CONFIG.playback.msPerSample / this.speed;

    if (elapsed > msPerSample / 60) {
      if (this.currentIndex < this.session.length - 1) {
        this.currentIndex += elapsed / msPerSample;
        this.currentIndex = Math.min(this.currentIndex, this.session.length - 1);
        this.onUpdate?.();
      } else {
        this.pause();
      }
      this.lastFrameTime = now;
    }
  }

  get progress() {
    if (this.session.length <= 1) return 0;
    return this.currentIndex / (this.session.length - 1);
  }

  get currentSample() {
    return this.session.getSample(this.currentIndex);
  }

  get elapsedTime() {
    return this.session.getTimeAtIndex(this.currentIndex);
  }

  get totalTime() {
    return this.session.duration;
  }
}

/**
 * Format seconds as MM:SS
 */
export function formatTime(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}
