/**
 * frameAnalyzer — quality-metric and frame-sample utilities for the Vision Camera pipeline.
 *
 * All functions operate on pre-extracted centre-ROI RGB means that come from
 * the `extractCenterRoiAverage` worklet inside CameraCapture.tsx.  The worklet
 * reads raw pixel bytes directly from the Vision Camera frame buffer at 30 FPS
 * (standard) or up to 60 FPS (Deep Dive), so there is no JPEG round-trip and
 * no expo-camera dependency.
 *
 * Privacy: only per-frame RGB mean values leave the worklet — never full pixel
 * buffers or video frames.  Only FrameSample objects ({t_ms, r_mean, g_mean,
 * b_mean}) are sent to the backend.
 */

import { FrameSample } from '../types';

export interface RgbTraceSample {
  r_mean: number;
  g_mean: number;
  b_mean: number;
}

function clamp01(value: number): number {
  return Math.max(0.0, Math.min(1.0, value));
}

/**
 * Maps a centre-ROI RGB sample to a normalised lighting score.
 *
 * We use perceptual luminance so the score reflects apparent brightness
 * instead of a single channel. The 0.4 gate threshold maps well to a
 * mid-bright face ROI under ordinary indoor lighting.
 */
export function computeLightingScoreFromRgb(sample: RgbTraceSample): number {
  const luminance = 0.299 * sample.r_mean + 0.587 * sample.g_mean + 0.114 * sample.b_mean;
  return clamp01(luminance / 255.0);
}

/**
 * Estimates motion stability from successive centre-ROI colour means.
 *
 * Large frame-to-frame RGB deltas usually indicate head motion, ROI drift, or
 * lighting flicker. The score stays near 1.0 when the ROI is stable.
 */
export function computeMotionScoreFromRgb(
  previous: RgbTraceSample | null,
  current: RgbTraceSample,
): number {
  if (!previous) return 1.0;

  const delta =
    (Math.abs(current.r_mean - previous.r_mean) +
      Math.abs(current.g_mean - previous.g_mean) +
      Math.abs(current.b_mean - previous.b_mean)) /
    3.0;

  return clamp01(1.0 - delta / 60.0);
}

/**
 * Builds a FrameSample from already-aggregated ROI RGB means.
 */
export function buildFrameSampleFromRgb(sample: RgbTraceSample, tMs: number): FrameSample {
  return {
    t_ms: tMs,
    r_mean: sample.r_mean,
    g_mean: sample.g_mean,
    b_mean: sample.b_mean,
  };
}

/**
 * Heuristic face-presence confidence without a dedicated face detector.
 *
 * This remains a soft quality hint, not a detection claim. It rewards
 * plausible skin-channel balance, sufficient brightness, and steady capture.
 */
export function computeFaceConfidenceFromRgb(
  sample: RgbTraceSample,
  lightingScore: number,
  motionScore: number,
): number {
  const rgGap = Math.abs(sample.r_mean - sample.g_mean);
  const gbGap = Math.abs(sample.g_mean - sample.b_mean);
  const colourBalance = clamp01(1.0 - (rgGap + gbGap) / 160.0);

  const raw = 0.05 + lightingScore * 0.5 + motionScore * 0.35 + colourBalance * 0.15;
  return clamp01(raw);
}

// ---------------------------------------------------------------------------
// Legacy JPEG-based functions (kept for test coverage only)
//
// These functions were part of the old expo-camera JPEG-capture pipeline that
// was replaced by the Vision Camera frame-processor approach. They are no
// longer called by any production code. They are retained here solely so that
// the existing test suite in __tests__/frameAnalyzer.test.ts continues to
// pass without modification.
//
// Do NOT use these in new features. The canonical replacements are:
//   computeLightingScore  → computeLightingScoreFromRgb
//   computeMotionScore    → computeMotionScoreFromRgb
//   buildFrameSample      → buildFrameSampleFromRgb
//   computeFaceConfidence → computeFaceConfidenceFromRgb
// ---------------------------------------------------------------------------

// JPEG size ranges at quality=0.05 for a typical front camera (640×480)
// Measured empirically on Pixel 6a / iPhone 12 class devices.
const JPEG_DARK_SIZE = 1_200;   // chars — very dark frame
const JPEG_BRIGHT_SIZE = 12_000; // chars — well-lit face

/**
 * @deprecated Use {@link computeLightingScoreFromRgb} instead.
 * Legacy heuristic: estimates lighting from JPEG base64 string length.
 * Retained for backward-compatibility with existing tests only.
 */
export function computeLightingScore(base64: string): number {
  if (!base64 || base64.length < 50) return 0.0;
  const score = (base64.length - JPEG_DARK_SIZE) / (JPEG_BRIGHT_SIZE - JPEG_DARK_SIZE);
  return Math.max(0.0, Math.min(1.0, score));
}

/**
 * @deprecated Use {@link computeMotionScoreFromRgb} instead.
 * Legacy heuristic: estimates motion from consecutive JPEG base64 strings.
 * Retained for backward-compatibility with existing tests only.
 */
