import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useBetaAccess } from '../hooks/useBetaAccess';

interface BetaOnboardingScreenProps {
  onEnrolled: (userId: string) => void;
}

export function BetaOnboardingScreen({ onEnrolled }: BetaOnboardingScreenProps) {
  const { userId, betaStatus, isLoading, error, redeemInvite } = useBetaAccess();
  const [inviteCode, setInviteCode] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const hasContinuedRef = useRef(false);

  const continueToConsent = useCallback(() => {
    if (!userId || hasContinuedRef.current) {
      return;
    }
    hasContinuedRef.current = true;
    onEnrolled(userId);
  }, [onEnrolled, userId]);

  useEffect(() => {
    if (!userId || !betaStatus) {
      return;
    }
    if (!betaStatus.beta_onboarding_enabled || betaStatus.enrolled) {
      continueToConsent();
    }
  }, [betaStatus, continueToConsent, userId]);

  const handleRedeem = async () => {
    if (!userId || !inviteCode.trim()) {
      return;
    }

    setSubmitting(true);
    try {
      await redeemInvite(inviteCode.trim());
      continueToConsent();
    } catch {
      // Error is surfaced through the hook.
    } finally {
      setSubmitting(false);
    }
  };

  if (isLoading && !betaStatus) {
    return (
      <View style={styles.centered} testID="beta-loading">
        <ActivityIndicator size="large" color="#f97316" />
      </View>
    );
  }

  return (
    <View style={styles.container} testID="beta-screen">
      <View style={styles.card}>
        <Text style={styles.badge}>Closed Beta</Text>
        <Text style={styles.title}>You’re early.</Text>
        <Text style={styles.subtitle}>
          PranaScan is currently onboarding a limited group of proactive professionals and remote
          caregivers. Enter your invite code to continue.
        </Text>

        <Text style={styles.label}>Invite code</Text>
        <TextInput
          autoCapitalize="characters"
          autoCorrect={false}
          placeholder="Enter your beta code"
          placeholderTextColor="#7c7c93"
          style={styles.input}
          value={inviteCode}
          onChangeText={setInviteCode}
          testID="beta-invite-input"
        />

        {error && (
          <View style={styles.errorBox} testID="beta-error">
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}

        <TouchableOpacity
          accessibilityState={{ disabled: !inviteCode.trim() || submitting || isLoading }}
          disabled={!inviteCode.trim() || submitting || isLoading}
          onPress={handleRedeem}
          style={[
            styles.button,
            (!inviteCode.trim() || submitting || isLoading) && styles.buttonDisabled,
          ]}
          testID="beta-redeem-button"
        >
          {submitting ? (
            <ActivityIndicator color="#ffffff" />
          ) : (
            <Text style={styles.buttonText}>Redeem Invite</Text>
          )}
        </TouchableOpacity>

        <Text style={styles.footer}>
          This onboarding step only unlocks access to the closed beta. PranaScan remains a wellness
          indicator tool and does not provide diagnoses.
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f1a',
    justifyContent: 'center',
    paddingHorizontal: 20,
  },
  centered: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#0f0f1a',
  },
  card: {
    backgroundColor: '#171726',
    borderRadius: 24,
    padding: 24,
    borderWidth: 1,
    borderColor: '#2d2d46',
  },
  badge: {
    alignSelf: 'flex-start',
    backgroundColor: '#3b2214',
    color: '#fb923c',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 999,
    fontSize: 12,
    fontWeight: '700',
    marginBottom: 16,
    overflow: 'hidden',
  },
  title: {
    color: '#ffffff',
    fontSize: 28,
    fontWeight: '700',
    marginBottom: 10,
  },
  subtitle: {
    color: '#b6b6c8',
    fontSize: 15,
    lineHeight: 24,
    marginBottom: 22,
  },
  label: {
    color: '#f4f4fa',
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 8,
  },
  input: {
    backgroundColor: '#0f0f1a',
    borderWidth: 1,
    borderColor: '#32324a',
    borderRadius: 14,
    color: '#ffffff',
    fontSize: 16,
    paddingHorizontal: 16,
    paddingVertical: 14,
    marginBottom: 16,
  },
  errorBox: {
    backgroundColor: '#2a1a1a',
    borderRadius: 10,
    padding: 14,
    marginBottom: 16,
  },
  errorText: {
    color: '#fca5a5',
    fontSize: 14,
    lineHeight: 20,
  },
  button: {
    backgroundColor: '#f97316',
    borderRadius: 14,
    paddingVertical: 16,
    alignItems: 'center',
    marginBottom: 16,
  },
  buttonDisabled: {
    opacity: 0.45,
  },
  buttonText: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '700',
  },
  footer: {
    color: '#7c7c93',
    fontSize: 12,
    lineHeight: 18,
  },
});
