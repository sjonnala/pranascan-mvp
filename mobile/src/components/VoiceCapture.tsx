/**
 * VoiceCapture — records a real 5-second sustained vowel clip.
 *
 * The mobile client captures real microphone input, derives a live waveform
 * from metering updates, extracts audio samples from the recorded clip, and
 * runs on-device voice DSP (jitter, shimmer, SNR) via voiceProcessor.
 * Only the derived wellness indicator scalars leave the device — audio samples
 * never leave the device.
 */

import { Audio, AVPlaybackStatus } from 'expo-av';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import {
  AUDIO_SNR_PASS_THRESHOLD_DB,
  TARGET_AUDIO_SAMPLE_COUNT,
  buildFallbackAudioSamples,
  buildWaveformBars,
  computeSnrDb,
  meteringDbToAmplitude,
  resampleAudioSamples,
} from '../utils/voiceAnalyzer';
import { processVoice } from '../utils/voiceProcessor';

const RECORD_DURATION_MS = 5_000;
const STATUS_UPDATE_INTERVAL_MS = 100;
const SAMPLE_EXTRACTION_RATE = 16;
const PROCESSING_TIMEOUT_MS = 2_000;

const RECORDING_OPTIONS: Audio.RecordingOptions = {
  isMeteringEnabled: true,
  android: {
    extension: '.m4a',
    outputFormat: Audio.AndroidOutputFormat.MPEG_4,
    audioEncoder: Audio.AndroidAudioEncoder.AAC,
    sampleRate: 44_100,
    numberOfChannels: 1,
    bitRate: 128_000,
  },
  ios: {
    extension: '.m4a',
    outputFormat: Audio.IOSOutputFormat.MPEG4AAC,
    audioQuality: Audio.IOSAudioQuality.MAX,
    sampleRate: 44_100,
    numberOfChannels: 1,
    bitRate: 128_000,
    linearPCMBitDepth: 16,
    linearPCMIsBigEndian: false,
    linearPCMIsFloat: false,
  },
  web: {
    mimeType: 'audio/webm',
    bitsPerSecond: 128_000,
  },
};

export interface VoiceResult {
  /** On-device computed voice jitter percentage (wellness indicator). */
  voice_jitter_pct: number | undefined;
  /** On-device computed voice shimmer percentage (wellness indicator). */
  voice_shimmer_pct: number | undefined;
  /** Client-side SNR proxy in dB from the real recording. */
  audio_snr_db: number | undefined;
  /** Whether the captured voice signal passes the SNR quality threshold. */
  passed_snr: boolean;
}

interface VoiceCaptureProps {
  onComplete: (result: VoiceResult) => void;
  onCancel: () => void;
}

type RecordingState = 'idle' | 'recording' | 'processing' | 'done';

