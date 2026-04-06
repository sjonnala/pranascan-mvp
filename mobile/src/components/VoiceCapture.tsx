/**
 * VoiceCapture — records a real 5-second sustained vowel clip.
 *
 * The mobile client captures real microphone input, derives a live waveform
 * from metering updates, and runs on-device voice DSP (jitter, shimmer, SNR)
 * via voiceProcessor. On native Expo Go builds, completion uses the captured
 * metering envelope instead of replaying the clip for PCM extraction.
 * Only the derived wellness indicator scalars leave the device — audio samples
 * never leave the device.
 */

import { Audio } from 'expo-av';
import { MaterialIcons } from '@expo/vector-icons';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Platform, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { pranaPulseShadow, pranaPulseTheme, withAlpha } from '../theme/pranaPulse';
import {
  AUDIO_SNR_PASS_THRESHOLD_DB,
  TARGET_AUDIO_SAMPLE_COUNT,
  buildFallbackAudioSamples,
  buildWaveformBars,
  computeSnrDb,
  meteringDbToAmplitude,
} from '../utils/voiceAnalyzer';
import { processVoice } from '../utils/voiceProcessor';

const RECORD_DURATION_MS = 5_000;
const STATUS_UPDATE_INTERVAL_MS = 100;
const USE_METERING_ONLY_AUDIO = Platform.OS !== 'web';

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

      await new Promise<void>((resolve, reject) => {
        sound.setOnPlaybackStatusUpdate((status) => {
          if (!status.isLoaded) {
            return;
          }

          if (status.didJustFinish) {
            resolve();
          }
        });

        sound.replayAsync({ shouldPlay: true, volume: 0 }).catch((error) => {
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

      // Expo Go on native platforms has been unstable when replaying a fresh
      // recording for PCM extraction, so use the already-collected metering
      // envelope there and keep the replay-based path for web only.
      const pcmFrames = USE_METERING_ONLY_AUDIO
        ? []
        : await extractAudioSamples(activeRecording).catch(() => []);
      const audioSamples =
        pcmFrames.length > 0
          ? pcmFrames
          : buildFallbackAudioSamples(meteringSamplesRef.current, TARGET_AUDIO_SAMPLE_COUNT);
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
        <View style={styles.permissionCard}>
          <MaterialIcons color={pranaPulseTheme.colors.primary} name="mic-none" size={28} />
          <Text style={styles.messageText}>Requesting microphone access...</Text>
        </View>
      </View>
    );
  }

  if (!permission.granted) {
    return (
      <View style={styles.container} testID="voice-capture">
        <View style={styles.permissionCard}>
          <View style={styles.permissionIconShell}>
            <MaterialIcons color={pranaPulseTheme.colors.secondary} name="graphic-eq" size={28} />
          </View>
          <Text style={styles.title}>Voice Step</Text>
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
      </View>
    );
  }

  const stateLabel =
    recordingState === 'recording'
      ? 'Listening'
      : recordingState === 'processing'
        ? 'Processing'
        : recordingState === 'done'
          ? 'Complete'
          : 'Ready';

  return (
    <View style={styles.container} testID="voice-capture">
      <View style={styles.heroSection}>
        <View style={styles.heroBadge}>
          <MaterialIcons color={pranaPulseTheme.colors.primary} name="multitrack-audio" size={18} />
          <Text style={styles.heroBadgeText}>Voice Step</Text>
        </View>
        <Text style={styles.title}>Finish with a calm, steady vowel.</Text>
        <Text style={styles.subtitle}>
          Say &quot;Aaah&quot; in a steady tone for 5 seconds in a quiet space.
        </Text>
      </View>

      <View style={styles.panel}>
        <View style={styles.panelGlowPrimary} />
        <View style={styles.panelGlowSecondary} />

        <View style={styles.statusRow}>
          <Text style={styles.timerText} testID="voice-timer">
            {recordingState === 'recording'
              ? `${timeRemaining}s remaining`
              : recordingState === 'processing'
                ? 'Processing...'
                : recordingState === 'done'
                  ? 'Done'
                  : 'Ready'}
          </Text>
          <View style={styles.statePill}>
            <Text style={styles.statePillText}>{stateLabel}</Text>
          </View>
        </View>

        <View style={styles.waveContainer} testID="waveform">
          {waveAmplitudes.map((amp, index) => (
            <View
              key={index}
              style={[
                styles.waveBar,
                {
                  height: Math.max(8, amp * 74),
                  backgroundColor:
                    recordingState === 'recording'
                      ? pranaPulseTheme.colors.secondary
                      : pranaPulseTheme.colors.surfaceDim,
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

        <View style={styles.guidanceRow}>
          <View style={styles.guidanceChip}>
            <MaterialIcons color={pranaPulseTheme.colors.primary} name="hearing" size={14} />
            <Text style={styles.guidanceText}>Quiet room</Text>
          </View>
          <View style={styles.guidanceChip}>
            <MaterialIcons color={pranaPulseTheme.colors.secondary} name="air" size={14} />
            <Text style={styles.guidanceText}>Steady breath</Text>
          </View>
        </View>

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
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
  },
  heroSection: {
    marginBottom: 18,
    gap: 8,
  },
  heroBadge: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderRadius: pranaPulseTheme.radius.full,
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.62),
  },
  heroBadgeText: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.primary,
    fontSize: 11,
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  title: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    fontSize: 28,
    color: pranaPulseTheme.colors.onSurface,
  },
  subtitle: {
    fontFamily: pranaPulseTheme.fonts.medium,
    fontSize: 14,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    lineHeight: 22,
  },
  panel: {
    position: 'relative',
    overflow: 'hidden',
    borderRadius: pranaPulseTheme.radius.lg,
    padding: 20,
    backgroundColor: pranaPulseTheme.colors.surfaceContainerLowest,
    gap: 16,
    ...pranaPulseShadow,
  },
  panelGlowPrimary: {
    position: 'absolute',
    top: -26,
    right: -24,
    width: 132,
    height: 132,
    borderRadius: 66,
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.68),
  },
  panelGlowSecondary: {
    position: 'absolute',
    bottom: -20,
    left: -20,
    width: 116,
    height: 116,
    borderRadius: 58,
    backgroundColor: withAlpha(pranaPulseTheme.colors.secondaryContainer, 0.62),
  },
  permissionCard: {
    borderRadius: pranaPulseTheme.radius.lg,
    padding: 24,
    alignItems: 'center',
    backgroundColor: pranaPulseTheme.colors.surfaceContainerLowest,
    gap: 12,
    ...pranaPulseShadow,
  },
  permissionIconShell: {
    width: 60,
    height: 60,
    borderRadius: 30,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: withAlpha(pranaPulseTheme.colors.secondaryContainer, 0.8),
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  waveContainer: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'space-between',
    height: 108,
    gap: 3,
    paddingHorizontal: 4,
    paddingVertical: 8,
    borderRadius: pranaPulseTheme.radius.md,
    backgroundColor: withAlpha(pranaPulseTheme.colors.surfaceContainer, 0.88),
  },
  waveBar: {
    flex: 1,
    borderRadius: 999,
    minHeight: 8,
  },
  progressBar: {
    width: '100%',
    height: 6,
    backgroundColor: withAlpha(pranaPulseTheme.colors.surfaceDim, 0.8),
    borderRadius: 999,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    backgroundColor: pranaPulseTheme.colors.primary,
    borderRadius: 999,
  },
  timerText: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    fontSize: 20,
    color: pranaPulseTheme.colors.onSurface,
  },
  statePill: {
    borderRadius: pranaPulseTheme.radius.full,
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: withAlpha(pranaPulseTheme.colors.surfaceContainer, 0.92),
  },
  statePillText: {
    fontFamily: pranaPulseTheme.fonts.bold,
    fontSize: 11,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  guidanceRow: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
  guidanceChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: pranaPulseTheme.radius.full,
    backgroundColor: pranaPulseTheme.colors.surfaceContainer,
  },
  guidanceText: {
    fontFamily: pranaPulseTheme.fonts.bold,
    fontSize: 12,
    color: pranaPulseTheme.colors.onSurfaceVariant,
  },
  buttonRow: {
    width: '100%',
  },
  recordButton: {
    backgroundColor: pranaPulseTheme.colors.primary,
    borderRadius: pranaPulseTheme.radius.full,
    paddingVertical: 16,
    alignItems: 'center',
  },
  recordButtonText: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onPrimary,
    fontSize: 16,
  },
  cancelButton: {
    backgroundColor: withAlpha(pranaPulseTheme.colors.secondaryContainer, 0.72),
    borderRadius: pranaPulseTheme.radius.full,
    paddingVertical: 16,
    alignItems: 'center',
  },
  cancelButtonText: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.secondary,
    fontSize: 16,
  },
  disclaimer: {
    fontFamily: pranaPulseTheme.fonts.medium,
    fontSize: 12,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    textAlign: 'center',
    lineHeight: 18,
  },
  messageText: {
    fontFamily: pranaPulseTheme.fonts.bold,
    fontSize: 16,
    color: pranaPulseTheme.colors.onSurface,
    textAlign: 'center',
  },
});
