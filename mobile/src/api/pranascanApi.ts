import axios from 'axios';
import * as SecureStore from 'expo-secure-store'; // Import expo-secure-store

// DECISION: API_BASE_URL is now loaded from environment variables using process.env.EXPO_PUBLIC_API_BASE_URL.
// A fallback URL is provided for development environments where the variable might not be explicitly set.
const API_BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL || 'https://api.pranascan.com/v1';

interface ApiResponse {
  message: string;
  [key: string]: any;
}

// DECISION: Authentication headers are now implemented to securely retrieve a JWT token
// using expo-secure-store and include it in the Authorization header.
const getAuthHeaders = async () => {
  const token = await SecureStore.getItemAsync('userToken'); // Retrieve token from secure storage
  return token ? { Authorization: `Bearer ${token}` } : {};
};

export const revokeConsent = async (): Promise<ApiResponse> => {
  try {
    const response = await axios.post<ApiResponse>(`${API_BASE_URL}/consent/revoke`, {}, {
      headers: await getAuthHeaders(), // Await the async getAuthHeaders function
    });
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error) && error.response) {
      throw new Error(error.response.data.message || 'Failed to revoke consent.');
    }
    throw new Error('An unexpected error occurred during consent revocation.');
  }
};

export const requestDataDeletion = async (): Promise<ApiResponse> => {
  try {
    const response = await axios.post<ApiResponse>(`${API_BASE_URL}/consent/deletion-request`, {}, {
      headers: await getAuthHeaders(), // Await the async getAuthHeaders function
    });
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error) && error.response) {
      throw new Error(error.response.data.message || 'Failed to request data deletion.');
    }
    throw new Error('An unexpected error occurred during data deletion request.');
  }
};
