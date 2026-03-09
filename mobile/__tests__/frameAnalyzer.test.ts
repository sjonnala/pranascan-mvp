/**
 * Unit tests for frameAnalyzer utilities.
 * These are pure functions — no mocking needed.
 */

import {
  buildFrameSample,
  computeFaceConfidence,
  computeLightingScore,
  computeMotionScore,
  computeOverallQualityScore,
} from '../src/utils/frameAnalyzer';

// ─── computeLightingScore ─────────────────────────────────────────────────────

describe('computeLightingScore', () => {
  it('returns 0 for empty string', () => {
    expect(computeLightingScore('')).toBe(0.0);
  });

  it('returns 0 for very short string (< 50 chars)', () => {
    expect(computeLightingScore('abc')).toBe(0.0);
  });

  it('returns 0 for a very dark frame (short JPEG)', () => {
    const darkFrame = 'A'.repeat(800); // well below JPEG_DARK_SIZE=1200
    expect(computeLightingScore(darkFrame)).toBe(0.0);
  });

  it('returns higher score for a longer (brighter) frame', () => {
    const dim = 'A'.repeat(2_000);
    const bright = 'A'.repeat(8_000);
    expect(computeLightingScore(bright)).toBeGreaterThan(computeLightingScore(dim));
  });

  it('returns 1 for a very large frame (above JPEG_BRIGHT_SIZE)', () => {
    const overexposed = 'A'.repeat(15_000);
    expect(computeLightingScore(overexposed)).toBe(1.0);
  });

  it('returns value in [0, 1] for any input', () => {
    const inputs = ['', 'x'.repeat(500), 'x'.repeat(5_000), 'x'.repeat(20_000)];
    for (const s of inputs) {
      const score = computeLightingScore(s);
      expect(score).toBeGreaterThanOrEqual(0.0);
      expect(score).toBeLessThanOrEqual(1.0);
    }
  });
});

// ─── computeMotionScore ───────────────────────────────────────────────────────

describe('computeMotionScore', () => {
  it('returns 1.0 when either string is empty', () => {
    expect(computeMotionScore('', 'abc')).toBe(1.0);
    expect(computeMotionScore('abc', '')).toBe(1.0);
    expect(computeMotionScore('', '')).toBe(1.0);
  });

  it('returns 1.0 for identical frames', () => {
    const frame = 'AbCdEfGhIjKlMnOpQrStUvWxYz1234'.repeat(200);
    expect(computeMotionScore(frame, frame)).toBe(1.0);
  });

  it('returns lower score when frames differ significantly', () => {
    const frameA = 'A'.repeat(5_000);
    const frameB = 'z'.repeat(5_000);
    const score = computeMotionScore(frameA, frameB);
    expect(score).toBeLessThan(1.0);
  });

  it('returns higher score for similar frames than very different ones', () => {
    const base = 'AbCdEfGh'.repeat(800);
    const similar = 'AbCdEfGi'.repeat(800); // 1 char difference per 8
    const different = 'zZzZzZzZ'.repeat(800);
    expect(computeMotionScore(base, similar)).toBeGreaterThan(
      computeMotionScore(base, different),
    );
  });

  it('returns value in [0, 1] for any pair', () => {
    const pairs: [string, string][] = [
      ['A'.repeat(3000), 'B'.repeat(3000)],
      ['A'.repeat(3000), 'A'.repeat(5000)],
      ['x'.repeat(100), 'y'.repeat(100)],
    ];
    for (const [a, b] of pairs) {
      const score = computeMotionScore(a, b);
      expect(score).toBeGreaterThanOrEqual(0.0);
      expect(score).toBeLessThanOrEqual(1.0);
    }
  });
});

// ─── buildFrameSample ─────────────────────────────────────────────────────────

describe('buildFrameSample', () => {
  it('returns a FrameSample with correct t_ms', () => {
    const sample = buildFrameSample('A'.repeat(5_000), 1500);
    expect(sample.t_ms).toBe(1500);
  });

  it('returns r_mean, g_mean, b_mean all in [0, 255]', () => {
    const inputs = [
      'A'.repeat(500),
      'A'.repeat(5_000),
      'A'.repeat(15_000),
    ];
    for (const b64 of inputs) {
      const s = buildFrameSample(b64, 0);
      expect(s.r_mean).toBeGreaterThanOrEqual(0);
      expect(s.r_mean).toBeLessThanOrEqual(255);
      expect(s.g_mean).toBeGreaterThanOrEqual(0);
      expect(s.g_mean).toBeLessThanOrEqual(255);
      expect(s.b_mean).toBeGreaterThanOrEqual(0);
      expect(s.b_mean).toBeLessThanOrEqual(255);
    }
  });

  it('brighter frame produces higher channel means', () => {
    const dim = buildFrameSample('A'.repeat(2_000), 0);
    const bright = buildFrameSample('A'.repeat(10_000), 0);
    expect(bright.g_mean).toBeGreaterThan(dim.g_mean);
    expect(bright.r_mean).toBeGreaterThan(dim.r_mean);
  });

  it('applies skin-tone channel bias (r >= g >= b)', () => {
    const sample = buildFrameSample('A'.repeat(6_000), 0);
    expect(sample.r_mean).toBeGreaterThanOrEqual(sample.g_mean);
    expect(sample.g_mean).toBeGreaterThanOrEqual(sample.b_mean);
  });
});

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

