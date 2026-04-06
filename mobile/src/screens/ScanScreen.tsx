/**
 * ScanScreen — orchestrates standard selfie scans and Weekly Deep Dive scans.
 */

import { MaterialIcons } from '@expo/vector-icons';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  useWindowDimensions,
  View,
} from 'react-native';
import { CameraCapture, CameraResult } from '../components/CameraCapture';
import { QualityGate } from '../components/QualityGate';
import { VoiceCapture, VoiceResult } from '../components/VoiceCapture';
import { PranaPulseReveal } from '../components/pranapulse/PranaPulseReveal';
import { PranaPulseScaffold } from '../components/pranapulse/PranaPulseScaffold';
import { evaluateQuality, useQualityCheck } from '../hooks/useQualityCheck';
import { useScan } from '../hooks/useScan';
import { pranaPulseShadow, pranaPulseTheme, withAlpha } from '../theme/pranaPulse';
import { QualityMetrics, ScanResultPayload, ScanType } from '../types';

type ScanStep = 'mode_select' | 'creating_session' | 'camera' | 'voice' | 'submitting' | 'error';

interface ScanScreenProps {
  onComplete: (sessionId: string) => void;
  onCancel: () => void;
  initialScanType?: ScanType;
  hideModeSelect?: boolean;
}

