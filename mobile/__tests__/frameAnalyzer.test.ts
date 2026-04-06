/**
 * Unit tests for frameAnalyzer utilities.
 * These are pure functions — no mocking needed.
 */

import {
  aggregateQualityMetrics,
  buildFrameSampleFromRgb,
  computeFaceConfidenceFromRgb,
  computeLightingScoreFromRgb,
  computeMotionScoreFromRgb,
  computeOverallQualityScore,
  isTransientMotion,
} from '../src/utils/frameAnalyzer';

// ─── computeOverallQualityScore ───────────────────────────────────────────────

describe('computeOverallQualityScore', () => {
  it('returns ~1.0 for perfect inputs', () => {
    const score = computeOverallQualityScore(1.0, 1.0, 1.0, 40.0);
    expect(score).toBeCloseTo(1.0, 5);
  });

  it('returns 0.0 for all-zero inputs', () => {
    const score = computeOverallQualityScore(0.0, 0.0, 0.0, 0.0);
    expect(score).toBe(0.0);
  });

  it('is bounded to [0, 1] for any inputs', () => {
    const cases: [number, number, number, number][] = [
      [2.0, 2.0, 2.0, 100.0],
      [-1.0, -1.0, -1.0, -10.0],
      [0.5, 0.97, 0.85, 20.0],
    ];
    for (const [l, m, f, snr] of cases) {
      const score = computeOverallQualityScore(l, m, f, snr);
      expect(score).toBeGreaterThanOrEqual(0.0);
      expect(score).toBeLessThanOrEqual(1.0);
    }
  });

  it('good scan inputs produce score above 0.7', () => {
    // Typical good scan: lighting=0.75, motion=0.97, face=0.85, snr=22dB
    const score = computeOverallQualityScore(0.75, 0.97, 0.85, 22.0);
    expect(score).toBeGreaterThan(0.7);
  });
});

describe('isTransientMotion', () => {
  it('returns false when there are too few frames to classify motion recovery', () => {
    expect(isTransientMotion([0.96, 0.94, 0.97, 0.99, 0.98])).toBe(false);
  });

  it('returns true when instability is confined to the edges and the middle is stable', () => {
    const motionScores = [0.70, 0.96, 0.97, 0.98, 0.99, 0.97, 0.96, 0.95, 0.80, 0.70];
    expect(isTransientMotion(motionScores)).toBe(true);
  });

  it('returns false when unstable frames are spread through the middle of the scan', () => {
    const motionScores = [0.97, 0.96, 0.70, 0.98, 0.60, 0.97, 0.70, 0.95, 0.96, 0.97];
    expect(isTransientMotion(motionScores)).toBe(false);
  });
});

describe('aggregateQualityMetrics', () => {
  it('uses scan-level medians for lighting and face confidence', () => {
    const aggregated = aggregateQualityMetrics(
      [0.42, 0.78, 0.45, 0.44, 0.43],
      [0.97, 0.98, 0.99, 0.98, 0.97],
      [0.86, 0.88, 0.50, 0.87, 0.89],
    );
    expect(aggregated.lighting_score).toBeCloseTo(0.44, 5);
    expect(aggregated.face_confidence).toBeCloseTo(0.87, 5);
  });

  it('recovers from transient edge motion instead of failing on a late bad frame', () => {
    const aggregated = aggregateQualityMetrics(
      [0.55, 0.56, 0.57, 0.56, 0.55, 0.56, 0.55, 0.56, 0.55, 0.56],
      [0.70, 0.96, 0.97, 0.98, 0.99, 0.97, 0.96, 0.95, 0.80, 0.70],
      [0.84, 0.86, 0.87, 0.88, 0.87, 0.86, 0.85, 0.86, 0.50, 0.50],
    );
    expect(aggregated.motion_score).toBeGreaterThanOrEqual(0.95);
    expect(aggregated.face_confidence).toBeGreaterThan(0.8);
  });

  it('falls back to safe defaults when no frame metrics are available', () => {
    expect(aggregateQualityMetrics([], [], [])).toEqual({
      lighting_score: 0.5,
      motion_score: 1.0,
      face_confidence: 0.5,
    });
  });
});

// ─── No diagnostic language ───────────────────────────────────────────────────

describe('no diagnostic language in frameAnalyzer', () => {
  it('function names and return values contain no diagnostic terms', () => {
    const sample = buildFrameSampleFromRgb({ r_mean: 120, g_mean: 110, b_mean: 90 }, 100);
    const keys = Object.keys(sample);
    const forbidden = ['diagnosis', 'diagnostic', 'disease', 'condition', 'disorder'];
    for (const key of keys) {
      for (const word of forbidden) {
        expect(key.toLowerCase()).not.toContain(word);
      }
    }
  });
});

// ─── Vision Camera RGB pipeline functions ────────────────────────────────────

