/**
 * ResultsScreen — displays wellness indicator results.
 *
 * IMPORTANT: No diagnostic language anywhere in this screen.
 * All values are described as "wellness indicators" only.
 */

import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { getFeedbackForSession, getScanSession, submitScanFeedback } from '../api/client';
import { ScanFeedback, ScanResult, UsefulResponse } from '../types';

interface MetricCardProps {
  label: string;
  value: number | null | undefined;
  unit: string;
  description: string;
  testID?: string;
}

function MetricCard({ label, value, unit, description, testID }: MetricCardProps) {
  return (
    <View style={styles.metricCard} testID={testID}>
      <Text style={styles.metricLabel}>{label}</Text>
      {value != null ? (
        <Text style={styles.metricValue}>
          {value.toFixed(1)}
          <Text style={styles.metricUnit}> {unit}</Text>
        </Text>
      ) : (
        <Text style={styles.metricNA}>N/A</Text>
      )}
      <Text style={styles.metricDescription}>{description}</Text>
    </View>
  );
}

interface ResultsScreenProps {
  sessionId: string;
  userId: string;
  onScanAgain: () => void;
}

const NPS_OPTIONS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

export function ResultsScreen({ sessionId, userId, onScanAgain }: ResultsScreenProps) {
  const [result, setResult] = useState<ScanResult | null>(null);
  const [feedback, setFeedback] = useState<ScanFeedback | null>(null);
  const [isLoading, setIsLoading] = useState(true);
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
        const [sessionData, existingFeedback] = await Promise.all([
          getScanSession(sessionId, userId),
          getFeedbackForSession(sessionId, userId),
        ]);

        if (!isMounted) {
          return;
        }

        setResult(sessionData.result);
        setFeedback(existingFeedback);
      } catch {
        if (isMounted) {
          setError('Could not load your results. Please check your connection.');
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
  }, [sessionId, userId]);

  const handleSubmitFeedback = async () => {
    if (!usefulResponse || isSubmittingFeedback) {
      return;
    }

    setFeedbackError(null);
    setIsSubmittingFeedback(true);

    try {
      const created = await submitScanFeedback(userId, {
        session_id: sessionId,
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

  if (isLoading) {
    return (
      <View style={styles.centered} testID="results-loading">
        <ActivityIndicator size="large" color="#4f46e5" />
        <Text style={styles.loadingText}>Loading your wellness indicators…</Text>
      </View>
    );
  }

  if (error || !result) {
    return (
      <View style={styles.centered} testID="results-error">
        <Text style={styles.errorEmoji}>⚠️</Text>
        <Text style={styles.errorText}>{error ?? 'Results not available.'}</Text>
        <TouchableOpacity onPress={onScanAgain} style={styles.retryButton}>
          <Text style={styles.retryText}>Try Again</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const qualityPct = Math.round(result.quality_score * 100);

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      testID="results-screen"
    >
      <View style={styles.header}>
        <Text style={styles.checkmark}>✓</Text>
        <Text style={styles.title}>Wellness Check Complete</Text>
        <Text style={styles.subtitle}>
          Scan quality: {qualityPct}% · {new Date(result.created_at).toLocaleTimeString()}
        </Text>
      </View>

      {result.trend_alert === 'consider_lab_followup' && (
        <View style={styles.trendAlert} testID="trend-alert">
          <Text style={styles.trendAlertTitle}>📊 Trend Notice</Text>
          <Text style={styles.trendAlertText}>
            Your wellness indicators show a notable shift compared to your recent average. Consider
            scheduling a check-up with your doctor or visiting a lab for a more detailed assessment.
          </Text>
        </View>
      )}

      <Text style={styles.sectionTitle}>Heart & Circulation</Text>
      <View style={styles.metricsRow}>
        <MetricCard
          label="Heart Rate"
          value={result.hr_bpm}
          unit="bpm"
          description="Wellness indicator — not a clinical reading"
          testID="metric-hr"
        />
        <MetricCard
          label="HRV"
          value={result.hrv_ms}
          unit="ms"
          description="Heart rate variability estimate"
          testID="metric-hrv"
        />
      </View>

      <Text style={styles.sectionTitle}>Breathing</Text>
      <MetricCard
        label="Respiratory Rate"
        value={result.respiratory_rate}
        unit="br/min"
        description="Breathing rate wellness indicator"
        testID="metric-rr"
      />

      <Text style={styles.sectionTitle}>Voice Wellness</Text>
      <View style={styles.metricsRow}>
        <MetricCard
          label="Voice Jitter"
          value={result.voice_jitter_pct}
          unit="%"
          description="Vocal frequency variation"
          testID="metric-jitter"
        />
        <MetricCard
          label="Voice Shimmer"
          value={result.voice_shimmer_pct}
          unit="%"
          description="Vocal amplitude variation"
          testID="metric-shimmer"
        />
      </View>

      {result.flags.length > 0 && (
        <View style={styles.flagsBox} testID="result-flags">
          <Text style={styles.flagsTitle}>Scan notes</Text>
          {result.flags.map((flag) => (
            <Text key={flag} style={styles.flagText}>
              · {flag.replace(/_/g, ' ')}
            </Text>
          ))}
        </View>
      )}

      <View style={styles.disclaimer} testID="results-disclaimer">
        <Text style={styles.disclaimerText}>
          ⚕️ These are wellness indicators only — not medical measurements. Consult a qualified
          healthcare professional before making any health decisions.
        </Text>
      </View>

      {feedback ? (
        <View style={styles.feedbackThanksCard} testID="feedback-thanks">
          <Text style={styles.feedbackTitle}>Thanks for the feedback</Text>
          <Text style={styles.feedbackSummary}>
            Useful: {feedback.useful_response === 'useful' ? 'Yes' : 'Needs work'}
            {feedback.nps_score != null ? ` · NPS ${feedback.nps_score}/10` : ''}
          </Text>
          {feedback.comment ? (
            <Text style={styles.feedbackComment}>{`"${feedback.comment}"`}</Text>
          ) : null}
        </View>
      ) : (
        <View style={styles.feedbackCard} testID="feedback-card">
          <Text style={styles.feedbackTitle}>Was this scan useful?</Text>
          <Text style={styles.feedbackSubtitle}>
            Help us improve the post-scan experience with one quick response.
          </Text>

          <View style={styles.feedbackChoices}>
            <TouchableOpacity
              style={[
                styles.feedbackChoice,
                usefulResponse === 'useful' && styles.feedbackChoiceSelected,
              ]}
              onPress={() => setUsefulResponse('useful')}
              testID="feedback-useful"
            >
              <Text style={styles.feedbackChoiceText}>Useful</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[
                styles.feedbackChoice,
                usefulResponse === 'needs_work' && styles.feedbackChoiceSelected,
              ]}
              onPress={() => setUsefulResponse('needs_work')}
              testID="feedback-needs-work"
            >
              <Text style={styles.feedbackChoiceText}>Needs work</Text>
            </TouchableOpacity>
          </View>

          <Text style={styles.npsTitle}>How likely are you to use PranaScan again?</Text>
          <View style={styles.npsRow}>
            {NPS_OPTIONS.map((score) => (
              <TouchableOpacity
                key={score}
                style={[styles.npsPill, npsScore === score && styles.npsPillSelected]}
                onPress={() => setNpsScore(score)}
                testID={`feedback-nps-${score}`}
              >
                <Text style={styles.npsPillText}>{score}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <TextInput
            style={styles.commentInput}
            placeholder="Any quick note? (optional)"
            placeholderTextColor="#666688"
            value={comment}
            onChangeText={setComment}
            multiline
            maxLength={500}
            textAlignVertical="top"
            testID="feedback-comment-input"
          />

          {feedbackError ? (
            <Text style={styles.feedbackError} testID="feedback-error">
              {feedbackError}
            </Text>
          ) : null}

          <TouchableOpacity
            style={[
              styles.feedbackSubmitButton,
              (!usefulResponse || isSubmittingFeedback) && styles.feedbackSubmitDisabled,
            ]}
            onPress={handleSubmitFeedback}
            disabled={!usefulResponse || isSubmittingFeedback}
            testID="feedback-submit"
          >
            <Text style={styles.feedbackSubmitText}>
              {isSubmittingFeedback ? 'Saving…' : 'Send feedback'}
            </Text>
          </TouchableOpacity>
        </View>
      )}

      <TouchableOpacity style={styles.scanAgainButton} onPress={onScanAgain} testID="scan-again">
        <Text style={styles.scanAgainText}>Scan Again</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f1a',
  },
  content: {
    paddingHorizontal: 20,
    paddingTop: 60,
    paddingBottom: 40,
  },
  centered: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#0f0f1a',
    padding: 20,
  },
  loadingText: {
    color: '#ffffff',
    fontSize: 16,
    marginTop: 16,
    textAlign: 'center',
  },
  errorEmoji: { fontSize: 48, marginBottom: 16 },
  errorText: { color: '#f87171', fontSize: 16, textAlign: 'center', marginBottom: 20 },
  retryButton: {
    backgroundColor: '#4f46e5',
    borderRadius: 12,
    paddingVertical: 12,
    paddingHorizontal: 24,
  },
  retryText: { color: '#ffffff', fontWeight: '600', fontSize: 16 },
  header: {
    alignItems: 'center',
    marginBottom: 28,
  },
  checkmark: {
    fontSize: 48,
    color: '#4ade80',
    marginBottom: 12,
  },
  title: {
    fontSize: 26,
    fontWeight: '700',
    color: '#ffffff',
    marginBottom: 6,
    textAlign: 'center',
  },
  subtitle: {
    fontSize: 14,
    color: '#aaaacc',
    textAlign: 'center',
  },
  trendAlert: {
    backgroundColor: '#1a1a00',
    borderColor: '#eab308',
    borderWidth: 1,
    borderRadius: 12,
    padding: 16,
    marginBottom: 20,
  },
  trendAlertTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: '#eab308',
    marginBottom: 6,
  },
  trendAlertText: {
    fontSize: 14,
    color: '#fef3c7',
    lineHeight: 21,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: '#666688',
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: 10,
    marginTop: 16,
  },
  metricsRow: {
    flexDirection: 'row',
    gap: 12,
  },
  metricCard: {
    flex: 1,
    backgroundColor: '#1a1a2e',
    borderRadius: 14,
    padding: 16,
    marginBottom: 12,
  },
  metricLabel: {
    fontSize: 13,
    color: '#aaaacc',
    marginBottom: 4,
  },
  metricValue: {
    fontSize: 28,
    fontWeight: '700',
    color: '#ffffff',
    marginBottom: 4,
  },
  metricUnit: {
    fontSize: 14,
    fontWeight: '400',
    color: '#aaaacc',
  },
  metricNA: {
    fontSize: 22,
    color: '#555577',
    marginBottom: 4,
  },
  metricDescription: {
    fontSize: 11,
    color: '#555577',
    lineHeight: 16,
  },
  flagsBox: {
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 14,
    marginTop: 8,
  },
  flagsTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: '#aaaacc',
    marginBottom: 6,
  },
  flagText: {
    fontSize: 13,
    color: '#888899',
    lineHeight: 20,
  },
  disclaimer: {
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 16,
    marginTop: 20,
  },
  disclaimerText: {
    fontSize: 13,
    color: '#aaaacc',
    lineHeight: 20,
  },
  feedbackCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 14,
    padding: 16,
    marginTop: 16,
  },
  feedbackThanksCard: {
    backgroundColor: '#102018',
    borderColor: '#4ade80',
    borderWidth: 1,
    borderRadius: 14,
    padding: 16,
    marginTop: 16,
  },
  feedbackTitle: {
    color: '#ffffff',
    fontSize: 17,
    fontWeight: '700',
    marginBottom: 6,
  },
  feedbackSubtitle: {
    color: '#aaaacc',
    fontSize: 13,
    lineHeight: 19,
    marginBottom: 12,
  },
  feedbackChoices: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 14,
  },
  feedbackChoice: {
    flex: 1,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#2f2f55',
    paddingVertical: 12,
    alignItems: 'center',
    backgroundColor: '#141428',
  },
  feedbackChoiceSelected: {
    borderColor: '#4f46e5',
    backgroundColor: '#232347',
  },
  feedbackChoiceText: {
    color: '#ffffff',
    fontWeight: '600',
    fontSize: 14,
  },
  npsTitle: {
    color: '#aaaacc',
    fontSize: 13,
    marginBottom: 10,
  },
  npsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: 14,
  },
  npsPill: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: '#141428',
    borderWidth: 1,
    borderColor: '#2f2f55',
    justifyContent: 'center',
    alignItems: 'center',
  },
  npsPillSelected: {
    backgroundColor: '#233329',
    borderColor: '#4ade80',
  },
  npsPillText: {
    color: '#ffffff',
    fontWeight: '600',
  },
  commentInput: {
    minHeight: 76,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#2f2f55',
    backgroundColor: '#141428',
    color: '#ffffff',
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginBottom: 12,
  },
  feedbackError: {
    color: '#f87171',
    fontSize: 13,
    marginBottom: 10,
  },
  feedbackSubmitButton: {
    backgroundColor: '#4f46e5',
    borderRadius: 12,
    paddingVertical: 12,
    alignItems: 'center',
  },
  feedbackSubmitDisabled: {
    opacity: 0.5,
  },
  feedbackSubmitText: {
    color: '#ffffff',
    fontWeight: '700',
    fontSize: 15,
  },
  feedbackSummary: {
    color: '#d1fae5',
    fontSize: 13,
    lineHeight: 20,
  },
  feedbackComment: {
    color: '#d1fae5',
    fontSize: 13,
    lineHeight: 20,
    marginTop: 8,
    fontStyle: 'italic',
  },
  scanAgainButton: {
    backgroundColor: '#4f46e5',
    borderRadius: 14,
    paddingVertical: 16,
    alignItems: 'center',
    marginTop: 20,
  },
  scanAgainText: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '700',
  },
});