export function ScanScreen({
  onComplete,
  onCancel,
  initialScanType,
  hideModeSelect = false,
}: ScanScreenProps) {
  const { width: screenWidth } = useWindowDimensions();
  const autoStartEnabled = Boolean(hideModeSelect && initialScanType);
  const [step, setStep] = useState<ScanStep>(autoStartEnabled ? 'creating_session' : 'mode_select');
  const [cameraResult, setCameraResult] = useState<CameraResult | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [scanType, setScanType] = useState<ScanType>(initialScanType ?? 'standard');
  const [userHeightCmInput, setUserHeightCmInput] = useState('170');
  const [modeError, setModeError] = useState<string | null>(null);
  const autoStartedRef = useRef(false);

  const { startScan, submitResults, error: scanError } = useScan();
  const { quality, updateMetrics, reset: resetQuality } = useQualityCheck();
  const compactLayout = screenWidth < 390;

  const parseDeepDiveHeight = useCallback((): number | null => {
    const parsed = Number.parseFloat(userHeightCmInput);
    if (!Number.isFinite(parsed) || parsed < 100 || parsed > 250) {
      return null;
    }
    return parsed;
  }, [userHeightCmInput]);

  const beginScan = useCallback(
    async (selectedType: ScanType) => {
      if (selectedType === 'deep_dive' && parseDeepDiveHeight() == null) {
        setModeError('Enter your height in centimetres to calculate the stiffness index.');
        setStep('mode_select');
        return;
      }

      setModeError(null);
      setScanType(selectedType);
      setStep('creating_session');
      try {
        const sid = await startScan(selectedType);
        setSessionId(sid);
        setStep('camera');
      } catch {
        setStep('error');
      }
    },
    [parseDeepDiveHeight, startScan]
  );

  useEffect(() => {
    if (!autoStartEnabled || !initialScanType || autoStartedRef.current) {
      return;
    }

    autoStartedRef.current = true;
    void beginScan(initialScanType);
  }, [autoStartEnabled, beginScan, initialScanType]);

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
    [parseDeepDiveHeight, scanType]
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
    [buildPayload, onComplete, sessionId, submitResults]
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
    [resetQuality, scanType, submitCapturedScan]
  );

  const handleQualityUpdate = useCallback(
    (metrics: QualityMetrics) => {
      updateMetrics(metrics, scanType);
    },
    [scanType, updateMetrics]
  );

  const handleVoiceComplete = useCallback(
    async (voiceResult: VoiceResult) => {
      if (!cameraResult) {
        return;
      }
      await submitCapturedScan(cameraResult, voiceResult);
    },
    [cameraResult, submitCapturedScan]
  );

  if (step === 'mode_select') {
    const deepDiveSelected = scanType === 'deep_dive';

    return (
      <PranaPulseScaffold
        activeTab="scan"
        onHomePress={onCancel}
        onScanPress={() => undefined}
        showBottomNav
      >
        <PranaPulseReveal delay={20}>
          <View style={styles.heroSection}>
            <Text style={styles.heroEyebrow}>Scan Studio</Text>
            <Text style={[styles.heroTitle, compactLayout && styles.heroTitleCompact]}>Choose your PranaPulse flow.</Text>
            <Text style={styles.heroSubtitle}>
              Daily Glow is the warm, face-guided scan. Weekly Deep Dive preserves the contact-PPG flow for longer pulse-wave analysis.
            </Text>
          </View>
        </PranaPulseReveal>

        <PranaPulseReveal delay={100}>
          <TouchableOpacity
            onPress={() => setScanType('standard')}
            style={[styles.modeCard, scanType === 'standard' && styles.modeCardActive]}
            testID="scan-mode-standard"
          >
            <View style={styles.modeHeader}>
              <View style={[styles.modeIconShell, styles.modeIconSage]}>
                <MaterialIcons color={pranaPulseTheme.colors.primary} name="face-retouching-natural" size={20} />
              </View>
              <View style={styles.modeDurationPill}>
                <Text style={styles.modeDurationText}>30s + voice</Text>
              </View>
            </View>
            <Text style={styles.modeEyebrow}>Daily Glow</Text>
            <Text style={styles.modeTitle}>Warm face-guided vitality scan</Text>
            <Text style={styles.modeDescription}>
              30-second camera capture, then a short voice step to complete the standard wellness flow.
            </Text>
            <View style={styles.modeFeatureRow}>
              <View style={styles.modeFeatureChip}>
                <MaterialIcons color={pranaPulseTheme.colors.primary} name="center-focus-strong" size={14} />
                <Text style={styles.modeFeatureText}>Ghost guide</Text>
              </View>
              <View style={styles.modeFeatureChip}>
                <MaterialIcons color={pranaPulseTheme.colors.secondary} name="waves" size={14} />
                <Text style={styles.modeFeatureText}>Breathing wave</Text>
              </View>
            </View>
          </TouchableOpacity>
        </PranaPulseReveal>

        <PranaPulseReveal delay={160}>
          <TouchableOpacity
            onPress={() => setScanType('deep_dive')}
            style={[styles.modeCard, deepDiveSelected && styles.modeCardActive]}
            testID="scan-mode-deep-dive"
          >
            <View style={styles.modeHeader}>
              <View style={[styles.modeIconShell, styles.modeIconSunset]}>
                <MaterialIcons color={pranaPulseTheme.colors.secondary} name="fingerprint" size={20} />
              </View>
              <View style={styles.modeDurationPill}>
                <Text style={styles.modeDurationText}>60s contact</Text>
              </View>
            </View>
            <Text style={styles.modeEyebrow}>Weekly Deep Dive</Text>
            <Text style={styles.modeTitle}>Contact-PPG thumb scan</Text>
            <Text style={styles.modeDescription}>
              Preserves the existing 60-second back-camera mode so the deeper pulse-wave logic still works.
            </Text>
            <View style={styles.modeFeatureRow}>
              <View style={styles.modeFeatureChip}>
                <MaterialIcons color={pranaPulseTheme.colors.secondary} name="flash-on" size={14} />
                <Text style={styles.modeFeatureText}>Torch assist</Text>
              </View>
              <View style={styles.modeFeatureChip}>
                <MaterialIcons color={pranaPulseTheme.colors.primary} name="timeline" size={14} />
                <Text style={styles.modeFeatureText}>Morphology</Text>
              </View>
            </View>
          </TouchableOpacity>
        </PranaPulseReveal>

        {deepDiveSelected ? (
          <PranaPulseReveal delay={220}>
            <View style={styles.deepDiveBox}>
              <Text style={styles.deepDivePrompt}>Height is required for the stiffness estimate.</Text>
              <Text style={styles.deepDiveSubtext}>
                Your frame processor path stays unchanged. This input only supplements the backend payload.
              </Text>
              <TextInput
                keyboardType="numeric"
                onChangeText={setUserHeightCmInput}
                placeholder="Height (cm)"
                placeholderTextColor={withAlpha(pranaPulseTheme.colors.onSurfaceVariant, 0.8)}
                style={styles.heightInput}
                testID="deep-dive-height-input"
                value={userHeightCmInput}
              />
            </View>
          </PranaPulseReveal>
        ) : null}

        {modeError ? (
          <PranaPulseReveal delay={250}>
            <Text style={styles.modeError} testID="scan-mode-error">
              {modeError}
            </Text>
          </PranaPulseReveal>
        ) : null}

        <PranaPulseReveal delay={280}>
          <TouchableOpacity
            onPress={() => {
              void beginScan(scanType);
            }}
            style={styles.primaryButton}
            testID="begin-scan-flow"
          >
            <Text style={styles.primaryButtonText}>
              {deepDiveSelected ? 'Begin Weekly Deep Dive' : 'Begin Daily Glow'}
            </Text>
          </TouchableOpacity>
        </PranaPulseReveal>

        <PranaPulseReveal delay={320}>
          <TouchableOpacity onPress={onCancel} style={styles.cancelModeButton} testID="cancel-scan">
            <Text style={styles.cancelLinkText}>Back to Home</Text>
          </TouchableOpacity>
        </PranaPulseReveal>
      </PranaPulseScaffold>
    );
  }

  if (step === 'creating_session') {
    return (
      <PranaPulseScaffold activeTab="scan" profileLabel="P" scroll={false} showBottomNav={false}>
        <PranaPulseReveal delay={20} style={styles.centered}>
          <View style={styles.centeredPanel} testID="scan-starting">
            <View style={styles.stateOrb}>
              <ActivityIndicator color={pranaPulseTheme.colors.primary} size="large" />
            </View>
            <Text style={styles.stateEyebrow}>Preparing Session</Text>
            <Text style={styles.loadingText}>Preparing your PranaPulse scan…</Text>
            <Text style={styles.loadingSubtext}>Creating the capture session and warming up the guided flow.</Text>
          </View>
        </PranaPulseReveal>
      </PranaPulseScaffold>
    );
  }

  if (step === 'submitting') {
    return (
      <PranaPulseScaffold activeTab="scan" profileLabel="P" scroll={false} showBottomNav={false}>
        <PranaPulseReveal delay={20} style={styles.centered}>
          <View style={styles.centeredPanel} testID="scan-submitting">
            <View style={styles.stateOrb}>
              <ActivityIndicator color={pranaPulseTheme.colors.primary} size="large" />
            </View>
            <Text style={styles.stateEyebrow}>Analysing</Text>
            <Text style={styles.loadingText}>
              {scanType === 'deep_dive'
                ? 'Analysing your pulse-wave morphology…'
                : 'Analysing your heart and recovery signals…'}
            </Text>
            <Text style={styles.loadingSubtext}>This takes a few seconds.</Text>
          </View>
        </PranaPulseReveal>
      </PranaPulseScaffold>
    );
  }

  if (step === 'error') {
    return (
      <PranaPulseScaffold activeTab="scan" profileLabel="P" scroll={false} showBottomNav={false}>
        <PranaPulseReveal delay={20} style={styles.centered}>
          <View style={styles.centeredPanel} testID="scan-error">
            <View style={[styles.stateOrb, styles.stateOrbError]}>
              <MaterialIcons color={pranaPulseTheme.colors.secondary} name="error-outline" size={26} />
            </View>
            <Text style={styles.stateEyebrow}>Capture Interrupted</Text>
            <Text style={styles.errorText}>
              {scanError ?? modeError ?? 'Something went wrong. Please try again.'}
            </Text>
            <TouchableOpacity onPress={onCancel} style={styles.primaryButton}>
              <Text style={styles.primaryButtonText}>Return Home</Text>
            </TouchableOpacity>
          </View>
        </PranaPulseReveal>
      </PranaPulseScaffold>
    );
  }

  const stepIndex = step === 'voice' ? 2 : 1;
  const stepTitle =
    step === 'camera'
      ? 'Align with the ghost guide and breathe with the wave.'
      : 'Finish with a short voice capture.';
  const stepSubtitle =
    scanType === 'deep_dive'
      ? 'The native frame-processor path is preserved exactly as before.'
      : step === 'camera'
        ? 'The overlay is visual only. The 100x100 ROI tracking path stays untouched.'
        : 'Your voice step uses the existing local capture and DSP flow.';

  return (
    <PranaPulseScaffold activeTab="scan" profileLabel="P" scroll={false} showBottomNav={false}>
      <View style={styles.captureScreen} testID="scan-screen">
        <PranaPulseReveal delay={20} key={`capture-header-${step}`}>
          <View style={styles.captureHeader}>
            <View style={styles.captureMetaRow}>
              <View style={styles.captureStepPill}>
                <Text style={styles.captureStepText}>{scanType === 'deep_dive' ? 'Deep Dive' : 'Daily Glow'}</Text>
              </View>
              <View style={styles.stepDots}>
                {[1, 2].map((dot) => (
                  <View
                    key={dot}
                    style={[
                      styles.stepDot,
                      dot <= stepIndex ? styles.stepDotActive : styles.stepDotInactive,
                    ]}
                  />
                ))}
              </View>
            </View>
            <Text style={styles.captureEyebrow}>
              {scanType === 'deep_dive' ? 'Weekly Deep Dive' : step === 'camera' ? 'Daily Glow' : 'Voice Step'}
            </Text>
            <Text style={[styles.captureTitle, compactLayout && styles.captureTitleCompact]}>{stepTitle}</Text>
            <Text style={styles.captureSubtitle}>{stepSubtitle}</Text>
          </View>
        </PranaPulseReveal>

        <PranaPulseReveal delay={100} key={`capture-stage-${step}`} style={styles.captureStage}>
          <View style={styles.captureStageInner}>
            {step === 'camera' ? (
              <>
                <CameraCapture
                  onCancel={onCancel}
                  onComplete={handleCameraComplete}
                  onQualityUpdate={handleQualityUpdate}
                  scanType={scanType}
                />
                {quality ? (
                  <PranaPulseReveal delay={40} distance={12} duration={360} style={styles.qualityOverlay}>
                    <QualityGate quality={quality} scanType={scanType} testID="scan-quality-gate" />
                  </PranaPulseReveal>
                ) : null}
              </>
            ) : (
              <VoiceCapture onCancel={onCancel} onComplete={handleVoiceComplete} />
            )}
          </View>
        </PranaPulseReveal>
      </View>
    </PranaPulseScaffold>
  );
}

