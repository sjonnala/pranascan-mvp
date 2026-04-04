import axios from 'axios';
import MockAdapter from 'axios-mock-adapter';
import { revokeConsent, requestDataDeletion } from '../pranascanApi';
import * as SecureStore from 'expo-secure-store'; // Import SecureStore for mocking

const mock = new MockAdapter(axios);

// Mock process.env.EXPO_PUBLIC_API_BASE_URL
const MOCK_API_BASE_URL = 'https://mock-api.pranascan.com/v1';
process.env.EXPO_PUBLIC_API_BASE_URL = MOCK_API_BASE_URL;

// Mock SecureStore
jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
}));

const mockGetItemAsync = SecureStore.getItemAsync as jest.Mock;

describe('pranascanApi', () => {
  beforeEach(() => {
    mock.reset();
    mockGetItemAsync.mockResolvedValue(null); // Default: no token
  });

  describe('revokeConsent', () => {
    it('should successfully revoke consent with authentication', async () => {
      const successResponse = { message: 'Consent revoked successfully.' };
      const testToken = 'test-jwt-token';
      mockGetItemAsync.mockResolvedValue(testToken);
      mock.onPost(`${MOCK_API_BASE_URL}/consent/revoke`, {}, {
        headers: { Authorization: `Bearer ${testToken}` }
      }).reply(200, successResponse);

      const result = await revokeConsent();
      expect(result).toEqual(successResponse);
      expect(mockGetItemAsync).toHaveBeenCalledWith('userToken');
      expect(mock.history.post[0].headers?.Authorization).toBe(`Bearer ${testToken}`);
    });

    it('should successfully revoke consent without authentication if no token is present', async () => {
      const successResponse = { message: 'Consent revoked successfully.' };
      mockGetItemAsync.mockResolvedValue(null); // No token
      mock.onPost(`${MOCK_API_BASE_URL}/consent/revoke`).reply(200, successResponse);

      const result = await revokeConsent();
      expect(result).toEqual(successResponse);
      expect(mockGetItemAsync).toHaveBeenCalledWith('userToken');
      expect(mock.history.post[0].headers?.Authorization).toBeUndefined(); // No auth header
    });

    it('should throw an error if consent revocation fails', async () => {
      const errorResponse = { message: 'Consent revocation failed due to server error.' };
      mock.onPost(`${MOCK_API_BASE_URL}/consent/revoke`).reply(500, errorResponse);

      await expect(revokeConsent()).rejects.toThrow('Consent revocation failed due to server error.');
    });

    it('should throw a generic error for network issues', async () => {
      mock.onPost(`${MOCK_API_BASE_URL}/consent/revoke`).networkError();

      await expect(revokeConsent()).rejects.toThrow('An unexpected error occurred during consent revocation.');
    });
  });

  describe('requestDataDeletion', () => {
    it('should successfully request data deletion with authentication', async () => {
      const successResponse = { message: 'Data deletion request submitted successfully.' };
      const testToken = 'test-jwt-token-2';
      mockGetItemAsync.mockResolvedValue(testToken);
      mock.onPost(`${MOCK_API_BASE_URL}/consent/deletion-request`, {}, {
        headers: { Authorization: `Bearer ${testToken}` }
      }).reply(200, successResponse);

      const result = await requestDataDeletion();
      expect(result).toEqual(successResponse);
      expect(mockGetItemAsync).toHaveBeenCalledWith('userToken');
      expect(mock.history.post[0].headers?.Authorization).toBe(`Bearer ${testToken}`);
    });

    it('should successfully request data deletion without authentication if no token is present', async () => {
      const successResponse = { message: 'Data deletion request submitted successfully.' };
      mockGetItemAsync.mockResolvedValue(null); // No token
      mock.onPost(`${MOCK_API_BASE_URL}/consent/deletion-request`).reply(200, successResponse);

      const result = await requestDataDeletion();
      expect(result).toEqual(successResponse);
      expect(mockGetItemAsync).toHaveBeenCalledWith('userToken');
      expect(mock.history.post[0].headers?.Authorization).toBeUndefined(); // No auth header
    });

    it('should throw an error if data deletion request fails', async () => {
      const errorResponse = { message: 'Data deletion request failed due to server error.' };
      mock.onPost(`${MOCK_API_BASE_URL}/consent/deletion-request`).reply(500, errorResponse);

      await expect(requestDataDeletion()).rejects.toThrow('Data deletion request failed due to server error.');
    });

    it('should throw a generic error for network issues', async () => {
      mock.onPost(`${MOCK_API_BASE_URL}/consent/deletion-request`).networkError();

      await expect(requestDataDeletion()).rejects.toThrow('An unexpected error occurred during data deletion request.');
    });
  });
});
