import { Redirect, useLocalSearchParams, useRouter } from 'expo-router';
import React from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import { ScanScreen } from '../src/screens/ScanScreen';
import { useAppSession } from '../src/providers/AppSessionProvider';
import { pranaPulseTheme } from '../src/theme/pranaPulse';
import { ScanType } from '../src/types';

function parseScanType(value: string | string[] | undefined): ScanType | undefined {
  const candidate = Array.isArray(value) ? value[0] : value;
  return candidate === 'standard' || candidate === 'deep_dive' ? candidate : undefined;
}

export default function ScanRoute() {
  const router = useRouter();
  const params = useLocalSearchParams<{ scanType?: string | string[] }>();
  const { hasAccess, isBootstrapping } = useAppSession();

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
    <ScanScreen
      hideModeSelect={Boolean(parseScanType(params.scanType))}
      initialScanType={parseScanType(params.scanType)}
      onCancel={() => router.replace('/')}
      onComplete={(sessionId) => {
        router.replace({ pathname: '/results', params: { sessionId } });
      }}
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
