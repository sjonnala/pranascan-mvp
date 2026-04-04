import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import SettingsScreen from '../SettingsScreen';
import * as pranascanApi from '../../api/pranascanApi';
import { Alert } from 'react-native';

// Mock the API functions
jest.mock('../../api/pranascanApi', () => ({
  revokeConsent: jest.fn(),
  requestDataDeletion: jest.fn(),
}));

// Mock Alert
jest.mock('react-native', () => {
  const RN = jest.requireActual('react-native');
  RN.Alert.alert = jest.fn();
  return RN;
});

const mockRevokeConsent = pranascanApi.revokeConsent as jest.Mock;
const mockRequestDataDeletion = pranascanApi.requestDataDeletion as jest.Mock;
const mockAlert = Alert.alert as jest.Mock;

describe('SettingsScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockRevokeConsent.mockResolvedValue({ message: 'Consent revoked successfully.' });
    mockRequestDataDeletion.mockResolvedValue({ message: 'Data deletion request submitted successfully.' });
  });

  it('renders correctly with both buttons', () => {
    const { getByText } = render(<SettingsScreen />);
    expect(getByText('Settings')).toBeTruthy();
    expect(getByText('Revoke Consent')).toBeTruthy();
    expect(getByText('Request Data Deletion (30-day hold)')).toBeTruthy();
  });

  describe('Revoke Consent Flow', () => {
    it('shows confirmation modal when "Revoke Consent" is pressed', () => {
      const { getByText, queryByText } = render(<SettingsScreen />);
      fireEvent.press(getByText('Revoke Consent'));
      expect(getByText('Confirm Consent Revocation')).toBeTruthy();
      expect(queryByText('Confirm Data Deletion Request')).toBeNull(); // Ensure only one modal
    });

    it('hides modal and does not call API when "Cancel" is pressed on revoke modal', () => {
      const { getByText, queryByText } = render(<SettingsScreen />);
      fireEvent.press(getByText('Revoke Consent'));
      fireEvent.press(getByText('Cancel'));
      expect(queryByText('Confirm Consent Revocation')).toBeNull(); // Modal should be gone
      expect(mockRevokeConsent).not.toHaveBeenCalled();
    });

    it('calls revokeConsent API and shows success alert when confirmed', async () => {
      const { getByText, queryByText } = render(<SettingsScreen />);
      fireEvent.press(getByText('Revoke Consent'));
      fireEvent.press(getByText('Revoke Now'));

      expect(mockRevokeConsent).toHaveBeenCalledTimes(1);
      await waitFor(() => {
        expect(queryByText('Confirm Consent Revocation')).toBeNull(); // Modal should be gone
        expect(mockAlert).toHaveBeenCalledWith('Success', 'Consent revoked successfully.');
      });
    });

    it('shows error alert if revokeConsent API fails', async () => {
      mockRevokeConsent.mockRejectedValue(new Error('API Error: Failed to revoke.'));
      const { getByText, queryByText } = render(<SettingsScreen />);
      fireEvent.press(getByText('Revoke Consent'));
      fireEvent.press(getByText('Revoke Now'));

      await waitFor(() => {
        expect(queryByText('Confirm Consent Revocation')).toBeNull();
        expect(mockAlert).toHaveBeenCalledWith('Error', 'API Error: Failed to revoke.');
      });
      expect(getByText('API Error: Failed to revoke.')).toBeTruthy(); // Error message on screen
    });

    it('shows loading indicator during revoke consent API call', async () => {
      mockRevokeConsent.mockReturnValue(new Promise(() => { })); // Never resolve
      const { getByText, queryByText } = render(<SettingsScreen />);
      fireEvent.press(getByText('Revoke Consent'));
      fireEvent.press(getByText('Revoke Now'));

      expect(queryByText('Processing...')).toBeTruthy();
      expect(getByText('Revoke Now')).toBeDisabled(); // Confirm button should be disabled
      // The button text might change to ActivityIndicator, but the button itself is disabled
    });
  });

  describe('Data Deletion Request Flow', () => {
    it('shows confirmation modal when "Request Data Deletion" is pressed', () => {
      const { getByText, queryByText } = render(<SettingsScreen />);
      fireEvent.press(getByText('Request Data Deletion (30-day hold)'));
      expect(getByText('Confirm Data Deletion Request')).toBeTruthy();
      expect(queryByText('Confirm Consent Revocation')).toBeNull(); // Ensure only one modal
    });

    it('hides modal and does not call API when "Cancel" is pressed on deletion modal', () => {
      const { getByText, queryByText } = render(<SettingsScreen />);
      fireEvent.press(getByText('Request Data Deletion (30-day hold)'));
      fireEvent.press(getByText('Cancel'));
      expect(queryByText('Confirm Data Deletion Request')).toBeNull(); // Modal should be gone
      expect(mockRequestDataDeletion).not.toHaveBeenCalled();
    });

    it('calls requestDataDeletion API and shows success alert when confirmed', async () => {
      const { getByText, queryByText } = render(<SettingsScreen />);
      fireEvent.press(getByText('Request Data Deletion (30-day hold)'));
      fireEvent.press(getByText('Request Deletion'));

      expect(mockRequestDataDeletion).toHaveBeenCalledTimes(1);
      await waitFor(() => {
        expect(queryByText('Confirm Data Deletion Request')).toBeNull(); // Modal should be gone
        expect(mockAlert).toHaveBeenCalledWith('Success', 'Data deletion request submitted. You have 30 days to cancel.');
      });
    });

    it('shows error alert if requestDataDeletion API fails', async () => {
      mockRequestDataDeletion.mockRejectedValue(new Error('API Error: Failed to request deletion.'));
      const { getByText, queryByText } = render(<SettingsScreen />);
      fireEvent.press(getByText('Request Data Deletion (30-day hold)'));
      fireEvent.press(getByText('Request Deletion'));

      await waitFor(() => {
        expect(queryByText('Confirm Data Deletion Request')).toBeNull();
        expect(mockAlert).toHaveBeenCalledWith('Error', 'API Error: Failed to request deletion.');
      });
      expect(getByText('API Error: Failed to request deletion.')).toBeTruthy(); // Error message on screen
    });

    it('shows loading indicator during data deletion request API call', async () => {
      mockRequestDataDeletion.mockReturnValue(new Promise(() => { })); // Never resolve
      const { getByText, queryByText } = render(<SettingsScreen />);
      fireEvent.press(getByText('Request Data Deletion (30-day hold)'));
      fireEvent.press(getByText('Request Deletion'));

      expect(queryByText('Processing...')).toBeTruthy();
      expect(getByText('Request Deletion')).toBeDisabled(); // Confirm button should be disabled
    });
  });
});
