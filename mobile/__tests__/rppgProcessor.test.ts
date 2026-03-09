/**
 * Unit tests for the on-device rPPG processor.
 *
 * Strategy: generate synthetic green-channel signals with a known
 * sinusoidal HR component and verify the processor recovers it within
 * acceptable tolerance (±10% of true HR — matches backend accuracy target).
 */

import { FrameSample } from '../src/types';
import {
  processFrames,
  linearInterp,
  linearDetrend,
  filtfiltHP,
  filtfiltLP,
  findPeaks,
} from '../src/utils/rppgProcessor';

// ─── Synthetic signal helpers ─────────────────────────────────────────────────

/**
 * Generate a FrameSample array with a sinusoidal green channel at `hrBpm`.
 *
 * @param hrBpm   True heart rate embedded in the signal.
 * @param fps     Capture frame rate (Hz). Default: 2 (matches app).
 * @param durationS  Scan duration (seconds). Default: 30.
 * @param noise   Gaussian noise amplitude (fraction of signal). Default: 0.1.
 */
function makeSyntheticFrames(
  hrBpm: number,
  fps = 2.0,
  durationS = 30.0,
  noise = 0.1,
): FrameSample[] {
  const frames: FrameSample[] = [];
  const hrHz = hrBpm / 60.0;
  const n = Math.floor(fps * durationS);
  for (let i = 0; i < n; i++) {
    const tMs = (i / fps) * 1000;
    const tS = i / fps;
    // Pulsatile green signal: DC offset + sinusoidal at HR frequency
    const signal = 130 + 15 * Math.sin(2 * Math.PI * hrHz * tS);
    // Simple pseudo-random noise (deterministic for reproducibility)
    const noiseVal = noise * 30 * (Math.sin(i * 1.7 + 2.3) + Math.sin(i * 3.1 + 0.7));
    // Slow baseline drift (simulates illumination change)
    const drift = 5 * Math.sin(2 * Math.PI * 0.05 * tS);
    const g = signal + noiseVal + drift;
    frames.push({ t_ms: tMs, r_mean: g * 1.05, g_mean: g, b_mean: g * 0.9 });
  }
  return frames;
}

// ─── processFrames ────────────────────────────────────────────────────────────

