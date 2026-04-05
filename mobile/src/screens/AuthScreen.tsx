import React from 'react';
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

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
    <View style={styles.container} testID="auth-screen">
      <View style={styles.hero}>
        <Text style={styles.eyebrow}>PranaPulse Core</Text>
        <Text style={styles.title}>Sign in to continue</Text>
        <Text style={styles.subtitle}>
          Your mobile session now uses the same OIDC identity as `service-core`, so consent, scan
          history, and feedback all stay attached to your real account.
        </Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Before you start</Text>
        <Text style={styles.cardText}>
          Use the identity provider configured for your local `service-core` environment. On a
          physical device, the issuer URL must be reachable from your phone.
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
            <ActivityIndicator color="#ffffff" />
          ) : (
            <Text style={styles.signInButtonText}>Sign In With OIDC</Text>
          )}
        </TouchableOpacity>

        <Text style={styles.helperText}>
          If this button never enables, check `EXPO_PUBLIC_OIDC_ISSUER` and `EXPO_PUBLIC_OIDC_CLIENT_ID`.
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f1a',
    paddingHorizontal: 24,
    paddingVertical: 48,
    justifyContent: 'center',
  },
  hero: {
    marginBottom: 28,
  },
  eyebrow: {
    color: '#7dd3fc',
    fontSize: 13,
    fontWeight: '700',
    letterSpacing: 1.4,
    textTransform: 'uppercase',
    marginBottom: 12,
  },
  title: {
    color: '#ffffff',
    fontSize: 34,
    fontWeight: '700',
    marginBottom: 12,
  },
  subtitle: {
    color: '#b8b8d8',
    fontSize: 16,
    lineHeight: 24,
  },
  card: {
    backgroundColor: '#17172a',
    borderRadius: 18,
    padding: 20,
  },
  cardTitle: {
    color: '#ffffff',
    fontSize: 18,
    fontWeight: '700',
    marginBottom: 10,
  },
  cardText: {
    color: '#b8b8d8',
    fontSize: 15,
    lineHeight: 22,
    marginBottom: 20,
  },
  signInButton: {
    backgroundColor: '#2563eb',
    borderRadius: 14,
    paddingVertical: 16,
    alignItems: 'center',
  },
  signInButtonDisabled: {
    opacity: 0.5,
  },
  signInButtonText: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '700',
  },
  helperText: {
    color: '#7d7d99',
    fontSize: 12,
    lineHeight: 18,
    marginTop: 14,
  },
  errorBox: {
    backgroundColor: '#2f1620',
    borderRadius: 12,
    padding: 12,
    marginBottom: 16,
  },
  errorText: {
    color: '#fda4af',
    fontSize: 14,
    lineHeight: 20,
  },
});
