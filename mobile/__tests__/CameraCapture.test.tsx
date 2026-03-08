/**
 * Tests for CameraCapture component.
 *
 * expo-camera is mocked so tests run in Node/Jest without native binaries.
 * The mock exposes:
 *   - CameraView: renders a plain View, ref has takePictureAsync
 *   - useCameraPermissions: configurable per-test
 */

import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

// ─── expo-camera mock ─────────────────────────────────────────────────────────

const mockTakePictureAsync = jest.fn();

jest.mock('expo-camera', () => {
  const ReactInMock = require('react');
  const { View } = require('react-native');

  const CameraView = ReactInMock.forwardRef(
    (
      {
        children,
        testID,
        style,
      }: { children?: React.ReactNode; testID?: string; style?: object },
      ref: React.Ref<unknown>,
    ) => {
      ReactInMock.useImperativeHandle(ref, () => ({
        takePictureAsync: mockTakePictureAsync,
      }));
      return ReactInMock.createElement(View, { testID, style }, children);
    },
  );
  CameraView.displayName = 'CameraView';

  return {
    CameraView,
    useCameraPermissions: jest.fn(() => [
      { granted: true, status: 'granted' },
      jest.fn().mockResolvedValue({ granted: true, status: 'granted' }),
    ]),
  };
});

// ─── Import after mock ────────────────────────────────────────────────────────

import { useCameraPermissions } from 'expo-camera';
import { CameraCapture } from '../src/components/CameraCapture';
import { QualityMetrics } from '../src/types';

const mockUseCameraPermissions = useCameraPermissions as jest.MockedFunction<
  typeof useCameraPermissions
>;

// ─── Helpers ──────────────────────────────────────────────────────────────────

const MOCK_B64 = 'A'.repeat(6_000); // simulates a well-lit JPEG frame

function makeGrantedPermission() {
  const requestFn = jest.fn().mockResolvedValue({ granted: true, status: 'granted' });
  mockUseCameraPermissions.mockReturnValue([
    { granted: true, status: 'granted', expires: 'never', canAskAgain: true },
    requestFn,
    requestFn,
  ] as unknown as ReturnType<typeof useCameraPermissions>);
  return requestFn;
}

function makeDeniedPermission() {
  const requestFn = jest.fn().mockResolvedValue({ granted: false, status: 'denied' });
  mockUseCameraPermissions.mockReturnValue([
    { granted: false, status: 'denied', expires: 'never', canAskAgain: true },
    requestFn,
    requestFn,
  ] as unknown as ReturnType<typeof useCameraPermissions>);
  return requestFn;
}

function makeUndeterminedPermission() {
  const requestFn = jest.fn().mockResolvedValue({ granted: false, status: 'undetermined' });
  mockUseCameraPermissions.mockReturnValue([
    null,
    requestFn,
    requestFn,
  ] as unknown as ReturnType<typeof useCameraPermissions>);
  return requestFn;
}

const noop = () => {};

// ─── Tests ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  jest.clearAllMocks();
  mockTakePictureAsync.mockResolvedValue({ base64: MOCK_B64, uri: 'mock://frame.jpg' });
  makeGrantedPermission();
});

// ── Permission states ────────────────────────────────────────────────────────

describe('permission states', () => {
  it('renders loading state while permission is undetermined', () => {
    makeUndeterminedPermission();
    const { getByTestId } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={noop} onCancel={noop} />,
    );
    expect(getByTestId('camera-capture')).toBeTruthy();
  });

  it('renders permission denied UI when camera not granted', () => {
    makeDeniedPermission();
    const { getByTestId } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={noop} onCancel={noop} />,
    );
    expect(getByTestId('permission-message')).toBeTruthy();
    expect(getByTestId('allow-camera')).toBeTruthy();
  });

  it('calls requestPermission when Allow Camera is pressed', () => {
    const requestFn = makeDeniedPermission();
    const { getByTestId } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={noop} onCancel={noop} />,
    );
    fireEvent.press(getByTestId('allow-camera'));
    expect(requestFn).toHaveBeenCalledTimes(1);
  });

  it('calls onCancel from permission-denied screen', () => {
    makeDeniedPermission();
    const onCancel = jest.fn();
    const { getByTestId } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={noop} onCancel={onCancel} />,
    );
    fireEvent.press(getByTestId('cancel-scan'));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('renders camera view when permission granted', () => {
    makeGrantedPermission();
    const { getByTestId } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={noop} onCancel={noop} />,
    );
    expect(getByTestId('camera-view')).toBeTruthy();
    expect(getByTestId('face-guide')).toBeTruthy();
  });
});

