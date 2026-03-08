/**
 * ConsentScreen — informed consent flow.
 *
 * Users must explicitly agree before any wellness scan can begin.
 * Written in plain language — no legalese.
 */

import React, { useState } from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useConsent } from '../hooks/useConsent';

interface ConsentScreenProps {
  onConsentGranted: (userId: string) => void;
}

export function ConsentScreen({ onConsentGranted }: ConsentScreenProps) {
  const { userId, isLoading, error, grantUserConsent, hasActiveConsent } = useConsent();
  const [checked, setChecked] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // If consent is already active (returning user), auto-advance
  React.useEffect(() => {
    if (hasActiveConsent && userId) {
      onConsentGranted(userId);
    }
  }, [hasActiveConsent, userId, onConsentGranted]);

  const handleAgree = async () => {
    if (!checked || !userId) return;
    setSubmitting(true);
    try {
      await grantUserConsent();
      onConsentGranted(userId);
    } catch {
      // error shown via hook
    } finally {
      setSubmitting(false);
    }
  };

  if (isLoading) {
    return (
      <View style={styles.centered} testID="consent-loading">
        <ActivityIndicator size="large" color="#4f46e5" />
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      testID="consent-screen"
    >
      <View style={styles.header}>
        <Text style={styles.logo}>🫁</Text>
        <Text style={styles.title}>Welcome to PranaScan</Text>
        <Text style={styles.subtitle}>
          Your personal wellness check-in — takes about 35 seconds.
        </Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>What PranaScan does</Text>
        <Text style={styles.cardText}>
          • Uses your front camera (30 seconds) to estimate heart rate and breathing patterns.{'\n'}
          • Uses your microphone (5 seconds) for a quick voice wellness check.{'\n'}
          • All processing happens on your phone — your video and audio are never sent anywhere.{'\n'}
          • Only anonymised wellness numbers are stored on our servers.
        </Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>What PranaScan is not</Text>
        <Text style={styles.cardText}>
          PranaScan is a wellness indicator tool, not a medical device. The results are for
          informational self-monitoring only. Always consult a qualified doctor for any health
          concerns.
        </Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Your data rights</Text>
        <Text style={styles.cardText}>
          • You can revoke consent and request data deletion at any time from Settings.{'\n'}
          • Deletion requests are honoured within 30 days (legal hold period).{'\n'}
          • We never sell your data or share it with advertisers.
        </Text>
      </View>

      {error && (
        <View style={styles.errorBox} testID="consent-error">
          <Text style={styles.errorText}>{error}</Text>
        </View>
      )}

      <TouchableOpacity
        style={styles.checkRow}
        onPress={() => setChecked((c) => !c)}
        testID="consent-checkbox"
        accessibilityRole="checkbox"
        accessibilityState={{ checked }}
      >
        <View style={[styles.checkbox, checked && styles.checkboxChecked]}>
          {checked && <Text style={styles.checkmark}>✓</Text>}
        </View>
        <Text style={styles.checkLabel}>
          I understand that PranaScan provides wellness indicators only — not medical advice — and I
          consent to anonymous wellness data being stored to track my trends.
        </Text>
      </TouchableOpacity>

      <TouchableOpacity
        style={[styles.agreeButton, (!checked || submitting) && styles.agreeButtonDisabled]}
        onPress={handleAgree}
        disabled={!checked || submitting}
        testID="consent-agree-button"
      >
        {submitting ? (
          <ActivityIndicator color="#ffffff" />
        ) : (
          <Text style={styles.agreeButtonText}>I Agree — Start Scan</Text>
        )}
      </TouchableOpacity>

      <Text style={styles.footerText}>
        You can withdraw consent at any time in Settings. This consent is stored in compliance
        with the Digital Personal Data Protection Act 2023 (India).
      </Text>
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
  },
  header: {
    alignItems: 'center',
    marginBottom: 32,
  },
  logo: {
    fontSize: 48,
    marginBottom: 12,
  },
  title: {
    fontSize: 28,
    fontWeight: '700',
    color: '#ffffff',
    marginBottom: 8,
    textAlign: 'center',
  },
  subtitle: {
    fontSize: 16,
    color: '#aaaacc',
    textAlign: 'center',
    lineHeight: 24,
  },
  card: {
    backgroundColor: '#1a1a2e',
    borderRadius: 14,
    padding: 18,
    marginBottom: 14,
  },
  cardTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: '#ffffff',
    marginBottom: 8,
  },
  cardText: {
    fontSize: 14,
    color: '#aaaacc',
    lineHeight: 22,
  },
  errorBox: {
    backgroundColor: '#2a1a1a',
    borderRadius: 10,
    padding: 14,
    marginBottom: 14,
  },
  errorText: {
    color: '#f87171',
    fontSize: 14,
    textAlign: 'center',
  },
  checkRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: 20,
    marginTop: 4,
  },
  checkbox: {
    width: 24,
    height: 24,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: '#4f46e5',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
    marginTop: 2,
    flexShrink: 0,
  },
  checkboxChecked: {
    backgroundColor: '#4f46e5',
  },
  checkmark: {
    color: '#ffffff',
    fontSize: 14,
    fontWeight: '700',
  },
  checkLabel: {
    flex: 1,
    fontSize: 14,
    color: '#ccccee',
    lineHeight: 22,
  },
  agreeButton: {
    backgroundColor: '#4f46e5',
    borderRadius: 14,
    paddingVertical: 16,
    alignItems: 'center',
    marginBottom: 20,
  },
  agreeButtonDisabled: {
    opacity: 0.4,
  },
  agreeButtonText: {
    color: '#ffffff',
    fontSize: 17,
    fontWeight: '700',
  },
  footerText: {
    fontSize: 12,
    color: '#555577',
    textAlign: 'center',
    lineHeight: 18,
  },
});