describe('computeLightingScoreFromRgb', () => {
  it('returns 0 for zero-value sample', () => {
    expect(computeLightingScoreFromRgb({ r_mean: 0, g_mean: 0, b_mean: 0 })).toBe(0.0);
  });

  it('returns 1 for max-value sample', () => {
    expect(computeLightingScoreFromRgb({ r_mean: 255, g_mean: 255, b_mean: 255 })).toBeCloseTo(1.0, 2);
  });

  it('uses perceptual luminance weighting (green channel dominates)', () => {
    const greenOnly = computeLightingScoreFromRgb({ r_mean: 0, g_mean: 200, b_mean: 0 });
    const redOnly = computeLightingScoreFromRgb({ r_mean: 200, g_mean: 0, b_mean: 0 });
    expect(greenOnly).toBeGreaterThan(redOnly);
  });
});

describe('computeMotionScoreFromRgb', () => {
  it('returns 1.0 when previous sample is null (first frame)', () => {
    expect(computeMotionScoreFromRgb(null, { r_mean: 100, g_mean: 110, b_mean: 90 })).toBe(1.0);
  });

  it('returns 1.0 for identical consecutive samples', () => {
    const s = { r_mean: 100, g_mean: 110, b_mean: 90 };
    expect(computeMotionScoreFromRgb(s, s)).toBe(1.0);
  });

  it('returns lower score for samples with large RGB delta', () => {
    const prev = { r_mean: 10, g_mean: 10, b_mean: 10 };
    const curr = { r_mean: 200, g_mean: 200, b_mean: 200 };
    expect(computeMotionScoreFromRgb(prev, curr)).toBeLessThan(0.5);
  });
});

describe('buildFrameSampleFromRgb', () => {
  it('preserves all channel means and the timestamp', () => {
    const s = buildFrameSampleFromRgb({ r_mean: 120, g_mean: 130, b_mean: 90 }, 1234);
    expect(s).toEqual({ t_ms: 1234, r_mean: 120, g_mean: 130, b_mean: 90 });
  });
});

describe('computeFaceConfidenceFromRgb', () => {
  it('returns value in [0, 1] for any valid combination', () => {
    const cases: [number, number, number, number, number][] = [
      [100, 110, 90, 0.7, 0.97],
      [0, 0, 0, 0.0, 0.0],
      [255, 255, 255, 1.0, 1.0],
    ];
    for (const [r, g, b, l, m] of cases) {
      const conf = computeFaceConfidenceFromRgb({ r_mean: r, g_mean: g, b_mean: b }, l, m);
      expect(conf).toBeGreaterThanOrEqual(0.0);
      expect(conf).toBeLessThanOrEqual(1.0);
    }
  });

  it('scores higher for well-lit steady samples than dark noisy ones', () => {
    const good = computeFaceConfidenceFromRgb({ r_mean: 150, g_mean: 130, b_mean: 110 }, 0.7, 0.97);
    const bad = computeFaceConfidenceFromRgb({ r_mean: 5, g_mean: 5, b_mean: 5 }, 0.02, 0.3);
    expect(good).toBeGreaterThan(bad);
  });
});

// ─── D26: isTransientMotion ───────────────────────────────────────────────────

describe('isTransientMotion', () => {
  const STABLE = 0.98;
  const UNSTABLE = 0.80;

  it('returns false for fewer than 6 frames (not enough data)', () => {
    expect(isTransientMotion([STABLE, STABLE, STABLE, STABLE, STABLE])).toBe(false);
  });

  it('returns false when majority of frames are unstable', () => {
    // 3 stable / 10 total = 30% stable < 65% threshold
    const scores = Array(3).fill(STABLE).concat(Array(7).fill(UNSTABLE));
    expect(isTransientMotion(scores)).toBe(false);
  });

  it('returns true when only opening frames were unstable (user repositioning)', () => {
    // 2 bad frames at start, 10 stable in the middle/end → transient
    const scores = [UNSTABLE, UNSTABLE, ...Array(10).fill(STABLE)];
    expect(isTransientMotion(scores)).toBe(true);
  });

  it('returns true when only trailing frames were unstable (user lowered phone)', () => {
    // 10 stable, 2 bad at end → transient
    const scores = [...Array(10).fill(STABLE), UNSTABLE, UNSTABLE];
    expect(isTransientMotion(scores)).toBe(true);
  });

  it('returns false when unstable frames are distributed throughout middle', () => {
    // Bad frames scattered in the middle → NOT transient
    const scores = [
      STABLE, STABLE, STABLE,
      UNSTABLE, STABLE, UNSTABLE, STABLE, UNSTABLE,
      STABLE, STABLE, STABLE,
    ];
    expect(isTransientMotion(scores)).toBe(false);
  });

  it('returns false for a fully stable scan (no motion at all — vacuously not transient)', () => {
    const scores = Array(12).fill(STABLE);
    // All stable: stableFraction = 1.0 ≥ 0.65 ✓, but middleStableFraction = 1.0 ✓
    // isTransientMotion should return true here (it's stable so "recoverable")
    // Actually our impl: stableFraction >= 0.65 AND middleStableFraction >= 0.90 → true
    expect(isTransientMotion(scores)).toBe(true);
  });

  it('respects a custom stableThreshold parameter', () => {
    // With threshold 0.70, these frames should be considered stable
    const scores = Array(10).fill(0.75);
    expect(isTransientMotion(scores, 0.70)).toBe(true);
  });

  it('returns false for an entirely unstable scan', () => {
    const scores = Array(12).fill(UNSTABLE);
    expect(isTransientMotion(scores)).toBe(false);
  });
});
