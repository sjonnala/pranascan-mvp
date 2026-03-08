/**
 * PranaScan App — root component.
 *
 * Manages top-level navigation state:
 *   Consent → Scan → Results → (repeat)
 */

import React, { useState } from 'react';
import { SafeAreaView, StatusBar, StyleSheet } from 'react-native';
import { ConsentScreen } from './src/screens/ConsentScreen';
import { ScanScreen } from './src/screens/ScanScreen';
import { ResultsScreen } from './src/screens/ResultsScreen';

type AppScreen = 'consent' | 'scan' | 'results';

export default function App() {
  const [screen, setScreen] = useState<AppScreen>('consent');
  const [userId, setUserId] = useState<string | null>(null);
  const [completedSessionId, setCompletedSessionId] = useState<string | null>(null);

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#0f0f1a" />

      {screen === 'consent' && (
        <ConsentScreen
          onConsentGranted={(uid) => {
            setUserId(uid);
            setScreen('scan');
          }}
        />
      )}

      {screen === 'scan' && userId && (
        <ScanScreen
          userId={userId}
          onComplete={(sessionId) => {
            setCompletedSessionId(sessionId);
            setScreen('results');
          }}
          onCancel={() => setScreen('consent')}
        />
      )}

      {screen === 'results' && completedSessionId && (
        <ResultsScreen
          sessionId={completedSessionId}
          onScanAgain={() => setScreen('scan')}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f1a',
  },
});
