/**
 * useQualityCheck hook — evaluates real-time scan quality metrics.
 */

import { useState, useCallback } from 'react';
import { QualityFlag, QualityGateResult, QualityMetrics, ScanType } from '../types';

const SKIP_QUALITY_GATE = process.env.EXPO_PUBLIC_SKIP_QUALITY_GATE === 'true';

// Thresholds must match backend config
const THRESHOLDS = {
  lighting_score: 0.4,
  motion_score: 0.95,
  face_confidence: 0.8,
  audio_snr_db: 15.0,
} as const;

export function evaluateQuality(
  metrics: QualityMetrics,
  scanType: ScanType = 'standard',
): QualityGateResult {
  if (SKIP_QUALITY_GATE) {
    return {
      passed: true,
      flags: [],
      metrics,
      overallScore: 1.0,
    };
  }

  const flags: QualityFlag[] = [];

  if (metrics.lighting_score <= THRESHOLDS.lighting_score) {
    flags.push('low_lighting');
  }
  if (metrics.motion_score < THRESHOLDS.motion_score) {
    flags.push('motion_detected');
  }
  if (scanType === 'deep_dive') {
    if (metrics.face_confidence <= THRESHOLDS.face_confidence) {
      flags.push('poor_thumb_contact');
    }
  } else {
    if (metrics.face_confidence <= THRESHOLDS.face_confidence) {
      flags.push('face_not_detected');
    }
    if (metrics.audio_snr_db <= THRESHOLDS.audio_snr_db) {
      flags.push('high_noise');
    }
  }

  const overallScore =
    scanType === 'deep_dive'
      ? metrics.lighting_score * 0.4 + metrics.motion_score * 0.35 + metrics.face_confidence * 0.25
      : metrics.lighting_score * 0.3 +
        metrics.motion_score * 0.3 +
        metrics.face_confidence * 0.3 +
        Math.min(metrics.audio_snr_db / 40, 1.0) * 0.1;

  return {
    passed: flags.length === 0,
    flags,
    metrics,
    overallScore: Math.min(Math.max(overallScore, 0), 1),
  };
}

export interface UseQualityCheckReturn {
  quality: QualityGateResult | null;
  updateMetrics: (metrics: QualityMetrics, scanType?: ScanType) => void;
  reset: () => void;
}

export function useQualityCheck(): UseQualityCheckReturn {
  const [quality, setQuality] = useState<QualityGateResult | null>(null);

  const updateMetrics = useCallback((metrics: QualityMetrics, scanType: ScanType = 'standard') => {
    setQuality(evaluateQuality(metrics, scanType));
  }, []);

  const reset = useCallback(() => {
    setQuality(null);
  }, []);

  return { quality, updateMetrics, reset };
}
