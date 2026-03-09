/**
 * CameraCapture — real 30-second front-camera scan component.
 *
 * Sprint 2.1 (S2-01): replaced placeholder View with expo-camera CameraView.
 * - Real permission handling via useCameraPermissions()
 * - Real frame capture via takePictureAsync at quality=0.05
 * - Quality metrics derived from real JPEG frame data (see frameAnalyzer.ts)
 * - Face confidence: fixed 0.85 proxy (expo-face-detector not included in SDK 51
 *   base; Sprint 3 target for native face detection via ML Kit)
 * - frame_data accumulated for backend rPPG processing (S2-02)
 *
 * Privacy: raw frame base64 data is discarded after metric extraction.
 * Only FrameSample values ({t_ms, r_mean, g_mean, b_mean}) are forwarded.
 * Raw video NEVER leaves the device.
 */

import { CameraView, useCameraPermissions } from 'expo-camera';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { FrameSample, QualityMetrics } from '../types';
import {
  buildFrameSample,
  computeFaceConfidence,
  computeLightingScore,
  computeMotionScore,
  computeOverallQualityScore,
} from '../utils/frameAnalyzer';

// ─── Constants ────────────────────────────────────────────────────────────────

const SCAN_DURATION_MS = 30_000;
/** Frame sampling interval. ~2fps: fast enough for quality monitoring, low CPU. */
const FRAME_INTERVAL_MS = 500;
/**
 * Audio SNR is evaluated in VoiceCapture; default here keeps gate open.
 * Face confidence is now computed per-frame via computeFaceConfidence()
 * (Sprint 3 will replace with native ML Kit face detector).
 */
const AUDIO_SNR_DEFAULT = 20.0;

// ─── Types ────────────────────────────────────────────────────────────────────

export interface CameraResult {
  /** null until backend rPPG processes frame_data (S2-02). */
  hr_bpm: number | null;
  /** null until backend rPPG processes frame_data (S2-02). */
  hrv_ms: number | null;
  /** null until backend rPPG processes frame_data (S2-02). */
  respiratory_rate: number | null;
  quality: QualityMetrics;
  quality_score: number;
  /** Per-frame RGB means sent to backend for server-side rPPG. */
  frame_data: FrameSample[];
}

interface CameraCaptureProps {
  onComplete: (result: CameraResult) => void;
  onQualityUpdate: (metrics: QualityMetrics) => void;
  onCancel: () => void;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function CameraCapture({ onComplete, onQualityUpdate, onCancel }: CameraCaptureProps) {
  const [permission, requestPermission] = useCameraPermissions();
  const [timeRemaining, setTimeRemaining] = useState(SCAN_DURATION_MS / 1000);
  const [isScanning, setIsScanning] = useState(false);
  const [currentQuality, setCurrentQuality] = useState<QualityMetrics | null>(null);

  const cameraRef = useRef<CameraView>(null);
  const scanStartRef = useRef<number | null>(null);
  const frameDataRef = useRef<FrameSample[]>([]);
  const prevBase64Ref = useRef<string | null>(null);
  const lastLightingRef = useRef<number>(0.5);
  const lastMotionRef = useRef<number>(1.0);
  /**
   * Tracks the most-recently computed face confidence so finaliseScan() can
   * use the real value instead of a constant proxy.
   * Initialised to 0.5 (uncertain) — updated each frame via computeFaceConfidence().
   */
  const lastFaceConfidenceRef = useRef<number>(0.5);
  const frameIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Cleanup ──────────────────────────────────────────────────────────────

  const stopTimers = useCallback(() => {
    if (frameIntervalRef.current) {
      clearInterval(frameIntervalRef.current);
      frameIntervalRef.current = null;
    }
    if (countdownRef.current) {
      clearInterval(countdownRef.current);
      countdownRef.current = null;
    }
  }, []);

  useEffect(() => () => stopTimers(), [stopTimers]);

  // ── Frame capture ─────────────────────────────────────────────────────────

  const captureFrame = useCallback(async (): Promise<string | null> => {
    try {
      const photo = await cameraRef.current?.takePictureAsync({
        quality: 0.05,
        base64: true,
        skipProcessing: true,
      });
      return photo?.base64 ?? null;
    } catch {
      return null;
    }
  }, []);

  // ── Scan orchestration ───────────────────────────────────────────────────

  const finaliseScan = useCallback(() => {
    stopTimers();
    setIsScanning(false);

    const frames = frameDataRef.current;
    const lighting = lastLightingRef.current;
    const motion = lastMotionRef.current;
    const faceConf = lastFaceConfidenceRef.current;

    const finalQuality: QualityMetrics = {
      lighting_score: lighting,
      motion_score: motion,
      face_confidence: faceConf,
      audio_snr_db: AUDIO_SNR_DEFAULT,
    };

    onComplete({
      hr_bpm: null,           // computed by backend rPPG (S2-02)
      hrv_ms: null,
      respiratory_rate: null,
      quality: finalQuality,
      quality_score: computeOverallQualityScore(
        lighting,
        motion,
        faceConf,
        AUDIO_SNR_DEFAULT,
      ),
      frame_data: frames,
    });
  }, [stopTimers, onComplete]);

  const startScan = useCallback(async () => {
    if (!permission?.granted) {
      await requestPermission();
      return;
    }

    setIsScanning(true);
    frameDataRef.current = [];
    prevBase64Ref.current = null;
    lastFaceConfidenceRef.current = 0.5; // reset to uncertain at scan start
    scanStartRef.current = Date.now();

    // Frame sampling interval
    frameIntervalRef.current = setInterval(async () => {
      const elapsed = Date.now() - (scanStartRef.current ?? Date.now());
      const base64 = await captureFrame();

      if (base64) {
        const lighting = computeLightingScore(base64);
        const motion = prevBase64Ref.current
          ? computeMotionScore(prevBase64Ref.current, base64)
          : 1.0;

        // Real per-frame face confidence: heuristic from lighting + JPEG size +
        // motion stability.  Sprint 3 will replace with ML Kit face detector.
        const faceConf = computeFaceConfidence(base64, lighting, motion);

        lastLightingRef.current = lighting;
        lastMotionRef.current = motion;
        lastFaceConfidenceRef.current = faceConf;
        prevBase64Ref.current = base64;

        const frame = buildFrameSample(base64, elapsed);
        frameDataRef.current.push(frame);

        const metrics: QualityMetrics = {
          lighting_score: lighting,
          motion_score: motion,
          face_confidence: faceConf,
          audio_snr_db: AUDIO_SNR_DEFAULT,
        };
        setCurrentQuality(metrics);
        onQualityUpdate(metrics);
      }
    }, FRAME_INTERVAL_MS);

    // Countdown interval
    countdownRef.current = setInterval(() => {
      const elapsed = Date.now() - (scanStartRef.current ?? Date.now());
      const remaining = Math.max(0, Math.ceil((SCAN_DURATION_MS - elapsed) / 1000));
      setTimeRemaining(remaining);
      if (remaining <= 0) finaliseScan();
    }, 200);
  }, [permission, requestPermission, captureFrame, onQualityUpdate, finaliseScan]);

  // ── Render: awaiting permission decision ─────────────────────────────────

  if (!permission) {
    return (
      <View style={styles.centeredContainer} testID="camera-capture">
        <Text style={styles.messageText}>Requesting camera access…</Text>
      </View>
    );
  }

  // ── Render: permission denied ─────────────────────────────────────────────

  if (!permission.granted) {
    return (
      <View style={styles.centeredContainer} testID="camera-capture">
        <Text style={styles.messageText} testID="permission-message">
          Camera access is needed for wellness scanning.
        </Text>
        <Text style={styles.subText}>
          Your camera feed stays on your device — no footage is stored or shared.
        </Text>
        <TouchableOpacity
          style={styles.startButton}
          onPress={requestPermission}
          testID="allow-camera"
        >
          <Text style={styles.startButtonText}>Allow Camera</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.cancelLinkButton} onPress={onCancel} testID="cancel-scan">
          <Text style={styles.cancelLinkText}>Cancel</Text>
        </TouchableOpacity>
      </View>
    );
  }