export function computeMotionScore(prevBase64: string, currBase64: string): number {
  if (!prevBase64 || !currBase64 || prevBase64.length < 50 || currBase64.length < 50) {
    return 1.0; // no comparison possible → assume stable
  }

  const lenA = prevBase64.length;
  const lenB = currBase64.length;

  // Length ratio component (0–1): files with similar lengths → similar scene
  const lengthRatio = Math.min(lenA, lenB) / Math.max(lenA, lenB);

  // Character diff component: sample 64 positions spread across the string
  const sampleCount = 64;
  const minLen = Math.min(lenA, lenB);
  let diffSum = 0;
  for (let i = 0; i < sampleCount; i++) {
    const pos = Math.floor((i / sampleCount) * minLen);
    diffSum += Math.abs(prevBase64.charCodeAt(pos) - currBase64.charCodeAt(pos));
  }
  // Max possible diff per char: 122 ('z') - 43 ('+') = 79 in base64 alphabet
  const maxDiff = sampleCount * 79;
  const charSimilarity = 1.0 - Math.min(1.0, diffSum / maxDiff);

  // Weighted combination: character diff is more sensitive to actual content change
  const raw = lengthRatio * 0.3 + charSimilarity * 0.7;
  return Math.max(0.0, Math.min(1.0, raw));
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}

/**
 * @deprecated Use {@link buildFrameSampleFromRgb} instead.
 * Legacy: builds a FrameSample from a base64 JPEG using a luminance heuristic.
 * Retained for backward-compatibility with existing tests only.
 */
export function buildFrameSample(base64: string, tMs: number): FrameSample {
  const luminance = computeLightingScore(base64) * 255;

  // Skin-tone channel bias
  const g_mean = luminance;
  const r_mean = Math.min(255, luminance * 1.1);
  const b_mean = Math.min(255, luminance * 0.85);

  return { t_ms: tMs, r_mean, g_mean, b_mean };
}

/**
 * @deprecated Use {@link computeFaceConfidenceFromRgb} instead.
 * Legacy heuristic: estimates face confidence from JPEG base64 properties.
 * Retained for backward-compatibility with existing tests only.
 */
export function computeFaceConfidence(
  base64: string,
  lightingScore: number,
  motionScore: number,
): number {
  // Insufficient data → uncertain; return below-gate value rather than faking a pass.
  if (!base64 || base64.length < 50) return 0.5;

  // ── 1. Lighting window ───────────────────────────────────────────────────
  // Optimal face zone: [0.25, 0.88].  Ramp linearly outside it.
  let lightComponent: number;
  if (lightingScore < 0.25) {
    // Dim/dark: score from 0 at total darkness up to 0.60 at lower edge of window.
    lightComponent = (lightingScore / 0.25) * 0.6;
  } else if (lightingScore <= 0.88) {
    lightComponent = 1.0;
  } else {
    // Over-exposed: still likely a face but rPPG signal is degraded.
    // Ramp from 1.0 at 0.88 down to 0.5 at 1.0.
    lightComponent = 1.0 - ((lightingScore - 0.88) / 0.12) * 0.5;
  }

  // ── 2. JPEG size signature ───────────────────────────────────────────────
  // Face-at-selfie-distance zone: 3 500–9 500 chars at quality=0.05.
  const FACE_SIZE_MIN = 3_500;
  const FACE_SIZE_OPT_MAX = 9_500;
  const len = base64.length;
  let sizeComponent: number;
  if (len >= FACE_SIZE_MIN && len <= FACE_SIZE_OPT_MAX) {
    sizeComponent = 1.0;
  } else if (len < FACE_SIZE_MIN) {
    // Frame too small → very dark/empty scene; no face likely.
    sizeComponent = len / FACE_SIZE_MIN;
  } else {
    // Larger frame → over-exposed or highly textured scene.
    // Clamp floor at 0.4 (face may still be present, just over-lit).
    sizeComponent = Math.max(0.4, 1.0 - (len - FACE_SIZE_OPT_MAX) / FACE_SIZE_OPT_MAX);
  }

  // ── 3. Motion stability bonus ────────────────────────────────────────────
  // Max bonus: 0.10.  Degraded smoothly below the 0.95 gate threshold.
  const stabilityBonus = Math.min(motionScore / 0.95, 1.0) * 0.1;

  // ── Weighted combination ─────────────────────────────────────────────────
  // lightComponent (55%) + sizeComponent (35%) + stabilityBonus (up to 10%)
  const raw = lightComponent * 0.55 + sizeComponent * 0.35 + stabilityBonus;
  return Math.max(0.0, Math.min(1.0, raw));
}

/**
 * Computes an overall quality score from a collected set of frame samples.
 * Used to produce the final quality_score submitted with the scan result.
 */