export function VoiceCapture({ onComplete, onCancel }: VoiceCaptureProps) {
  const [permission, requestPermission] = Audio.usePermissions();
  const [recordingState, setRecordingState] = useState<RecordingState>('idle');
  const [timeRemaining, setTimeRemaining] = useState(RECORD_DURATION_MS / 1000);
  const [waveAmplitudes, setWaveAmplitudes] = useState<number[]>(Array(20).fill(0.1));

  const recordingRef = useRef<Audio.Recording | null>(null);
  const startRef = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const stoppingRef = useRef(false);
  const meteringSamplesRef = useRef<number[]>([]);

  const stopTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const resetCaptureState = useCallback(() => {
    meteringSamplesRef.current = [];
    setWaveAmplitudes(Array(20).fill(0.1));
    setTimeRemaining(RECORD_DURATION_MS / 1000);
    startRef.current = null;
    stoppingRef.current = false;
  }, []);

  const cleanupRecording = useCallback(async () => {
    const activeRecording = recordingRef.current;
    recordingRef.current = null;
    if (!activeRecording) {
      return;
    }

    activeRecording.setOnRecordingStatusUpdate(null);
    try {
      await activeRecording.stopAndUnloadAsync();
    } catch {
      // Recorder might already be stopped. Safe to ignore here.
    }
  }, []);

  useEffect(() => {
    return () => {
      stopTimer();
      void cleanupRecording();
    };
  }, [cleanupRecording, stopTimer]);

  const extractAudioSamples = useCallback(async (recording: Audio.Recording): Promise<number[]> => {
    const { sound } = await recording.createNewLoadedSoundAsync({ shouldPlay: false, volume: 0 });
    const collectedFrames: number[] = [];

    try {
      sound.setOnAudioSampleReceived((sample) => {
        const primaryChannel = sample.channels[0];
        if (primaryChannel?.frames?.length) {
          collectedFrames.push(...primaryChannel.frames);
        }
      });

      try {
        await sound.setRateAsync(SAMPLE_EXTRACTION_RATE, false);
      } catch {
        // Rate adjustment is optional. Continue at normal speed if unavailable.
      }

      await new Promise<void>((resolve, reject) => {
        const timeout = setTimeout(resolve, PROCESSING_TIMEOUT_MS);

        sound.setOnPlaybackStatusUpdate((status: AVPlaybackStatus) => {
          if (!status.isLoaded) {
            return;
          }

          if (status.didJustFinish) {
            clearTimeout(timeout);
            resolve();
          }
        });

        sound.replayAsync({ shouldPlay: true, volume: 0 }).catch((error) => {
          clearTimeout(timeout);
          reject(error);
        });
      });
    } finally {
      sound.setOnAudioSampleReceived(null);
      sound.setOnPlaybackStatusUpdate(null);
      await sound.unloadAsync().catch(() => undefined);
    }

    return collectedFrames;
  }, []);

  const completeRecording = useCallback(async () => {
    if (stoppingRef.current) {
      return;
    }

    stoppingRef.current = true;
    stopTimer();
    setRecordingState('processing');

    const activeRecording = recordingRef.current;
    if (!activeRecording) {
      setRecordingState('done');
      // On-device voice DSP complete. Only derived indicators leave the device.
      onComplete({
        voice_jitter_pct: undefined,
        voice_shimmer_pct: undefined,
        audio_snr_db: undefined,
        passed_snr: false,
      });
      return;
    }

    try {
      activeRecording.setOnRecordingStatusUpdate(null);
      await activeRecording.stopAndUnloadAsync();
      await Audio.setAudioModeAsync({ allowsRecordingIOS: false, playsInSilentModeIOS: true });

      const pcmFrames = await extractAudioSamples(activeRecording).catch(() => []);
      const audioSamples =
        pcmFrames.length > 0
          ? resampleAudioSamples(pcmFrames, TARGET_AUDIO_SAMPLE_COUNT)
          : buildFallbackAudioSamples(
              meteringSamplesRef.current,
              TARGET_AUDIO_SAMPLE_COUNT,
            );
      const snrDb = computeSnrDb(
        pcmFrames.length > 0 ? audioSamples : meteringSamplesRef.current,
      );

      // Run on-device voice DSP — computes jitter and shimmer locally.
      const voiceDsp = processVoice(audioSamples);

      recordingRef.current = null;
      setRecordingState('done');
      // On-device voice DSP complete. Only derived indicators leave the device.
      onComplete({
        voice_jitter_pct: voiceDsp.jitter_pct ?? undefined,
        voice_shimmer_pct: voiceDsp.shimmer_pct ?? undefined,
        audio_snr_db: snrDb,
        passed_snr: typeof snrDb === 'number' && snrDb > AUDIO_SNR_PASS_THRESHOLD_DB,
      });
    } catch {
      recordingRef.current = null;
      setRecordingState('done');
      // On-device voice DSP complete. Only derived indicators leave the device.
      onComplete({
        voice_jitter_pct: undefined,
        voice_shimmer_pct: undefined,
        audio_snr_db: undefined,
        passed_snr: false,
      });
    }
  }, [extractAudioSamples, onComplete, stopTimer]);

  const handleCancel = useCallback(async () => {
    stopTimer();
    await cleanupRecording();
    resetCaptureState();
    setRecordingState('idle');
    await Audio.setAudioModeAsync({ allowsRecordingIOS: false, playsInSilentModeIOS: true }).catch(
      () => undefined,
    );
    onCancel();
  }, [cleanupRecording, onCancel, resetCaptureState, stopTimer]);

  const startRecording = useCallback(async () => {
    if (!permission?.granted) {
      await requestPermission();
      return;
    }

    try {
      resetCaptureState();
      setRecordingState('recording');
      setWaveAmplitudes(Array(20).fill(0.1));
      startRef.current = Date.now();

      await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });

      const recording = new Audio.Recording();
      recordingRef.current = recording;
      recording.setProgressUpdateInterval(STATUS_UPDATE_INTERVAL_MS);
      recording.setOnRecordingStatusUpdate((status) => {
        if (typeof status.metering !== 'number') {
          return;
        }

        const amplitude = meteringDbToAmplitude(status.metering);
        meteringSamplesRef.current.push(amplitude);
        setWaveAmplitudes(buildWaveformBars(meteringSamplesRef.current));
      });

      await recording.prepareToRecordAsync(RECORDING_OPTIONS);
      await recording.startAsync();

      timerRef.current = setInterval(() => {
        const elapsed = Date.now() - (startRef.current ?? Date.now());
        const remaining = Math.max(0, Math.ceil((RECORD_DURATION_MS - elapsed) / 1000));
        setTimeRemaining(remaining);

        if (remaining <= 0) {
          void completeRecording();
        }
      }, 200);
    } catch {
      await Audio.setAudioModeAsync({ allowsRecordingIOS: false, playsInSilentModeIOS: true }).catch(
        () => undefined,
      );
      await cleanupRecording();
      resetCaptureState();
      setRecordingState('idle');
    }
  }, [
    cleanupRecording,
    completeRecording,
    permission,
    requestPermission,
    resetCaptureState,
  ]);

  const progressPct =
    ((RECORD_DURATION_MS / 1000 - timeRemaining) / (RECORD_DURATION_MS / 1000)) * 100;

  if (!permission) {
    return (
      <View style={styles.container} testID="voice-capture">
        <Text style={styles.messageText}>Requesting microphone access...</Text>
      </View>
    );
  }

  if (!permission.granted) {
    return (
      <View style={styles.container} testID="voice-capture">
        <Text style={styles.messageText} testID="mic-permission-message">
          Microphone access is needed for the voice check.
        </Text>
        <Text style={styles.subtitle}>
          Your recording stays on your device. Only derived wellness signals are shared.
        </Text>
        <TouchableOpacity
          style={styles.recordButton}
          onPress={requestPermission}
          testID="allow-mic"
        >
          <Text style={styles.recordButtonText}>Allow Microphone</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.cancelButton} onPress={onCancel} testID="cancel-voice">
          <Text style={styles.cancelButtonText}>Cancel</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={styles.container} testID="voice-capture">
      <Text style={styles.title}>Voice Check</Text>
      <Text style={styles.subtitle}>
        Say &quot;Aaah&quot; in a steady tone for 5 seconds in a quiet space.
      </Text>

      <View style={styles.waveContainer} testID="waveform">
        {waveAmplitudes.map((amp, index) => (
          <View
            key={index}
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
          ? 'Processing...'
          : recordingState === 'done'
          ? 'Done'
          : 'Ready'}
      </Text>

      <View style={styles.buttonRow}>
        {recordingState === 'idle' && (
          <TouchableOpacity
            style={styles.recordButton}
            onPress={startRecording}
            testID="start-voice"
          >
            <Text style={styles.recordButtonText}>Start Voice Check</Text>
          </TouchableOpacity>
        )}

        {recordingState === 'recording' && (
          <TouchableOpacity
            style={styles.cancelButton}
            onPress={() => void handleCancel()}
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
  buttonRow: {
    width: '100%',
  },
  recordButton: {
    backgroundColor: '#4f46e5',
    borderRadius: 14,
    paddingVertical: 16,
    alignItems: 'center',
    marginBottom: 12,
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
    color: '#fca5a5',
    fontSize: 16,
    fontWeight: '600',
  },
  disclaimer: {
    fontSize: 12,
    color: '#555570',
    textAlign: 'center',
    lineHeight: 18,
    marginTop: 20,
  },
  messageText: {
    fontSize: 16,
    color: '#ffffff',
    textAlign: 'center',
    marginBottom: 12,
  },
});
