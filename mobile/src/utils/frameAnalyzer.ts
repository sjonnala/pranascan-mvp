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

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
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
