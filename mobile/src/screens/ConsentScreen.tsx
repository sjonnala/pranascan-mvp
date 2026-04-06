/**
 * ConsentScreen — informed consent flow.
 */

import React, { useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { PranaPulseReveal } from '../components/pranapulse/PranaPulseReveal';
import { PranaPulseScaffold } from '../components/pranapulse/PranaPulseScaffold';
import { useConsent } from '../hooks/useConsent';
import { pranaPulseShadow, pranaPulseTheme, withAlpha } from '../theme/pranaPulse';

interface ConsentScreenProps {
  onConsentGranted: () => void;
}

export function ConsentScreen({ onConsentGranted }: ConsentScreenProps) {
  const { isLoading, error, grantUserConsent, hasActiveConsent } = useConsent();
  const [checked, setChecked] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  React.useEffect(() => {
    if (hasActiveConsent) {
      onConsentGranted();
    }
  }, [hasActiveConsent, onConsentGranted]);

  const handleAgree = async () => {
    if (!checked) {
      return;
    }

    setSubmitting(true);
    try {
      await grantUserConsent();
      onConsentGranted();
    } catch {
      // error shown via hook
    } finally {
      setSubmitting(false);
    }
  };

  if (isLoading) {
    return (
      <PranaPulseScaffold activeTab="home" scroll={false} showBottomNav={false}>
        <View style={styles.centered} testID="consent-loading">
          <ActivityIndicator size="large" color={pranaPulseTheme.colors.primary} />
        </View>
      </PranaPulseScaffold>
    );
  }

  return (
    <PranaPulseScaffold activeTab="home" showBottomNav={false}>
      <View style={styles.content} testID="consent-screen">
        <PranaPulseReveal delay={20}>
          <View style={styles.header}>
            <Text style={styles.eyebrow}>Consent</Text>
            <Text style={styles.title}>Begin with clarity</Text>
            <Text style={styles.subtitle}>
              Your Daily Glow check-in takes about 35 seconds. Here is exactly what PranaPulse captures and stores.
            </Text>
          </View>
        </PranaPulseReveal>

        <PranaPulseReveal delay={100}>
          <View style={styles.card}>
            <Text style={styles.cardTitle}>What PranaPulse does</Text>
            <Text style={styles.cardText}>
              • Uses your front camera for 30 seconds to estimate heart rate and breathing patterns.{'\n'}
              • Uses your microphone for 5 seconds for a quick voice wellness check.{'\n'}
              • Keeps video and audio on your phone; only summary wellness values reach the backend.{'\n'}
              • Stores pseudonymous wellness trends so your results stay connected over time.
            </Text>
          </View>
        </PranaPulseReveal>

        <PranaPulseReveal delay={160}>
          <View style={styles.card}>
            <Text style={styles.cardTitle}>What it is not</Text>
            <Text style={styles.cardText}>
              PranaPulse is a wellness indicator tool, not a medical device. The results are for informational self-monitoring only. Always consult a qualified clinician for health concerns.
            </Text>
          </View>
        </PranaPulseReveal>

        <PranaPulseReveal delay={220}>
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Your data rights</Text>
            <Text style={styles.cardText}>
              • You can revoke consent and request deletion at any time from Settings.{'\n'}
              • Deletion requests are honored within the configured legal hold window.{'\n'}
              • Your data is never sold or shared with advertisers.
            </Text>
          </View>
        </PranaPulseReveal>

        {error ? (
          <PranaPulseReveal delay={260}>
            <View style={styles.errorBox} testID="consent-error">
              <Text style={styles.errorText}>{error}</Text>
            </View>
          </PranaPulseReveal>
        ) : null}

        <PranaPulseReveal delay={300}>
          <TouchableOpacity
            style={styles.checkRow}
            onPress={() => setChecked((current) => !current)}
            testID="consent-checkbox"
            accessibilityRole="checkbox"
            accessibilityState={{ checked }}
          >
            <View style={[styles.checkbox, checked && styles.checkboxChecked]}>
              {checked ? <Text style={styles.checkmark}>OK</Text> : null}
            </View>
            <Text style={styles.checkLabel}>
              I understand that PranaPulse provides wellness indicators only, not medical advice, and I consent to my wellness data being stored to track my trends.
            </Text>
          </TouchableOpacity>
        </PranaPulseReveal>

        <PranaPulseReveal delay={340}>
          <TouchableOpacity
            style={[styles.agreeButton, (!checked || submitting) && styles.agreeButtonDisabled]}
            onPress={handleAgree}
            disabled={!checked || submitting}
            testID="consent-agree-button"
          >
            {submitting ? (
              <ActivityIndicator color={pranaPulseTheme.colors.onPrimary} />
            ) : (
              <Text style={styles.agreeButtonText}>I Agree - Start Scan</Text>
            )}
          </TouchableOpacity>
        </PranaPulseReveal>

        <PranaPulseReveal delay={380}>
          <Text style={styles.footerText}>
            You can withdraw consent at any time in Settings. This consent is recorded against your signed-in PranaPulse account.
          </Text>
        </PranaPulseReveal>
      </View>
    </PranaPulseScaffold>
  );
}

const styles = StyleSheet.create({
  content: {
    gap: 14,
    paddingBottom: 24,
  },
  centered: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  header: {
    gap: 8,
    marginBottom: 6,
  },
  eyebrow: {
    ...pranaPulseTheme.type.eyebrow,
    color: pranaPulseTheme.colors.primary,
  },
  title: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 32,
    letterSpacing: -0.7,
  },
  subtitle: {
    ...pranaPulseTheme.type.body,
    maxWidth: 330,
  },
  card: {
    backgroundColor: pranaPulseTheme.colors.surfaceContainerLowest,
    borderRadius: pranaPulseTheme.radius.md,
    padding: 18,
    gap: 8,
    ...pranaPulseShadow,
  },
  cardTitle: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    fontSize: 16,
    color: pranaPulseTheme.colors.onSurface,
  },
  cardText: {
    fontFamily: pranaPulseTheme.fonts.medium,
    fontSize: 14,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    lineHeight: 22,
  },
  errorBox: {
    borderRadius: pranaPulseTheme.radius.md,
    padding: 14,
    backgroundColor: withAlpha(pranaPulseTheme.colors.secondaryContainer, 0.74),
  },
  errorText: {
    color: pranaPulseTheme.colors.secondary,
    fontSize: 14,
    lineHeight: 20,
  },
  checkRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
    marginTop: 4,
  },
  checkbox: {
    width: 26,
    height: 26,
    borderRadius: 8,
    borderWidth: 2,
    borderColor: pranaPulseTheme.colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
    flexShrink: 0,
    marginTop: 2,
  },
  checkboxChecked: {
    backgroundColor: pranaPulseTheme.colors.primary,
  },
  checkmark: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.onPrimary,
    fontSize: 10,
    letterSpacing: 0.6,
  },
  checkLabel: {
    fontFamily: pranaPulseTheme.fonts.medium,
    flex: 1,
    fontSize: 14,
    color: pranaPulseTheme.colors.onSurface,
    lineHeight: 22,
  },
  agreeButton: {
    backgroundColor: pranaPulseTheme.colors.primary,
    borderRadius: pranaPulseTheme.radius.full,
    paddingVertical: 17,
    alignItems: 'center',
    marginTop: 6,
  },
  agreeButtonDisabled: {
    opacity: 0.4,
  },
  agreeButtonText: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onPrimary,
    fontSize: 16,
  },
  footerText: {
    fontFamily: pranaPulseTheme.fonts.medium,
    fontSize: 12,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    textAlign: 'center',
    lineHeight: 18,
    marginTop: 4,
  },
});
