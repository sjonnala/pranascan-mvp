/**
 * Tests for CameraCapture with Vision Camera frame processing.
 */

import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

type MockRgbFrame = {
  r: number;
  g: number;
  b: number;
};

let mockPermissionGranted = true;
let mockRequestPermission = jest.fn<Promise<boolean>, []>();
let mockFrameSamples: MockRgbFrame[] = [];

function mockBuildFrameBuffer(sample: MockRgbFrame): ArrayBuffer {
  const { Platform } = require('react-native');
  const width = 120;
  const height = 120;
  const bytesPerPixel = 4;
  const bytesPerRow = width * bytesPerPixel;
  const buffer = new Uint8Array(bytesPerRow * height);
  const isBgra = Platform.OS === 'ios';

  for (let index = 0; index < buffer.length; index += bytesPerPixel) {
    if (isBgra) {
      buffer[index] = sample.b;
      buffer[index + 1] = sample.g;
      buffer[index + 2] = sample.r;
      buffer[index + 3] = 255;
    } else {
      buffer[index] = sample.r;
      buffer[index + 1] = sample.g;
      buffer[index + 2] = sample.b;
      buffer[index + 3] = 255;
    }
  }

  return buffer.buffer;
}

jest.mock('react-native-worklets-core', () => ({
  Worklets: {
    createRunOnJS: (fn: (...args: unknown[]) => unknown) => fn,
  },
}));

jest.mock('react-native-vision-camera', () => {
  const ReactInMock = require('react');
  const { act } = require('@testing-library/react-native');
  const { View } = require('react-native');

  const Camera = ({ frameProcessor, testID, style }: any) => {
    ReactInMock.useEffect(() => {
      if (!frameProcessor) {
        return undefined;
      }

      const timers = mockFrameSamples.map((sample, index) =>
        setTimeout(() => {
          act(() => {
            frameProcessor.frameProcessor({
              width: 120,
              height: 120,
              bytesPerRow: 120 * 4,
              pixelFormat: 'rgb',
              toArrayBuffer: () => mockBuildFrameBuffer(sample),
            });
          });
        }, index * 5)
      );

      return () => {
        timers.forEach(clearTimeout);
      };
    }, [frameProcessor]);

    return ReactInMock.createElement(View, { testID, style });
  };

  return {
    Camera,
    useCameraPermission: jest.fn(() => ({
      hasPermission: mockPermissionGranted,
      requestPermission: mockRequestPermission,
    })),
    useCameraDevice: jest.fn(() => ({
      id: 'front-camera',
      formats: [{ minFps: 30, maxFps: 30 }],
    })),
    useCameraFormat: jest.fn(() => ({ minFps: 30, maxFps: 30 })),
    useFrameProcessor: jest.fn((processor: (frame: unknown) => void) => ({
      frameProcessor: processor,
      type: 'readonly',
    })),
    runAtTargetFps: jest.fn((_fps: number, callback: () => void) => callback()),
  };
});

import { CameraCapture } from '../src/components/CameraCapture';
import { QualityMetrics } from '../src/types';

const noop = () => {};

function setFrameSamples(samples: MockRgbFrame[]) {
  mockFrameSamples = samples;
}

beforeEach(() => {
  jest.clearAllMocks();
  mockPermissionGranted = true;
  mockRequestPermission = jest.fn().mockResolvedValue(true);
  setFrameSamples([
    { r: 150, g: 132, b: 112 },
    { r: 148, g: 130, b: 110 },
    { r: 149, g: 131, b: 111 },
    { r: 147, g: 129, b: 109 },
    { r: 150, g: 132, b: 112 },
  ]);
});

describe('permission states', () => {
  it('renders permission UI when camera permission is not granted', () => {
    mockPermissionGranted = false;

    const { getByTestId } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={noop} onCancel={noop} />
    );

    expect(getByTestId('permission-message')).toBeTruthy();
    expect(getByTestId('allow-camera')).toBeTruthy();
  });

  it('calls requestPermission when Allow Camera is pressed', () => {
    mockPermissionGranted = false;

    const { getByTestId } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={noop} onCancel={noop} />
    );

    fireEvent.press(getByTestId('allow-camera'));
    expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  });

  it('calls onCancel from permission screen', () => {
    mockPermissionGranted = false;
    const onCancel = jest.fn();

    const { getByTestId } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={noop} onCancel={onCancel} />
    );

    fireEvent.press(getByTestId('cancel-scan'));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('renders camera view when permission is granted', () => {
    const { getByTestId } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={noop} onCancel={noop} />
    );

    expect(getByTestId('camera-view')).toBeTruthy();
    expect(getByTestId('face-guide')).toBeTruthy();
  });
});