// ── Pre-scan idle state ──────────────────────────────────────────────────────

describe('idle state (before scan starts)', () => {
  it('shows Start button and timer at 30s', () => {
    const { getByTestId } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={noop} onCancel={noop} />,
    );
    expect(getByTestId('start-scan')).toBeTruthy();
    // React Native renders {timeRemaining}s as a children array [30, "s"]
    const timerChildren = getByTestId('timer').props.children;
    const timerText = Array.isArray(timerChildren) ? timerChildren.join('') : String(timerChildren);
    expect(timerText).toBe('30s');
  });

  it('shows progress bar', () => {
    const { getByTestId } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={noop} onCancel={noop} />,
    );
    expect(getByTestId('progress-bar')).toBeTruthy();
  });

  it('does not show scanning indicator before scan starts', () => {
    const { queryByTestId } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={noop} onCancel={noop} />,
    );
    expect(queryByTestId('scanning-indicator')).toBeNull();
  });
});

// ── Scan start ───────────────────────────────────────────────────────────────

describe('scan start', () => {
  it('shows Cancel button after pressing Start', async () => {
    const { getByTestId } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={noop} onCancel={noop} />,
    );
    fireEvent.press(getByTestId('start-scan'));
    await waitFor(() => expect(getByTestId('cancel-scan')).toBeTruthy());
  });

  it('shows scanning indicator after start', async () => {
    const { getByTestId } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={noop} onCancel={noop} />,
    );
    fireEvent.press(getByTestId('start-scan'));
    await waitFor(() => expect(getByTestId('scanning-indicator')).toBeTruthy());
  });
});

// ── Cancel ───────────────────────────────────────────────────────────────────

describe('cancel', () => {
  it('calls onCancel when Cancel pressed during scan', async () => {
    const onCancel = jest.fn();
    const { getByTestId } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={noop} onCancel={onCancel} />,
    );
    fireEvent.press(getByTestId('start-scan'));
    await waitFor(() => getByTestId('cancel-scan'));
    fireEvent.press(getByTestId('cancel-scan'));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});

// ── Quality update ───────────────────────────────────────────────────────────

describe('quality update', () => {
  it('calls onQualityUpdate with metrics object after frame capture', async () => {
    const onQualityUpdate = jest.fn();
    const { getByTestId } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={onQualityUpdate} onCancel={noop} />,
    );
    fireEvent.press(getByTestId('start-scan'));

    await waitFor(() => expect(onQualityUpdate).toHaveBeenCalled(), { timeout: 2000 });

    const [metrics]: [QualityMetrics] = onQualityUpdate.mock.calls[0];
    expect(typeof metrics.lighting_score).toBe('number');
    expect(typeof metrics.motion_score).toBe('number');
    expect(typeof metrics.face_confidence).toBe('number');
    expect(typeof metrics.audio_snr_db).toBe('number');
  });

  it('lighting_score is in [0, 1]', async () => {
    const onQualityUpdate = jest.fn();
    const { getByTestId } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={onQualityUpdate} onCancel={noop} />,
    );
    fireEvent.press(getByTestId('start-scan'));

    await waitFor(() => expect(onQualityUpdate).toHaveBeenCalled(), { timeout: 2000 });
    const [metrics]: [QualityMetrics] = onQualityUpdate.mock.calls[0];
    expect(metrics.lighting_score).toBeGreaterThanOrEqual(0);
    expect(metrics.lighting_score).toBeLessThanOrEqual(1);
  });
});

// ── No diagnostic language ───────────────────────────────────────────────────

describe('no diagnostic language', () => {
  it('renders no diagnostic text in idle state', () => {
    const { toJSON } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={noop} onCancel={noop} />,
    );
    const tree = JSON.stringify(toJSON());
    const forbidden = ['diagnosis', 'diagnostic', 'disease', 'medical condition', 'disorder'];
    for (const word of forbidden) {
      expect(tree.toLowerCase()).not.toContain(word);
    }
  });

  it('renders no diagnostic text in denied-permission state', () => {
    makeDeniedPermission();
    const { toJSON } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={noop} onCancel={noop} />,
    );
    const tree = JSON.stringify(toJSON());
    expect(tree.toLowerCase()).not.toContain('diagnosis');
  });
});
