/**
 * Tests for on-device voice DSP (voiceProcessor.ts).
 */

import { processVoice } from '../src/utils/voiceProcessor';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makeSyntheticVoice(f0Hz: number, durationS = 5, amplitude = 0.5): number[] {
  const n = Math.floor(durationS * 4410);
  const samples: number[] = new Array(n);
  for (let i = 0; i < n; i++) {
    samples[i] = amplitude * Math.sin((2 * Math.PI * f0Hz * i) / 4410);
  }
  return samples;
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('processVoice', () => {
  test('returns null vitals for empty samples', () => {
    const result = processVoice([]);
    expect(result.jitter_pct).toBeNull();
    expect(result.shimmer_pct).toBeNull();
    expect(result.snr_db).toBeNull();
    expect(result.flags).toContain('insufficient_samples');
  });

  test('returns null for < 2 seconds of audio', () => {
    const samples = makeSyntheticVoice(100, 1.0);
    const result = processVoice(samples);
    expect(result.jitter_pct).toBeNull();
    expect(result.shimmer_pct).toBeNull();
    expect(result.flags).toContain('insufficient_samples');
  });

  test('returns null for silent audio (all zeros)', () => {
    const samples = Array(22050).fill(0) as number[];
    const result = processVoice(samples);
    expect(result.jitter_pct).toBeNull();
    expect(result.voiced_fraction).toBeCloseTo(0, 1);
  });

  test('voiced_fraction is near 1.0 for a full sustained tone', () => {
    const samples = makeSyntheticVoice(100);
    const result = processVoice(samples);
    expect(result.voiced_fraction).toBeGreaterThan(0.8);
  });

  test('jitter_pct is low for a pure sustained tone at 100 Hz', () => {
    const samples = makeSyntheticVoice(100);
    const result = processVoice(samples);
    expect(result.jitter_pct).not.toBeNull();
    expect(result.jitter_pct!).toBeLessThan(5);
  });

  test('shimmer_pct is low for a pure constant-amplitude tone', () => {
    const samples = makeSyntheticVoice(100);
    const result = processVoice(samples);
    expect(result.shimmer_pct).not.toBeNull();
    expect(result.shimmer_pct!).toBeLessThan(10);
  });

  test('snr_db is 40 when entire signal is voiced (no silence frames)', () => {
    const samples = makeSyntheticVoice(100);
    const result = processVoice(samples);
    expect(result.snr_db).toBe(40);
  });

  test('flags is always an array', () => {
    const result = processVoice([]);
    expect(Array.isArray(result.flags)).toBe(true);
  });

  test('works for 200 Hz tone', () => {
    const samples = makeSyntheticVoice(200);
    const result = processVoice(samples);
    expect(result.jitter_pct).not.toBeNull();
    expect(result.jitter_pct!).toBeLessThan(5);
    expect(result.shimmer_pct).not.toBeNull();
    expect(result.shimmer_pct!).toBeLessThan(10);
  });
});
