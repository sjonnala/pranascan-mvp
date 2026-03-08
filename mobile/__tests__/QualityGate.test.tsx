/**
 * Tests for QualityGate component.
 */

import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import { QualityGate } from '../src/components/QualityGate';
import { QualityGateResult } from '../src/types';

const goodQuality: QualityGateResult = {
  passed: true,
  flags: [],
  metrics: {
    lighting_score: 0.85,
    motion_score: 0.97,
    face_confidence: 0.92,
    audio_snr_db: 25.0,
  },
  overallScore: 0.91,
};

const badQuality: QualityGateResult = {
  passed: false,
  flags: ['low_lighting', 'motion_detected'],
  metrics: {
    lighting_score: 0.2,
    motion_score: 0.7,
    face_confidence: 0.92,
    audio_snr_db: 25.0,
  },
  overallScore: 0.55,
};

describe('QualityGate', () => {
  it('renders quality indicators', () => {
    const { getByTestId } = render(<QualityGate quality={goodQuality} />);
    expect(getByTestId('quality-gate')).toBeTruthy();
    expect(getByTestId('quality-indicator-Lighting')).toBeTruthy();
    expect(getByTestId('quality-indicator-Steady')).toBeTruthy();
    expect(getByTestId('quality-indicator-Face')).toBeTruthy();
  });

  it('shows passed banner for good quality', () => {
    const { getByTestId } = render(<QualityGate quality={goodQuality} />);
    expect(getByTestId('quality-passed')).toBeTruthy();
  });

  it('shows flags for bad quality', () => {
    const { getByTestId } = render(<QualityGate quality={badQuality} />);
    expect(getByTestId('quality-flags')).toBeTruthy();
  });

  it('calls onRetry when retry button pressed', () => {
    const onRetry = jest.fn();
    const { getByTestId } = render(<QualityGate quality={badQuality} onRetry={onRetry} />);
    fireEvent.press(getByTestId('retry-button'));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('does not render retry button if no onRetry prop', () => {
    const { queryByTestId } = render(<QualityGate quality={badQuality} />);
    expect(queryByTestId('retry-button')).toBeNull();
  });
});