describe('processFrames', () => {
  // ── Insufficient data guards ─────────────────────────────────────────────

  it('returns null vitals for empty frame array', () => {
    const result = processFrames([]);
    expect(result.hr_bpm).toBeNull();
    expect(result.hrv_ms).toBeNull();
    expect(result.respiratory_rate).toBeNull();
    expect(result.flags).toContain('insufficient_frames');
  });

  it('returns null vitals for fewer than 30 frames', () => {
    const frames = makeSyntheticFrames(70, 2.0, 10.0); // ~20 frames
    const result = processFrames(frames);
    expect(result.hr_bpm).toBeNull();
    expect(result.flags).toContain('insufficient_frames');
  });

  it('returns null vitals for span < 8 seconds even with enough frames', () => {
    // 50 frames at very high fps but only 5 seconds of data
    const frames: FrameSample[] = Array.from({ length: 50 }, (_, i) => ({
      t_ms: i * 100, // 10 fps, 5 seconds total
      r_mean: 140,
      g_mean: 130 + 5 * Math.sin(i * 0.5),
      b_mean: 120,
    }));
    const result = processFrames(frames);
    expect(result.hr_bpm).toBeNull();
    expect(result.flags).toContain('insufficient_temporal_span');
  });

  it('returns null for a flat (no-signal) frame stream', () => {
    const frames: FrameSample[] = Array.from({ length: 60 }, (_, i) => ({
      t_ms: i * 500,
      r_mean: 130,
      g_mean: 130, // completely flat — no pulsatile signal
      b_mean: 115,
    }));
    const result = processFrames(frames);
    expect(result.hr_bpm).toBeNull();
    expect(result.flags.some(f => ['flat_signal', 'insufficient_peaks', 'low_signal_quality'].includes(f))).toBe(true);
  });

  // ── HR recovery ──────────────────────────────────────────────────────────

  it('recovers 60 bpm HR within ±10%', () => {
    const frames = makeSyntheticFrames(60, 2.0, 30.0, 0.05);
    const result = processFrames(frames);
    expect(result.hr_bpm).not.toBeNull();
    expect(result.hr_bpm!).toBeGreaterThanOrEqual(54);  // 60 − 10%
    expect(result.hr_bpm!).toBeLessThanOrEqual(66);    // 60 + 10%
  });

  it('recovers 75 bpm HR within ±10%', () => {
    // Use fps=30 so 75 bpm (1.25 Hz) is well below the Nyquist limit (15 Hz)
    // and is not aliased before upsampling to TARGET_FS (10 Hz).
    const frames = makeSyntheticFrames(75, 30.0, 30.0, 0.05);
    const result = processFrames(frames);
    expect(result.hr_bpm).not.toBeNull();
    expect(result.hr_bpm!).toBeGreaterThanOrEqual(67);
    expect(result.hr_bpm!).toBeLessThanOrEqual(83);
  });

  it('recovers 90 bpm HR within ±10%', () => {
    // Use fps=30 so 90 bpm (1.5 Hz) is well below the Nyquist limit (15 Hz)
    // and is not aliased before upsampling to TARGET_FS (10 Hz).
    const frames = makeSyntheticFrames(90, 30.0, 30.0, 0.05);
    const result = processFrames(frames);
    expect(result.hr_bpm).not.toBeNull();
    expect(result.hr_bpm!).toBeGreaterThanOrEqual(81);
    expect(result.hr_bpm!).toBeLessThanOrEqual(99);
  });

  // ── Output ranges ────────────────────────────────────────────────────────

  it('hr_bpm is always in [30, 220] when non-null', () => {
    for (const bpm of [45, 60, 80, 100, 120]) {
      const frames = makeSyntheticFrames(bpm, 2.0, 30.0, 0.05);
      const result = processFrames(frames);
      if (result.hr_bpm !== null) {
        expect(result.hr_bpm).toBeGreaterThanOrEqual(30);
        expect(result.hr_bpm).toBeLessThanOrEqual(220);
      }
    }
  });

  it('hrv_ms is non-negative when non-null', () => {
    const frames = makeSyntheticFrames(70, 2.0, 30.0, 0.05);
    const result = processFrames(frames);
    if (result.hrv_ms !== null) {
      expect(result.hrv_ms).toBeGreaterThanOrEqual(0);
    }
  });

  it('quality_score is in [0, 1]', () => {
    const frames = makeSyntheticFrames(70, 2.0, 30.0, 0.1);
    const result = processFrames(frames);
    expect(result.quality_score).toBeGreaterThanOrEqual(0);
    expect(result.quality_score).toBeLessThanOrEqual(1);
  });

  it('always includes low_framerate_upsampled flag for 2fps input', () => {
    const frames = makeSyntheticFrames(70, 2.0, 30.0, 0.05);
    const result = processFrames(frames);
    // Flag is always set since capture fps (2) < TARGET_FS (10)
    expect(result.flags).toContain('low_framerate_upsampled');
  });

  // ── No diagnostic language ───────────────────────────────────────────────

  it('contains no diagnostic language in flags or return type keys', () => {
    const frames = makeSyntheticFrames(70, 2.0, 30.0, 0.05);
    const result = processFrames(frames);
    const forbidden = ['diagnosis', 'diagnostic', 'disease', 'condition', 'disorder'];
    const allText = JSON.stringify(result);
    for (const word of forbidden) {
      expect(allText.toLowerCase()).not.toContain(word);
    }
  });
});

// ─── linearInterp ─────────────────────────────────────────────────────────────

describe('linearInterp', () => {
  it('returns original values at original x points', () => {
    const x = [0, 1, 2, 3];
    const y = [10, 20, 30, 40];
    const result = linearInterp(x, y, x);
    expect(result).toEqual([10, 20, 30, 40]);
  });

  it('interpolates midpoints correctly', () => {
    const x = [0, 2];
    const y = [0, 4];
    const result = linearInterp(x, y, [0, 0.5, 1, 1.5, 2]);
    expect(result[2]).toBeCloseTo(2.0, 5); // midpoint
    expect(result[1]).toBeCloseTo(1.0, 5);
  });

  it('handles single-segment arrays', () => {
    const result = linearInterp([0, 10], [100, 200], [0, 5, 10]);
    expect(result[0]).toBeCloseTo(100, 5);
    expect(result[1]).toBeCloseTo(150, 5);
    expect(result[2]).toBeCloseTo(200, 5);
  });
});

// ─── linearDetrend ────────────────────────────────────────────────────────────

