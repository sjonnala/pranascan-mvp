import { Redirect, useLocalSearchParams, useRouter } from 'expo-router';
import React from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import { ResultsScreen } from '../src/screens/ResultsScreen';
import { useAppSession } from '../src/providers/AppSessionProvider';
import { pranaPulseTheme } from '../src/theme/pranaPulse';

export default function ResultsRoute() {
  const router = useRouter();
  const params = useLocalSearchParams<{ sessionId?: string | string[] }>();
  const { auth, hasAccess, isBootstrapping } = useAppSession();
  const sessionId = Array.isArray(params.sessionId) ? params.sessionId[0] : params.sessionId;

  if (isBootstrapping) {
    return (
      <View style={styles.loadingShell}>
        <ActivityIndicator color={pranaPulseTheme.colors.primary} size="large" />
      </View>
    );
  }

  if (!isBootstrapping && !hasAccess) {
    return <Redirect href="/" />;
  }

  return (
    <ResultsScreen
      displayName={auth.user?.displayName ?? null}
      onGoCircle={() => router.push('/circle')}
      onGoHome={() => router.push('/')}
      onGoResults={() => router.push('/results')}
      onGoScan={() => router.push('/scan')}
      onScanAgain={() => router.push({ pathname: '/scan', params: { scanType: 'standard' } })}
      sessionId={sessionId}
    />
  );
}

const styles = StyleSheet.create({
  loadingShell: {
    flex: 1,
    backgroundColor: pranaPulseTheme.colors.background,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
