import { MaterialIcons } from '@expo/vector-icons';
import React, { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import {
  getCurrentVitalityStreak,
  getLatestVitalityReport,
  getScanHistory,
} from '../api/client';
import { PranaPulseReveal } from '../components/pranapulse/PranaPulseReveal';
import { PranaPulseScaffold } from '../components/pranapulse/PranaPulseScaffold';
import { ScanHistoryPage, VitalityReport, VitalityStreak } from '../types';
import { pranaPulseShadow, pranaPulseTheme, withAlpha } from '../theme/pranaPulse';

interface HomeScreenProps {
  displayName?: string | null;
  onStartDailyGlow: () => void;
  onOpenScanModes: () => void;
  onOpenCircle: () => void;
  onOpenResults: () => void;
}

function formatMetric(value: number | null | undefined, unit: string): string {
  if (value == null) {
    return `-- ${unit}`;
  }
  const fixed = Math.abs(value) >= 10 ? value.toFixed(0) : value.toFixed(1);
  return `${fixed} ${unit}`;
}

function takeFirstSentence(text: string | null | undefined, fallback: string): string {
  if (!text?.trim()) return fallback;
  const sentence = text.split('. ')[0]?.trim();
  return sentence ? `${sentence.replace(/\.$/, '')}.` : fallback;
}

function describeDelta(value: number | null | undefined, unit: string, label: string): string | null {
  if (value == null || value === 0) return null;
  const amount = Math.abs(value);
  const formatted = amount >= 10 ? amount.toFixed(0) : amount.toFixed(1);
  return `${label} ${value > 0 ? 'up' : 'down'} ${formatted} ${unit}`;
}

const CAM_BG = '#1C2118';

export function HomeScreen({
  displayName,
  onStartDailyGlow,
  onOpenScanModes,
  onOpenCircle,
  onOpenResults,
}: HomeScreenProps) {
  const [history, setHistory] = useState<ScanHistoryPage | null>(null);
  const [report, setReport] = useState<VitalityReport | null>(null);
  const [streak, setStreak] = useState<VitalityStreak | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;
    (async () => {
      try {
        const [historyData, streakData, reportData] = await Promise.all([
          getScanHistory(1, 3),
          getCurrentVitalityStreak(),
          getLatestVitalityReport(),
        ]);
        if (!isMounted) return;
        setHistory(historyData);
        setStreak(streakData);
        setReport(reportData);
      } catch {
        if (isMounted) {
          setError('Home insights are temporarily unavailable. You can still start a Daily Glow scan.');
        }
      } finally {
        if (isMounted) setIsLoading(false);
      }
    })();
    return () => { isMounted = false; };
  }, []);

  const latestResult = history?.items[0]?.result;
  const firstName = useMemo(() => {
    const trimmed = displayName?.trim();
    return trimmed ? trimmed.split(/\s+/)[0] : 'there';
  }, [displayName]);

  const trendTitle =
    describeDelta(report?.delta_hrv_ms ?? history?.items[0]?.hrv_trend_delta, 'ms', 'HRV') ??
    describeDelta(report?.delta_hr_bpm ?? history?.items[0]?.hr_trend_delta, 'bpm', 'Heart rate') ??
    (report?.scan_count
      ? `${report.scan_count} scans in your current window`
      : `${formatMetric(latestResult?.hrv_ms, 'ms')} recovery rhythm`);

  const trendCopy = report?.summary_text?.trim()
    ? takeFirstSentence(report.summary_text, 'Review how your recent scans are moving together.')
    : history?.items[0]?.hrv_trend_delta != null
      ? `Recent check-ins show ${history.items[0].hrv_trend_delta > 0 ? 'more recovery headroom' : 'a softer recovery rhythm'} than your previous window.`
      : 'Review how your recent scans are moving together.';

  return (
    <PranaPulseScaffold
      activeTab="home"
      onCirclePress={onOpenCircle}
      onHomePress={() => undefined}
      onResultsPress={onOpenResults}
      onScanPress={onOpenScanModes}
      profileLabel={displayName ?? 'P'}
    >
      {/* ── Section header row ── */}
      <PranaPulseReveal delay={10}>
        <View style={styles.sectionHeaderRow}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <Text style={styles.sectionTitle}>Daily Balance</Text>
            {isLoading ? <ActivityIndicator color={pranaPulseTheme.colors.primary} size="small" /> : null}
          </View>
          <View style={styles.scanModePill}>
            <Text style={styles.scanModeText}>30s rPPG Scan</Text>
          </View>
        </View>
      </PranaPulseReveal>

      {/* ── Face scan viewfinder (tappable → launches live scan) ── */}
      <PranaPulseReveal delay={70}>
        <TouchableOpacity
          activeOpacity={0.94}
          onPress={onStartDailyGlow}
          style={styles.viewfinderCard}
          testID="home-face-scan-preview"
        >
          <View style={styles.cameraCanvas}>
            {/* subtle ambient glows */}
            <View style={styles.cameraGlowTop} />
            <View style={styles.cameraGlowBottom} />

            {/* DETECTION ACTIVE badge */}
            <View style={styles.detectionBadge}>
              <View style={styles.detectionDot} />
              <Text style={styles.detectionText}>DETECTION ACTIVE</Text>
            </View>

            {/* Face oval guide ring */}
            <View pointerEvents="none" style={styles.faceOvalOuter}>
              <View style={styles.faceOvalInner} />
            </View>

            {/* Begin Face Scan pill at bottom */}
            <View style={styles.scanCtaRow}>
              <View style={styles.scanCtaButton}>
                <MaterialIcons color={pranaPulseTheme.colors.onPrimary} name="videocam" size={18} />
                <Text style={styles.scanCtaText}>Begin Face Scan</Text>
              </View>
            </View>
          </View>
        </TouchableOpacity>
      </PranaPulseReveal>

      {error ? <Text style={styles.inlineError}>{error}</Text> : null}

      {/* ── Metric chips ── */}
      <PranaPulseReveal delay={160}>
        <View style={styles.metricGrid}>
          <View style={styles.metricCard}>
            <View style={styles.metricHeader}>
              <View style={[styles.metricIconShell, styles.metricIconPrimary]}>
                <MaterialIcons color={pranaPulseTheme.colors.primary} name="favorite" size={16} />
              </View>
              <Text style={styles.metricEyebrow}>Resting HR</Text>
            </View>
            <Text style={styles.metricValue}>{formatMetric(latestResult?.hr_bpm, 'bpm')}</Text>
            <Text style={styles.metricCopy}>Latest check-in heart rhythm.</Text>
          </View>

          <View style={styles.metricCard}>
            <View style={styles.metricHeader}>
              <View style={[styles.metricIconShell, styles.metricIconSecondary]}>
                <MaterialIcons color={pranaPulseTheme.colors.secondary} name="air" size={16} />
              </View>
              <Text style={styles.metricEyebrow}>Breath</Text>
            </View>
            <Text style={styles.metricValue}>{formatMetric(latestResult?.respiratory_rate, 'rpm')}</Text>
            <Text style={styles.metricCopy}>Breathing cadence from the same check-in.</Text>
          </View>
        </View>
      </PranaPulseReveal>

      {/* ── Weekly Deep Dive section ── */}
      <PranaPulseReveal delay={220}>
        <View style={styles.deepDiveSectionRow}>
          <Text style={styles.sectionTitle}>Weekly Deep Dive</Text>
          <Text style={styles.deepDiveBadge}>Full Biomarker Sync</Text>
        </View>

        <TouchableOpacity
          activeOpacity={0.9}
          onPress={onOpenScanModes}
          style={styles.deepDiveCard}
          testID="home-deep-dive-card"
        >
          <View style={styles.deepDiveIconShell}>
            <MaterialIcons color={pranaPulseTheme.colors.secondary} name="fingerprint" size={36} />
          </View>
          <Text style={styles.deepDiveTitle}>Contact-PPG Thumb Scan</Text>
          <Text style={styles.deepDiveCopy}>
            60-second thumb-press for pulse-wave morphology and stiffness index.
          </Text>
          <View style={styles.deepDiveChipRow}>
            <View style={styles.deepDiveChip}>
              <MaterialIcons color={pranaPulseTheme.colors.secondary} name="flash-on" size={12} />
              <Text style={styles.deepDiveChipText}>Torch assist</Text>
            </View>
            <View style={styles.deepDiveChip}>
              <MaterialIcons color={pranaPulseTheme.colors.primary} name="timeline" size={12} />
              <Text style={styles.deepDiveChipText}>Morphology</Text>
            </View>
          </View>
        </TouchableOpacity>
      </PranaPulseReveal>

      {/* ── Streak / Trend support cards ── */}
      <PranaPulseReveal delay={290}>
        <View style={styles.supportStack}>
          <View style={[styles.supportCard, styles.supportCardSage]}>
            <Text style={styles.supportEyebrow}>Glow Streak</Text>
            <Text style={styles.supportTitle}>
              {streak?.currentStreakDays != null
                ? `${streak.currentStreakDays} days in rhythm`
                : 'Start today'}
            </Text>
            <Text style={styles.supportCopy}>
              {streak?.status === 'AT_RISK'
                ? 'A quick check-in today keeps your pattern intact.'
                : 'Repeated morning scans build the clearest picture of your baseline.'}
            </Text>
          </View>

          <TouchableOpacity onPress={onOpenResults} style={styles.supportCard}>
            <Text style={styles.supportEyebrow}>Trend Lab</Text>
            <Text style={styles.supportTitle}>{trendTitle}</Text>
            <Text style={styles.supportCopy}>{trendCopy}</Text>
          </TouchableOpacity>
        </View>
      </PranaPulseReveal>
    </PranaPulseScaffold>
  );
}

