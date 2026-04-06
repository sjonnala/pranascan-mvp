/**
 * QualityGate component — shows real-time scan quality feedback.
 *
 * Displays a colour-coded indicator for each quality dimension
 * and a "Retry" option if any gate fails.
 */

import { MaterialIcons } from '@expo/vector-icons';
import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { pranaPulseShadow, pranaPulseTheme, withAlpha } from '../theme/pranaPulse';
import { QualityFlag, QualityGateResult, ScanType } from '../types';

const SKIP_QUALITY_GATE = process.env.EXPO_PUBLIC_SKIP_QUALITY_GATE === 'true';

const FLAG_LABELS: Record<QualityFlag, string> = {
  low_lighting: 'Move to a brighter area',
  borderline_lighting: 'Lighting is borderline but still usable',
  motion_detected: 'Hold your phone steady',
  face_not_detected: 'Position your face in the frame',
  partial_occlusion_suspected: 'Face is partially occluded',
  poor_thumb_contact: 'Cover the camera and flash fully with your thumb',
  borderline_thumb_contact: 'Thumb contact is usable but could be tighter',
  low_signal_quality: 'Pulse signal quality is weak',
  height_required_for_stiffness_index: 'Height is required to calculate the Stiffness Index',
  insufficient_cycles_for_morphology: 'Not enough stable pulse cycles were captured',
  morphology_peaks_not_found: 'Pulse-wave landmarks were not detected clearly',
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
  const passed = SKIP_QUALITY_GATE || score > threshold;
  const percent = Math.max(4, Math.round(score * 100));

  return (
    <View style={styles.indicatorCard} testID={`quality-indicator-${label}`}>
      <View style={styles.indicatorHeader}>
        <View style={styles.indicatorLabelRow}>
          <View style={[styles.dot, passed ? styles.dotGood : styles.dotBad]} />
          <Text style={styles.indicatorLabel}>{label}</Text>
        </View>
        <Text style={[styles.indicatorScore, passed ? styles.textGood : styles.textBad]}>{percent}%</Text>
      </View>
      <View style={styles.progressTrack}>
        <View
          style={[
            styles.progressValue,
            passed ? styles.progressValueGood : styles.progressValueBad,
            { width: `${percent}%` as `${number}%` },
          ]}
        />
      </View>
    </View>
  );
}

interface QualityGateProps {
  quality: QualityGateResult;
  scanType?: ScanType;
  onRetry?: () => void;
  testID?: string;
}