// ─── computeFaceConfidence ────────────────────────────────────────────────────

describe('computeFaceConfidence', () => {
  // ── Fallback for bad input ─────────────────────────────────────────────

  it('returns 0.5 (uncertain) for empty string', () => {
    expect(computeFaceConfidence('', 0.5, 1.0)).toBe(0.5);
  });

  it('returns 0.5 (uncertain) for a string shorter than 50 chars', () => {
    expect(computeFaceConfidence('A'.repeat(30), 0.5, 1.0)).toBe(0.5);
  });

  // ── Range guarantee ────────────────────────────────────────────────────

  it('returns value in [0, 1] for any valid combination of inputs', () => {
    const lightings = [0.0, 0.1, 0.25, 0.5, 0.88, 1.0];
    const motions = [0.0, 0.5, 0.95, 1.0];
    const sizes = [100, 1_000, 3_500, 6_000, 9_500, 14_000];
    for (const l of lightings) {
      for (const m of motions) {
        for (const s of sizes) {
          const conf = computeFaceConfidence('A'.repeat(s), l, m);
          expect(conf).toBeGreaterThanOrEqual(0.0);
          expect(conf).toBeLessThanOrEqual(1.0);
        }
      }
    }
  });

  // ── Good-scan pass (≥ 0.80 gate) ──────────────────────────────────────

  it('returns ≥ 0.80 for a well-lit, face-sized, steady frame', () => {
    // lighting=0.7 (well-lit), size=6 000 (optimal zone), motion=1.0
    const conf = computeFaceConfidence('A'.repeat(6_000), 0.7, 1.0);
    expect(conf).toBeGreaterThanOrEqual(0.8);
  });

  it('returns ≥ 0.80 for the lower edge of the lighting window', () => {
    // lighting=0.25 is just inside the optimal zone
    const conf = computeFaceConfidence('A'.repeat(5_000), 0.25, 1.0);
    expect(conf).toBeGreaterThanOrEqual(0.8);
  });

  it('returns ≥ 0.80 for a large-but-reasonable frame (face still likely)', () => {
    // size=9 500 = upper bound of optimal zone
    const conf = computeFaceConfidence('A'.repeat(9_500), 0.7, 1.0);
    expect(conf).toBeGreaterThanOrEqual(0.8);
  });

  // ── Poor-condition fail (< 0.80 gate) ─────────────────────────────────

  it('returns < 0.80 for a very dark, tiny frame (no face detectable)', () => {
    // size=600 → lighting≈0.037 (well below dark threshold)
    const conf = computeFaceConfidence('A'.repeat(600), 0.037, 1.0);
    expect(conf).toBeLessThan(0.8);
  });

  it('returns < 0.80 when lighting is below 0.20 regardless of frame size', () => {
    const conf = computeFaceConfidence('A'.repeat(6_000), 0.05, 1.0);
    expect(conf).toBeLessThan(0.8);
  });

  it('returns < 0.80 for an over-exposed, blown-out frame', () => {
    // lighting=1.0 (fully blown out), very large JPEG
    const conf = computeFaceConfidence('A'.repeat(14_000), 1.0, 1.0);
    expect(conf).toBeLessThan(0.8);
  });

  // ── Sensitivity ────────────────────────────────────────────────────────

  it('scores an optimal-zone frame higher than a sub-optimal small frame', () => {
    // dim: size=2 000 is below FACE_SIZE_MIN (3 500) → sizeComponent < 1
    // bright: size=6 500 is inside the optimal zone → sizeComponent = 1
    const dim = computeFaceConfidence('A'.repeat(2_000), 0.3, 1.0);
    const bright = computeFaceConfidence('A'.repeat(6_500), 0.65, 1.0);
    expect(bright).toBeGreaterThan(dim);
  });

  it('steady frame scores higher than a high-motion frame (minor bonus)', () => {
    const base64 = 'A'.repeat(6_000);
    const lighting = 0.7;
    const steady = computeFaceConfidence(base64, lighting, 1.0);
    const moving = computeFaceConfidence(base64, lighting, 0.0);
    expect(steady).toBeGreaterThan(moving);
    // Bonus is minor (max 0.10) — not a primary gate dimension
    expect(steady - moving).toBeLessThanOrEqual(0.11);
  });

  // ── Not a constant ────────────────────────────────────────────────────

  it('is NOT a constant — different inputs produce different scores', () => {
    const goodFrame = computeFaceConfidence('A'.repeat(6_000), 0.7, 1.0);
    const darkFrame = computeFaceConfidence('A'.repeat(800), 0.05, 0.3);
    expect(goodFrame).not.toBeCloseTo(darkFrame, 1);
  });
});

// ─── No diagnostic language ───────────────────────────────────────────────────

describe('no diagnostic language in frameAnalyzer', () => {
  it('function names and return values contain no diagnostic terms', () => {
    const sample = buildFrameSample('A'.repeat(5_000), 100);
    const keys = Object.keys(sample);
    const forbidden = ['diagnosis', 'diagnostic', 'disease', 'condition', 'disorder'];
    for (const key of keys) {
      for (const word of forbidden) {
        expect(key.toLowerCase()).not.toContain(word);
      }
    }
  });
});
