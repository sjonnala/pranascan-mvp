/**
 * voiceAnalyzer — light client-side audio helpers for the voice capture flow.
 *
 * These helpers do not compute wellness metrics. They prepare real audio-derived
 * samples and an SNR proxy so the backend voice DSP can analyse the clip.
 */

export const TARGET_AUDIO_SAMPLE_RATE = 4_410;
export const TARGET_AUDIO_DURATION_SECONDS = 5;
export const TARGET_AUDIO_SAMPLE_COUNT =
  TARGET_AUDIO_SAMPLE_RATE * TARGET_AUDIO_DURATION_SECONDS;
export const AUDIO_SNR_PASS_THRESHOLD_DB = 15;

const DEFAULT_WAVE_BAR = 0.1;
const MAX_METERING_DB = 0;
const MIN_METERING_DB = -160;
const DEFAULT_HIGH_SNR_DB = 40;
const FRAME_SIZE = 88; // 20 ms at 4410 Hz
const RMS_SILENCE_THRESHOLD = 0.01;

export function meteringDbToAmplitude(metering?: number): number {
  if (typeof metering !== 'number') {
    return 0;
  }

  if (metering <= MIN_METERING_DB) {
    return 0;
  }

  if (metering >= MAX_METERING_DB) {
    return 1;
  }

  return Math.max(0, Math.min(1, 10 ** (metering / 20)));
}

export function buildWaveformBars(samples: number[], barCount = 20): number[] {
  if (samples.length === 0) {
    return Array(barCount).fill(DEFAULT_WAVE_BAR);
  }

  const recent = samples.slice(-barCount * 4);
  const bars: number[] = [];

  for (let index = 0; index < barCount; index += 1) {
    const start = Math.floor((index / barCount) * recent.length);
    const end = Math.max(start + 1, Math.floor(((index + 1) / barCount) * recent.length));
    const window = recent.slice(start, end);
    const avg = window.reduce((sum, value) => sum + Math.abs(value), 0) / window.length;
    bars.push(Math.max(DEFAULT_WAVE_BAR, Math.min(1, avg)));
  }

  return bars;
}

export function resampleAudioSamples(samples: number[], targetCount: number): number[] {
  if (samples.length === 0 || targetCount <= 0) {
    return [];
  }

  if (samples.length === targetCount) {
    return samples.map(clampAudioSample);
  }

  if (samples.length === 1) {
    return Array(targetCount).fill(clampAudioSample(samples[0]));
  }

  const resampled: number[] = [];
  const scale = (samples.length - 1) / (targetCount - 1);

  for (let index = 0; index < targetCount; index += 1) {
    const sourceIndex = index * scale;
    const lowerIndex = Math.floor(sourceIndex);
    const upperIndex = Math.min(samples.length - 1, Math.ceil(sourceIndex));
    const weight = sourceIndex - lowerIndex;
    const lowerValue = samples[lowerIndex];
    const upperValue = samples[upperIndex];
    const interpolated = lowerValue * (1 - weight) + upperValue * weight;
    resampled.push(clampAudioSample(interpolated));
  }

  return resampled;
}

export function buildFallbackAudioSamples(
  meteringSamples: number[],
  targetCount = TARGET_AUDIO_SAMPLE_COUNT,
): number[] {
  if (meteringSamples.length === 0) {
    return Array(targetCount).fill(0);
  }

  const resampled = resampleAudioSamples(meteringSamples, targetCount);
  return resampled.map((value, index) => (index % 2 === 0 ? value : -value));
}

export function computeSnrDb(samples: number[]): number | undefined {
  if (samples.length === 0) {
    return undefined;
  }

  const frameRms: number[] = [];
  for (let offset = 0; offset < samples.length; offset += FRAME_SIZE) {
    const frame = samples.slice(offset, offset + FRAME_SIZE);
    if (frame.length === 0) {
      continue;
    }
    const meanSquare =
      frame.reduce((sum, sample) => sum + sample * sample, 0) / frame.length;
    frameRms.push(Math.sqrt(meanSquare));
  }

  if (frameRms.length === 0) {
    return undefined;
  }

  const voiced = frameRms.filter((value) => value > RMS_SILENCE_THRESHOLD);
  if (voiced.length === 0) {
    return 0;
  }

  const silence = frameRms.filter((value) => value <= RMS_SILENCE_THRESHOLD);
  const voicedRms = average(voiced);

  if (silence.length === 0) {
    return DEFAULT_HIGH_SNR_DB;
  }

  const noiseRms = Math.max(average(silence), 1e-4);
  return Number((20 * Math.log10(voicedRms / noiseRms)).toFixed(1));
}

function average(values: number[]): number {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function clampAudioSample(value: number): number {
  return Math.max(-1, Math.min(1, value));
}
