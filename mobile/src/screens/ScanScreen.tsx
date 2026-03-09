/**
 * ScanScreen — orchestrates the full scan flow.
 *
 * Sequence: Camera (30s) → Voice (5s) → Submit → Navigate to Results
 */

import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { CameraCapture, CameraResult } from '../components/CameraCapture';
import { VoiceCapture, VoiceResult } from '../components/VoiceCapture';
import { QualityGate } from '../components/QualityGate';
import { evaluateQuality, useQualityCheck } from '../hooks/useQualityCheck';
import { useScan } from '../hooks/useScan';
import { QualityMetrics, ScanResultPayload } from '../types';

type ScanStep = 'starting' | 'camera' | 'voice' | 'submitting' | 'error';

interface ScanScreenProps {
  userId: string;
  onComplete: (sessionId: string) => void;
  onCancel: () => void;
}

export function ScanScreen({ userId, onComplete, onCancel }: ScanScreenProps) {
  const [step, setStep] = useState<ScanStep>('starting');
  const [cameraResult, setCameraResult] = useState<CameraResult | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);

  const { startScan, submitResults, error: scanError } = useScan();
  const { quality, updateMetrics, reset: resetQuality } = useQualityCheck();

  // Create session on mount
  useEffect(() => {
    (async () => {
      try {
        const sid = await startScan(userId);
        setSessionId(sid);
        setStep('camera');
      } catch {
        setStep('error');
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  const handleCameraComplete = useCallback((result: CameraResult) => {
    setCameraResult(result);
    resetQuality();
    setStep('voice');
  }, [resetQuality]);

  const handleQualityUpdate = useCallback(
    (metrics: QualityMetrics) => {
      updateMetrics(metrics);
    },
    [updateMetrics]
  );

  const handleVoiceComplete = useCallback(
    async (voiceResult: VoiceResult) => {
      if (!cameraResult || !sessionId) return;
      setStep('submitting');

      // Edge-processing path: on-device rPPG and voice DSP have already run.
      // We submit the derived wellness indicator values directly — frame_data
      // and audio_samples are NOT sent to the backend (privacy-aligned
      // edge-first architecture). null from on-device → undefined so the
      // backend omits those fields.

      // Build final QualityMetrics, overriding audio_snr_db with the real
      // voice-capture SNR if available.
      const finalMetrics: import('../types').QualityMetrics = {
        ...cameraResult.quality,
        audio_snr_db: voiceResult.audio_snr_db ?? cameraResult.quality.audio_snr_db,
      };
      // Evaluate quality gates and collect real flags.
      const qualityFlags = evaluateQuality(finalMetrics).flags;

      const payload: ScanResultPayload = {
        hr_bpm: cameraResult.hr_bpm ?? undefined,
        hrv_ms: cameraResult.hrv_ms ?? undefined,
        respiratory_rate: cameraResult.respiratory_rate ?? undefined,
        // Voice metrics computed on-device by voiceProcessor.
        voice_jitter_pct: voiceResult.voice_jitter_pct,
        voice_shimmer_pct: voiceResult.voice_shimmer_pct,
        quality_score: cameraResult.quality_score,
        lighting_score: cameraResult.quality.lighting_score,
        motion_score: cameraResult.quality.motion_score,
        face_confidence: cameraResult.quality.face_confidence,
        audio_snr_db: voiceResult.audio_snr_db,
        flags: qualityFlags,
        // frame_data intentionally omitted: on-device rPPG has already run.
        // Raw frame bytes stay on device — they are not sent to the backend.
        // audio_samples intentionally omitted: on-device voice DSP has run.
        // Audio samples never leave the device (privacy-aligned edge-first architecture).
        // Aggregate RGB means for anemia conjunctiva color proxy (on-device derived scalars only).
        frame_r_mean: cameraResult.frame_r_mean ?? undefined,
        frame_g_mean: cameraResult.frame_g_mean ?? undefined,
        frame_b_mean: cameraResult.frame_b_mean ?? undefined,
      };

      try {
        await submitResults(payload);
        onComplete(sessionId);
      } catch {
        setStep('error');
      }
    },
    [cameraResult, sessionId, submitResults, onComplete]
  );

  if (step === 'starting') {
    return (
      <View style={styles.centered} testID="scan-starting">
        <ActivityIndicator size="large" color="#4f46e5" />
        <Text style={styles.loadingText}>Preparing your scan…</Text>
      </View>
    );
  }

  if (step === 'submitting') {
    return (
      <View style={styles.centered} testID="scan-submitting">
        <ActivityIndicator size="large" color="#4f46e5" />
        <Text style={styles.loadingText}>Analysing your wellness indicators…</Text>
        <Text style={styles.subText}>This takes a few seconds</Text>
      </View>
    );
  }

  if (step === 'error') {
    return (
      <View style={styles.centered} testID="scan-error">
        <Text style={styles.errorEmoji}>⚠️</Text>
        <Text style={styles.errorText}>{scanError ?? 'Something went wrong. Please try again.'}</Text>
        <Text style={styles.retryText} onPress={onCancel}>
          ← Go Back
        </Text>
      </View>
    );
  }

  return (
    <View style={styles.container} testID="scan-screen">
      {/* Step indicator */}
      <View style={styles.stepIndicator}>
        <View style={[styles.step, step === 'camera' && styles.stepActive]} />
        <View style={styles.stepConnector} />
        <View style={[styles.step, step === 'voice' && styles.stepActive]} />
      </View>

      <Text style={styles.stepLabel}>
        {step === 'camera' ? '1 of 2 — Camera Scan' : '2 of 2 — Voice Check'}
      </Text>

      {step === 'camera' && (
        <>
          <CameraCapture
            onComplete={handleCameraComplete}
            onQualityUpdate={handleQualityUpdate}
            onCancel={onCancel}
          />
          {quality && (
            <View style={styles.qualityOverlay}>
              <QualityGate quality={quality} testID="scan-quality-gate" />
            </View>
          )}
        </>
      )}

      {step === 'voice' && (
        <VoiceCapture onComplete={handleVoiceComplete} onCancel={onCancel} />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f1a',
  },
  centered: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#0f0f1a',
    padding: 20,
  },
  loadingText: {
    color: '#ffffff',
    fontSize: 18,
    fontWeight: '600',
    marginTop: 20,
    textAlign: 'center',
  },
  subText: {
    color: '#aaaacc',
    fontSize: 14,
    marginTop: 8,
    textAlign: 'center',
  },
  errorEmoji: {
    fontSize: 48,
    marginBottom: 16,
  },
  errorText: {
    color: '#f87171',
    fontSize: 16,
    textAlign: 'center',
    lineHeight: 24,
    marginBottom: 24,
  },
  retryText: {
    color: '#4f46e5',
    fontSize: 16,
    fontWeight: '600',
  },
  stepIndicator: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    paddingTop: 16,
    paddingBottom: 4,
  },
  step: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: '#2a2a4e',
  },
  stepActive: {
    backgroundColor: '#4f46e5',
    width: 24,
    borderRadius: 12,
  },
  stepConnector: {
    width: 32,
    height: 2,
    backgroundColor: '#2a2a4e',
    marginHorizontal: 6,
  },
  stepLabel: {
    color: '#aaaacc',
    fontSize: 13,
    textAlign: 'center',
    marginBottom: 8,
  },
  qualityOverlay: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    paddingBottom: 16,
  },
});