describe('linearDetrend', () => {
  it('removes a pure linear trend completely', () => {
    // y = 2 + 3×i  →  detrend → near-zero
    const x = Array.from({ length: 20 }, (_, i) => 2 + 3 * i);
    const result = linearDetrend(x);
    for (const v of result) {
      expect(Math.abs(v)).toBeLessThan(1e-9);
    }
  });

  it('leaves zero-mean constant signal unchanged', () => {
    const x = [5, 5, 5, 5, 5];
    const result = linearDetrend(x);
    // Constant signal has zero slope → detrend subtracts the mean → all zeros
    for (const v of result) {
      expect(Math.abs(v)).toBeLessThan(1e-9);
    }
  });

  it('preserves sinusoidal component after trend removal', () => {
    // Signal = trend + sinusoid
    const n = 30;
    const x = Array.from({ length: n }, (_, i) => {
      const trend = 100 + 2 * i;
      const sin = 10 * Math.sin((2 * Math.PI * i) / 10);
      return trend + sin;
    });
    const result = linearDetrend(x);
    // After detrending, the sinusoidal component should dominate
    const stdResult = Math.sqrt(result.map(v => v * v).reduce((a, b) => a + b) / n);
    expect(stdResult).toBeGreaterThan(5); // sinusoid amplitude should be present
    expect(stdResult).toBeLessThan(20);  // trend should be gone
  });
});

// ─── filtfiltHP / filtfiltLP ──────────────────────────────────────────────────

describe('filtfiltHP', () => {
  const K_HP = Math.exp((-2 * Math.PI * 0.7) / 10);

  it('reduces DC component significantly', () => {
    // Pure DC offset → HP filter should nearly eliminate it
    const dc = Array.from({ length: 100 }, () => 50.0);
    const result = filtfiltHP(dc, K_HP);
    // After HP filter, mean of output should be close to 0
    const m = result.reduce((a, b) => a + b, 0) / result.length;
    expect(Math.abs(m)).toBeLessThan(5.0);
  });

  it('returns array of same length', () => {
    const x = Array.from({ length: 50 }, (_, i) => Math.sin(i));
    expect(filtfiltHP(x, K_HP).length).toBe(50);
  });
});

describe('filtfiltLP', () => {
  const ALPHA = 1 - Math.exp((-2 * Math.PI * 4.0) / 10);

  it('smooths high-frequency noise', () => {
    // Alternating high-freq noise (5 Hz at 10Hz FS = aliased)
    const x = Array.from({ length: 100 }, (_, i) => (i % 2 === 0 ? 1 : -1));
    const result = filtfiltLP(x, ALPHA);
    // RMS of filtered should be much lower than original
    const rmsOrig = Math.sqrt(1); // alternating ±1 → RMS=1
    const rmsFiltered = Math.sqrt(result.map(v => v * v).reduce((a, b) => a + b) / result.length);
    // First-order LP at 4 Hz / 10 Hz FS cannot attenuate Nyquist (5 Hz) to < 50%;
    // 0.85 is the realistic upper bound for this filter order and cutoff.
    expect(rmsFiltered).toBeLessThan(rmsOrig * 0.85);
  });

  it('returns array of same length', () => {
    const x = Array.from({ length: 50 }, (_, i) => Math.sin(i));
    expect(filtfiltLP(x, ALPHA).length).toBe(50);
  });
});

// ─── findPeaks ────────────────────────────────────────────────────────────────

describe('findPeaks', () => {
  it('finds a single peak in a simple triangle signal', () => {
    const x = [0, 1, 2, 3, 2, 1, 0];
    const peaks = findPeaks(x, 1, 0.1);
    expect(peaks).toContain(3);
  });

  it('respects minimum distance between peaks', () => {
    // Two peaks close together — only the first should survive with minDist=5
    const x = Array.from({ length: 20 }, (_, i) => {
      if (i === 3 || i === 5) return 10;
      return 0;
    });
    const peaks = findPeaks(x, 5, 0.01);
    // With minDist=5, only peak at idx 3 should be returned
    expect(peaks.length).toBe(1);
    expect(peaks[0]).toBe(3);
  });

  it('finds multiple peaks separated by minDist', () => {
    // Peaks at 5, 15, 25 (10 samples apart)
    const x = Array.from({ length: 30 }, (_, i) => {
      if ([5, 15, 25].includes(i)) return 1;
      return 0;
    });
    const peaks = findPeaks(x, 5, 0.01);
    expect(peaks.length).toBe(3);
  });

  it('returns empty array for monotonically increasing signal', () => {
    const x = Array.from({ length: 20 }, (_, i) => i);
    const peaks = findPeaks(x, 1, 0.01);
    expect(peaks.length).toBe(0);
  });

  it('returns empty array for flat signal', () => {
    const x = Array.from({ length: 20 }, () => 5);
    const peaks = findPeaks(x, 1, 0.01);
    expect(peaks.length).toBe(0);
  });
});
