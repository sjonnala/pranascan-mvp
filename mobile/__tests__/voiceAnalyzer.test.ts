/**
 * Unit tests for voiceAnalyzer utilities.
 */

import {
  AUDIO_SNR_PASS_THRESHOLD_DB,
  TARGET_AUDIO_SAMPLE_COUNT,
  buildFallbackAudioSamples,
  buildWaveformBars,
  computeSnrDb,
  meteringDbToAmplitude,
  resampleAudioSamples,
} from '../src/utils/voiceAnalyzer';

describe('meteringDbToAmplitude', () => {
  it('returns 0 when metering is undefined', () => {
    expect(meteringDbToAmplitude(undefined)).toBe(0);
  });

  it('maps 0 dBFS to full amplitude', () => {
    expect(meteringDbToAmplitude(0)).toBe(1);
  });

  it('keeps values within [0, 1]', () => {
    expect(meteringDbToAmplitude(-200)).toBeGreaterThanOrEqual(0);
    expect(meteringDbToAmplitude(-200)).toBeLessThanOrEqual(1);
    expect(meteringDbToAmplitude(10)).toBeLessThanOrEqual(1);
  });
});

describe('buildWaveformBars', () => {
  it('returns default bars for empty input', () => {
    const bars = buildWaveformBars([]);
    expect(bars).toHaveLength(20);
    expect(bars.every((value) => value === 0.1)).toBe(true);
  });

  it('returns normalised bars for real amplitudes', () => {
    const bars = buildWaveformBars([0.1, 0.2, 0.5, 0.8, 1.0], 5);
    expect(bars).toHaveLength(5);
    expect(bars.every((value) => value >= 0.1 && value <= 1)).toBe(true);
  });
});

describe('resampleAudioSamples', () => {
  it('returns empty array for empty samples', () => {
    expect(resampleAudioSamples([], 100)).toEqual([]);
  });

  it('resamples to the requested target count', () => {
    const result = resampleAudioSamples([0, 1, 0, -1], 20);
    expect(result).toHaveLength(20);
  });
});

describe('buildFallbackAudioSamples', () => {
  it('builds a full target-length fallback clip from metering values', () => {
    const result = buildFallbackAudioSamples([0.2, 0.4, 0.1]);
    expect(result).toHaveLength(TARGET_AUDIO_SAMPLE_COUNT);
  });

  it('alternates sign so backend DSP receives oscillating samples', () => {
    const result = buildFallbackAudioSamples([0.5], 4);
    expect(result).toEqual([0.5, -0.5, 0.5, -0.5]);
  });
});

describe('computeSnrDb', () => {
  it('returns undefined for no samples', () => {
    expect(computeSnrDb([])).toBeUndefined();
  });

  it('returns low SNR for near-silent audio', () => {
    const snr = computeSnrDb(Array(1_000).fill(0));
    expect(snr).toBe(0);
  });

  it('returns a passing SNR for a clear voiced signal with silence windows', () => {
    const quiet = Array(440).fill(0.001);
    const voiced = Array(880).fill(0).map((_, index) => Math.sin(index / 10) * 0.4);
    const samples = [...quiet, ...voiced, ...quiet];
    const snr = computeSnrDb(samples);
    expect(snr).toBeDefined();
    expect((snr ?? 0) > AUDIO_SNR_PASS_THRESHOLD_DB).toBe(true);
  });
});
