/**
 * Tests for pranascanApi consent/deletion functions.
 *
 * NOTE: jest.mock is hoisted. We get the mock references by importing the module
 * AFTER jest.mock declarations — this ensures pranascanApi.ts and this test file
 * share the same mocked module instances.
 */

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
}));

// Use a manual jest.mock factory for axios so we control post and isAxiosError.
// Both this test file and pranascanApi.ts will get the same mock object
// because jest module registry is shared within a test file.
jest.mock('axios', () => {
  const post = jest.fn();
  const isAxiosError = jest.fn().mockImplementation((e: any) => e?.isAxiosError === true);
  return {
    __esModule: true,
    default: { post, isAxiosError },
    post,
    isAxiosError,
  };
});

// Import AFTER jest.mock so both this file and pranascanApi.ts get the same instance
import axios from 'axios';
import { revokeConsent, requestDataDeletion } from '../pranascanApi';
import * as SecureStore from 'expo-secure-store';

const mockPost = axios.post as jest.Mock;
const mockGetItemAsync = SecureStore.getItemAsync as jest.Mock;

describe('pranascanApi', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetItemAsync.mockResolvedValue(null); // Default: no token
  });

  describe('revokeConsent', () => {
    it('should successfully revoke consent with authentication', async () => {
      const testToken = 'test-jwt-token';
      mockGetItemAsync.mockResolvedValue(testToken);
      mockPost.mockResolvedValue({ data: { message: 'Consent revoked successfully.' } });

      const result = await revokeConsent();

      expect(result).toEqual({ message: 'Consent revoked successfully.' });
      expect(mockGetItemAsync).toHaveBeenCalledWith('userToken');
      expect(mockPost).toHaveBeenCalledWith(
        expect.stringContaining('/consent/revoke'),
        {},
        { headers: { Authorization: `Bearer ${testToken}` } },
      );
    });

    it('should successfully revoke consent without authentication if no token is present', async () => {
      mockPost.mockResolvedValue({ data: { message: 'Consent revoked successfully.' } });

      const result = await revokeConsent();

      expect(result).toEqual({ message: 'Consent revoked successfully.' });
      expect(mockPost).toHaveBeenCalledWith(
        expect.stringContaining('/consent/revoke'),
        {},
        { headers: {} },
      );
    });

    it('should throw an error if consent revocation fails', async () => {
      const axiosError = {
        isAxiosError: true,
        response: { data: { message: 'Consent revocation failed due to server error.' } },
      };
      mockPost.mockRejectedValue(axiosError);

      await expect(revokeConsent()).rejects.toThrow('Consent revocation failed due to server error.');
    });

    it('should throw a generic error for network issues', async () => {
      mockPost.mockRejectedValue(new Error('Network Error'));

      await expect(revokeConsent()).rejects.toThrow('An unexpected error occurred during consent revocation.');
    });
  });

  describe('requestDataDeletion', () => {
    it('should successfully request data deletion with authentication', async () => {
      const testToken = 'test-jwt-token-2';
      mockGetItemAsync.mockResolvedValue(testToken);
      mockPost.mockResolvedValue({ data: { message: 'Data deletion request submitted successfully.' } });

      const result = await requestDataDeletion();

      expect(result).toEqual({ message: 'Data deletion request submitted successfully.' });
      expect(mockPost).toHaveBeenCalledWith(
        expect.stringContaining('/consent/deletion-request'),
        {},
        { headers: { Authorization: `Bearer ${testToken}` } },
      );
    });

    it('should successfully request data deletion without authentication if no token is present', async () => {
      mockPost.mockResolvedValue({ data: { message: 'Data deletion request submitted successfully.' } });

      const result = await requestDataDeletion();

      expect(result).toEqual({ message: 'Data deletion request submitted successfully.' });
      expect(mockPost).toHaveBeenCalledWith(
        expect.stringContaining('/consent/deletion-request'),
        {},
        { headers: {} },
      );
    });

    it('should throw an error if data deletion request fails', async () => {
      const axiosError = {
        isAxiosError: true,
        response: { data: { message: 'Data deletion request failed due to server error.' } },
      };
      mockPost.mockRejectedValue(axiosError);

      await expect(requestDataDeletion()).rejects.toThrow('Data deletion request failed due to server error.');
    });

    it('should throw a generic error for network issues', async () => {
      mockPost.mockRejectedValue(new Error('Network Error'));

      await expect(requestDataDeletion()).rejects.toThrow('An unexpected error occurred during data deletion request.');
    });
  });
});
