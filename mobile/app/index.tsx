import { useRouter } from 'expo-router';
import React from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { AuthScreen } from '../src/screens/AuthScreen';
import { ConsentScreen } from '../src/screens/ConsentScreen';
import { HomeScreen } from '../src/screens/HomeScreen';
import { useAppSession } from '../src/providers/AppSessionProvider';
import { pranaPulseTheme } from '../src/theme/pranaPulse';

function AppBootSplash() {
  return (
    <View style={styles.loadingContainer} testID="app-loading">
      <ActivityIndicator color={pranaPulseTheme.colors.primary} size="large" />
      <Text style={styles.loadingText}>Restoring your PranaPulse session…</Text>
    </View>
  );
}

export default function IndexRoute() {
  const router = useRouter();
  const { auth, hasAccess, isBootstrapping } = useAppSession();

  if (isBootstrapping) {
    return <AppBootSplash />;
  }

  if (auth.status !== 'signed_in' || !auth.user) {
    return (
      <AuthScreen
        error={auth.error}
        isAuthenticating={auth.isAuthenticating}
        isReady={auth.isReady}
        onSignIn={auth.signIn}
      />
    );
  }

  if (!hasAccess) {
    return <ConsentScreen onConsentGranted={() => router.replace('/')} />;
  }

  return (
    <HomeScreen
      displayName={auth.user.displayName}
      onOpenCircle={() => router.push('/circle')}
      onOpenResults={() => router.push('/results')}
      onOpenScanModes={() => router.push('/scan')}
      onStartDailyGlow={() => router.push({ pathname: '/scan', params: { scanType: 'standard' } })}
    />
  );
}

const styles = StyleSheet.create({
  loadingContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: pranaPulseTheme.colors.background,
    paddingHorizontal: 24,
  },
  loadingText: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 16,
    marginTop: 14,
    textAlign: 'center',
  },
});