export function computeOverallQualityScore(
  lightingScore: number,
  motionScore: number,
  faceConfidence: number,
  audioSnrDb: number,
): number {
  const snrNorm = Math.min(audioSnrDb / 40.0, 1.0);
  return Math.max(
    0,
    Math.min(1, lightingScore * 0.3 + motionScore * 0.3 + faceConfidence * 0.3 + snrNorm * 0.1),
  );
}

export interface AggregatedQualityMetrics {
  lighting_score: number;
  motion_score: number;
  face_confidence: number;
}

/**
 * Summarises per-frame quality into one stable scan-level snapshot.
 *
 * We use robust aggregation instead of the final frame only, because one bad
 * frame near the end of the 30-second capture can otherwise reject an
 * otherwise-usable scan.
 */
export function aggregateQualityMetrics(
  lightingScores: number[],
  motionScores: number[],
  faceConfidences: number[],
): AggregatedQualityMetrics {
  const lighting_score = lightingScores.length > 0 ? median(lightingScores) : 0.5;
  const face_confidence = faceConfidences.length > 0 ? median(faceConfidences) : 0.5;

  let motion_score = motionScores.length > 0 ? median(motionScores) : 1.0;
  if (motionScores.length > 0 && isTransientMotion(motionScores)) {
    const stableScores = motionScores.filter((score) => score >= 0.95);
    if (stableScores.length > 0) {
      motion_score = median(stableScores);
    }
  }

  return {
    lighting_score,
    motion_score,
    face_confidence,
  };
}

// ---------------------------------------------------------------------------
// D26 Bug bash — edge case detection helpers
// ---------------------------------------------------------------------------

/**
 * Occlusion hint values returned by detectOcclusionHint().
 * These are advisory only — never block a scan.
 */
export type OcclusionHint = 'glasses_suspected' | 'beard_suspected' | null;

/**
 * Detects potential partial face occlusion from JPEG properties.
 *
 * Heuristic: glasses and thick frames add high-frequency texture to a selfie,
 * producing a larger JPEG than expected for the measured luminance level.
 * Beards add a low-luminance region that skews the size/brightness ratio.
 *
 *   glasses_suspected : size-to-luminance ratio unusually HIGH
 *                       (high texture at mid-to-low luminance)
 *   beard_suspected   : very low lighting score but non-trivially large frame
 *                       (dark lower face region)
 *   null              : no clear occlusion signal
 *
 * Sprint 3: replace with ML Kit face landmark detection.
 *
 * @param base64        - base64-encoded JPEG string
 * @param lightingScore - normalised lighting score [0, 1] from computeLightingScore()
 */
export function detectOcclusionHint(base64: string, lightingScore: number): OcclusionHint {
  if (!base64 || base64.length < 50) return null;

  const len = base64.length;

  // Expected JPEG size for this luminance level using the linear size model
  const expectedSize = JPEG_DARK_SIZE + lightingScore * (JPEG_BRIGHT_SIZE - JPEG_DARK_SIZE);
  const sizeRatio = len / Math.max(expectedSize, 1);

  // Glasses produce a JPEG roughly 40–100% larger than expected for the
  // luminance level (lenses, frames, reflections add high-frequency texture).
  if (sizeRatio > 1.4 && lightingScore > 0.2 && lightingScore < 0.85) {
    return 'glasses_suspected';
  }

  // Beard: dark lower-face region → low luminance score but JPEG still
  // moderately sized because the beard has texture.
  if (lightingScore < 0.30 && len > JPEG_DARK_SIZE * 2.5) {
    return 'beard_suspected';
  }

  return null;
}

/**
 * Determines whether detected motion was transient (short-lived and recoverable).
 *
 * A scan is considered to have recovered from motion when:
 *   - ≥ 2/3 of frame motion scores are above the stable threshold, AND
 *   - the low-motion frames are concentrated at the START or END of the scan
 *     (not distributed throughout), meaning the user settled quickly.
 *
 * This avoids rejecting scans where the user moved briefly at the beginning
 * (repositioning) or at the very end (lowering the phone).
 *
 * @param motionScores  - array of per-frame motion scores in capture order
 * @param stableThreshold - score above which a frame is considered stable (default 0.95)
 * @returns true if motion was transient and the scan should be considered recoverable
 */
export function isTransientMotion(
  motionScores: number[],
  stableThreshold: number = 0.95,
): boolean {
  if (motionScores.length < 6) return false; // not enough frames to judge

  const stableCount = motionScores.filter(s => s >= stableThreshold).length;
  const stableFraction = stableCount / motionScores.length;

  // Must be mostly stable overall
  if (stableFraction < 0.65) return false;

  // Check if unstable frames are concentrated in the outer 25% (start or end)
  const edgeFrames = Math.max(2, Math.floor(motionScores.length * 0.25));
  const middleScores = motionScores.slice(edgeFrames, motionScores.length - edgeFrames);
  const middleStableFraction =
    middleScores.filter(s => s >= stableThreshold).length / Math.max(middleScores.length, 1);

  // Middle section should be fully stable if motion was only edge-transient
  return middleStableFraction >= 0.90;
}
