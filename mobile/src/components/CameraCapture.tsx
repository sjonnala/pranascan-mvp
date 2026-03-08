/**
 * CameraCapture component — 30-second guided camera scan.
 *
 * Sprint 1: Uses simulated rPPG output for MVP scaffolding.
 * Sprint 2: Replace simulateRppgProcessing() with real on-device algorithm.
 *
 * Raw video frames NEVER leave the device.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { QualityMetrics } from '../types';

const SCAN_DURATION_MS = 30_000;
const QUALITY_POLL_INTERVAL_MS = 500;

export interface CameraResult {
  hr_bpm: number;
  hrv_ms: number;
  respiratory_rate: number;
  quality: QualityMetrics;
  quality_score: number;
}

interface CameraCaptureProps {
  onComplete: (result: CameraResult) => void;
  onQualityUpdate: (metrics: QualityMetrics) => void;
  onCancel: () => void;
}

/**
 * Simulates rPPG processing for Sprint 1.
 * Returns plausible wellness indicator values.
 * Replace with real algorithm in Sprint 2.
 */
function simulateRppgProcessing(): Pick<CameraResult, 'hr_bpm' | 'hrv_ms' | 'respiratory_rate'> {
  return {
    hr_bpm: 60 + Math.random() * 40, // 60–100 bpm
    hrv_ms: 30 + Math.random() * 40, // 30–70 ms
    respiratory_rate: 12 + Math.random() * 8, // 12–20 bpm
  };
}

/**
 * Simulates real-time quality metrics from camera feed.
 * Sprint 2: Replace with actual face detection + lighting analysis.
 */
function simulateQualityMetrics(): QualityMetrics {
  return {
    lighting_score: 0.7 + Math.random() * 0.3, // 0.7–1.0 (good)
    motion_score: 0.95 + Math.random() * 0.05, // 0.95–1.0 (stable)
    face_confidence: 0.85 + Math.random() * 0.15, // 0.85–1.0 (detected)
    audio_snr_db: 20 + Math.random() * 15, // 20–35 dB (quiet)
  };
}

export function CameraCapture({ onComplete, onQualityUpdate, onCancel }: CameraCaptureProps) {
  const [timeRemaining, setTimeRemaining] = useState(SCAN_DURATION_MS / 1000);
  const [isScanning, setIsScanning] = useState(false);
  const scanStartTime = useRef<number | null>(null);
  const qualityInterval = useRef<ReturnType<typeof setInterval> | null>(null);
  const countdownInterval = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopScan = useCallback(() => {
    if (qualityInterval.current) clearInterval(qualityInterval.current);
    if (countdownInterval.current) clearInterval(countdownInterval.current);
  }, []);

  const startScan = useCallback(() => {
    setIsScanning(true);
    scanStartTime.current = Date.now();

    // Poll quality metrics every 500ms
    qualityInterval.current = setInterval(() => {
      const metrics = simulateQualityMetrics();
      onQualityUpdate(metrics);
    }, QUALITY_POLL_INTERVAL_MS);

    // Countdown timer
    countdownInterval.current = setInterval(() => {
      const elapsed = Date.now() - (scanStartTime.current ?? Date.now());
      const remaining = Math.max(0, Math.ceil((SCAN_DURATION_MS - elapsed) / 1000));
      setTimeRemaining(remaining);

      if (remaining <= 0) {
        stopScan();
        setIsScanning(false);

        const rppg = simulateRppgProcessing();
        const finalQuality = simulateQualityMetrics();

        onComplete({
          ...rppg,
          quality: finalQuality,
          quality_score:
            finalQuality.lighting_score * 0.3 +
            finalQuality.motion_score * 0.3 +
            finalQuality.face_confidence * 0.3 +
            Math.min(finalQuality.audio_snr_db / 40, 1.0) * 0.1,
        });
      }
    }, 200);
  }, [onComplete, onQualityUpdate, stopScan]);

  useEffect(() => {
    return () => stopScan();
  }, [stopScan]);

  const progressPct = ((SCAN_DURATION_MS / 1000 - timeRemaining) / (SCAN_DURATION_MS / 1000)) * 100;

  return (
    <View style={styles.container} testID="camera-capture">
      {/* Camera preview placeholder — in real app, use expo-camera CameraView */}
      <View style={styles.cameraPreview} testID="camera-preview">
        <View style={styles.faceGuide} testID="face-guide" />
        {isScanning && (
          <View style={styles.scanningOverlay}>
            <Text style={styles.scanningText}>Scanning…</Text>
          </View>
        )}
      </View>

      {/* Progress bar */}
      <View style={styles.progressBar}>
        <View style={[styles.progressFill, { width: `${progressPct}%` as `${number}%` }]} />
      </View>

      <View style={styles.infoRow}>
        <Text style={styles.timerText} testID="timer">
          {timeRemaining}s
        </Text>
        <Text style={styles.instructionText}>
          {isScanning ? 'Keep your face steady and lit' : 'Position your face in the oval above'}
        </Text>
      </View>

      <View style={styles.buttonRow}>
        {!isScanning ? (
          <TouchableOpacity style={styles.startButton} onPress={startScan} testID="start-scan">
            <Text style={styles.startButtonText}>Start 30s Scan</Text>
          </TouchableOpacity>
        ) : (
          <TouchableOpacity style={styles.cancelButton} onPress={onCancel} testID="cancel-scan">
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

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f1a',
    alignItems: 'center',
  },
  cameraPreview: {
    width: '100%',
    height: 400,
    backgroundColor: '#1a1a2e',
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
  scanningOverlay: {
    position: 'absolute',
    bottom: 16,
    backgroundColor: 'rgba(79, 70, 229, 0.8)',
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 6,
  },
  scanningText: {
    color: '#ffffff',
    fontSize: 14,
    fontWeight: '600',
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
  disclaimer: {
    fontSize: 12,
    color: '#666688',
    textAlign: 'center',
    marginTop: 16,
    marginHorizontal: 24,
    lineHeight: 18,
  },
});
