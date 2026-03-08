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
  TouchableOpacity,
  View,
} from 'react-native';
import { getScanSession } from '../api/client';
import { ScanResult } from '../types';

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
  onScanAgain: () => void;
}

export function ResultsScreen({ sessionId, onScanAgain }: ResultsScreenProps) {
  const [result, setResult] = useState<ScanResult | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const sessionData = await getScanSession(sessionId);
        setResult(sessionData.result);
      } catch {
        setError('Could not load your results. Please check your connection.');
      } finally {
        setIsLoading(false);
      }
    })();
  }, [sessionId]);

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

      {/* Trend alert — only "consider_lab_followup", never diagnostic language */}
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
    backgroundColor: '#0a1a0a',
    borderRadius: 12,
    padding: 14,
    marginTop: 20,
  },
  disclaimerText: {
    fontSize: 13,
    color: '#4ade80',
    lineHeight: 20,
    textAlign: 'center',
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
    fontSize: 17,
    fontWeight: '700',
  },
});
