import React from 'react';
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { PranaPulseReveal } from '../components/pranapulse/PranaPulseReveal';
import { PranaPulseScaffold } from '../components/pranapulse/PranaPulseScaffold';
import { pranaPulseShadow, pranaPulseTheme, withAlpha } from '../theme/pranaPulse';

interface AuthScreenProps {
  onSignIn: () => Promise<void>;
  isAuthenticating: boolean;
  isReady: boolean;
  error: string | null;
}

export function AuthScreen({
  onSignIn,
  isAuthenticating,
  isReady,
  error,
}: AuthScreenProps) {
  return (
    <PranaPulseScaffold activeTab="home" scroll={false} showBottomNav={false}>
      <View style={styles.content} testID="auth-screen">
        <PranaPulseReveal delay={20}>
          <View style={styles.hero}>
            <Text style={styles.eyebrow}>PranaPulse Core</Text>
            <Text style={styles.title}>Sign in to continue</Text>
            <Text style={styles.subtitle}>
              Your OIDC session keeps consent, scan history, and feedback attached to the same PranaPulse account.
            </Text>
          </View>
        </PranaPulseReveal>

        <PranaPulseReveal delay={110}>
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Before you start</Text>
            <Text style={styles.cardText}>
              Use the identity provider configured for your local `service-core` environment. On a physical device, the issuer URL must be reachable from your phone.
            </Text>

            {error ? (
              <View style={styles.errorBox} testID="auth-error">
                <Text style={styles.errorText}>{error}</Text>
              </View>
            ) : null}

            <TouchableOpacity
              style={[styles.signInButton, (!isReady || isAuthenticating) && styles.signInButtonDisabled]}
              onPress={() => {
                void onSignIn();
              }}
              disabled={!isReady || isAuthenticating}
              testID="auth-sign-in-button"
            >
              {isAuthenticating ? (
                <ActivityIndicator color={pranaPulseTheme.colors.onPrimary} />
              ) : (
                <Text style={styles.signInButtonText}>Sign In With OIDC</Text>
              )}
            </TouchableOpacity>

            <View style={styles.helperPanel}>
              <Text style={styles.helperLabel}>Setup note</Text>
              <Text style={styles.helperText}>
                If this button never enables, check `EXPO_PUBLIC_OIDC_ISSUER` and `EXPO_PUBLIC_OIDC_CLIENT_ID`.
              </Text>
            </View>
          </View>
        </PranaPulseReveal>
      </View>
    </PranaPulseScaffold>
  );
}

const styles = StyleSheet.create({
  content: {
    flex: 1,
    justifyContent: 'center',
    gap: 22,
    paddingBottom: 24,
  },
  hero: {
    gap: 8,
  },
  eyebrow: {
    ...pranaPulseTheme.type.eyebrow,
    color: pranaPulseTheme.colors.primary,
  },
  title: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 34,
    letterSpacing: -0.8,
  },
  subtitle: {
    ...pranaPulseTheme.type.body,
    maxWidth: 330,
  },
  card: {
    borderRadius: pranaPulseTheme.radius.lg,
    padding: 24,
    backgroundColor: pranaPulseTheme.colors.surfaceContainerLowest,
    gap: 16,
    ...pranaPulseShadow,
  },
  cardTitle: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 22,
  },
  cardText: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 15,
    lineHeight: 23,
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
  signInButton: {
    borderRadius: pranaPulseTheme.radius.full,
    paddingVertical: 17,
    alignItems: 'center',
    backgroundColor: pranaPulseTheme.colors.primary,
  },
  signInButtonDisabled: {
    opacity: 0.45,
  },
  signInButtonText: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onPrimary,
    fontSize: 16,
  },
  helperPanel: {
    borderRadius: pranaPulseTheme.radius.md,
    padding: 16,
    backgroundColor: pranaPulseTheme.colors.surfaceContainerLow,
    gap: 6,
  },
  helperLabel: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 13,
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  helperText: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 13,
    lineHeight: 20,
  },
});
