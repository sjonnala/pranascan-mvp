/**
 * ResultsScreen — displays wellness indicator results.
 *
 * IMPORTANT: No diagnostic language anywhere in this screen.
 * All values are described as "wellness indicators" only.
 */

import { MaterialIcons } from '@expo/vector-icons';
import React, { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Platform,
  StyleProp,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  useWindowDimensions,
  View,
  ViewStyle,
} from 'react-native';
import * as apiClient from '../api/client';
import { PranaPulseReveal } from '../components/pranapulse/PranaPulseReveal';
import { PranaPulseScaffold } from '../components/pranapulse/PranaPulseScaffold';
import {
  ScanFeedback,
  ScanHistoryPage,
  ScanResult,
  ScanSession,
  UsefulResponse,
  VitalityReport,
} from '../types';
import { pranaPulseShadow, pranaPulseTheme, withAlpha } from '../theme/pranaPulse';

interface MetricCardProps {
  label: string;
  value: number | null | undefined;
  unit: string;
  description: string;
  icon: React.ComponentProps<typeof MaterialIcons>['name'];
  tone?: 'sage' | 'sunset';
  style?: StyleProp<ViewStyle>;
  testID?: string;
}

function formatMetricValue(value: number | null | undefined): string {
  if (value == null) {
    return 'N/A';
  }

  return Math.abs(value) >= 10 ? value.toFixed(0) : value.toFixed(1);
}

function MetricCard({
  label,
  value,
  unit,
  description,
  icon,
  tone = 'sage',
  style,
  testID,
}: MetricCardProps) {
  return (
    <View style={[styles.metricCard, style]} testID={testID}>
      <View style={styles.metricHeader}>
        <View style={[styles.metricIconShell, tone === 'sage' ? styles.metricIconSage : styles.metricIconSunset]}>
          <MaterialIcons
            color={tone === 'sage' ? pranaPulseTheme.colors.primary : pranaPulseTheme.colors.secondary}
            name={icon}
            size={17}
          />
        </View>
        <Text style={styles.metricLabel}>{label}</Text>
      </View>
      {value != null ? (
        <Text style={styles.metricValue}>
          {formatMetricValue(value)}
          <Text style={styles.metricUnit}>{` ${unit}`}</Text>
        </Text>
      ) : (
        <Text style={styles.metricNA}>N/A</Text>
      )}
      <Text style={styles.metricDescription}>{description}</Text>
    </View>
  );
}

interface StateCardProps {
  icon: React.ComponentProps<typeof MaterialIcons>['name'];
  eyebrow: string;
  title: string;
  body: string;
  testID: string;
  children?: React.ReactNode;
}

function StateCard({ icon, eyebrow, title, body, testID, children }: StateCardProps) {
  return (
    <PranaPulseReveal delay={20}>
      <View style={styles.stateCard} testID={testID}>
        <View style={styles.stateGlowPrimary} />
        <View style={styles.stateGlowSecondary} />
        <View style={styles.stateIconShell}>
          <MaterialIcons color={pranaPulseTheme.colors.secondary} name={icon} size={24} />
        </View>
        <Text style={styles.stateEyebrow}>{eyebrow}</Text>
        <Text style={styles.stateTitle}>{title}</Text>
        <Text style={styles.stateBody}>{body}</Text>
        {children}
      </View>
    </PranaPulseReveal>
  );
}

interface ResultsScreenProps {
  sessionId?: string | null;
  displayName?: string | null;
  onGoHome?: () => void;
  onGoCircle?: () => void;
  onGoScan?: () => void;
  onGoResults?: () => void;
  onScanAgain: () => void;
}

const NPS_OPTIONS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

function firstSentence(text: string | null | undefined, fallback: string): string {
  if (!text?.trim()) {
    return fallback;
  }

  const sentence = text.split('. ')[0]?.trim();
  return sentence ? `${sentence.replace(/\.$/, '')}.` : fallback;
}

function formatShortDate(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }

  return new Date(value).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  });
}

function describeDelta(value: number | null | undefined, unit: string, label: string): string | null {
  if (value == null || value === 0) {
    return null;
  }

  const amount = Math.abs(value);
  const formatted = amount >= 10 ? amount.toFixed(0) : amount.toFixed(1);
  return `${label} is ${value > 0 ? 'up' : 'down'} ${formatted} ${unit} versus your recent window.`;
}

