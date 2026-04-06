import { Redirect, useRouter } from 'expo-router';
import React from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import { CircleScreen } from '../src/screens/CircleScreen';
import { useAppSession } from '../src/providers/AppSessionProvider';
import { pranaPulseTheme } from '../src/theme/pranaPulse';

export default function CircleRoute() {
  const router = useRouter();
  const { auth, hasAccess, isBootstrapping } = useAppSession();

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
    <CircleScreen
      currentUserId={auth.user?.id ?? ''}
      displayName={auth.user?.displayName ?? null}
      onOpenHome={() => router.push('/')}
      onOpenResults={() => router.push('/results')}
      onOpenScan={() => router.push('/scan')}
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
