/**
 * VoiceCapture component — 5-second sustained vowel capture.
 *
 * Sprint 1: Simulated voice analysis for MVP scaffolding.
 * Sprint 2: Replace simulateVoiceAnalysis() with real jitter/shimmer algorithm.
 *
 * Raw audio NEVER leaves the device.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

const RECORD_DURATION_MS = 5_000;

export interface VoiceResult {
  voice_jitter_pct: number;
  voice_shimmer_pct: number;
  audio_snr_db: number;
  passed_snr: boolean;
}

interface VoiceCaptureProps {
  onComplete: (result: VoiceResult) => void;
  onCancel: () => void;
}

/**
 * Simulates voice analysis for Sprint 1.
 * Returns plausible jitter/shimmer values.
 * Replace with real audio processing in Sprint 2.
 */
function simulateVoiceAnalysis(): VoiceResult {
  const audio_snr_db = 18 + Math.random() * 15; // 18–33 dB
  return {
    voice_jitter_pct: 0.1 + Math.random() * 0.8, // 0.1–0.9%
    voice_shimmer_pct: 0.5 + Math.random() * 3.0, // 0.5–3.5%
    audio_snr_db,
    passed_snr: audio_snr_db > 15.0,
  };
}

type RecordingState = 'idle' | 'countdown' | 'recording' | 'processing' | 'done';

export function VoiceCapture({ onComplete, onCancel }: VoiceCaptureProps) {
  const [recordingState, setRecordingState] = useState<RecordingState>('idle');
  const [timeRemaining, setTimeRemaining] = useState(RECORD_DURATION_MS / 1000);
  const [waveAmplitudes, setWaveAmplitudes] = useState<number[]>(Array(20).fill(0.1));
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const waveRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startRef = useRef<number | null>(null);

  const stopTimers = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    if (waveRef.current) clearInterval(waveRef.current);
  }, []);

  useEffect(() => () => stopTimers(), [stopTimers]);

  const startRecording = useCallback(() => {
    setRecordingState('recording');
    setTimeRemaining(RECORD_DURATION_MS / 1000);
    startRef.current = Date.now();

    // Animate waveform
    waveRef.current = setInterval(() => {
      setWaveAmplitudes(Array.from({ length: 20 }, () => 0.2 + Math.random() * 0.8));
    }, 100);

    // Countdown
    timerRef.current = setInterval(() => {
      const elapsed = Date.now() - (startRef.current ?? Date.now());
      const remaining = Math.max(0, Math.ceil((RECORD_DURATION_MS - elapsed) / 1000));
      setTimeRemaining(remaining);

      if (remaining <= 0) {
        stopTimers();
        setRecordingState('processing');
        setWaveAmplitudes(Array(20).fill(0.1));

        // Simulate processing delay
        setTimeout(() => {
          const voiceResult = simulateVoiceAnalysis();
          setRecordingState('done');
          onComplete(voiceResult);
        }, 800);
      }
    }, 200);
  }, [onComplete, stopTimers]);

  const progressPct = ((RECORD_DURATION_MS / 1000 - timeRemaining) / (RECORD_DURATION_MS / 1000)) * 100;

  return (
    <View style={styles.container} testID="voice-capture">
      <Text style={styles.title}>Voice Check</Text>
      <Text style={styles.subtitle}>
        Say &quot;Aaah&quot; in a steady tone for 5 seconds in a quiet space.
      </Text>

      {/* Waveform visualisation */}
      <View style={styles.waveContainer} testID="waveform">
        {waveAmplitudes.map((amp, i) => (
          <View
            key={i}
            style={[
              styles.waveBar,
              {
                height: Math.max(4, amp * 60),
                backgroundColor:
                  recordingState === 'recording' ? '#4f46e5' : '#2a2a4e',
              },
            ]}
          />
        ))}
      </View>

      {/* Progress */}
      {(recordingState === 'recording' || recordingState === 'processing') && (
        <View style={styles.progressBar}>
          <View
            style={[
              styles.progressFill,
              { width: `${progressPct}%` as `${number}%` },
            ]}
          />
        </View>
      )}

      <Text style={styles.timerText} testID="voice-timer">
        {recordingState === 'recording'
          ? `${timeRemaining}s remaining`
          : recordingState === 'processing'
          ? 'Analysing…'
          : recordingState === 'done'
          ? '✓ Done'
          : 'Ready'}
      </Text>

      <View style={styles.buttonRow}>
        {recordingState === 'idle' && (
          <TouchableOpacity style={styles.recordButton} onPress={startRecording} testID="start-voice">
            <Text style={styles.recordButtonText}>🎙 Start Voice Check</Text>
          </TouchableOpacity>
        )}
        {recordingState === 'recording' && (
          <TouchableOpacity style={styles.cancelButton} onPress={onCancel} testID="cancel-voice">
            <Text style={styles.cancelButtonText}>Cancel</Text>
          </TouchableOpacity>
        )}
      </View>

      <Text style={styles.disclaimer}>
        Voice recordings stay on your device. Only wellness indicators are shared.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f1a',
    alignItems: 'center',
    paddingTop: 40,
    paddingHorizontal: 20,
  },
  title: {
    fontSize: 24,
    fontWeight: '700',
    color: '#ffffff',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 15,
    color: '#aaaacc',
    textAlign: 'center',
    lineHeight: 22,
    marginBottom: 32,
  },
  waveContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    height: 80,
    gap: 3,
    marginBottom: 20,
  },
  waveBar: {
    width: 8,
    borderRadius: 4,
    minHeight: 4,
  },
  progressBar: {
    width: '100%',
    height: 4,
    backgroundColor: '#2a2a4e',
    borderRadius: 2,
    overflow: 'hidden',
    marginBottom: 12,
  },
  progressFill: {
    height: '100%',
    backgroundColor: '#4f46e5',
    borderRadius: 2,
  },
  timerText: {
    fontSize: 18,
    fontWeight: '600',
    color: '#aaaacc',
    marginBottom: 32,
  },
  buttonRow: {
    width: '100%',
  },
  recordButton: {
    backgroundColor: '#4f46e5',
    borderRadius: 14,
    paddingVertical: 16,
    alignItems: 'center',
  },
  recordButtonText: {
    color: '#ffffff',
    fontSize: 17,
    fontWeight: '700',
  },
  cancelButton: {
    backgroundColor: '#2a1a1a',
    borderRadius: 14,
    paddingVertical: 16,
    alignItems: 'center',
  },
  cancelButtonText: {
    color: '#f87171',
    fontSize: 17,
    fontWeight: '600',
  },
  disclaimer: {
    fontSize: 12,
    color: '#666688',
    textAlign: 'center',
    marginTop: 'auto',
    paddingBottom: 20,
    lineHeight: 18,
  },
});