export function ResultsScreen({
  sessionId,
  displayName,
  onGoCircle,
  onGoHome,
  onGoResults,
  onGoScan,
  onScanAgain,
}: ResultsScreenProps) {
  const { width: screenWidth } = useWindowDimensions();
  const [result, setResult] = useState<ScanResult | null>(null);
  const [session, setSession] = useState<ScanSession | null>(null);
  const [report, setReport] = useState<VitalityReport | null>(null);
  const [history, setHistory] = useState<ScanHistoryPage | null>(null);
  const [feedback, setFeedback] = useState<ScanFeedback | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isEmpty, setIsEmpty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [usefulResponse, setUsefulResponse] = useState<UsefulResponse | null>(null);
  const [npsScore, setNpsScore] = useState<number | null>(null);
  const [comment, setComment] = useState('');
  const [feedbackError, setFeedbackError] = useState<string | null>(null);
  const [isSubmittingFeedback, setIsSubmittingFeedback] = useState(false);

  useEffect(() => {
    let isMounted = true;

    (async () => {
      try {
        setIsLoading(true);
        setError(null);
        setIsEmpty(false);

        let resolvedSessionId = sessionId ?? null;

        if (!resolvedSessionId) {
          const historyLoader = apiClient.getScanHistory;
          if (!historyLoader) {
            throw new Error('History API unavailable.');
          }
          const history = await historyLoader(1, 1);
          resolvedSessionId = history.items[0]?.session.id ?? null;
        }

        if (!resolvedSessionId) {
          if (isMounted) {
            setIsEmpty(true);
          }
          return;
        }

        const [sessionData, existingFeedback, latestReport, historyData] = await Promise.all([
          apiClient.getScanSession(resolvedSessionId),
          apiClient.getFeedbackForSession(resolvedSessionId),
          apiClient.getLatestVitalityReport
            ? apiClient.getLatestVitalityReport().catch(() => null)
            : Promise.resolve(null),
          apiClient.getScanHistory
            ? apiClient.getScanHistory(1, 4).catch(() => null)
            : Promise.resolve(null),
        ]);

        if (!isMounted) {
          return;
        }

        setSession(sessionData.session);
        setResult(sessionData.result);
        setFeedback(existingFeedback);
        setReport(latestReport);
        setHistory(historyData);
      } catch {
        if (isMounted) {
          setError('Could not load your Trend Lab insights. Please check your connection.');
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
  }, [sessionId]);

  const handleSubmitFeedback = async () => {
    if (!usefulResponse || isSubmittingFeedback || !session?.id) {
      return;
    }

    setFeedbackError(null);
    setIsSubmittingFeedback(true);

    try {
      const created = await apiClient.submitScanFeedback({
        session_id: session.id,
        useful_response: usefulResponse,
        nps_score: npsScore ?? undefined,
        comment: comment.trim() || undefined,
      });
      setFeedback(created);
      setComment('');
    } catch {
      setFeedbackError('Could not save your feedback right now. Please try again.');
    } finally {
      setIsSubmittingFeedback(false);
    }
  };

  const headerSummary = useMemo(() => {
    return firstSentence(
      report?.summary_text,
      'Your body signals are captured here as wellness indicators, not medical measurements.'
    );
  }, [report?.summary_text]);
  const compactLayout = screenWidth < 390;
  const stackedMetrics = screenWidth < 360;

  if (isLoading) {
    return (
      <PranaPulseScaffold
        activeTab="results"
        onCirclePress={onGoCircle}
        onHomePress={onGoHome}
        onResultsPress={onGoResults}
        onScanPress={onGoScan}
        profileLabel={displayName ?? 'P'}
      >
        <View style={styles.centered}>
          <StateCard
            body="We’re pulling in your latest wellness indicators and arranging the soft-card summary."
            eyebrow="Trend Lab"
            icon="insights"
            testID="results-loading"
            title="Loading your latest vitality read."
          >
            <ActivityIndicator color={pranaPulseTheme.colors.primary} size="large" />
            <View style={styles.stateSkeletonRow}>
              <View style={styles.stateSkeletonShort} />
              <View style={styles.stateSkeletonLong} />
            </View>
          </StateCard>
        </View>
      </PranaPulseScaffold>
    );
  }

  if (isEmpty) {
    return (
      <PranaPulseScaffold
        activeTab="results"
        onCirclePress={onGoCircle}
        onHomePress={onGoHome}
        onResultsPress={onGoResults}
        onScanPress={onGoScan}
        profileLabel={displayName ?? 'P'}
      >
        <View style={styles.centered}>
          <StateCard
            body="Complete one Daily Glow session and this space will fill with your HR, HRV, and reflection cards."
            eyebrow="Trend Lab"
            icon="favorite-border"
            testID="results-empty"
            title="No scan insights yet."
          >
            <View style={styles.emptyIllustrationRow}>
              <View style={styles.emptyDotPrimary} />
              <View style={styles.emptyDotSecondary} />
              <View style={styles.emptyDotPrimary} />
            </View>
            <TouchableOpacity onPress={onScanAgain} style={styles.primaryButton}>
              <Text style={styles.primaryButtonText}>Start Daily Glow</Text>
            </TouchableOpacity>
          </StateCard>
        </View>
      </PranaPulseScaffold>
    );
  }

  if (error || !result) {
    return (
      <PranaPulseScaffold
        activeTab="results"
        onCirclePress={onGoCircle}
        onHomePress={onGoHome}
        onResultsPress={onGoResults}
        onScanPress={onGoScan}
        profileLabel={displayName ?? 'P'}
      >
        <View style={styles.centered}>
          <StateCard
            body={error ?? 'Results not available.'}
            eyebrow="Trend Lab"
            icon="cloud-off"
            testID="results-error"
            title="We couldn’t load this results view."
          >
            <TouchableOpacity onPress={onScanAgain} style={styles.primaryButton}>
              <Text style={styles.primaryButtonText}>Try Again</Text>
            </TouchableOpacity>
          </StateCard>
        </View>
      </PranaPulseScaffold>
    );
  }

  const qualityPct = Math.round(result.quality_score * 100);
  const scanModeLabel = session?.scan_type === 'deep_dive' ? 'Weekly Deep Dive' : 'Vitality Scan';
  const currentHistoryItem =
    history?.items.find((item) => item.session.id === session?.id) ?? history?.items[0] ?? null;
  const windowLabel =
    report?.period_start && report?.period_end
      ? `${formatShortDate(report.period_start)} - ${formatShortDate(report.period_end)}`
      : null;
  const heroTrendTitle =
    describeDelta(report?.delta_hrv_ms ?? currentHistoryItem?.hrv_trend_delta, 'ms', 'HRV') ??
    describeDelta(report?.delta_hr_bpm ?? currentHistoryItem?.hr_trend_delta, 'bpm', 'Heart rate') ??
    (report?.scan_count
      ? `Trend Lab has ${report.scan_count} recent scans in view.`
      : 'HR and HRV are ready from your most recent service-intelligence session.');
  const hasDynamicTrendSummary = Boolean(
    report?.summary_text?.trim() ||
      currentHistoryItem?.hrv_trend_delta != null ||
      currentHistoryItem?.hr_trend_delta != null
  );
  const reflectionSummaryTitle = hasDynamicTrendSummary ? 'Recent Trend' : 'Summary';
  const reflectionSummaryText =
    report?.summary_text?.trim()
      ? firstSentence(report.summary_text, 'Your latest session is now reflected in Trend Lab.')
      : describeDelta(currentHistoryItem?.hrv_trend_delta, 'ms', 'HRV') ??
        describeDelta(currentHistoryItem?.hr_trend_delta, 'bpm', 'Heart rate') ??
        'Your latest session is now reflected in Trend Lab.';

  return (
    <PranaPulseScaffold
      activeTab="results"
      onCirclePress={onGoCircle}
      onHomePress={onGoHome}
      onResultsPress={onGoResults}
      onScanPress={onGoScan}
      profileLabel={displayName ?? 'P'}
    >
      <PranaPulseReveal delay={10}>
        <View style={styles.heroSection}>
          <Text style={styles.heroEyebrow}>Trend Lab</Text>
          <Text style={[styles.heroTitle, compactLayout && styles.heroTitleCompact]}>
            Your body has been speaking.
          </Text>
          <Text style={styles.heroSubtitle}>
            Here is what we've heard over the last week.
          </Text>
        </View>
      </PranaPulseReveal>

      <PranaPulseReveal delay={90}>
        <View style={styles.heroCard}>
          <View style={styles.heroGlowPrimary} />
          <View style={styles.heroGlowSecondary} />
          <View style={styles.heroCardHeader}>
            <View style={styles.heroIconCircle}>
              <MaterialIcons color={pranaPulseTheme.colors.secondary} name="favorite" size={20} />
            </View>
            <Text style={styles.heroTag}>{scanModeLabel}</Text>
          </View>
          <Text style={[styles.heroCardTitle, compactLayout && styles.heroCardTitleCompact]}>{heroTrendTitle}</Text>
          <Text style={styles.heroCardBody}>
            Quality score {qualityPct}% · {windowLabel ?? new Date(result.created_at).toLocaleTimeString()}
          </Text>
          <View style={styles.heroMetricStrip}>
            <View style={styles.heroMetricPill}>
              <Text style={styles.heroMetricEyebrow}>HR</Text>
              <Text style={styles.heroMetricValue}>{result.hr_bpm != null ? `${formatMetricValue(result.hr_bpm)} bpm` : 'N/A'}</Text>
            </View>
            <View style={styles.heroMetricPill}>
              <Text style={styles.heroMetricEyebrow}>HRV</Text>
              <Text style={styles.heroMetricValue}>{result.hrv_ms != null ? `${formatMetricValue(result.hrv_ms)} ms` : 'N/A'}</Text>
            </View>
          </View>
        </View>
      </PranaPulseReveal>

      {result.trend_alert === 'consider_lab_followup' ? (
        <PranaPulseReveal delay={140}>
          <View style={styles.trendAlert} testID="trend-alert">
            <Text style={styles.trendAlertTitle}>Trend Notice</Text>
            <Text style={styles.trendAlertText}>
              Your recent wellness indicators shifted against your recent baseline. Consider a check-in with a qualified healthcare professional if the shift feels unusual for you.
            </Text>
          </View>
        </PranaPulseReveal>
      ) : null}

      {/* ── Stitch-style narrative insight cards ── */}
      <PranaPulseReveal delay={155}>
        <View style={styles.insightCard}>
          <View style={styles.insightCardHeader}>
            <View style={styles.insightIconShell}>
              <MaterialIcons color={pranaPulseTheme.colors.secondary} name="favorite" size={22} />
            </View>
            <View style={styles.insightCategoryChip}>
              <Text style={styles.insightCategoryText}>HEART HEALTH</Text>
            </View>
          </View>
          <Text style={[styles.insightHeadline, compactLayout && styles.insightHeadlineCompact]}>
            {heroTrendTitle}
          </Text>
          <Text style={styles.insightSubtext}>
            Quality score {qualityPct}%
            {windowLabel ? ` · ${windowLabel}` : ''}
          </Text>
        </View>
      </PranaPulseReveal>

      {result.hrv_ms != null ? (
        <PranaPulseReveal delay={175}>
          <View style={[styles.insightCard, styles.insightCardSleep]}>
            <View style={styles.insightCardHeader}>
              <View style={[styles.insightIconShell, styles.insightIconSage]}>
                <MaterialIcons color={pranaPulseTheme.colors.primary} name="bar-chart" size={22} />
              </View>
              <View style={[styles.insightCategoryChip, styles.insightCategoryChipSage]}>
                <Text style={[styles.insightCategoryText, styles.insightCategoryTextSage]}>HRV RECOVERY</Text>
              </View>
            </View>
            <Text style={[styles.insightHeadline, compactLayout && styles.insightHeadlineCompact]}>
              {reflectionSummaryText}
            </Text>
            <Text style={styles.insightSubtext}>
              HRV {result.hrv_ms != null ? `${formatMetricValue(result.hrv_ms)} ms` : 'N/A'}
              {result.hr_bpm != null ? ` · HR ${formatMetricValue(result.hr_bpm)} bpm` : ''}
            </Text>
          </View>
        </PranaPulseReveal>
      ) : null}

      <PranaPulseReveal delay={180}>
        <View style={[styles.metricGrid, stackedMetrics && styles.metricGridStacked]}>
          <MetricCard
            description="Heart rate wellness indicator from your latest scan."
            icon="favorite"
            label="Heart Rate"
            style={stackedMetrics ? styles.metricCardStacked : undefined}
            testID="metric-hr"
            tone="sunset"
            unit="bpm"
            value={result.hr_bpm}
          />
          <MetricCard
            description="Heart rate variability estimate from the same session."
            icon="monitor-heart"
            label="HRV"
            style={stackedMetrics ? styles.metricCardStacked : undefined}
            testID="metric-hrv"
            unit="ms"
            value={result.hrv_ms}
          />
          <MetricCard
            description="Breathing cadence paired to the scan."
            icon="air"
            label="Respiratory Rate"
            style={stackedMetrics ? styles.metricCardStacked : undefined}
            testID="metric-rr"
            tone="sunset"
            unit="rpm"
            value={result.respiratory_rate}
          />
          {session?.scan_type === 'deep_dive' ? (
            <MetricCard
              description="Pulse-wave stiffness estimate from the thumb-press flow."
              icon="timeline"
              label="Stiffness Index"
              style={stackedMetrics ? styles.metricCardStacked : undefined}
              testID="metric-stiffness-index"
              unit="m/s"
              value={result.stiffness_index}
            />
          ) : (
            <MetricCard
              description="Voice stability estimate from your guided voice capture."
              icon="graphic-eq"
              label="Voice Jitter"
              style={stackedMetrics ? styles.metricCardStacked : undefined}
              testID="metric-jitter"
              tone="sunset"
              unit="%"
              value={result.voice_jitter_pct}
            />
          )}
        </View>
      </PranaPulseReveal>

      {session?.scan_type !== 'deep_dive' ? (
        <PranaPulseReveal delay={220}>
          <View style={styles.secondaryMetricCard}>
            <Text style={styles.secondaryMetricLabel}>Voice Shimmer</Text>
            <Text style={styles.secondaryMetricValue}>
              {result.voice_shimmer_pct != null ? `${formatMetricValue(result.voice_shimmer_pct)} %` : 'N/A'}
            </Text>
            <Text style={styles.secondaryMetricCopy}>A second voice wellness indicator from the backend evaluation.</Text>
          </View>
        </PranaPulseReveal>
      ) : null}

      <PranaPulseReveal delay={260}>
        <View style={styles.reflectionSection}>
          <View style={styles.reflectionHeader}>
            <Text style={styles.sectionTitle}>Monthly Reflection</Text>
            <Text style={styles.reflectionAction}>View Archive</Text>
          </View>

          <View style={styles.reflectionCard}>
            <Text style={styles.reflectionAccentPrimary} />
            <View style={styles.reflectionCopy}>
              <Text style={styles.reflectionTitle}>Scan Quality</Text>
              <Text style={styles.reflectionText}>
                {qualityPct >= 85
                  ? 'Your capture quality was strong enough for a confident wellness read.'
                  : 'Your session completed, but steadier framing or brighter light may improve future scans.'}
              </Text>
            </View>
          </View>

          <View style={styles.reflectionCard}>
            <Text style={styles.reflectionAccentSecondary} />
            <View style={styles.reflectionCopy}>
              <Text style={styles.reflectionTitle}>{reflectionSummaryTitle}</Text>
              <Text style={styles.reflectionText}>{reflectionSummaryText}</Text>
            </View>
          </View>
        </View>
      </PranaPulseReveal>

      {result.flags.length > 0 ? (
        <PranaPulseReveal delay={300}>
          <View style={styles.flagsBox} testID="result-flags">
            <Text style={styles.flagsTitle}>Scan notes</Text>
            {result.flags.map((flag) => (
              <Text key={flag} style={styles.flagText}>
                · {flag.replace(/_/g, ' ')}
              </Text>
            ))}
          </View>
        </PranaPulseReveal>
      ) : null}

      <PranaPulseReveal delay={330}>
        <View style={styles.disclaimer} testID="results-disclaimer">
          <Text style={styles.disclaimerText}>
            These are wellness indicators only, not medical measurements. Consult a qualified healthcare professional before making health decisions.
          </Text>
        </View>
      </PranaPulseReveal>

      {feedback ? (
        <PranaPulseReveal delay={360}>
          <View style={styles.feedbackThanksCard} testID="feedback-thanks">
            <Text style={styles.feedbackTitle}>Thanks for the feedback</Text>
            <Text style={styles.feedbackSummary}>
              Useful: {feedback.useful_response === 'useful' ? 'Yes' : 'Needs work'}
              {feedback.nps_score != null ? ` · NPS ${feedback.nps_score}/10` : ''}
            </Text>
            {feedback.comment ? <Text style={styles.feedbackComment}>{`"${feedback.comment}"`}</Text> : null}
          </View>
        </PranaPulseReveal>
      ) : (
        <PranaPulseReveal delay={360}>
          <View style={styles.feedbackCard} testID="feedback-card">
            <Text style={styles.feedbackTitle}>Was this scan useful?</Text>
            <Text style={styles.feedbackSubtitle}>
              Help us improve the post-scan experience with one quick response.
            </Text>

            <View style={styles.feedbackChoices}>
              <TouchableOpacity
                onPress={() => setUsefulResponse('useful')}
                style={[
                  styles.feedbackChoice,
                  usefulResponse === 'useful' && styles.feedbackChoiceSelected,
                ]}
                testID="feedback-useful"
              >
                <Text style={styles.feedbackChoiceText}>Useful</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={() => setUsefulResponse('needs_work')}
                style={[
                  styles.feedbackChoice,
                  usefulResponse === 'needs_work' && styles.feedbackChoiceSelected,
                ]}
                testID="feedback-needs-work"
              >
                <Text style={styles.feedbackChoiceText}>Needs work</Text>
              </TouchableOpacity>
            </View>

            <Text style={styles.npsTitle}>How likely are you to use PranaPulse again?</Text>
            <View style={styles.npsRow}>
              {NPS_OPTIONS.map((score) => (
                <TouchableOpacity
                  key={score}
                  onPress={() => setNpsScore(score)}
                  style={[styles.npsPill, npsScore === score && styles.npsPillSelected]}
                  testID={`feedback-nps-${score}`}
                >
                  <Text style={styles.npsPillText}>{score}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <TextInput
              maxLength={500}
              multiline
              onChangeText={setComment}
              placeholder="Any quick note? (optional)"
              placeholderTextColor={withAlpha(pranaPulseTheme.colors.onSurfaceVariant, 0.7)}
              style={[styles.commentInput, Platform.OS === 'ios' && styles.commentInputIos]}
              testID="feedback-comment-input"
              textAlignVertical="top"
              value={comment}
            />

            {feedbackError ? (
              <Text style={styles.feedbackError} testID="feedback-error">
                {feedbackError}
              </Text>
            ) : null}

            <TouchableOpacity
              disabled={!usefulResponse || isSubmittingFeedback}
              onPress={handleSubmitFeedback}
              style={[
                styles.feedbackSubmitButton,
                (!usefulResponse || isSubmittingFeedback) && styles.feedbackSubmitDisabled,
              ]}
              testID="feedback-submit"
            >
              <Text style={styles.feedbackSubmitText}>
                {isSubmittingFeedback ? 'Saving…' : 'Send feedback'}
              </Text>
            </TouchableOpacity>
          </View>
        </PranaPulseReveal>
      )}

      <PranaPulseReveal delay={420}>
        <TouchableOpacity onPress={onScanAgain} style={styles.scanAgainButton} testID="scan-again">
          <Text style={styles.scanAgainText}>Scan Again</Text>
        </TouchableOpacity>
      </PranaPulseReveal>
    </PranaPulseScaffold>
  );
}

const styles = StyleSheet.create({
  centered: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingTop: 96,
  },
  stateCard: {
    position: 'relative',
    overflow: 'hidden',
    width: '100%',
    borderRadius: pranaPulseTheme.radius.lg,
    padding: 24,
    alignItems: 'center',
    gap: 12,
    backgroundColor: pranaPulseTheme.colors.surfaceContainerLowest,
    ...pranaPulseShadow,
  },
  stateGlowPrimary: {
    position: 'absolute',
    top: -30,
    right: -24,
    width: 140,
    height: 140,
    borderRadius: 70,
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.66),
  },
  stateGlowSecondary: {
    position: 'absolute',
    bottom: -26,
    left: -20,
    width: 120,
    height: 120,
    borderRadius: 60,
    backgroundColor: withAlpha(pranaPulseTheme.colors.secondaryContainer, 0.64),
  },
  stateIconShell: {
    width: 60,
    height: 60,
    borderRadius: 30,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: withAlpha(pranaPulseTheme.colors.secondaryContainer, 0.86),
  },
  stateEyebrow: {
    ...pranaPulseTheme.type.eyebrow,
    color: pranaPulseTheme.colors.secondary,
  },
  stateTitle: {
    ...pranaPulseTheme.type.display,
    textAlign: 'center',
    fontSize: 30,
  },
  stateBody: {
    ...pranaPulseTheme.type.body,
    textAlign: 'center',
    maxWidth: 300,
  },
  stateSkeletonRow: {
    width: '100%',
    gap: 10,
    marginTop: 6,
  },
  stateSkeletonShort: {
    alignSelf: 'center',
    width: '48%',
    height: 10,
    borderRadius: 999,
    backgroundColor: withAlpha(pranaPulseTheme.colors.surfaceDim, 0.74),
  },
  stateSkeletonLong: {
    alignSelf: 'center',
    width: '76%',
    height: 10,
    borderRadius: 999,
    backgroundColor: withAlpha(pranaPulseTheme.colors.surfaceDim, 0.58),
  },
  emptyIllustrationRow: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 4,
    marginBottom: 6,
  },
  emptyDotPrimary: {
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: pranaPulseTheme.colors.primary,
  },
  emptyDotSecondary: {
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: pranaPulseTheme.colors.secondary,
  },
  loadingText: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 16,
    textAlign: 'center',
  },
  errorText: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.error,
    fontSize: 16,
    textAlign: 'center',
    lineHeight: 24,
  },
  heroSection: {
    marginTop: 8,
    marginBottom: 16,
    gap: 6,
  },
  heroEyebrow: {
    ...pranaPulseTheme.type.eyebrow,
  },
  heroTitle: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 34,
    letterSpacing: -0.8,
  },
  heroTitleCompact: {
    fontSize: 30,
  },
  heroSubtitle: {
    ...pranaPulseTheme.type.body,
  },
  heroCard: {
    position: 'relative',
    overflow: 'hidden',
    backgroundColor: pranaPulseTheme.colors.surfaceContainerLowest,
    borderRadius: pranaPulseTheme.radius.lg,
    padding: 24,
    marginBottom: 18,
    ...pranaPulseShadow,
  },
  heroGlowPrimary: {
    position: 'absolute',
    top: -38,
    right: -28,
    width: 156,
    height: 156,
    borderRadius: 78,
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.68),
  },
  heroGlowSecondary: {
    position: 'absolute',
    bottom: -36,
    left: -18,
    width: 126,
    height: 126,
    borderRadius: 63,
    backgroundColor: withAlpha(pranaPulseTheme.colors.secondaryContainer, 0.56),
  },
  heroCardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 18,
  },
  heroIconCircle: {
    width: 56,
    height: 56,
    borderRadius: 28,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: pranaPulseTheme.colors.secondaryContainer,
  },
  heroTag: {
    fontFamily: pranaPulseTheme.fonts.bold,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: pranaPulseTheme.radius.full,
    backgroundColor: pranaPulseTheme.colors.surfaceContainer,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 11,
    textTransform: 'uppercase',
    letterSpacing: 1.1,
  },
  heroCardTitle: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 24,
    lineHeight: 32,
    marginBottom: 10,
  },
  heroCardTitleCompact: {
    fontSize: 21,
    lineHeight: 28,
  },
  heroCardBody: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 14,
    lineHeight: 22,
  },
  heroMetricStrip: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 16,
  },
  heroMetricPill: {
    flex: 1,
    borderRadius: 18,
    paddingHorizontal: 14,
    paddingVertical: 12,
    backgroundColor: withAlpha(pranaPulseTheme.colors.surfaceContainer, 0.86),
  },
  heroMetricEyebrow: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 10,
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: 6,
  },
  heroMetricValue: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 16,
  },
  trendAlert: {
    borderRadius: pranaPulseTheme.radius.md,
    backgroundColor: withAlpha(pranaPulseTheme.colors.secondaryContainer, 0.8),
    padding: 18,
    marginBottom: 18,
  },
  trendAlertTitle: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.secondary,
    fontSize: 15,
    marginBottom: 8,
  },
  trendAlertText: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 14,
    lineHeight: 22,
  },
  metricGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
  },
  metricGridStacked: {
    gap: 10,
  },
  metricCard: {
    flexBasis: '47%',
    flexGrow: 1,
    backgroundColor: pranaPulseTheme.colors.surfaceContainerLowest,
    borderRadius: pranaPulseTheme.radius.md,
    padding: 18,
    minHeight: 156,
    ...pranaPulseShadow,
  },
  metricCardStacked: {
    flexBasis: '100%',
  },
  metricHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 12,
  },
  metricIconShell: {
    width: 30,
    height: 30,
    borderRadius: 15,
    alignItems: 'center',
    justifyContent: 'center',
  },
  metricIconSage: {
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.7),
  },
  metricIconSunset: {
    backgroundColor: withAlpha(pranaPulseTheme.colors.secondaryContainer, 0.78),
  },
  metricLabel: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 11,
    textTransform: 'uppercase',
    letterSpacing: 1.05,
  },
  metricValue: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 30,
    marginBottom: 8,
  },
  metricUnit: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 14,
  },
  metricNA: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 26,
    marginBottom: 8,
  },
  metricDescription: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 12,
    lineHeight: 18,
  },
  secondaryMetricCard: {
    borderRadius: pranaPulseTheme.radius.md,
    backgroundColor: pranaPulseTheme.colors.surfaceContainerLow,
    padding: 20,
    marginTop: 12,
    marginBottom: 18,
  },
  secondaryMetricLabel: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 11,
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: 8,
  },
  secondaryMetricValue: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 28,
    marginBottom: 6,
  },
  secondaryMetricCopy: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 13,
    lineHeight: 20,
  },
  reflectionSection: {
    borderRadius: pranaPulseTheme.radius.md,
    backgroundColor: pranaPulseTheme.colors.surfaceContainerLow,
    padding: 20,
    marginBottom: 18,
    gap: 12,
  },
  reflectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  sectionTitle: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 20,
  },
  reflectionAction: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.primary,
    fontSize: 13,
  },
  reflectionCard: {
    flexDirection: 'row',
    gap: 14,
    alignItems: 'center',
    backgroundColor: pranaPulseTheme.colors.surfaceContainerLowest,
    borderRadius: pranaPulseTheme.radius.md,
    padding: 16,
  },
  reflectionAccentPrimary: {
    width: 6,
    alignSelf: 'stretch',
    borderRadius: pranaPulseTheme.radius.full,
    backgroundColor: pranaPulseTheme.colors.primary,
  },
  reflectionAccentSecondary: {
    width: 6,
    alignSelf: 'stretch',
    borderRadius: pranaPulseTheme.radius.full,
    backgroundColor: pranaPulseTheme.colors.secondary,
  },
  reflectionCopy: {
    flex: 1,
    gap: 4,
  },
  reflectionTitle: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 14,
  },
  reflectionText: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 13,
    lineHeight: 20,
  },
  flagsBox: {
    backgroundColor: pranaPulseTheme.colors.surfaceContainerLowest,
    borderRadius: pranaPulseTheme.radius.md,
    padding: 18,
    marginBottom: 18,
  },
  flagsTitle: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 14,
    marginBottom: 8,
  },
  flagText: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 13,
    lineHeight: 20,
  },
  disclaimer: {
    backgroundColor: pranaPulseTheme.colors.surfaceContainer,
    borderRadius: pranaPulseTheme.radius.md,
    padding: 18,
    marginBottom: 18,
  },
  disclaimerText: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 13,
    lineHeight: 20,
  },
  feedbackCard: {
    backgroundColor: pranaPulseTheme.colors.surfaceContainerLowest,
    borderRadius: pranaPulseTheme.radius.md,
    padding: 18,
    marginBottom: 18,
    ...pranaPulseShadow,
  },
  feedbackThanksCard: {
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.55),
    borderRadius: pranaPulseTheme.radius.md,
    padding: 18,
    marginBottom: 18,
  },
  feedbackTitle: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 18,
    marginBottom: 6,
  },
  feedbackSubtitle: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 13,
    lineHeight: 20,
    marginBottom: 14,
  },
  feedbackChoices: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 14,
  },
  feedbackChoice: {
    flex: 1,
    borderRadius: pranaPulseTheme.radius.full,
    backgroundColor: pranaPulseTheme.colors.surfaceContainerHigh,
    paddingVertical: 12,
    alignItems: 'center',
  },
  feedbackChoiceSelected: {
    backgroundColor: pranaPulseTheme.colors.secondaryContainer,
  },
  feedbackChoiceText: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 14,
  },
  npsTitle: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 14,
    marginBottom: 10,
  },
  npsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: 14,
  },
  npsPill: {
    minWidth: 36,
    borderRadius: pranaPulseTheme.radius.full,
    backgroundColor: pranaPulseTheme.colors.surfaceContainerHigh,
    paddingVertical: 8,
    paddingHorizontal: 10,
    alignItems: 'center',
  },
  npsPillSelected: {
    backgroundColor: pranaPulseTheme.colors.primaryContainer,
  },
  npsPillText: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 13,
  },
  commentInput: {
    minHeight: 112,
    borderRadius: pranaPulseTheme.radius.md,
    backgroundColor: pranaPulseTheme.colors.surfaceContainerHigh,
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurface,
    paddingHorizontal: 14,
    paddingVertical: 14,
    fontSize: 14,
    marginBottom: 12,
  },
  commentInputIos: {
    paddingTop: 14,
  },
  feedbackError: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.error,
    fontSize: 13,
    marginBottom: 10,
  },
  feedbackSubmitButton: {
    borderRadius: pranaPulseTheme.radius.full,
    backgroundColor: pranaPulseTheme.colors.primary,
    paddingVertical: 15,
    alignItems: 'center',
  },
  feedbackSubmitDisabled: {
    opacity: 0.45,
  },
  feedbackSubmitText: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onPrimary,
    fontSize: 15,
  },
  feedbackSummary: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 14,
    lineHeight: 20,
  },
  feedbackComment: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 14,
    lineHeight: 22,
    marginTop: 10,
    fontStyle: 'italic',
  },
  scanAgainButton: {
    borderRadius: pranaPulseTheme.radius.full,
    backgroundColor: pranaPulseTheme.colors.primary,
    paddingVertical: 16,
    alignItems: 'center',
    marginBottom: 4,
  },
  scanAgainText: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onPrimary,
    fontSize: 16,
  },
  primaryButton: {
    borderRadius: pranaPulseTheme.radius.full,
    backgroundColor: pranaPulseTheme.colors.primary,
    paddingVertical: 16,
    paddingHorizontal: 24,
    alignItems: 'center',
    marginTop: 6,
    minWidth: 190,
  },
  primaryButtonText: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onPrimary,
    fontSize: 16,
  },

  // ── Stitch Insight Cards ──
  insightCard: {
    borderRadius: pranaPulseTheme.radius.lg,
    backgroundColor: pranaPulseTheme.colors.surfaceContainerLowest,
    padding: 24,
    gap: 14,
    marginBottom: 14,
    ...pranaPulseShadow,
  },
  insightCardSleep: {
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.22),
  },
  insightCardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  insightIconShell: {
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: withAlpha(pranaPulseTheme.colors.secondaryContainer, 0.72),
    alignItems: 'center',
    justifyContent: 'center',
  },
  insightIconSage: {
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.72),
  },
  insightCategoryChip: {
    borderRadius: pranaPulseTheme.radius.full,
    paddingHorizontal: 12,
    paddingVertical: 5,
    backgroundColor: pranaPulseTheme.colors.surfaceContainerHigh,
  },
  insightCategoryChipSage: {
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.52),
  },
  insightCategoryText: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.secondary,
    fontSize: 10,
    letterSpacing: 1.4,
  },
  insightCategoryTextSage: {
    color: pranaPulseTheme.colors.primary,
  },
  insightHeadline: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 26,
    lineHeight: 33,
    letterSpacing: -0.5,
  },
  insightHeadlineCompact: {
    fontSize: 22,
    lineHeight: 29,
  },
  insightSubtext: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 14,
    lineHeight: 21,
  },
});
