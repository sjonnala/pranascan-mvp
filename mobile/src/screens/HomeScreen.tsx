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
  if (!text?.trim()) {
    return fallback;
  }

  const sentence = text.split('. ')[0]?.trim();
  return sentence ? `${sentence.replace(/\.$/, '')}.` : fallback;
}

function describeDelta(value: number | null | undefined, unit: string, label: string): string | null {
  if (value == null || value === 0) {
    return null;
  }

  const amount = Math.abs(value);
  const formatted = amount >= 10 ? amount.toFixed(0) : amount.toFixed(1);
  return `${label} ${value > 0 ? 'up' : 'down'} ${formatted} ${unit}`;
}

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

        if (!isMounted) {
          return;
        }

        setHistory(historyData);
        setStreak(streakData);
        setReport(reportData);
      } catch {
        if (isMounted) {
          setError('Home insights are temporarily unavailable. You can still start a Daily Glow scan.');
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    })();

    return () => {
      isMounted = false;
    };
  }, []);

  const latestResult = history?.items[0]?.result;
  const firstName = useMemo(() => {
    const trimmed = displayName?.trim();
    return trimmed ? trimmed.split(/\s+/)[0] : 'there';
  }, [displayName]);

  const heroSummary = takeFirstSentence(
    report?.summary_text,
    'Take a moment to align your rhythm before the day accelerates.'
  );
  const trendTitle =
    describeDelta(report?.delta_hrv_ms ?? history?.items[0]?.hrv_trend_delta, 'ms', 'HRV') ??
    describeDelta(report?.delta_hr_bpm ?? history?.items[0]?.hr_trend_delta, 'bpm', 'Heart rate') ??
    (report?.scan_count ? `${report.scan_count} scans in your current window` : `${formatMetric(latestResult?.hrv_ms, 'ms')} recovery rhythm`);
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
      <PranaPulseReveal delay={10}>
        <View style={styles.heroSection}>
          <View style={styles.heroLabelRow}>
            <Text style={styles.eyebrow}>Daily Glow</Text>
            {isLoading ? <ActivityIndicator color={pranaPulseTheme.colors.primary} size="small" /> : null}
          </View>
          <Text style={styles.heroTitle}>Morning Vitality</Text>
          <Text style={styles.heroSubtitle}>{`Good to see you, ${firstName}. ${heroSummary}`}</Text>
        </View>
      </PranaPulseReveal>

      <PranaPulseReveal delay={90}>
        <View style={styles.viewfinderShell}>
          <View style={styles.frameOutline} />
          <View style={[styles.corner, styles.cornerTopLeft]} />
          <View style={[styles.corner, styles.cornerTopRight]} />
          <View style={[styles.corner, styles.cornerBottomLeft]} />
          <View style={[styles.corner, styles.cornerBottomRight]} />

          <View style={styles.viewfinderInner}>
            <View style={styles.previewGlowSage} />
            <View style={styles.previewGlowSunset} />

            <View style={styles.previewBadgeRow}>
              <Text style={styles.previewEyebrow}>30s video + voice</Text>
              <View style={styles.previewBadge}>
                <Text style={styles.previewBadgeText}>Warm / Soft-UI</Text>
              </View>
            </View>

            <View style={styles.waveOrb}>
              <View style={styles.waveRing} />
              <View style={styles.waveStack}>
                <View style={[styles.waveLine, styles.waveLineWide]} />
                <View style={[styles.waveLine, styles.waveLineMid]} />
                <View style={[styles.waveLine, styles.waveLineShort]} />
              </View>
              <Text style={styles.waveCount}>30s</Text>
              <Text style={styles.waveState}>Aligning</Text>
            </View>

            <Text style={styles.previewCopy}>
              Follow the ghost guide, breathe with the wave, and let Daily Glow capture your steady baseline.
            </Text>
          </View>
        </View>
      </PranaPulseReveal>

      <PranaPulseReveal delay={150}>
        <View>
          <TouchableOpacity onPress={onStartDailyGlow} style={styles.primaryButton}>
            <Text style={styles.primaryButtonText}>Start Daily Glow</Text>
          </TouchableOpacity>

          <TouchableOpacity onPress={onOpenScanModes} style={styles.secondaryLink}>
            <Text style={styles.secondaryLinkText}>Explore scan modes</Text>
          </TouchableOpacity>
        </View>
      </PranaPulseReveal>

      {error ? <Text style={styles.inlineError}>{error}</Text> : null}

      <PranaPulseReveal delay={230}>
        <View style={styles.metricGrid}>
          <View style={styles.metricCard}>
            <View style={styles.metricHeader}>
              <View style={[styles.metricIconShell, styles.metricIconPrimary]}>
                <MaterialIcons color={pranaPulseTheme.colors.primary} name="favorite" size={16} />
              </View>
              <Text style={styles.metricEyebrow}>Resting HR</Text>
            </View>
            <Text style={styles.metricValue}>{formatMetric(latestResult?.hr_bpm, 'bpm')}</Text>
            <Text style={styles.metricCopy}>Latest Daily Glow heart rhythm snapshot.</Text>
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

      <PranaPulseReveal delay={300}>
        <View style={styles.supportStack}>
          <View style={[styles.supportCard, styles.supportCardSage]}>
            <Text style={styles.supportEyebrow}>Glow Streak</Text>
            <Text style={styles.supportTitle}>
              {streak?.currentStreakDays != null ? `${streak.currentStreakDays} days in rhythm` : 'Start today'}
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
  heroSection: {
    alignItems: 'center',
    gap: 8,
    marginBottom: 18,
  },
  heroLabelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  eyebrow: {
    ...pranaPulseTheme.type.eyebrow,
    color: pranaPulseTheme.colors.primary,
  },
  heroTitle: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 34,
    letterSpacing: -0.9,
    textAlign: 'center',
  },
  heroSubtitle: {
    ...pranaPulseTheme.type.body,
    maxWidth: 320,
    textAlign: 'center',
  },
  viewfinderShell: {
    position: 'relative',
    width: '100%',
    maxWidth: 332,
    aspectRatio: 1,
    alignSelf: 'center',
    marginBottom: 26,
    justifyContent: 'center',
    alignItems: 'center',
  },
  frameOutline: {
    ...StyleSheet.absoluteFillObject,
    borderRadius: 30,
    borderWidth: 3,
    borderColor: withAlpha(pranaPulseTheme.colors.outlineVariant, 0.28),
  },
  corner: {
    position: 'absolute',
    width: 48,
    height: 48,
    borderColor: pranaPulseTheme.colors.primary,
  },
  cornerTopLeft: {
    top: -2,
    left: -2,
    borderTopWidth: 3,
    borderLeftWidth: 3,
    borderTopLeftRadius: 30,
  },
  cornerTopRight: {
    top: -2,
    right: -2,
    borderTopWidth: 3,
    borderRightWidth: 3,
    borderTopRightRadius: 30,
  },
  cornerBottomLeft: {
    bottom: -2,
    left: -2,
    borderBottomWidth: 3,
    borderLeftWidth: 3,
    borderBottomLeftRadius: 30,
  },
  cornerBottomRight: {
    bottom: -2,
    right: -2,
    borderBottomWidth: 3,
    borderRightWidth: 3,
    borderBottomRightRadius: 30,
  },
  viewfinderInner: {
    width: '92%',
    height: '92%',
    borderRadius: pranaPulseTheme.radius.lg,
    paddingHorizontal: 18,
    paddingVertical: 16,
    overflow: 'hidden',
    justifyContent: 'space-between',
    backgroundColor: pranaPulseTheme.colors.surfaceContainer,
  },
  previewGlowSage: {
    position: 'absolute',
    top: 24,
    left: -14,
    width: 160,
    height: 160,
    borderRadius: 80,
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.58),
  },
  previewGlowSunset: {
    position: 'absolute',
    right: -26,
    bottom: 20,
    width: 176,
    height: 176,
    borderRadius: 88,
    backgroundColor: withAlpha(pranaPulseTheme.colors.secondaryContainer, 0.64),
  },
  previewBadgeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  previewEyebrow: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.primary,
    fontSize: 11,
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  previewBadge: {
    paddingHorizontal: 10,
    paddingVertical: 7,
    borderRadius: pranaPulseTheme.radius.full,
    backgroundColor: withAlpha(pranaPulseTheme.colors.surfaceContainerLowest, 0.82),
  },
  previewBadgeText: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 11,
  },
  waveOrb: {
    alignSelf: 'center',
    width: 188,
    height: 188,
    borderRadius: 94,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: withAlpha(pranaPulseTheme.colors.surfaceContainerLowest, 0.32),
  },
  waveRing: {
    position: 'absolute',
    width: 154,
    height: 154,
    borderRadius: 77,
    borderWidth: 1,
    borderColor: withAlpha(pranaPulseTheme.colors.primary, 0.18),
  },
  waveStack: {
    position: 'absolute',
    top: 52,
    width: 120,
    gap: 7,
  },
  waveLine: {
    height: 3,
    borderRadius: 999,
    alignSelf: 'center',
  },
  waveLineWide: {
    width: 88,
    backgroundColor: withAlpha(pranaPulseTheme.colors.secondary, 0.78),
  },
  waveLineMid: {
    width: 112,
    backgroundColor: withAlpha(pranaPulseTheme.colors.primary, 0.7),
  },
  waveLineShort: {
    width: 74,
    backgroundColor: withAlpha(pranaPulseTheme.colors.secondary, 0.48),
  },
  waveCount: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 38,
    letterSpacing: -1,
  },
  waveState: {
    fontFamily: pranaPulseTheme.fonts.bold,
    marginTop: 4,
    color: pranaPulseTheme.colors.primary,
    fontSize: 11,
    letterSpacing: 1.6,
    textTransform: 'uppercase',
  },
  previewCopy: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 14,
    lineHeight: 21,
    textAlign: 'center',
    maxWidth: 260,
    alignSelf: 'center',
  },
  primaryButton: {
    borderRadius: pranaPulseTheme.radius.full,
    backgroundColor: pranaPulseTheme.colors.primary,
    paddingVertical: 18,
    alignItems: 'center',
    marginBottom: 10,
    ...pranaPulseShadow,
  },
  primaryButtonText: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onPrimary,
    fontSize: 18,
    letterSpacing: -0.2,
  },
  secondaryLink: {
    alignItems: 'center',
    marginBottom: 18,
  },
  secondaryLinkText: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 13,
  },
  inlineError: {
    color: pranaPulseTheme.colors.error,
    fontSize: 13,
    lineHeight: 20,
    textAlign: 'center',
    marginBottom: 18,
  },
  metricGrid: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 16,
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
    fontSize: 26,
    marginBottom: 6,
    letterSpacing: -0.6,
  },
  metricCopy: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 13,
    lineHeight: 19,
  },
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
});