  // ── Render: camera active ─────────────────────────────────────────────────

  const progressPct =
    ((SCAN_DURATION_MS / 1000 - timeRemaining) / (SCAN_DURATION_MS / 1000)) * 100;

  return (
    <View style={styles.container} testID="camera-capture">
      {/* Real camera preview */}
      <CameraView
        ref={cameraRef}
        style={styles.cameraPreview}
        facing="front"
        testID="camera-view"
      >
        {/* Oval face-placement guide */}
        <View style={styles.faceGuide} testID="face-guide" />

        {isScanning && (
          <View style={styles.scanningPill} testID="scanning-indicator">
            <Text style={styles.scanningText}>Scanning…</Text>
          </View>
        )}

        {/* Real-time quality dots — green = pass, red = fail */}
        {currentQuality && (
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
        )}
      </CameraView>

      {/* Scan progress bar */}
      <View style={styles.progressBar} testID="progress-bar">
        <View style={[styles.progressFill, { width: `${progressPct}%` as `${number}%` }]} />
      </View>

      <View style={styles.infoRow}>
        <Text style={styles.timerText} testID="timer">
          {timeRemaining}s
        </Text>
        <Text style={styles.instructionText}>
          {isScanning
            ? 'Keep your face steady and well-lit'
            : 'Position your face in the oval above'}
        </Text>
      </View>

      <View style={styles.buttonRow}>
        {!isScanning ? (
          <TouchableOpacity style={styles.startButton} onPress={startScan} testID="start-scan">
            <Text style={styles.startButtonText}>Start 30-second Scan</Text>
          </TouchableOpacity>
        ) : (
          <TouchableOpacity
            style={styles.cancelButton}
            onPress={onCancel}
            testID="cancel-scan"
          >
            <Text style={styles.cancelButtonText}>Cancel</Text>
          </TouchableOpacity>
        )}
      </View>

      <Text style={styles.disclaimer}>
        Your camera feed stays on your device. Only wellness indicator values are shared.
      </Text>
    </View>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

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
  cameraPreview: {
    width: '100%',
    height: 400,
    justifyContent: 'center',
    alignItems: 'center',
    position: 'relative',
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
    fontWeight: '600',
  },
  cancelLinkButton: {
    marginTop: 16,
    paddingVertical: 8,
  },
  cancelLinkText: {
    color: '#666688',
    fontSize: 15,
  },
  messageText: {
    color: '#e0e0f0',
    fontSize: 18,
    fontWeight: '600',
    textAlign: 'center',
    marginBottom: 12,
    lineHeight: 26,
  },
  subText: {
    color: '#8888aa',
    fontSize: 14,
    textAlign: 'center',
    marginBottom: 28,
    lineHeight: 20,
  },
  disclaimer: {
    fontSize: 12,
    color: '#555570',
    textAlign: 'center',
    marginTop: 16,
    marginHorizontal: 24,
    lineHeight: 18,
  },
});
