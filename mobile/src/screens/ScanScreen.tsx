/**
 * ScanScreen — orchestrates standard selfie scans and Weekly Deep Dive scans.
 */

import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { CameraCapture, CameraResult } from '../components/CameraCapture';
import { QualityGate } from '../components/QualityGate';
import { VoiceCapture, VoiceResult } from '../components/VoiceCapture';
import { evaluateQuality, useQualityCheck } from '../hooks/useQualityCheck';
import { useScan } from '../hooks/useScan';
import { QualityMetrics, ScanResultPayload, ScanType } from '../types';

type ScanStep = 'mode_select' | 'creating_session' | 'camera' | 'voice' | 'submitting' | 'error';

interface ScanScreenProps {
  onComplete: (sessionId: string) => void;
  onCancel: () => void;
}

export function ScanScreen({ onComplete, onCancel }: ScanScreenProps) {
  const [step, setStep] = useState<ScanStep>('mode_select');
  const [cameraResult, setCameraResult] = useState<CameraResult | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [scanType, setScanType] = useState<ScanType>('standard');
  const [userHeightCmInput, setUserHeightCmInput] = useState('170');
  const [modeError, setModeError] = useState<string | null>(null);

  const { startScan, submitResults, error: scanError } = useScan();
  const { quality, updateMetrics, reset: resetQuality } = useQualityCheck();

  const parseDeepDiveHeight = useCallback((): number | null => {
    const parsed = Number.parseFloat(userHeightCmInput);
    if (!Number.isFinite(parsed) || parsed < 100 || parsed > 250) {
      return null;
    }
    return parsed;
  }, [userHeightCmInput]);

  const beginScan = useCallback(async () => {
    if (scanType === 'deep_dive' && parseDeepDiveHeight() == null) {
      setModeError('Enter your height in centimetres to calculate the stiffness index.');
      return;
    }

    setModeError(null);
    setStep('creating_session');
    try {
      const sid = await startScan(scanType);
      setSessionId(sid);
      setStep('camera');
    } catch {
      setStep('error');
    }
  }, [parseDeepDiveHeight, scanType, startScan]);

  const buildPayload = useCallback(
    (capturedCameraResult: CameraResult, voiceResult?: VoiceResult): ScanResultPayload => {
      const finalMetrics: QualityMetrics = {
        ...capturedCameraResult.quality,
        audio_snr_db:
          scanType === 'deep_dive'
            ? capturedCameraResult.quality.audio_snr_db
            : voiceResult?.audio_snr_db ?? capturedCameraResult.quality.audio_snr_db,
      };
      const qualityFlags = evaluateQuality(finalMetrics, scanType).flags;

      return {
        scan_type: scanType,
        user_height_cm: scanType === 'deep_dive' ? parseDeepDiveHeight() ?? undefined : undefined,
        voice_jitter_pct: voiceResult?.voice_jitter_pct,
        voice_shimmer_pct: voiceResult?.voice_shimmer_pct,
        quality_score: capturedCameraResult.quality_score,
        lighting_score: capturedCameraResult.quality.lighting_score,
        motion_score: capturedCameraResult.quality.motion_score,
        face_confidence: capturedCameraResult.quality.face_confidence,
        audio_snr_db: finalMetrics.audio_snr_db,
        flags: qualityFlags,
        frame_data: capturedCameraResult.frame_data,
        frame_r_mean: capturedCameraResult.frame_r_mean ?? undefined,
        frame_g_mean: capturedCameraResult.frame_g_mean ?? undefined,
        frame_b_mean: capturedCameraResult.frame_b_mean ?? undefined,
      };
    },
    [parseDeepDiveHeight, scanType],
  );

  const submitCapturedScan = useCallback(
    async (capturedCameraResult: CameraResult, voiceResult?: VoiceResult) => {
      if (!sessionId) {
        return;
      }

      setStep('submitting');
      try {
        await submitResults(buildPayload(capturedCameraResult, voiceResult));
        onComplete(sessionId);
      } catch {
        setStep('error');
      }
    },
    [buildPayload, onComplete, sessionId, submitResults],
  );

  const handleCameraComplete = useCallback(
    async (result: CameraResult) => {
      setCameraResult(result);
      resetQuality();

      if (scanType === 'deep_dive') {
        await submitCapturedScan(result);
        return;
      }

      setStep('voice');
    },
    [resetQuality, scanType, submitCapturedScan],
  );

  const handleQualityUpdate = useCallback(
    (metrics: QualityMetrics) => {
      updateMetrics(metrics, scanType);
    },
    [scanType, updateMetrics],
  );

  const handleVoiceComplete = useCallback(
    async (voiceResult: VoiceResult) => {
      if (!cameraResult) {
        return;
      }
      await submitCapturedScan(cameraResult, voiceResult);
    },
    [cameraResult, submitCapturedScan],
  );

  if (step === 'mode_select') {
    const deepDiveSelected = scanType === 'deep_dive';

    return (
      <View style={styles.centered} testID="scan-mode-select">
        <Text style={styles.modeEyebrow}>Choose Scan Mode</Text>
        <Text style={styles.loadingText}>Pick the workflow that matches this check-in.</Text>

        <TouchableOpacity
          style={[styles.modeCard, scanType === 'standard' && styles.modeCardActive]}
          onPress={() => setScanType('standard')}
          testID="scan-mode-standard"
        >
          <Text style={styles.modeTitle}>Quick Check</Text>
          <Text style={styles.modeDescription}>
            30-second front-camera scan with the normal voice step.
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.modeCard, deepDiveSelected && styles.modeCardActive]}
          onPress={() => setScanType('deep_dive')}
          testID="scan-mode-deep-dive"
        >
          <Text style={styles.modeTitle}>Weekly Deep Dive</Text>
          <Text style={styles.modeDescription}>
            Cover the camera and flash with your thumb for a 60-second contact-PPG scan.
          </Text>
        </TouchableOpacity>

        {deepDiveSelected ? (
          <View style={styles.deepDiveBox}>
            <Text style={styles.deepDivePrompt}>Cover the camera and flash with your thumb.</Text>
            <Text style={styles.deepDiveSubtext}>
              Enter your height so the Stiffness Index can be calculated from the pulse-wave delay.
            </Text>
            <TextInput
              value={userHeightCmInput}
              onChangeText={setUserHeightCmInput}
              keyboardType="numeric"
              style={styles.heightInput}
              placeholder="Height (cm)"
              placeholderTextColor="#75759a"
              testID="deep-dive-height-input"
            />
          </View>
        ) : null}

        {modeError ? (
          <Text style={styles.modeError} testID="scan-mode-error">
            {modeError}
          </Text>
        ) : null}

        <TouchableOpacity style={styles.startButton} onPress={beginScan} testID="begin-scan-flow">
          <Text style={styles.startButtonText}>
            {deepDiveSelected ? 'Begin Weekly Deep Dive' : 'Begin Quick Check'}
          </Text>
        </TouchableOpacity>

        <TouchableOpacity onPress={onCancel} style={styles.cancelModeButton} testID="cancel-scan">
          <Text style={styles.cancelLinkText}>Cancel</Text>
        </TouchableOpacity>
      </View>
    );
  }

  if (step === 'creating_session') {
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
        <Text style={styles.loadingText}>
          {scanType === 'deep_dive'
            ? 'Analysing your pulse-wave morphology…'
            : 'Analysing your wellness indicators…'}
        </Text>
        <Text style={styles.subText}>This takes a few seconds</Text>
      </View>
    );
  }

  if (step === 'error') {
    return (
      <View style={styles.centered} testID="scan-error">
        <Text style={styles.errorEmoji}>⚠️</Text>
        <Text style={styles.errorText}>
          {scanError ?? modeError ?? 'Something went wrong. Please try again.'}
        </Text>
        <Text style={styles.retryText} onPress={onCancel}>
          ← Go Back
        </Text>
      </View>
    );
  }

  return (
    <View style={styles.container} testID="scan-screen">
      <View style={styles.stepIndicator}>
        <View style={[styles.step, step === 'camera' && styles.stepActive]} />
        <View style={styles.stepConnector} />
        <View
          style={[
            styles.step,
            step === 'voice' && styles.stepActive,
            scanType === 'deep_dive' && styles.stepSkipped,
          ]}
        />
      </View>

      <Text style={styles.stepLabel}>
        {scanType === 'deep_dive'
          ? 'Deep Dive — Contact PPG Scan'
          : step === 'camera'
            ? '1 of 2 — Camera Scan'
            : '2 of 2 — Voice Check'}
      </Text>

      {step === 'camera' ? (
        <>
          <CameraCapture
            scanType={scanType}
            onComplete={handleCameraComplete}
            onQualityUpdate={handleQualityUpdate}
            onCancel={onCancel}
          />
          {quality ? (
            <View style={styles.qualityOverlay}>
              <QualityGate quality={quality} scanType={scanType} testID="scan-quality-gate" />
            </View>
          ) : null}
        </>
      ) : (
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
  modeEyebrow: {
    color: '#7dd3fc',
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
    marginBottom: 12,
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
  modeCard: {
    width: '100%',
    maxWidth: 420,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: '#2a2a4e',
    backgroundColor: '#17172a',
    padding: 18,
    marginTop: 16,
  },
  modeCardActive: {
    borderColor: '#4f46e5',
    backgroundColor: '#1e1b4b',
  },
  modeTitle: {
    color: '#ffffff',
    fontSize: 18,
    fontWeight: '700',
    marginBottom: 8,
  },
  modeDescription: {
    color: '#c8c8ee',
    fontSize: 14,
    lineHeight: 21,
  },
  deepDiveBox: {
    width: '100%',
    maxWidth: 420,
    marginTop: 18,
    borderRadius: 18,
    backgroundColor: '#1a2335',
    padding: 18,
  },
  deepDivePrompt: {
    color: '#fef3c7',
    fontSize: 15,
    fontWeight: '700',
    marginBottom: 6,
  },
  deepDiveSubtext: {
    color: '#cbd5f5',
    fontSize: 13,
    lineHeight: 19,
    marginBottom: 12,
  },
  heightInput: {
    backgroundColor: '#0f172a',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#334155',
    color: '#ffffff',
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 16,
  },
  modeError: {
    color: '#fca5a5',
    fontSize: 13,
    marginTop: 12,
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
  stepSkipped: {
    backgroundColor: '#334155',
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
  startButton: {
    marginTop: 20,
    width: '100%',
    maxWidth: 420,
    backgroundColor: '#4f46e5',
    borderRadius: 14,
    paddingVertical: 15,
    alignItems: 'center',
  },
  startButtonText: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '700',
  },
  cancelModeButton: {
    marginTop: 14,
  },
  cancelLinkText: {
    color: '#94a3b8',
    fontSize: 15,
    fontWeight: '600',
  },
});