const styles = StyleSheet.create({
  // ── Section headers ──
  sectionHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 14,
  },
  sectionTitle: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 22,
    letterSpacing: -0.4,
  },
  scanModePill: {
    borderRadius: pranaPulseTheme.radius.full,
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.62),
  },
  scanModeText: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.primary,
    fontSize: 11,
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },

  // ── Face scan viewfinder ──
  viewfinderCard: {
    borderRadius: 28,
    overflow: 'hidden',
    marginBottom: 16,
    ...pranaPulseShadow,
  },
  cameraCanvas: {
    backgroundColor: CAM_BG,
    height: 330,
    justifyContent: 'center',
    alignItems: 'center',
    position: 'relative',
  },
  cameraGlowTop: {
    position: 'absolute',
    top: -20,
    left: -20,
    width: 200,
    height: 200,
    borderRadius: 100,
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.16),
  },
  cameraGlowBottom: {
    position: 'absolute',
    bottom: -24,
    right: -24,
    width: 220,
    height: 220,
    borderRadius: 110,
    backgroundColor: withAlpha(pranaPulseTheme.colors.secondaryContainer, 0.12),
  },
  detectionBadge: {
    position: 'absolute',
    top: 14,
    left: 16,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: withAlpha('#000000', 0.42),
    borderRadius: pranaPulseTheme.radius.full,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  detectionDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: '#4CAF50',
  },
  detectionText: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: '#FFFFFF',
    fontSize: 10,
    letterSpacing: 1.2,
  },
  faceOvalOuter: {
    width: 200,
    height: 248,
    borderRadius: 124,
    borderWidth: 2,
    borderColor: withAlpha('#FFFFFF', 0.52),
    alignItems: 'center',
    justifyContent: 'center',
  },
  faceOvalInner: {
    width: 182,
    height: 230,
    borderRadius: 115,
    borderWidth: 1,
    borderColor: withAlpha('#FFFFFF', 0.2),
  },
  scanCtaRow: {
    position: 'absolute',
    bottom: 18,
    left: 0,
    right: 0,
    alignItems: 'center',
  },
  scanCtaButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderRadius: pranaPulseTheme.radius.full,
    backgroundColor: withAlpha(pranaPulseTheme.colors.primary, 0.9),
    paddingHorizontal: 24,
    paddingVertical: 14,
  },
  scanCtaText: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onPrimary,
    fontSize: 15,
    letterSpacing: -0.1,
  },

  // ── Metric chips ──
  metricGrid: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 20,
  },
  metricCard: {
    flex: 1,
    borderRadius: pranaPulseTheme.radius.md,
    padding: 18,
    backgroundColor: pranaPulseTheme.colors.surfaceContainerLowest,
    ...pranaPulseShadow,
  },
  metricHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 12,
  },
  metricIconShell: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  metricIconPrimary: {
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.46),
  },
  metricIconSecondary: {
    backgroundColor: withAlpha(pranaPulseTheme.colors.secondaryContainer, 0.56),
  },
  metricEyebrow: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 11,
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  metricValue: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 24,
    marginBottom: 4,
    letterSpacing: -0.6,
  },
  metricCopy: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 12,
    lineHeight: 18,
  },

  // ── Weekly Deep Dive ──
  deepDiveSectionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 12,
  },
  deepDiveBadge: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.secondary,
    fontSize: 11,
    letterSpacing: 0.5,
  },
  deepDiveCard: {
    borderRadius: pranaPulseTheme.radius.lg,
    backgroundColor: pranaPulseTheme.colors.surfaceContainerLowest,
    padding: 24,
    alignItems: 'center',
    gap: 10,
    marginBottom: 16,
    ...pranaPulseShadow,
  },
  deepDiveIconShell: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: withAlpha(pranaPulseTheme.colors.secondaryContainer, 0.52),
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 4,
  },
  deepDiveTitle: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 17,
    textAlign: 'center',
  },
  deepDiveCopy: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 13,
    lineHeight: 20,
    textAlign: 'center',
    maxWidth: 270,
  },
  deepDiveChipRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 4,
  },
  deepDiveChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    borderRadius: pranaPulseTheme.radius.full,
    paddingHorizontal: 12,
    paddingVertical: 7,
    backgroundColor: pranaPulseTheme.colors.surfaceContainer,
  },
  deepDiveChipText: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 11,
  },

  // ── Support cards ──
  supportStack: {
    gap: 12,
  },
  supportCard: {
    borderRadius: pranaPulseTheme.radius.md,
    padding: 20,
    backgroundColor: pranaPulseTheme.colors.surfaceContainerLow,
  },
  supportCardSage: {
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.44),
  },
  supportEyebrow: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 11,
    letterSpacing: 1,
    textTransform: 'uppercase',
    marginBottom: 10,
  },
  supportTitle: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 21,
    lineHeight: 28,
    marginBottom: 8,
  },
  supportCopy: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 14,
    lineHeight: 22,
  },

  inlineError: {
    color: pranaPulseTheme.colors.error,
    fontSize: 13,
    lineHeight: 20,
    textAlign: 'center',
    marginBottom: 14,
  },
});
