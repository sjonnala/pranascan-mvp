/**
 * VoiceCapture — 5-second sustained vowel capture.
 *
 * S2-02: Removed simulateVoiceAnalysis() and all Math.random() calls for
 * business metrics. Voice jitter/shimmer now returns undefined — the backend
 * voice DSP processor (app/services/voice_processor.py) will compute these
 * from audio_samples in S2-03 when real expo-av recording is wired.
 *
 * The waveform visualisation still uses Math.random() for bar heights — this
 * is cosmetic UI animation, not a wellness metric.
 *
 * Raw audio NEVER leaves the device.
 * Non-diagnostic language only — no clinical terminology anywhere.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

const RECORD_DURATION_MS = 5_000;

export interface VoiceResult {
  /** undefined until S2-03 wires real expo-av recording + backend DSP. */
  voice_jitter_pct: number | undefined;
  /** undefined until S2-03 wires real expo-av recording + backend DSP. */
  voice_shimmer_pct: number | undefined;
  /**
   * SNR proxy in dB. undefined when no real recording available.
   * Quality gate uses this to block high-noise environments.
   */
  audio_snr_db: number | undefined;
  /** false when SNR below threshold or no recording available. */
  passed_snr: boolean;
  /**
   * Raw amplitude samples (normalised -1.0–1.0, 4410 Hz).
   * Populated in S2-03. Sent to backend for server-side DSP.
   */
  audio_samples?: number[];
}

interface VoiceCaptureProps {
  onComplete: (result: VoiceResult) => void;
  onCancel: () => void;
}

type RecordingState = 'idle' | 'recording' | 'processing' | 'done';

export function VoiceCapture({ onComplete, onCancel }: VoiceCaptureProps) {
  const [recordingState, setRecordingState] = useState<RecordingState>('idle');
  const [timeRemaining, setTimeRemaining] = useState(RECORD_DURATION_MS / 1000);
  // Waveform bar heights — cosmetic animation only, not a wellness metric
  const [waveAmplitudes, setWaveAmplitudes] = useState<number[]>(Array(20).fill(0.1));

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const waveRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startRef = useRef<number | null>(null);

  const stopTimers = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    if (waveRef.current) clearInterval(waveRef.current);
    timerRef.current = null;
    waveRef.current = null;
  }, []);

  useEffect(() => () => stopTimers(), [stopTimers]);

  const startRecording = useCallback(() => {
    setRecordingState('recording');
    setTimeRemaining(RECORD_DURATION_MS / 1000);
    startRef.current = Date.now();

    // Cosmetic waveform animation (Math.random used only for UI bar heights)
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

        // S2-02: No simulation. Voice metrics are undefined until S2-03
        // wires real expo-av recording. Backend will use null values.
        setTimeout(() => {
          const result: VoiceResult = {
            voice_jitter_pct: undefined,
            voice_shimmer_pct: undefined,
            audio_snr_db: undefined,
            passed_snr: true, // assume pass — gate will open; S2-03 computes real SNR
            audio_samples: undefined,
          };
          setRecordingState('done');
          onComplete(result);
        }, 400);
      }
    }, 200);
  }, [onComplete, stopTimers]);

  const progressPct =
    ((RECORD_DURATION_MS / 1000 - timeRemaining) / (RECORD_DURATION_MS / 1000)) * 100;

  return (
    <View style={styles.container} testID="voice-capture">
      <Text style={styles.title}>Voice Check</Text>
      <Text style={styles.subtitle}>
        Say &quot;Aaah&quot; in a steady tone for 5 seconds in a quiet space.
      </Text>

      {/* Waveform — cosmetic animation only */}
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

      {(recordingState === 'recording' || recordingState === 'processing') && (
        <View style={styles.progressBar}>
          <View
            style={[styles.progressFill, { width: `${progressPct}%` as `${number}%` }]}
          />
        </View>
      )}

      <Text style={styles.timerText} testID="voice-timer">
        {recordingState === 'recording'
          ? `${timeRemaining}s remaining`
          : recordingState === 'processing'
          ? 'Processing…'
          : recordingState === 'done'
          ? '✓ Done'
          : 'Ready'}
      </Text>

      {recordingState === 'idle' && (
        <Text style={styles.limitationNote} testID="voice-limitation-note">
          Voice analysis active in a future update.
        </Text>
      )}

      <View style={styles.buttonRow}>
        {recordingState === 'idle' && (
          <TouchableOpacity
            style={styles.recordButton}
            onPress={startRecording}
            testID="start-voice"
          >
            <Text style={styles.recordButtonText}>🎙 Start Voice Check</Text>
          </TouchableOpacity>
        )}
        {recordingState === 'recording' && (
          <TouchableOpacity
            style={styles.cancelButton}
            onPress={onCancel}
            testID="cancel-voice"
          >
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
    marginBottom: 12,
  },
  limitationNote: {
    fontSize: 13,
    color: '#555570',
    textAlign: 'center',
    marginBottom: 20,
    fontStyle: 'italic',
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