export function QualityGate({ quality, scanType = 'standard', onRetry, testID }: QualityGateProps) {
  const { passed, flags, metrics, overallScore } = quality;
  const tertiaryLabel = scanType === 'deep_dive' ? 'Contact' : 'Face';
  const overallLabel = SKIP_QUALITY_GATE ? 'Bypassed' : `${Math.round(overallScore * 100)}%`;

  return (
    <View style={styles.container} testID={testID ?? 'quality-gate'}>
      <View style={styles.headerRow}>
        <View style={styles.headerCopy}>
          <Text style={styles.title}>Capture Check</Text>
          <Text style={styles.subtitle}>
            {scanType === 'deep_dive'
              ? 'Keep firm thumb contact while the pulse trace settles.'
              : 'Stay steady and let the ghost guide hold your alignment.'}
          </Text>
        </View>

        <View style={[styles.overallPill, passed ? styles.overallPillGood : styles.overallPillBad]}>
          <MaterialIcons
            color={passed ? pranaPulseTheme.colors.primary : pranaPulseTheme.colors.secondary}
            name={passed ? 'verified' : 'pending'}
            size={16}
          />
          <Text style={[styles.overallScore, passed ? styles.textGood : styles.textBad]}>{overallLabel}</Text>
        </View>
      </View>

      <View style={styles.indicatorStack}>
        <QualityIndicator label="Lighting" score={metrics.lighting_score} threshold={0.4} />
        <QualityIndicator label="Steady" score={metrics.motion_score} threshold={0.95} />
        <QualityIndicator label={tertiaryLabel} score={metrics.face_confidence} threshold={0.8} />
      </View>

      {SKIP_QUALITY_GATE && (
        <View style={styles.banner} testID="quality-gate-bypassed">
          <MaterialIcons color={pranaPulseTheme.colors.primary} name="science" size={16} />
          <Text style={styles.bannerText}>Local testing mode keeps the scan moving.</Text>
        </View>
      )}

      {!passed && flags.length > 0 && (
        <View style={styles.flagsContainer} testID="quality-flags">
          {flags.map((flag) => (
            <View key={flag} style={styles.flagRow}>
              <MaterialIcons color={pranaPulseTheme.colors.secondary} name="warning-amber" size={16} />
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
        <View style={styles.banner} testID="quality-passed">
          <MaterialIcons color={pranaPulseTheme.colors.primary} name="check-circle" size={16} />
          <Text style={styles.bannerText}>
            {SKIP_QUALITY_GATE ? 'Local testing mode active' : 'Capture quality looks good'}
          </Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderRadius: pranaPulseTheme.radius.md,
    padding: 16,
    marginHorizontal: 16,
    backgroundColor: withAlpha(pranaPulseTheme.colors.surfaceContainerLowest, 0.94),
    borderWidth: 1,
    borderColor: withAlpha(pranaPulseTheme.colors.outlineVariant, 0.28),
    ...pranaPulseShadow,
  },
  headerRow: {
    flexDirection: 'row',
    gap: 12,
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    marginBottom: 14,
  },
  headerCopy: {
    flex: 1,
    gap: 4,
  },
  title: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    fontSize: 16,
    color: pranaPulseTheme.colors.onSurface,
  },
  subtitle: {
    fontFamily: pranaPulseTheme.fonts.medium,
    fontSize: 12,
    lineHeight: 18,
    color: pranaPulseTheme.colors.onSurfaceVariant,
  },
  overallPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: pranaPulseTheme.radius.full,
  },
  overallPillGood: {
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.72),
  },
  overallPillBad: {
    backgroundColor: withAlpha(pranaPulseTheme.colors.secondaryContainer, 0.8),
  },
  overallScore: {
    fontFamily: pranaPulseTheme.fonts.bold,
    fontSize: 12,
  },
  indicatorStack: {
    gap: 10,
  },
  indicatorCard: {
    borderRadius: 18,
    padding: 12,
    backgroundColor: pranaPulseTheme.colors.surfaceContainer,
  },
  indicatorHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  indicatorLabelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  dot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  dotGood: {
    backgroundColor: '#4ade80',
  },
  dotBad: {
    backgroundColor: '#f87171',
  },
  indicatorLabel: {
    fontFamily: pranaPulseTheme.fonts.bold,
    fontSize: 13,
    color: pranaPulseTheme.colors.onSurface,
  },
  indicatorScore: {
    fontFamily: pranaPulseTheme.fonts.bold,
    fontSize: 12,
  },
  textGood: {
    color: pranaPulseTheme.colors.primary,
  },
  textBad: {
    color: pranaPulseTheme.colors.secondary,
  },
  progressTrack: {
    width: '100%',
    height: 7,
    borderRadius: 999,
    overflow: 'hidden',
    backgroundColor: withAlpha(pranaPulseTheme.colors.surfaceDim, 0.72),
  },
  progressValue: {
    height: '100%',
    borderRadius: 999,
  },
  progressValueGood: {
    backgroundColor: pranaPulseTheme.colors.primary,
  },
  progressValueBad: {
    backgroundColor: pranaPulseTheme.colors.secondary,
  },
  flagsContainer: {
    marginTop: 14,
    gap: 8,
    borderRadius: 18,
    padding: 12,
    backgroundColor: withAlpha(pranaPulseTheme.colors.secondaryContainer, 0.46),
  },
  flagRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  flagText: {
    flex: 1,
    fontFamily: pranaPulseTheme.fonts.medium,
    fontSize: 12,
    lineHeight: 18,
    color: pranaPulseTheme.colors.onSurface,
  },
  retryButton: {
    marginTop: 14,
    borderRadius: pranaPulseTheme.radius.full,
    paddingVertical: 13,
    alignItems: 'center',
    backgroundColor: pranaPulseTheme.colors.primary,
  },
  retryText: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onPrimary,
    fontSize: 15,
  },
  banner: {
    marginTop: 14,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    borderRadius: 18,
    paddingHorizontal: 12,
    paddingVertical: 10,
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.42),
  },
  bannerText: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.primary,
    fontSize: 12,
  },
});
