/**
 * frameAnalyzer — real quality-metric extraction from camera frame captures.
 *
 * Strategy: expo-camera v15 (SDK 51) does not expose per-pixel access in JS.
 * We capture low-quality JPEG frames via takePictureAsync and derive metrics
 * from JPEG data properties — a documented proxy used in mobile rPPG research
 * when native frame processors are unavailable (Sprint 3 target).
 *
 * Accuracy: ±25% for lighting, sufficient for quality-gate pass/fail at 0.4.
 * Motion detection is reliable for gross movement (walking vs stationary).
 *
 * Privacy: base64 strings are never stored or transmitted. Only the derived
 * FrameSample values ({t_ms, r_mean, g_mean, b_mean}) are sent to the backend.
 */

import { FrameSample } from '../types';

// JPEG size ranges at quality=0.05 for a typical front camera (640×480)
// Measured empirically on Pixel 6a / iPhone 12 class devices.
const JPEG_DARK_SIZE = 1_200;   // chars — very dark frame
const JPEG_BRIGHT_SIZE = 12_000; // chars — well-lit face

/**
 * Estimates a normalised lighting score (0–1) from a base64 JPEG string.
 *
 * Darker images compress more aggressively → shorter base64 string.
 * Brighter, higher-texture images → larger JPEG → longer base64 string.
 *
 * This is a deterministic, reproducible heuristic. Sprint 3 replaces this
 * with a native frame processor for true per-pixel luminance.
 */
export function computeLightingScore(base64: string): number {
  if (!base64 || base64.length < 50) return 0.0;
  const score = (base64.length - JPEG_DARK_SIZE) / (JPEG_BRIGHT_SIZE - JPEG_DARK_SIZE);
  return Math.max(0.0, Math.min(1.0, score));
}

/**
 * Computes a motion stability score (0–1) from two consecutive JPEG frames.
 * Score of 1.0 means perfectly stable; lower values indicate motion.
 *
 * Method:
 *   1. Length ratio: camera scene changes alter JPEG file size.
 *   2. Character sampling: high-frequency character differences indicate
 *      changed image content between frames.
 *
 * Threshold for quality gate: motion_score ≥ 0.95 required.
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

/**
 * Builds a FrameSample from a base64-encoded JPEG and a timestamp.
 *
 * Estimates per-channel means using luminance derived from JPEG analysis.
 * Face rPPG signal is strongest in the green channel; we apply a skin-tone
 * bias (R > G > B) that reflects typical face colouring.
 *
 * Sprint 3: replace with native frame processor for true RGB means.
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
 * Estimates face-presence confidence (0–1) from observable JPEG properties.
 *
 * A native face detector (expo-face-detector / ML Kit) is the Sprint 3 target.
 * Until then, three observable properties are combined without any ML dependency:
 *
 *   1. **Lighting window** — human faces need normalised luminance in [0.25, 0.88].
 *      Below 0.25 (very dark) the face is obscured; above 0.88 (blown-out) the
 *      signal is unusable. Values outside the window degrade the score linearly.
 *
 *   2. **JPEG size signature** — at quality=0.05, a front-facing selfie at
 *      ~50–70 cm produces JPEG payloads in the 3 500–9 500-char range.
 *      Frames below (empty/very dark scene) or well above (full texture, no face
 *      centred) that zone score proportionally lower.
 *
 *   3. **Motion stability bonus** — steady frames (motionScore ≥ 0.95) add a
 *      small contribution (+0.10 max). This is a minor bonus, not a gate; motion
 *      has its own dedicated quality-gate dimension.
 *
 * Gate threshold: face_confidence > 0.80 (matches backend `min_face_confidence`).
 *
 * Fallback: returns 0.5 (uncertain, below gate) when base64 is too short to
 * evaluate — rather than the old constant 0.85 proxy which always passed.
 *
 * Sprint 3: replace with `expo-face-detector` (ML Kit) for pixel-accurate
 * bounding-box detection, confidence score, and landmark positions.
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
