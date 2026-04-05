/**
 * Tests for ConsentScreen component.
 */

import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import { ConsentScreen } from '../src/screens/ConsentScreen';

// Mock the useConsent hook directly — avoids async network calls in unit tests
jest.mock('../src/hooks/useConsent', () => ({
  useConsent: jest.fn(),
}));

import { useConsent } from '../src/hooks/useConsent';
const mockUseConsent = useConsent as jest.MockedFunction<typeof useConsent>;

const baseConsentState = {
  consentStatus: null,
  isLoading: false,
  error: null,
  grantUserConsent: jest.fn().mockResolvedValue(undefined),
  hasActiveConsent: false,
};

describe('ConsentScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseConsent.mockReturnValue(baseConsentState);
  });

  it('renders consent screen', () => {
    const { getByTestId } = render(<ConsentScreen onConsentGranted={jest.fn()} />);
    expect(getByTestId('consent-screen')).toBeTruthy();
  });

  it('agree button is disabled when checkbox is not checked', () => {
    const { getByTestId } = render(<ConsentScreen onConsentGranted={jest.fn()} />);
    const agreeButton = getByTestId('consent-agree-button');
    expect(agreeButton.props.accessibilityState?.disabled).toBeTruthy();
  });

  it('enables agree button after checking consent box', () => {
    const { getByTestId } = render(<ConsentScreen onConsentGranted={jest.fn()} />);
    fireEvent.press(getByTestId('consent-checkbox'));
    const agreeButton = getByTestId('consent-agree-button');
    expect(agreeButton.props.accessibilityState?.disabled).toBeFalsy();
  });

  it('calls onConsentGranted after agreeing', async () => {
    const onGranted = jest.fn();
    const { getByTestId } = render(<ConsentScreen onConsentGranted={onGranted} />);

    fireEvent.press(getByTestId('consent-checkbox'));
    fireEvent.press(getByTestId('consent-agree-button'));

    await waitFor(() => {
      expect(baseConsentState.grantUserConsent).toHaveBeenCalledTimes(1);
    });
    expect(onGranted).toHaveBeenCalledTimes(1);
  });

  it('auto-advances when user already has active consent', () => {
    const onGranted = jest.fn();
    mockUseConsent.mockReturnValue({
      ...baseConsentState,
      hasActiveConsent: true,
    });
    render(<ConsentScreen onConsentGranted={onGranted} />);
    expect(onGranted).toHaveBeenCalledTimes(1);
  });

  it('shows loading indicator while initialising', () => {
    mockUseConsent.mockReturnValue({
      ...baseConsentState,
      isLoading: true,
    });
    const { getByTestId } = render(<ConsentScreen onConsentGranted={jest.fn()} />);
    expect(getByTestId('consent-loading')).toBeTruthy();
  });
});
