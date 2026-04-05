/**
 * PranaScan App — root component.
 */

import React, { useEffect, useState } from 'react';
import { ActivityIndicator, SafeAreaView, StatusBar, StyleSheet, Text, View } from 'react-native';
import { useOidcAuth } from './src/hooks/useOidcAuth';
import { AuthScreen } from './src/screens/AuthScreen';
import { ConsentScreen } from './src/screens/ConsentScreen';
import { ResultsScreen } from './src/screens/ResultsScreen';
import { ScanScreen } from './src/screens/ScanScreen';

type AppScreen = 'consent' | 'scan' | 'results';

function AppBootSplash() {
  return (
    <View style={styles.loadingContainer} testID="app-loading">
      <ActivityIndicator size="large" color="#4f46e5" />
      <Text style={styles.loadingText}>Restoring your secure session…</Text>
    </View>
  );
}

export default function App() {
  const auth = useOidcAuth();
  const [screen, setScreen] = useState<AppScreen>('consent');
  const [completedSessionId, setCompletedSessionId] = useState<string | null>(null);

  useEffect(() => {
    if (auth.status !== 'signed_in') {
      setScreen('consent');
      setCompletedSessionId(null);
    }
  }, [auth.status]);

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#0f0f1a" />

      {auth.status === 'loading' ? (
        <AppBootSplash />
      ) : auth.status !== 'signed_in' || !auth.user ? (
        <AuthScreen
          onSignIn={auth.signIn}
          isAuthenticating={auth.isAuthenticating}
          isReady={auth.isReady}
          error={auth.error}
        />
      ) : (
        <>
          {screen === 'consent' ? (
            <ConsentScreen
              onConsentGranted={() => {
                setScreen('scan');
              }}
            />
          ) : null}

          {screen === 'scan' ? (
            <ScanScreen
              onComplete={(sessionId) => {
                setCompletedSessionId(sessionId);
                setScreen('results');
              }}
              onCancel={() => setScreen('consent')}
            />
          ) : null}

          {screen === 'results' && completedSessionId ? (
            <ResultsScreen
              sessionId={completedSessionId}
              onScanAgain={() => setScreen('scan')}
            />
          ) : null}
        </>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f1a',
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#0f0f1a',
    paddingHorizontal: 24,
  },
  loadingText: {
    color: '#c7c7e4',
    fontSize: 16,
    marginTop: 14,
  },
});