const styles = StyleSheet.create({
  heroSection: {
    marginTop: 8,
    marginBottom: 18,
    gap: 6,
  },
  heroEyebrow: {
    ...pranaPulseTheme.type.eyebrow,
  },
  heroTitle: {
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 32,
    fontFamily: pranaPulseTheme.fonts.extraBold,
    letterSpacing: -0.7,
  },
  heroTitleCompact: {
    fontSize: 29,
  },
  heroSubtitle: {
    ...pranaPulseTheme.type.body,
  },
  modeCard: {
    borderRadius: pranaPulseTheme.radius.lg,
    backgroundColor: pranaPulseTheme.colors.surfaceContainerLowest,
    padding: 22,
    marginBottom: 14,
    ...pranaPulseShadow,
  },
  modeCardActive: {
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.58),
  },
  modeHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 14,
  },
  modeIconShell: {
    width: 42,
    height: 42,
    borderRadius: 21,
    alignItems: 'center',
    justifyContent: 'center',
  },
  modeIconSage: {
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.76),
  },
  modeIconSunset: {
    backgroundColor: withAlpha(pranaPulseTheme.colors.secondaryContainer, 0.82),
  },
  modeDurationPill: {
    borderRadius: pranaPulseTheme.radius.full,
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: pranaPulseTheme.colors.surfaceContainer,
  },
  modeDurationText: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 11,
    letterSpacing: 0.9,
    textTransform: 'uppercase',
  },
  modeEyebrow: {
    color: pranaPulseTheme.colors.primary,
    fontSize: 11,
    fontFamily: pranaPulseTheme.fonts.extraBold,
    letterSpacing: 1.1,
    textTransform: 'uppercase',
    marginBottom: 8,
  },
  modeTitle: {
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 22,
    fontFamily: pranaPulseTheme.fonts.extraBold,
    lineHeight: 28,
    marginBottom: 8,
  },
  modeDescription: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 14,
    lineHeight: 22,
  },
  modeFeatureRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 14,
  },
  modeFeatureChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderRadius: pranaPulseTheme.radius.full,
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: pranaPulseTheme.colors.surfaceContainer,
  },
  modeFeatureText: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 12,
  },
  deepDiveBox: {
    borderRadius: pranaPulseTheme.radius.md,
    backgroundColor: pranaPulseTheme.colors.surfaceContainerLow,
    padding: 18,
    marginBottom: 14,
  },
  deepDivePrompt: {
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 15,
    fontFamily: pranaPulseTheme.fonts.bold,
    marginBottom: 6,
  },
  deepDiveSubtext: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 13,
    lineHeight: 20,
    marginBottom: 12,
  },
  heightInput: {
    borderRadius: pranaPulseTheme.radius.md,
    backgroundColor: pranaPulseTheme.colors.surfaceContainerHighest,
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurface,
    paddingHorizontal: 14,
    paddingVertical: 14,
    fontSize: 16,
  },
  modeError: {
    color: pranaPulseTheme.colors.error,
    fontFamily: pranaPulseTheme.fonts.medium,
    fontSize: 13,
    marginBottom: 14,
    lineHeight: 20,
  },
  primaryButton: {
    borderRadius: pranaPulseTheme.radius.full,
    backgroundColor: pranaPulseTheme.colors.primary,
    paddingVertical: 16,
    alignItems: 'center',
  },
  primaryButtonText: {
    color: pranaPulseTheme.colors.onPrimary,
    fontSize: 16,
    fontFamily: pranaPulseTheme.fonts.extraBold,
  },
  cancelModeButton: {
    alignItems: 'center',
    marginTop: 14,
  },
  cancelLinkText: {
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 15,
    fontFamily: pranaPulseTheme.fonts.bold,
  },
  centered: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingTop: 72,
    gap: 12,
  },
  centeredPanel: {
    width: '100%',
    borderRadius: pranaPulseTheme.radius.lg,
    padding: 24,
    alignItems: 'center',
    gap: 12,
    backgroundColor: pranaPulseTheme.colors.surfaceContainerLowest,
    ...pranaPulseShadow,
  },
  stateOrb: {
    width: 72,
    height: 72,
    borderRadius: 36,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.78),
  },
  stateOrbError: {
    backgroundColor: withAlpha(pranaPulseTheme.colors.secondaryContainer, 0.74),
  },
  stateEyebrow: {
    ...pranaPulseTheme.type.eyebrow,
    color: pranaPulseTheme.colors.secondary,
  },
  loadingText: {
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 18,
    fontFamily: pranaPulseTheme.fonts.bold,
    textAlign: 'center',
  },
  loadingSubtext: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 14,
    textAlign: 'center',
  },
  errorText: {
    color: pranaPulseTheme.colors.error,
    fontFamily: pranaPulseTheme.fonts.medium,
    fontSize: 16,
    lineHeight: 24,
    textAlign: 'center',
    marginBottom: 10,
  },
  captureScreen: {
    flex: 1,
    gap: 14,
  },
  captureHeader: {
    gap: 6,
  },
  captureMetaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  captureStepPill: {
    borderRadius: pranaPulseTheme.radius.full,
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.68),
  },
  captureStepText: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.primary,
    fontSize: 11,
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  stepDots: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  stepDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  stepDotActive: {
    backgroundColor: pranaPulseTheme.colors.primary,
  },
  stepDotInactive: {
    backgroundColor: withAlpha(pranaPulseTheme.colors.outlineVariant, 0.72),
  },
  captureEyebrow: {
    ...pranaPulseTheme.type.eyebrow,
    color: pranaPulseTheme.colors.primary,
  },
  captureTitle: {
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 28,
    fontFamily: pranaPulseTheme.fonts.extraBold,
    lineHeight: 34,
  },
  captureTitleCompact: {
    fontSize: 25,
    lineHeight: 31,
  },
  captureSubtitle: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 14,
    lineHeight: 22,
  },
  captureStage: {
    flex: 1,
    minHeight: 0,
  },
  captureStageInner: {
    flex: 1,
    minHeight: 0,
  },
  qualityOverlay: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    paddingBottom: 8,
  },
});