describe('idle state', () => {
  it('shows Start button and timer at 30s', () => {
    const { getByTestId } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={noop} onCancel={noop} />
    );

    expect(getByTestId('start-scan')).toBeTruthy();
    const timerChildren = getByTestId('timer').props.children;
    const timerText = Array.isArray(timerChildren) ? timerChildren.join('') : String(timerChildren);
    expect(timerText).toBe('30s');
  });

  it('shows progress bar', () => {
    const { getByTestId } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={noop} onCancel={noop} />
    );

    expect(getByTestId('progress-bar')).toBeTruthy();
  });

  it('does not show scanning indicator before scan starts', () => {
    const { queryByTestId } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={noop} onCancel={noop} />
    );

    expect(queryByTestId('scanning-indicator')).toBeNull();
  });
});

describe('scan lifecycle', () => {
  it('shows Cancel button and scanning indicator after pressing Start', async () => {
    const { getByTestId } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={noop} onCancel={noop} />
    );

    fireEvent.press(getByTestId('start-scan'));

    await waitFor(() => expect(getByTestId('cancel-scan')).toBeTruthy());
    expect(getByTestId('scanning-indicator')).toBeTruthy();
  });

  it('calls onCancel when Cancel pressed during scan', async () => {
    const onCancel = jest.fn();
    const { getByTestId } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={noop} onCancel={onCancel} />
    );

    fireEvent.press(getByTestId('start-scan'));
    await waitFor(() => expect(getByTestId('cancel-scan')).toBeTruthy());
    fireEvent.press(getByTestId('cancel-scan'));

    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});

describe('quality updates', () => {
  it('calls onQualityUpdate with metrics derived from RGB traces', async () => {
    const onQualityUpdate = jest.fn();
    const { getByTestId } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={onQualityUpdate} onCancel={noop} />
    );

    fireEvent.press(getByTestId('start-scan'));

    await waitFor(() => expect(onQualityUpdate).toHaveBeenCalled(), { timeout: 2000 });

    const [metrics]: [QualityMetrics] = onQualityUpdate.mock.calls[0];
    expect(typeof metrics.lighting_score).toBe('number');
    expect(typeof metrics.motion_score).toBe('number');
    expect(typeof metrics.face_confidence).toBe('number');
    expect(typeof metrics.audio_snr_db).toBe('number');
  });

  it('lighting_score stays in [0, 1]', async () => {
    const onQualityUpdate = jest.fn();
    const { getByTestId } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={onQualityUpdate} onCancel={noop} />
    );

    fireEvent.press(getByTestId('start-scan'));

    await waitFor(() => expect(onQualityUpdate).toHaveBeenCalled(), { timeout: 2000 });
    const [metrics]: [QualityMetrics] = onQualityUpdate.mock.calls[0];
    expect(metrics.lighting_score).toBeGreaterThanOrEqual(0);
    expect(metrics.lighting_score).toBeLessThanOrEqual(1);
  });

  it('face_confidence is high for a stable, well-lit ROI', async () => {
    setFrameSamples([
      { r: 170, g: 150, b: 130 },
      { r: 169, g: 149, b: 129 },
      { r: 171, g: 151, b: 131 },
      { r: 170, g: 150, b: 130 },
      { r: 169, g: 149, b: 129 },
    ]);

    const onQualityUpdate = jest.fn();
    const { getByTestId } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={onQualityUpdate} onCancel={noop} />
    );

    fireEvent.press(getByTestId('start-scan'));

    await waitFor(() => expect(onQualityUpdate).toHaveBeenCalled(), { timeout: 2000 });
    const [metrics]: [QualityMetrics] = onQualityUpdate.mock.calls[0];

    expect(metrics.face_confidence).toBeGreaterThanOrEqual(0.8);
  });

  it('face_confidence falls for a dark ROI', async () => {
    setFrameSamples([
      { r: 25, g: 22, b: 18 },
      { r: 24, g: 21, b: 17 },
      { r: 25, g: 22, b: 18 },
      { r: 24, g: 21, b: 17 },
      { r: 25, g: 22, b: 18 },
    ]);

    const onQualityUpdate = jest.fn();
    const { getByTestId } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={onQualityUpdate} onCancel={noop} />
    );

    fireEvent.press(getByTestId('start-scan'));

    await waitFor(() => expect(onQualityUpdate).toHaveBeenCalled(), { timeout: 2000 });
    const [metrics]: [QualityMetrics] = onQualityUpdate.mock.calls[0];

    expect(metrics.face_confidence).toBeLessThan(0.8);
  });
});

describe('no diagnostic language', () => {
  it('renders no diagnostic text in idle state', () => {
    const { toJSON } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={noop} onCancel={noop} />
    );

    const tree = JSON.stringify(toJSON());
    const forbidden = ['diagnosis', 'diagnostic', 'disease', 'medical condition', 'disorder'];
    for (const word of forbidden) {
      expect(tree.toLowerCase()).not.toContain(word);
    }
  });

  it('renders no diagnostic text in permission state', () => {
    mockPermissionGranted = false;
    const { toJSON } = render(
      <CameraCapture onComplete={noop} onQualityUpdate={noop} onCancel={noop} />
    );

    const tree = JSON.stringify(toJSON());
    expect(tree.toLowerCase()).not.toContain('diagnosis');
  });
});
