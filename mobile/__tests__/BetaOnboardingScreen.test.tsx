import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import { BetaOnboardingScreen } from '../src/screens/BetaOnboardingScreen';

jest.mock('../src/hooks/useBetaAccess', () => ({
  useBetaAccess: jest.fn(),
}));

import { useBetaAccess } from '../src/hooks/useBetaAccess';

const mockUseBetaAccess = useBetaAccess as jest.MockedFunction<typeof useBetaAccess>;

const baseBetaState = {
  userId: 'test-user-id',
  betaStatus: {
    user_id: 'test-user-id',
    beta_onboarding_enabled: true,
    enrolled: false,
    invite_required: true,
    cohort_name: null,
    invite_code: null,
    enrolled_at: null,
  },
  isLoading: false,
  error: null,
  redeemInvite: jest.fn().mockResolvedValue({
    user_id: 'test-user-id',
    beta_onboarding_enabled: true,
    enrolled: true,
    invite_required: false,
    cohort_name: 'proactive_professionals',
    invite_code: 'CLOSED50',
    enrolled_at: '2026-03-11T00:00:00Z',
  }),
};

describe('BetaOnboardingScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseBetaAccess.mockReturnValue(baseBetaState);
  });

  it('renders the beta onboarding screen', () => {
    const { getByTestId } = render(<BetaOnboardingScreen onEnrolled={jest.fn()} />);
    expect(getByTestId('beta-screen')).toBeTruthy();
  });

  it('redeem button is disabled when invite code is blank', () => {
    const { getByTestId } = render(<BetaOnboardingScreen onEnrolled={jest.fn()} />);
    expect(getByTestId('beta-redeem-button').props.accessibilityState.disabled).toBe(true);
  });

  it('redeems the invite and continues to consent', async () => {
    const onEnrolled = jest.fn();
    const { getByTestId } = render(<BetaOnboardingScreen onEnrolled={onEnrolled} />);

    fireEvent.changeText(getByTestId('beta-invite-input'), 'closed50');
    fireEvent.press(getByTestId('beta-redeem-button'));

    await waitFor(() => {
      expect(baseBetaState.redeemInvite).toHaveBeenCalledWith('closed50');
    });
    expect(onEnrolled).toHaveBeenCalledWith('test-user-id');
  });

  it('auto-advances when the user is already enrolled', () => {
    const onEnrolled = jest.fn();
    mockUseBetaAccess.mockReturnValue({
      ...baseBetaState,
      betaStatus: {
        ...baseBetaState.betaStatus,
        enrolled: true,
        invite_required: false,
      },
    });

    render(<BetaOnboardingScreen onEnrolled={onEnrolled} />);
    expect(onEnrolled).toHaveBeenCalledWith('test-user-id');
  });

  it('auto-advances when beta gating is disabled for the deployment', () => {
    const onEnrolled = jest.fn();
    mockUseBetaAccess.mockReturnValue({
      ...baseBetaState,
      betaStatus: {
        ...baseBetaState.betaStatus,
        beta_onboarding_enabled: false,
        invite_required: false,
      },
    });

    render(<BetaOnboardingScreen onEnrolled={onEnrolled} />);
    expect(onEnrolled).toHaveBeenCalledWith('test-user-id');
  });

  it('shows loading state while checking beta access', () => {
    mockUseBetaAccess.mockReturnValue({
      ...baseBetaState,
      betaStatus: null,
      isLoading: true,
    });

    const { getByTestId } = render(<BetaOnboardingScreen onEnrolled={jest.fn()} />);
    expect(getByTestId('beta-loading')).toBeTruthy();
  });

  it('renders hook errors', () => {
    mockUseBetaAccess.mockReturnValue({
      ...baseBetaState,
      error: 'Invite code could not be redeemed. Please check the code and try again.',
    });

    const { getByTestId } = render(<BetaOnboardingScreen onEnrolled={jest.fn()} />);
    expect(getByTestId('beta-error')).toBeTruthy();
  });
});
