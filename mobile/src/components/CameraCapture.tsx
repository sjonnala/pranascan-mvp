/**
 * CameraCapture - Vision Camera capture for both selfie POS and contact-PPG Deep Dive scans.
 *
 * Standard mode:
 *   - front camera
 *   - 30 seconds
 *   - 30 FPS target
 *   - centre ROI RGB traces for POS processing
 *
 * Deep Dive mode:
 *   - back camera + torch
 *   - 60 seconds
 *   - 60 FPS target when available
 *   - centre ROI red-derived trace for morphology processing
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Animated, Easing, Platform, StyleSheet, Text, TouchableOpacity, useWindowDimensions, View } from 'react-native';
import {
  Camera,
  runAtTargetFps,
  useCameraDevice,
  useCameraFormat,
  useCameraPermission,
  useFrameProcessor,
} from 'react-native-vision-camera';
import { Worklets } from 'react-native-worklets-core';

import { FrameSample, QualityMetrics, ScanType } from '../types';
import {
  aggregateQualityMetrics,
  buildFrameSampleFromRgb,
  computeFaceConfidenceFromRgb,
  computeLightingScoreFromRgb,
  computeMotionScoreFromRgb,
  computeOverallQualityScore,
  RgbTraceSample,
} from '../utils/frameAnalyzer';
import { pranaPulseTheme, withAlpha } from '../theme/pranaPulse';

const STANDARD_SCAN_DURATION_MS = 30_000;
const DEEP_DIVE_SCAN_DURATION_MS = 60_000;
const COUNTDOWN_INTERVAL_MS = 200;
const STANDARD_CAMERA_FPS = 30;
const DEEP_DIVE_CAMERA_FPS = 60;
const MINIMUM_CAPTURE_FPS = 30;
const ROI_SIZE_PX = 100;
const AUDIO_SNR_DEFAULT = 20.0;
const RGB_LAYOUT: 'rgba' | 'bgra' = Platform.OS === 'ios' ? 'bgra' : 'rgba';

export interface CameraResult {
  quality: QualityMetrics;
  quality_score: number;
  frame_data: FrameSample[];
  frame_r_mean: number | null;
  frame_g_mean: number | null;
  frame_b_mean: number | null;
}

interface CameraCaptureProps {
  scanType?: ScanType;
  onComplete: (result: CameraResult) => void;
  onQualityUpdate: (metrics: QualityMetrics) => void;
  onCancel: () => void;
}

type RoiAverage = {
  rMean: number;
  gMean: number;
  bMean: number;
};

function extractCenterRoiAverage(
  frame: {
  width: number;
  height: number;
  bytesPerRow: number;
  pixelFormat: string;
  toArrayBuffer: () => ArrayBuffer;
  },
  redOnly: boolean,
): RoiAverage | null {
  'worklet';

  if (frame.pixelFormat !== 'rgb' || frame.width <= 0 || frame.height <= 0) {
    return null;
  }

  const bytesPerPixel = Math.max(3, Math.round(frame.bytesPerRow / frame.width));
  if (bytesPerPixel < 3) {
    return null;
  }

  const roiWidth = Math.min(ROI_SIZE_PX, frame.width);
  const roiHeight = Math.min(ROI_SIZE_PX, frame.height);
  const startX = Math.max(0, Math.floor((frame.width - roiWidth) / 2));
  const startY = Math.max(0, Math.floor((frame.height - roiHeight) / 2));

  const data = new Uint8Array(frame.toArrayBuffer());
  let rTotal = 0;
  let gTotal = 0;
  let bTotal = 0;
  let samples = 0;

  for (let y = startY; y < startY + roiHeight; y += 1) {
    const rowOffset = y * frame.bytesPerRow;
    for (let x = startX; x < startX + roiWidth; x += 1) {
      const offset = rowOffset + x * bytesPerPixel;
      if (offset + 2 >= data.length) {
        continue;
      }

      const r = RGB_LAYOUT === 'bgra' ? data[offset + 2] : data[offset];
      const g = data[offset + 1];
      const b = RGB_LAYOUT === 'bgra' ? data[offset] : data[offset + 2];
      const redOnlyValue = r;

      rTotal += redOnly ? redOnlyValue : r;
      gTotal += redOnly ? redOnlyValue : g;
      bTotal += redOnly ? redOnlyValue : b;
      samples += 1;
    }
  }

  if (samples === 0) {
    return null;
  }

  return {
    rMean: rTotal / samples,
    gMean: gTotal / samples,
    bMean: bTotal / samples,
  };
}

export function CameraCapture({
  scanType = 'standard',
  onComplete,
  onQualityUpdate,
  onCancel,
}: CameraCaptureProps) {
  const { width: screenWidth, height: screenHeight } = useWindowDimensions();
  const { hasPermission, requestPermission } = useCameraPermission();
  const device = useCameraDevice(scanType === 'deep_dive' ? 'back' : 'front');
  const preferredCameraFps =
    scanType === 'deep_dive' && device?.formats.some((format) => format.maxFps >= DEEP_DIVE_CAMERA_FPS)
      ? DEEP_DIVE_CAMERA_FPS
      : STANDARD_CAMERA_FPS;
  const cameraFormat = useCameraFormat(device, [
    { fps: preferredCameraFps },
    { videoResolution: { width: 1280, height: 720 } },
  ]);
  const scanDurationMs = scanType === 'deep_dive' ? DEEP_DIVE_SCAN_DURATION_MS : STANDARD_SCAN_DURATION_MS;
  const isDeepDive = scanType === 'deep_dive';
  const compactDevice = screenWidth < 390;
  const cameraShellHeight = Math.min(
    Math.max(screenWidth * (compactDevice ? 0.98 : 1.04), compactDevice ? 350 : 384),
    screenHeight * 0.52,
  );
  const guideScale = compactDevice ? 0.92 : 1;

  const [timeRemaining, setTimeRemaining] = useState(scanDurationMs / 1000);
  const [isScanning, setIsScanning] = useState(false);
  const [currentQuality, setCurrentQuality] = useState<QualityMetrics | null>(null);
  const waveScale = useRef(new Animated.Value(1)).current;
  const waveOpacity = useRef(new Animated.Value(0.18)).current;
  const guideFloat = useRef(new Animated.Value(0)).current;
  const guideOpacity = useRef(new Animated.Value(0.72)).current;
  const deepDivePulseScale = useRef(new Animated.Value(1)).current;
  const deepDivePulseOpacity = useRef(new Animated.Value(0.18)).current;

  const frameDataRef = useRef<FrameSample[]>([]);
  const previousTraceRef = useRef<RgbTraceSample | null>(null);
  const lightingHistoryRef = useRef<number[]>([]);
  const motionHistoryRef = useRef<number[]>([]);
  const faceConfidenceHistoryRef = useRef<number[]>([]);
  const scanStartRef = useRef<number | null>(null);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const scanActiveRef = useRef(false);

  const supportsRequiredFps = Boolean(device?.formats.some((format) => format.maxFps >= MINIMUM_CAPTURE_FPS));

  const stopCountdown = useCallback(() => {
    if (countdownRef.current) {
      clearInterval(countdownRef.current);
      countdownRef.current = null;
    }
  }, []);

  const resetTraceState = useCallback(() => {
    frameDataRef.current = [];
    previousTraceRef.current = null;
    lightingHistoryRef.current = [];
    motionHistoryRef.current = [];
    faceConfidenceHistoryRef.current = [];
    scanStartRef.current = null;
    setCurrentQuality(null);
    setTimeRemaining(scanDurationMs / 1000);
  }, [scanDurationMs]);

  useEffect(() => {
    return () => {
      scanActiveRef.current = false;
      stopCountdown();
    };
  }, [stopCountdown]);

  useEffect(() => {
    if (isDeepDive) {
      waveScale.stopAnimation();
      waveOpacity.stopAnimation();
      guideFloat.stopAnimation();
      guideOpacity.stopAnimation();
      waveScale.setValue(1);
      waveOpacity.setValue(0.12);
      guideFloat.setValue(0);
      guideOpacity.setValue(0.72);
      return;
    }

    const pulseMaxScale = isScanning ? 1.1 : 1.05;
    const pulseMaxOpacity = isScanning ? 0.34 : 0.22;
    const guideLift = isScanning ? -5 : -2;
    const guideGlow = isScanning ? 0.94 : 0.78;

    const loop = Animated.loop(
      Animated.parallel([
        Animated.sequence([
          Animated.timing(waveScale, {
            toValue: pulseMaxScale,
            duration: 1800,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
          Animated.timing(waveScale, {
            toValue: 1,
            duration: 1800,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
        ]),
        Animated.sequence([
          Animated.timing(waveOpacity, {
            toValue: pulseMaxOpacity,
            duration: 1800,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
          Animated.timing(waveOpacity, {
            toValue: 0.12,
            duration: 1800,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
        ]),
        Animated.sequence([
          Animated.timing(guideFloat, {
            toValue: guideLift,
            duration: 1800,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
          Animated.timing(guideFloat, {
            toValue: 0,
            duration: 1800,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
        ]),
        Animated.sequence([
          Animated.timing(guideOpacity, {
            toValue: guideGlow,
            duration: 1800,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
          Animated.timing(guideOpacity, {
            toValue: 0.72,
            duration: 1800,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
        ]),
      ])
    );

    loop.start();
    return () => {
      loop.stop();
    };
  }, [guideFloat, guideOpacity, isDeepDive, isScanning, waveOpacity, waveScale]);

  useEffect(() => {
    if (!isDeepDive) {
      deepDivePulseScale.stopAnimation();
      deepDivePulseOpacity.stopAnimation();
      deepDivePulseScale.setValue(1);
      deepDivePulseOpacity.setValue(0.16);
      return;
    }

    const pulseLoop = Animated.loop(
      Animated.parallel([
        Animated.sequence([
          Animated.timing(deepDivePulseScale, {
            toValue: isScanning ? 1.08 : 1.04,
            duration: 1600,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
          Animated.timing(deepDivePulseScale, {
            toValue: 1,
            duration: 1600,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
        ]),
        Animated.sequence([
          Animated.timing(deepDivePulseOpacity, {
            toValue: isScanning ? 0.32 : 0.22,
            duration: 1600,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
          Animated.timing(deepDivePulseOpacity, {
            toValue: 0.14,
            duration: 1600,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
        ]),
      ])
    );

    pulseLoop.start();
    return () => {
      pulseLoop.stop();
    };
  }, [deepDivePulseOpacity, deepDivePulseScale, isDeepDive, isScanning]);

  const finaliseScan = useCallback(() => {
    if (!scanActiveRef.current) {
      return;
    }

    scanActiveRef.current = false;
    stopCountdown();
    setIsScanning(false);

    const frames = [...frameDataRef.current];
    const aggregatedQuality = aggregateQualityMetrics(
      lightingHistoryRef.current,
      motionHistoryRef.current,
      faceConfidenceHistoryRef.current,
    );

    const frameCount = frames.length;
    const frameRMean = frameCount > 0 ? frames.reduce((sum, frame) => sum + frame.r_mean, 0) / frameCount : null;
    const frameGMean = frameCount > 0 ? frames.reduce((sum, frame) => sum + frame.g_mean, 0) / frameCount : null;
    const frameBMean = frameCount > 0 ? frames.reduce((sum, frame) => sum + frame.b_mean, 0) / frameCount : null;

    const quality: QualityMetrics = {
      lighting_score: aggregatedQuality.lighting_score,
      motion_score: aggregatedQuality.motion_score,
      face_confidence: aggregatedQuality.face_confidence,
      audio_snr_db: AUDIO_SNR_DEFAULT,
    };

    onComplete({
      quality,
      quality_score: computeOverallQualityScore(
        quality.lighting_score,
        quality.motion_score,
        quality.face_confidence,
        AUDIO_SNR_DEFAULT,
      ),
      frame_data: frames,
      frame_r_mean: frameRMean,
      frame_g_mean: frameGMean,
      frame_b_mean: frameBMean,
    });
  }, [onComplete, stopCountdown]);

  const handleCancel = useCallback(() => {
    scanActiveRef.current = false;
    stopCountdown();
    setIsScanning(false);
    resetTraceState();
    onCancel();
  }, [onCancel, resetTraceState, stopCountdown]);

  const handleTraceSample = useCallback(
    (rMean: number, gMean: number, bMean: number) => {
      if (!scanActiveRef.current) {
        return;
      }

      const elapsed = Date.now() - (scanStartRef.current ?? Date.now());
      const rgbSample: RgbTraceSample = {
        r_mean: rMean,
        g_mean: gMean,
        b_mean: bMean,
      };
      const frameSample = buildFrameSampleFromRgb(rgbSample, elapsed);

      frameDataRef.current.push(frameSample);

      const lighting = computeLightingScoreFromRgb(rgbSample);
      const motion = computeMotionScoreFromRgb(previousTraceRef.current, rgbSample);
      const faceConfidence = isDeepDive
        ? Math.max(0, Math.min(1, lighting * 0.75 + motion * 0.25))
        : computeFaceConfidenceFromRgb(rgbSample, lighting, motion);

      previousTraceRef.current = rgbSample;
      lightingHistoryRef.current.push(lighting);
      motionHistoryRef.current.push(motion);
      faceConfidenceHistoryRef.current.push(faceConfidence);

      const metrics: QualityMetrics = {
        lighting_score: lighting,
        motion_score: motion,
        face_confidence: faceConfidence,
        audio_snr_db: AUDIO_SNR_DEFAULT,
      };

      if (frameDataRef.current.length === 1 || frameDataRef.current.length % 5 === 0) {
        setCurrentQuality(metrics);
        onQualityUpdate(metrics);
      }
    },
    [isDeepDive, onQualityUpdate],
  );

  const emitTraceSample = useMemo(
    () => Worklets.createRunOnJS(handleTraceSample),
    [handleTraceSample],
  );

  const frameProcessor = useFrameProcessor(
    (frame) => {
      'worklet';

      if (!isScanning) {
        return;
      }

      runAtTargetFps(preferredCameraFps, () => {
        'worklet';
        const roiAverage = extractCenterRoiAverage(frame, isDeepDive);
        if (!roiAverage) {
          return;
        }
        emitTraceSample(roiAverage.rMean, roiAverage.gMean, roiAverage.bMean);
      });
    },
    [emitTraceSample, isScanning, isDeepDive, preferredCameraFps],
  );

  const startScan = useCallback(async () => {
    if (!hasPermission) {
      const granted = await requestPermission();
      if (!granted) {
        return;
      }
    }

    resetTraceState();
    setIsScanning(true);
    scanActiveRef.current = true;
    scanStartRef.current = Date.now();

    countdownRef.current = setInterval(() => {
      const elapsed = Date.now() - (scanStartRef.current ?? Date.now());
      const remaining = Math.max(0, Math.ceil((scanDurationMs - elapsed) / 1000));
      setTimeRemaining(remaining);
      if (remaining <= 0) {
        finaliseScan();
      }
    }, COUNTDOWN_INTERVAL_MS);
  }, [finaliseScan, hasPermission, requestPermission, resetTraceState, scanDurationMs]);

  if (!hasPermission) {
    return (
      <View style={styles.centeredContainer} testID="camera-capture">
        <Text style={styles.messageText} testID="permission-message">
          Camera access is needed for wellness scanning.
        </Text>
        <Text style={styles.subText}>
          Only a centre-ROI RGB trace leaves the device, never the full video feed.
        </Text>
        <TouchableOpacity
          style={styles.startButton}
          onPress={requestPermission}
          testID="allow-camera"
        >
          <Text style={styles.startButtonText}>Allow Camera</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.cancelLinkButton}
          onPress={handleCancel}
          testID="cancel-scan"
        >
          <Text style={styles.cancelLinkText}>Cancel</Text>
        </TouchableOpacity>
      </View>
    );
  }

  if (!device) {
    return (
      <View style={styles.centeredContainer} testID="camera-capture">
        <Text style={styles.messageText}>Loading front camera…</Text>
      </View>
    );
  }

  if (!supportsRequiredFps || !cameraFormat) {
    return (
      <View style={styles.centeredContainer} testID="camera-capture">
        <Text style={styles.messageText} testID="camera-fps-warning">
          This device does not expose the required {MINIMUM_CAPTURE_FPS} FPS camera format.
        </Text>
        <Text style={styles.subText}>
          {isDeepDive
            ? 'Deep Dive contact PPG needs at least a stable 30 FPS back-camera stream.'
            : 'The upgraded selfie rPPG pipeline requires a native 30 FPS RGB stream.'}
        </Text>
        <TouchableOpacity
          style={styles.cancelLinkButton}
          onPress={handleCancel}
          testID="cancel-scan"
        >
          <Text style={styles.cancelLinkText}>Cancel</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const progressPct = ((scanDurationMs / 1000 - timeRemaining) / (scanDurationMs / 1000)) * 100;

  return (
    <View style={styles.container} testID="camera-capture">
      <View style={[styles.cameraShell, { height: cameraShellHeight }]}>
        <Camera
          device={device}
          format={cameraFormat}
          fps={preferredCameraFps}
          isActive
          style={StyleSheet.absoluteFill}
          pixelFormat="rgb"
          enableBufferCompression={false}
          frameProcessor={frameProcessor}
          androidPreviewViewType="texture-view"
          torch={isDeepDive ? 'on' : 'off'}
          testID="camera-view"
        />

        <View pointerEvents="none" style={styles.previewOverlay}>
          {!isDeepDive ? (
            <>
              <Animated.View
                style={[
                  styles.breathingAura,
                  {
                    opacity: waveOpacity,
                    transform: [{ scale: waveScale }],
                  },
                ]}
              />
              <Animated.View
                style={[
                  styles.breathingAuraSecondary,
                  {
                    opacity: waveOpacity,
                    transform: [{ scale: waveScale }],
                  },
                ]}
              />
              <Animated.View
                style={[
                  styles.waveField,
                  {
                    opacity: waveOpacity,
                    transform: [{ scaleX: waveScale }],
                  },
                ]}
              >
                <View style={[styles.waveLine, styles.waveLinePrimary]} />
                <View style={[styles.waveLine, styles.waveLineSecondary]} />
                <View style={[styles.waveLine, styles.waveLineTertiary]} />
              </Animated.View>
              <View style={styles.viewfinderFrame}>
                <View style={[styles.cornerBracket, styles.cornerTopLeft]} />
                <View style={[styles.cornerBracket, styles.cornerTopRight]} />
                <View style={[styles.cornerBracket, styles.cornerBottomLeft]} />
                <View style={[styles.cornerBracket, styles.cornerBottomRight]} />
                <Animated.View
                  style={[
                    styles.faceGuide,
                    {
                      opacity: guideOpacity,
                      transform: [{ translateY: guideFloat }, { scale: guideScale }],
                    },
                  ]}
                  testID="face-guide"
                >
                  <View style={styles.ghostHead} />
                  <View style={styles.ghostForehead} />
                  <View style={styles.ghostCenterLine} />
                  <View style={styles.ghostShoulders} />
                  <View style={styles.ghostBaseArc} />
                </Animated.View>
              </View>
            </>
          ) : (
            <View style={[styles.deepDiveGuideShell, { transform: [{ scale: guideScale }] }]}>
              <Animated.View
                style={[
                  styles.deepDivePulseRing,
                  {
                    opacity: deepDivePulseOpacity,
                    transform: [{ scale: deepDivePulseScale }],
                  },
                ]}
              />
              <View style={styles.deepDiveGuideOuter} />
              <View style={styles.deepDiveGuideRing} testID="face-guide" />
              <View style={styles.deepDiveGuideCore} />
            </View>
          )}

          {isScanning ? (
            <View style={styles.scanningPill} testID="scanning-indicator">
              <View style={styles.scanningDot} />
              <Text style={styles.scanningText}>Scanning…</Text>
            </View>
          ) : null}

          {currentQuality ? (
            <View style={styles.qualityOverlay} testID="quality-overlay">
              <View style={styles.qualityChip}>
                <View
                  style={[
                    styles.qualityDot,
                    {
                      backgroundColor:
                        currentQuality.lighting_score > 0.4 ? '#4ade80' : '#f87171',
                    },
                  ]}
                  testID="quality-dot-lighting"
                />
                <Text style={styles.qualityLabel}>Light</Text>
              </View>
              <View style={styles.qualityChip}>
                <View
                  style={[
                    styles.qualityDot,
                    {
                      backgroundColor:
                        currentQuality.motion_score >= 0.95 ? '#4ade80' : '#f87171',
                    },
                  ]}
                  testID="quality-dot-motion"
                />
                <Text style={styles.qualityLabel}>Steady</Text>
              </View>
            </View>
          ) : null}
        </View>
      </View>

      <View style={styles.progressBar} testID="progress-bar">
        <View style={[styles.progressFill, { width: `${progressPct}%` as `${number}%` }]} />
      </View>

      <View style={styles.infoRow}>
        <Text style={styles.timerText} testID="timer">
          {timeRemaining}s
        </Text>
        <Text style={styles.instructionText}>
          {isDeepDive
            ? isScanning
              ? 'Cover the camera and flash with your thumb.'
              : preferredCameraFps >= DEEP_DIVE_CAMERA_FPS
                ? 'Cover the camera and flash with your thumb.'
                : 'Cover the camera and flash with your thumb. 60 FPS is unavailable, so this device will use 30 FPS.'
            : isScanning
              ? 'Keep your forehead centred and your head steady'
              : 'Position your forehead in the guide above'}
        </Text>
      </View>

      <View style={styles.buttonRow}>
        {!isScanning ? (
          <TouchableOpacity style={styles.startButton} onPress={startScan} testID="start-scan">
            <Text style={styles.startButtonText}>
              {isDeepDive ? 'Start 60-second Deep Dive' : 'Start 30-second Scan'}
            </Text>
          </TouchableOpacity>
        ) : (
          <TouchableOpacity
            style={styles.cancelButton}
            onPress={handleCancel}
            testID="cancel-scan"
          >
            <Text style={styles.cancelButtonText}>Cancel</Text>
          </TouchableOpacity>
        )}
      </View>

      <Text style={styles.disclaimer}>
        {isDeepDive
          ? 'The app shares only a red-derived centre trace for contact-PPG processing, not full video.'
          : 'The app shares only centre-ROI RGB traces for wellness processing, not full video.'}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: pranaPulseTheme.colors.background,
    alignItems: 'center',
  },
  centeredContainer: {
    flex: 1,
    backgroundColor: pranaPulseTheme.colors.background,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 32,
  },
  cameraShell: {
    width: '100%',
    height: 430,
    position: 'relative',
    overflow: 'hidden',
    justifyContent: 'center',
    alignItems: 'center',
    borderRadius: pranaPulseTheme.radius.lg,
    backgroundColor: pranaPulseTheme.colors.surfaceContainer,
  },
  previewOverlay: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: 'center',
    alignItems: 'center',
  },
  viewfinderFrame: {
    width: '82%',
    height: '78%',
    borderRadius: pranaPulseTheme.radius.md,
    borderWidth: 2,
    borderColor: withAlpha(pranaPulseTheme.colors.outlineVariant, 0.42),
    alignItems: 'center',
    justifyContent: 'center',
  },
  cornerBracket: {
    position: 'absolute',
    width: 34,
    height: 34,
    borderColor: pranaPulseTheme.colors.primary,
  },
  cornerTopLeft: {
    top: -2,
    left: -2,
    borderTopWidth: 3,
    borderLeftWidth: 3,
    borderTopLeftRadius: pranaPulseTheme.radius.sm,
  },
  cornerTopRight: {
    top: -2,
    right: -2,
    borderTopWidth: 3,
    borderRightWidth: 3,
    borderTopRightRadius: pranaPulseTheme.radius.sm,
  },
  cornerBottomLeft: {
    bottom: -2,
    left: -2,
    borderBottomWidth: 3,
    borderLeftWidth: 3,
    borderBottomLeftRadius: pranaPulseTheme.radius.sm,
  },
  cornerBottomRight: {
    bottom: -2,
    right: -2,
    borderBottomWidth: 3,
    borderRightWidth: 3,
    borderBottomRightRadius: pranaPulseTheme.radius.sm,
  },
  faceGuide: {
    width: 196,
    height: 252,
    alignItems: 'center',
    justifyContent: 'center',
  },
  ghostHead: {
    position: 'absolute',
    top: 8,
    width: 144,
    height: 180,
    borderRadius: 92,
    borderWidth: 2,
    borderColor: withAlpha(pranaPulseTheme.colors.primary, 0.88),
    borderStyle: 'dashed',
  },
  ghostForehead: {
    position: 'absolute',
    top: 28,
    width: 78,
    height: 10,
    borderRadius: 999,
    backgroundColor: withAlpha(pranaPulseTheme.colors.surfaceContainerLowest, 0.34),
  },
  ghostCenterLine: {
    position: 'absolute',
    top: 84,
    width: 6,
    height: 48,
    borderRadius: 999,
    backgroundColor: withAlpha(pranaPulseTheme.colors.secondaryContainer, 0.52),
  },
  ghostShoulders: {
    position: 'absolute',
    bottom: 24,
    width: 168,
    height: 70,
    borderTopWidth: 2,
    borderLeftWidth: 2,
    borderRightWidth: 2,
    borderColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.72),
    borderTopLeftRadius: 90,
    borderTopRightRadius: 90,
  },
  ghostBaseArc: {
    position: 'absolute',
    bottom: 10,
    width: 118,
    height: 22,
    borderTopWidth: 2,
    borderColor: withAlpha(pranaPulseTheme.colors.secondaryContainer, 0.64),
    borderTopLeftRadius: 60,
    borderTopRightRadius: 60,
  },
  deepDiveGuideShell: {
    width: 220,
    height: 220,
    alignItems: 'center',
    justifyContent: 'center',
  },
  deepDivePulseRing: {
    position: 'absolute',
    width: 206,
    height: 206,
    borderRadius: 103,
    borderWidth: 1,
    borderColor: withAlpha(pranaPulseTheme.colors.secondaryContainer, 0.8),
  },
  deepDiveGuideOuter: {
    position: 'absolute',
    width: 196,
    height: 196,
    borderRadius: 98,
    borderWidth: 1,
    borderColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.46),
  },
  deepDiveGuideRing: {
    width: 176,
    height: 176,
    borderRadius: 88,
    borderWidth: 2,
    borderColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.8),
  },
  deepDiveGuideCore: {
    position: 'absolute',
    width: 54,
    height: 54,
    borderRadius: 27,
    backgroundColor: withAlpha(pranaPulseTheme.colors.surfaceContainerLowest, 0.18),
    borderWidth: 1,
    borderColor: withAlpha(pranaPulseTheme.colors.secondaryContainer, 0.56),
  },
  breathingAura: {
    position: 'absolute',
    width: 236,
    height: 236,
    borderRadius: 118,
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.4),
  },
  breathingAuraSecondary: {
    position: 'absolute',
    width: 280,
    height: 280,
    borderRadius: 140,
    borderWidth: 1,
    borderColor: withAlpha(pranaPulseTheme.colors.secondaryContainer, 0.65),
  },
  waveField: {
    position: 'absolute',
    alignItems: 'center',
    gap: 10,
  },
  waveLine: {
    height: 3,
    borderRadius: 999,
  },
  waveLinePrimary: {
    width: 104,
    backgroundColor: withAlpha(pranaPulseTheme.colors.secondaryContainer, 0.86),
  },
  waveLineSecondary: {
    width: 136,
    backgroundColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.9),
  },
  waveLineTertiary: {
    width: 86,
    backgroundColor: withAlpha(pranaPulseTheme.colors.secondaryContainer, 0.62),
  },
  scanningPill: {
    position: 'absolute',
    bottom: 22,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: withAlpha(pranaPulseTheme.colors.surfaceContainerLowest, 0.88),
    borderRadius: pranaPulseTheme.radius.full,
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: withAlpha(pranaPulseTheme.colors.primaryContainer, 0.5),
  },
  scanningDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: pranaPulseTheme.colors.secondary,
  },
  scanningText: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.primary,
    fontSize: 13,
    letterSpacing: 0.4,
  },
  qualityOverlay: {
    position: 'absolute',
    top: 18,
    right: 18,
    flexDirection: 'row',
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: pranaPulseTheme.radius.full,
    backgroundColor: withAlpha(pranaPulseTheme.colors.surfaceContainerLowest, 0.84),
    borderWidth: 1,
    borderColor: withAlpha(pranaPulseTheme.colors.outlineVariant, 0.28),
  },
  qualityChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  qualityDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  qualityLabel: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 11,
    letterSpacing: 0.4,
  },
  progressBar: {
    width: '100%',
    height: 6,
    backgroundColor: pranaPulseTheme.colors.surfaceContainerHigh,
    borderRadius: 999,
    marginTop: 16,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    backgroundColor: pranaPulseTheme.colors.primary,
    borderRadius: 999,
  },
  infoRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 14,
    gap: 12,
  },
  timerText: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    fontSize: 28,
    color: pranaPulseTheme.colors.primary,
    minWidth: 50,
    textAlign: 'center',
  },
  instructionText: {
    fontFamily: pranaPulseTheme.fonts.medium,
    flex: 1,
    fontSize: 14,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    lineHeight: 22,
  },
  buttonRow: {
    marginTop: 20,
    width: '100%',
  },
  startButton: {
    backgroundColor: pranaPulseTheme.colors.primary,
    borderRadius: pranaPulseTheme.radius.full,
    paddingVertical: 16,
    alignItems: 'center',
  },
  startButtonText: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.onPrimary,
    fontSize: 16,
  },
  cancelButton: {
    backgroundColor: pranaPulseTheme.colors.surfaceContainerHigh,
    borderRadius: pranaPulseTheme.radius.full,
    paddingVertical: 16,
    alignItems: 'center',
  },
  cancelButtonText: {
    fontFamily: pranaPulseTheme.fonts.extraBold,
    color: pranaPulseTheme.colors.secondary,
    fontSize: 16,
  },
  cancelLinkButton: {
    marginTop: 16,
  },
  cancelLinkText: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.secondary,
    fontSize: 15,
  },
  messageText: {
    fontFamily: pranaPulseTheme.fonts.bold,
    color: pranaPulseTheme.colors.onSurface,
    fontSize: 18,
    textAlign: 'center',
  },
  subText: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 14,
    textAlign: 'center',
    lineHeight: 22,
    marginTop: 8,
    marginBottom: 24,
  },
  disclaimer: {
    fontFamily: pranaPulseTheme.fonts.medium,
    color: pranaPulseTheme.colors.onSurfaceVariant,
    fontSize: 12,
    lineHeight: 18,
    textAlign: 'center',
    paddingHorizontal: 8,
    marginTop: 18,
  },
});
