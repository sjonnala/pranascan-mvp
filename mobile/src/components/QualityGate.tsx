/**
 * QualityGate component — shows real-time scan quality feedback.
 *
 * Displays a colour-coded indicator for each quality dimension
 * and a "Retry" option if any gate fails.
 */

import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { QualityFlag, QualityGateResult } from '../types';

const FLAG_LABELS: Record<QualityFlag, string> = {
  low_lighting: 'Move to a brighter area',
  borderline_lighting: 'Lighting is borderline but still usable',
  motion_detected: 'Hold your phone steady',
  face_not_detected: 'Position your face in the frame',
  partial_occlusion_suspected: 'Face is partially occluded',
  high_noise: 'Find a quieter environment',
  borderline_noise: 'Audio is usable but a bit noisy',
  accented_vowel_accommodated: 'Voice captured with accent accommodation',
  partial_scan: 'Keep still for the full duration',
};

interface QualityIndicatorProps {
  label: string;
  score: number;
  threshold: number;
}

function QualityIndicator({ label, score, threshold }: QualityIndicatorProps) {
  const passed = score > threshold;
  return (
    <View style={styles.indicatorRow} testID={`quality-indicator-${label}`}>
      <View style={[styles.dot, passed ? styles.dotGood : styles.dotBad]} />
      <Text style={styles.indicatorLabel}>{label}</Text>
      <Text style={[styles.indicatorScore, passed ? styles.textGood : styles.textBad]}>
        {(score * 100).toFixed(0)}%
      </Text>
    </View>
  );
}

interface QualityGateProps {
  quality: QualityGateResult;
  onRetry?: () => void;
  testID?: string;
}

export function QualityGate({ quality, onRetry, testID }: QualityGateProps) {
  const { passed, flags, metrics, overallScore } = quality;

  return (
    <View style={styles.container} testID={testID ?? 'quality-gate'}>
      <Text style={styles.title}>Scan Quality</Text>

      <View style={styles.overallRow}>
        <Text style={styles.overallLabel}>Overall</Text>
        <Text style={[styles.overallScore, passed ? styles.textGood : styles.textBad]}>
          {(overallScore * 100).toFixed(0)}%
        </Text>
      </View>

      <QualityIndicator label="Lighting" score={metrics.lighting_score} threshold={0.4} />
      <QualityIndicator label="Steady" score={metrics.motion_score} threshold={0.95} />
      <QualityIndicator label="Face" score={metrics.face_confidence} threshold={0.8} />

      {!passed && flags.length > 0 && (
        <View style={styles.flagsContainer} testID="quality-flags">
          {flags.map((flag) => (
            <View key={flag} style={styles.flagRow}>
              <Text style={styles.flagEmoji}>⚠️</Text>
              <Text style={styles.flagText}>{FLAG_LABELS[flag]}</Text>
            </View>
          ))}
        </View>
      )}

      {!passed && onRetry && (
        <TouchableOpacity style={styles.retryButton} onPress={onRetry} testID="retry-button">
          <Text style={styles.retryText}>Try Again</Text>
        </TouchableOpacity>
      )}

      {passed && (
        <View style={styles.passedBanner} testID="quality-passed">
          <Text style={styles.passedText}>✓ Good quality — scan in progress</Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#1a1a2e',
    borderRadius: 16,
    padding: 20,
    marginHorizontal: 16,
  },
  title: {
    fontSize: 16,
    fontWeight: '600',
    color: '#ffffff',
    marginBottom: 12,
  },
  overallRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 12,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#2a2a4e',
  },
  overallLabel: {
    fontSize: 14,
    color: '#aaaacc',
  },
  overallScore: {
    fontSize: 18,
    fontWeight: '700',
  },
  indicatorRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  dot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    marginRight: 10,
  },
  dotGood: {
    backgroundColor: '#4ade80',
  },
  dotBad: {
    backgroundColor: '#f87171',
  },
  indicatorLabel: {
    flex: 1,
    fontSize: 14,
    color: '#ccccee',
  },
  indicatorScore: {
    fontSize: 13,
    fontWeight: '600',
  },
  textGood: {
    color: '#4ade80',
  },
  textBad: {
    color: '#f87171',
  },
  flagsContainer: {
    marginTop: 12,
    padding: 12,
    backgroundColor: '#2a1a1a',
    borderRadius: 8,
  },
  flagRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 6,
  },
  flagEmoji: {
    marginRight: 8,
  },
  flagText: {
    color: '#ffccaa',
    fontSize: 13,
  },
  retryButton: {
    marginTop: 16,
    backgroundColor: '#4f46e5',
    borderRadius: 12,
    paddingVertical: 12,
    alignItems: 'center',
  },
  retryText: {
    color: '#ffffff',
    fontWeight: '600',
    fontSize: 16,
  },
  passedBanner: {
    marginTop: 12,
    backgroundColor: '#052e16',
    borderRadius: 8,
    padding: 10,
    alignItems: 'center',
  },
  passedText: {
    color: '#4ade80',
    fontWeight: '600',
    fontSize: 14,
  },
});
