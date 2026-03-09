/**
 * Tests for VoiceCapture component.
 */

import React from 'react';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';

const mockRequestPermission = jest.fn();
const mockSetAudioModeAsync = jest.fn();
const mockUsePermissions = jest.fn();
const mockCreateRecording = jest.fn();

let mockPermissionState: { granted: boolean; status: string } | null = {
  granted: true,
  status: 'granted',
};
let mockPlaybackShouldFail = false;
let mockPlaybackFrames: number[][] = [];
const mockRecordingInstances: MockRecording[] = [];

class MockSound {
  private onAudioSampleReceived:
    | ((sample: { channels: Array<{ frames: number[] }>; timestamp: number }) => void)
    | null = null;

  private onPlaybackStatusUpdate:
    | ((status: { isLoaded: boolean; didJustFinish?: boolean }) => void)
    | null = null;

  setOnAudioSampleReceived = jest.fn((callback) => {
    this.onAudioSampleReceived = callback;
  });

  setOnPlaybackStatusUpdate = jest.fn((callback) => {
    this.onPlaybackStatusUpdate = callback;
  });

  setRateAsync = jest.fn().mockResolvedValue(undefined);

  replayAsync = jest.fn(async () => {
    if (mockPlaybackShouldFail) {
      throw new Error('sample extraction unavailable');
    }

    mockPlaybackFrames.forEach((frames, index) => {
      this.onAudioSampleReceived?.({
        channels: [{ frames }],
        timestamp: index * 0.1,
      });
    });
    this.onPlaybackStatusUpdate?.({ isLoaded: true, didJustFinish: true });
    return { isLoaded: true, didJustFinish: true };
  });

  unloadAsync = jest.fn().mockResolvedValue({ isLoaded: false });
}

class MockRecording {
  private statusCallback:
    | ((status: {
        canRecord: boolean;
        isRecording: boolean;
        isDoneRecording: boolean;
        durationMillis: number;
        metering?: number;
      }) => void)
    | null = null;

  setOnRecordingStatusUpdate = jest.fn((callback) => {
    this.statusCallback = callback;
  });

  setProgressUpdateInterval = jest.fn();

  prepareToRecordAsync = jest.fn().mockResolvedValue({
    canRecord: true,
    isRecording: false,
    isDoneRecording: false,
    durationMillis: 0,
  });

  startAsync = jest.fn().mockResolvedValue({
    canRecord: true,
    isRecording: true,
    isDoneRecording: false,
    durationMillis: 0,
  });

  stopAndUnloadAsync = jest.fn().mockResolvedValue({
    canRecord: false,
    isRecording: false,
    isDoneRecording: true,
    durationMillis: 5_000,
  });

  createNewLoadedSoundAsync = jest.fn().mockResolvedValue({
    sound: new MockSound(),
    status: { isLoaded: true },
  });

  emitMetering(db: number) {
    this.statusCallback?.({
      canRecord: true,
      isRecording: true,
      isDoneRecording: false,
      durationMillis: 1_000,
      metering: db,
    });
  }
}

jest.mock('expo-av', () => ({
  Audio: {
    usePermissions: (...args: unknown[]) => mockUsePermissions(...args),
    setAudioModeAsync: (...args: unknown[]) => mockSetAudioModeAsync(...args),
    Recording: function MockExpoRecording() {
      return mockCreateRecording();
    },
    AndroidOutputFormat: { MPEG_4: 2 },
    AndroidAudioEncoder: { AAC: 3 },
    IOSOutputFormat: { MPEG4AAC: 'aac ' },
    IOSAudioQuality: { MAX: 127 },
  },
}));

import { TARGET_AUDIO_SAMPLE_COUNT } from '../src/utils/voiceAnalyzer';
import { VoiceCapture } from '../src/components/VoiceCapture';

describe('VoiceCapture', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    mockPermissionState = { granted: true, status: 'granted' };
    mockPlaybackShouldFail = false;
    mockPlaybackFrames = [
      Array(1_000).fill(0.001),
      Array(2_000).fill(0).map((_, index) => Math.sin(index / 8) * 0.4),
      Array(1_000).fill(0.001),
    ];
    mockRecordingInstances.length = 0;
    mockUsePermissions.mockImplementation(() => [
      mockPermissionState,
      mockRequestPermission,
      mockRequestPermission,
    ]);
    mockCreateRecording.mockImplementation(() => {
      const instance = new MockRecording();
      mockRecordingInstances.push(instance);
      return instance;
    });
    mockRequestPermission.mockResolvedValue({ granted: true, status: 'granted' });
    mockSetAudioModeAsync.mockResolvedValue(undefined);
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  it('renders permission prompt when microphone access is denied', () => {
    mockPermissionState = { granted: false, status: 'denied' };
    const { getByTestId } = render(
      <VoiceCapture onComplete={jest.fn()} onCancel={jest.fn()} />,
    );
    expect(getByTestId('mic-permission-message')).toBeTruthy();
  });

  it('requests microphone permission when Allow Microphone is pressed', () => {
    mockPermissionState = { granted: false, status: 'denied' };
    const { getByTestId } = render(
      <VoiceCapture onComplete={jest.fn()} onCancel={jest.fn()} />,
    );
    fireEvent.press(getByTestId('allow-mic'));
    expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  });

  it('captures real audio samples and returns SNR after recording completes', async () => {
    const onComplete = jest.fn();
    const { getByTestId } = render(
      <VoiceCapture onComplete={onComplete} onCancel={jest.fn()} />,
    );

    fireEvent.press(getByTestId('start-voice'));

    await waitFor(() => expect(mockRecordingInstances).toHaveLength(1));
    act(() => {
      mockRecordingInstances[0].emitMetering(-18);
      mockRecordingInstances[0].emitMetering(-12);
      jest.advanceTimersByTime(5_000);
    });

    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    const result = onComplete.mock.calls[0][0];
    // audio_samples no longer in result — on-device voice DSP runs instead
    expect(result.audio_samples).toBeUndefined();
    expect(typeof result.audio_snr_db).toBe('number');
    expect(result.passed_snr).toBe(true);
  });

  it('falls back to metering-derived samples when PCM extraction fails', async () => {
    mockPlaybackShouldFail = true;
    const onComplete = jest.fn();
    const { getByTestId } = render(
      <VoiceCapture onComplete={onComplete} onCancel={jest.fn()} />,
    );

    fireEvent.press(getByTestId('start-voice'));

    await waitFor(() => expect(mockRecordingInstances).toHaveLength(1));
    act(() => {
      mockRecordingInstances[0].emitMetering(-20);
      mockRecordingInstances[0].emitMetering(-24);
      mockRecordingInstances[0].emitMetering(-30);
      jest.advanceTimersByTime(5_000);
    });

    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    const result = onComplete.mock.calls[0][0];
    // audio_samples no longer in result — on-device voice DSP runs instead
    expect(result.audio_samples).toBeUndefined();
    expect(typeof result.audio_snr_db).toBe('number');
  });

  it('stops recording and calls onCancel when cancelled mid-capture', async () => {
    const onCancel = jest.fn();
    const { getByTestId } = render(
      <VoiceCapture onComplete={jest.fn()} onCancel={onCancel} />,
    );

    fireEvent.press(getByTestId('start-voice'));
    await waitFor(() => expect(mockRecordingInstances).toHaveLength(1));

    await act(async () => {
      fireEvent.press(getByTestId('cancel-voice'));
    });

    expect(mockRecordingInstances[0].stopAndUnloadAsync).toHaveBeenCalled();
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
