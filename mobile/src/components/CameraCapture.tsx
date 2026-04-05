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
import { Platform, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
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

  const [timeRemaining, setTimeRemaining] = useState(scanDurationMs / 1000);
  const [isScanning, setIsScanning] = useState(false);
  const [currentQuality, setCurrentQuality] = useState<QualityMetrics | null>(null);

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
      <View style={styles.cameraShell}>
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
          <View style={styles.faceGuide} testID="face-guide" />

          {isScanning ? (
            <View style={styles.scanningPill} testID="scanning-indicator">
              <Text style={styles.scanningText}>Scanning…</Text>
            </View>
          ) : null}

              {currentQuality ? (
            <View style={styles.qualityOverlay} testID="quality-overlay">
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
    backgroundColor: '#0f0f1a',
    alignItems: 'center',
  },
  centeredContainer: {
    flex: 1,
    backgroundColor: '#0f0f1a',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 32,
  },
  cameraShell: {
    width: '100%',
    height: 400,
    position: 'relative',
    overflow: 'hidden',
    justifyContent: 'center',
    alignItems: 'center',
  },
  previewOverlay: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: 'center',
    alignItems: 'center',
  },
  faceGuide: {
    width: 200,
    height: 260,
    borderRadius: 100,
    borderWidth: 2,
    borderColor: '#4f46e5',
    borderStyle: 'dashed',
  },
  scanningPill: {
    position: 'absolute',
    bottom: 16,
    backgroundColor: 'rgba(79, 70, 229, 0.85)',
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 6,
  },
  scanningText: {
    color: '#ffffff',
    fontSize: 14,
    fontWeight: '600',
  },
  qualityOverlay: {
    position: 'absolute',
    top: 12,
    right: 12,
    flexDirection: 'row',
    gap: 6,
  },
  qualityDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  progressBar: {
    width: '90%',
    height: 4,
    backgroundColor: '#2a2a4e',
    borderRadius: 2,
    marginTop: 12,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    backgroundColor: '#4f46e5',
    borderRadius: 2,
  },
  infoRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 12,
    paddingHorizontal: 20,
    gap: 12,
  },
  timerText: {
    fontSize: 28,
    fontWeight: '700',
    color: '#4f46e5',
    minWidth: 50,
    textAlign: 'center',
  },
  instructionText: {
    flex: 1,
    fontSize: 14,
    color: '#aaaacc',
    lineHeight: 20,
  },
  buttonRow: {
    marginTop: 20,
    width: '90%',
  },
  startButton: {
    backgroundColor: '#4f46e5',
    borderRadius: 14,
    paddingVertical: 16,
    alignItems: 'center',
  },
  startButtonText: {
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
    fontWeight: '700',
  },
  cancelLinkButton: {
    marginTop: 16,
  },
  cancelLinkText: {
    color: '#f87171',
    fontSize: 15,
    fontWeight: '600',
  },
  messageText: {
    color: '#ffffff',
    fontSize: 18,
    fontWeight: '600',
    textAlign: 'center',
  },
  subText: {
    color: '#aaaacc',
    fontSize: 14,
    textAlign: 'center',
    lineHeight: 20,
    marginTop: 8,
    marginBottom: 24,
  },
  disclaimer: {
    color: '#6b6b8f',
    fontSize: 12,
    lineHeight: 18,
    textAlign: 'center',
    paddingHorizontal: 24,
    marginTop: 20,
  },
});
