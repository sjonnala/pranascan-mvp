/**
 * On-device voice DSP — jitter, shimmer, and SNR estimation.
 *
 * All processing runs on the device. Only the derived jitter_pct and
 * shimmer_pct scalars are submitted to the backend — audio samples never
 * leave the device.
 *
 * Mirrors the logic from backend/app/services/voice_processor.py.
 */

import { filtfiltHP, filtfiltLP, findPeaks } from './rppgProcessor';

// ─── Constants (match backend voice_processor.py) ────────────────────────────

const SAMPLE_RATE = 4410;
const FRAME_SIZE = 88; // 20 ms at 4410 Hz
const SILENCE_THRESHOLD = 0.01;
const MIN_VOICED_FRACTION = 0.5;
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const F0_LOW_HZ = 80;
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const F0_HIGH_HZ = 400;
const MIN_PERIOD_SAMPLES = Math.floor(4410 / 400); // 11
const MAX_PERIOD_SAMPLES = Math.floor(4410 / 80); // 55
const K_HP_VOICE = Math.exp((-2 * Math.PI * 80) / 4410); // ≈ 0.8923
const ALPHA_LP_VOICE = 1 - Math.exp((-2 * Math.PI * 400) / 4410); // ≈ 0.4341

// ─── Public interface ─────────────────────────────────────────────────────────

export interface VoiceOnDeviceResult {
  jitter_pct: number | null;
  shimmer_pct: number | null;
  snr_db: number | null;
  voiced_fraction: number;
  flags: string[];
}

// ─── Private helpers ──────────────────────────────────────────────────────────

function mean(arr: number[]): number {
  if (arr.length === 0) return 0;
  let s = 0;
  for (let i = 0; i < arr.length; i++) s += arr[i];
  return s / arr.length;
}

function stdDev(arr: number[]): number {
  if (arr.length < 2) return 0;
  const m = mean(arr);
  let s = 0;
  for (let i = 0; i < arr.length; i++) s += (arr[i] - m) ** 2;
  return Math.sqrt(s / arr.length);
}

function round3(v: number): number {
  return Math.round(v * 1000) / 1000;
}

// ─── Main export ──────────────────────────────────────────────────────────────

export function processVoice(samples: number[]): VoiceOnDeviceResult {
  const flags: string[] = [];

  // 1. Guard: need at least 2 seconds of audio
  if (samples.length < SAMPLE_RATE * 2) {
    flags.push('insufficient_samples');
    return { jitter_pct: null, shimmer_pct: null, snr_db: null, voiced_fraction: 0, flags };
  }

  // 2. Frame RMS
  const numFrames = Math.floor(samples.length / FRAME_SIZE);
  const frameRms: number[] = new Array(numFrames);
  for (let f = 0; f < numFrames; f++) {
    const start = f * FRAME_SIZE;
    let sumSq = 0;
    for (let i = start; i < start + FRAME_SIZE; i++) sumSq += samples[i] * samples[i];
    frameRms[f] = Math.sqrt(sumSq / FRAME_SIZE);
  }

  // 3. Voiced mask
  const voicedMask: boolean[] = frameRms.map(rms => rms > SILENCE_THRESHOLD);

  // 4. voiced_fraction
  const voicedCount = voicedMask.filter(Boolean).length;
  const voiced_fraction = numFrames > 0 ? voicedCount / numFrames : 0;

  // 5. SNR
  const voicedRmsList = frameRms.filter((_, i) => voicedMask[i]);
  const silenceRmsList = frameRms.filter((_, i) => !voicedMask[i]);

  let snr_db: number | null;
  if (voicedRmsList.length === 0) {
    snr_db = null;
  } else if (silenceRmsList.length === 0) {
    snr_db = 40; // all voiced — no silence reference
  } else {
    const voicedRmsMean = mean(voicedRmsList);
    const noiseRmsMean = mean(silenceRmsList);
    snr_db = noiseRmsMean > 0 ? 20 * Math.log10(voicedRmsMean / noiseRmsMean) : 40;
  }

  if (snr_db !== null && snr_db < 10) {
    flags.push('high_noise');
  }

  // 6. Insufficient voiced content guard
  if (voiced_fraction < MIN_VOICED_FRACTION) {
    flags.push('insufficient_voiced_content');
    return {
      jitter_pct: null,
      shimmer_pct: null,
      snr_db,
      voiced_fraction: round3(voiced_fraction),
      flags,
    };
  }

  // 7. Concatenate voiced frames
  const voicedSamples: number[] = [];
  for (let f = 0; f < numFrames; f++) {
    if (voicedMask[f]) {
      const start = f * FRAME_SIZE;
      for (let i = start; i < start + FRAME_SIZE; i++) {
        voicedSamples.push(samples[i]);
      }
    }
  }

  // 8. Bandpass filter
  const filtered = filtfiltLP(filtfiltHP(voicedSamples, K_HP_VOICE), ALPHA_LP_VOICE);

  // 9. Peak detection
  const peaks = findPeaks(filtered, MIN_PERIOD_SAMPLES, 0.005);

  // 10. Insufficient glottal cycles guard
  if (peaks.length < 4) {
    flags.push('insufficient_glottal_cycles');
    return {
      jitter_pct: null,
      shimmer_pct: null,
      snr_db,
      voiced_fraction: round3(voiced_fraction),
      flags,
    };
  }

  // 11. Jitter: inter-peak periods
  const periods: number[] = [];
  for (let i = 1; i < peaks.length; i++) {
    const period = peaks[i] - peaks[i - 1];
    if (period >= MIN_PERIOD_SAMPLES && period <= MAX_PERIOD_SAMPLES) {
      periods.push(period);
    }
  }

  let jitter_pct: number | null = null;
  if (periods.length >= 3) {
    const meanPeriod = mean(periods);
    jitter_pct = meanPeriod > 0 ? round3((stdDev(periods) / meanPeriod) * 100) : null;
  }

  // 12. Shimmer: peak amplitudes
  const peakAmps = peaks.map(i => Math.abs(filtered[i]));
  const meanAmp = mean(peakAmps);
  let shimmer_pct: number | null = null;
  if (meanAmp >= 1e-8) {
    shimmer_pct = round3((stdDev(peakAmps) / meanAmp) * 100);
  }

  // 13. Return result
  return {
    jitter_pct,
    shimmer_pct,
    snr_db,
    voiced_fraction: round3(voiced_fraction),
    flags,
  };
}
