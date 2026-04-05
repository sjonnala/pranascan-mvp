import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

import * as apiClient from '../src/api/client';
import { ResultsScreen } from '../src/screens/ResultsScreen';

jest.mock('../src/api/client', () => ({
  getScanSession: jest.fn(),
  getFeedbackForSession: jest.fn(),
  submitScanFeedback: jest.fn(),
}));

const getScanSession = apiClient.getScanSession as jest.Mock;
const getFeedbackForSession = apiClient.getFeedbackForSession as jest.Mock;
const submitScanFeedback = apiClient.submitScanFeedback as jest.Mock;

const resultPayload = {
  id: 'result-1',
  session_id: 'session-1',
  user_id: 'user-123',
  hr_bpm: 72,
  hrv_ms: 45,
  respiratory_rate: 16,
  voice_jitter_pct: 0.4,
  voice_shimmer_pct: 1.7,
  quality_score: 0.92,
  flags: [],
  trend_alert: null,
  created_at: '2026-03-11T00:00:00Z',
};

describe('ResultsScreen feedback instrumentation', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    getScanSession.mockResolvedValue({
      session: {
        id: 'session-1',
        user_id: 'user-123',
        status: 'completed',
        device_model: null,
        app_version: null,
        created_at: '2026-03-11T00:00:00Z',
        completed_at: '2026-03-11T00:00:30Z',
      },
      result: resultPayload,
    });
  });

  it('renders the feedback prompt and submits a response', async () => {
    getFeedbackForSession.mockResolvedValue(null);
    submitScanFeedback.mockResolvedValue({
      id: 'feedback-1',
      session_id: 'session-1',
      user_id: 'user-123',
      useful_response: 'needs_work',
      nps_score: 7,
      comment: 'Voice step felt long.',
      created_at: '2026-03-11T00:02:00Z',
    });

    const { getByTestId, findByTestId, queryByTestId } = render(
      <ResultsScreen sessionId="session-1" onScanAgain={jest.fn()} />
    );

    expect(await findByTestId('feedback-card', {}, { timeout: 5000 })).toBeTruthy();

    fireEvent.press(getByTestId('feedback-needs-work'));
    fireEvent.press(getByTestId('feedback-nps-7'));
    fireEvent.changeText(getByTestId('feedback-comment-input'), 'Voice step felt long.');
    fireEvent.press(getByTestId('feedback-submit'));

    await waitFor(
      () => {
        expect(submitScanFeedback).toHaveBeenCalledWith({
          session_id: 'session-1',
          useful_response: 'needs_work',
          nps_score: 7,
          comment: 'Voice step felt long.',
        });
      },
      { timeout: 5000 },
    );

    await waitFor(() => expect(queryByTestId('feedback-card')).toBeNull(), { timeout: 5000 });
    expect(await findByTestId('feedback-thanks', {}, { timeout: 5000 })).toBeTruthy();
  }, 15000);

  it('shows saved feedback when feedback already exists for the session', async () => {
    getFeedbackForSession.mockResolvedValue({
      id: 'feedback-1',
      session_id: 'session-1',
      user_id: 'user-123',
      useful_response: 'useful',
      nps_score: 9,
      comment: 'Fast and easy.',
      created_at: '2026-03-11T00:02:00Z',
    });

    const { findByTestId, queryByTestId } = render(
      <ResultsScreen sessionId="session-1" onScanAgain={jest.fn()} />
    );

    expect(await findByTestId('feedback-thanks')).toBeTruthy();
    expect(queryByTestId('feedback-card')).toBeNull();
    expect(submitScanFeedback).not.toHaveBeenCalled();
  });
});
