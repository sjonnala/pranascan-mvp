/**
 * PranaScan API client.
 * Wraps all backend calls with typed request/response shapes.
 */

import axios, { AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import {
  BetaInviteRedeemPayload,
  BetaStatus,
  ConsentRecord,
  ConsentStatus,
  ScanFeedback,
  ScanFeedbackPayload,
  ScanResult,
  ScanResultPayload,
  ScanSession,
  ScanSessionWithResult,
} from '../types';

// In production, pull from expo-constants or environment config
const BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000';

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: 'bearer';
  expires_in: number;
}

interface AuthSession {
  userId: string;
  accessToken: string;
  refreshToken: string;
}

let authSession: AuthSession | null = null;
let authBootstrapPromise: Promise<void> | null = null;

const http: AxiosInstance = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  timeout: 15_000, // 15s matches latency budget
  headers: { 'Content-Type': 'application/json' },
});

http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (authSession?.accessToken && !isAuthRoute(config.url)) {
    config.headers.set?.('Authorization', `Bearer ${authSession.accessToken}`);
    if (!config.headers.get?.('Authorization')) {
      config.headers.Authorization = `Bearer ${authSession.accessToken}`;
    }
  }
  return config;
});

function isAuthRoute(url?: string): boolean {
  return url === '/auth/token' || url === '/auth/refresh';
}

async function requestAuthSession(userId: string): Promise<AuthSession> {
  const { data } = await http.post<TokenResponse>('/auth/token', { user_id: userId });
  return {
    userId,
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
  };
}

async function ensureAuthSession(userId: string): Promise<void> {
  if (authSession?.userId === userId && authSession.accessToken) {
    return;
  }

  if (authBootstrapPromise) {
    await authBootstrapPromise;
    if (authSession?.userId === userId && authSession.accessToken) {
      return;
    }
  }

  authBootstrapPromise = (async () => {
    authSession = await requestAuthSession(userId);
  })();

  try {
    await authBootstrapPromise;
  } finally {
    authBootstrapPromise = null;
  }
}

export function resetAuthSession(): void {
  authSession = null;
  authBootstrapPromise = null;
}

// ─── Closed beta onboarding ──────────────────────────────────────────────────

export async function getBetaStatus(userId: string): Promise<BetaStatus> {
  await ensureAuthSession(userId);
  const { data } = await http.get<BetaStatus>('/beta/status');
  return data;
}

export async function redeemBetaInvite(
  userId: string,
  payload: BetaInviteRedeemPayload
): Promise<BetaStatus> {
  await ensureAuthSession(userId);
  const { data } = await http.post<BetaStatus>('/beta/redeem', payload);
  return data;
}

// ─── Consent ─────────────────────────────────────────────────────────────────

export async function grantConsent(
  userId: string,
  consentVersion = '1.0',
  purpose = 'wellness_screening'
): Promise<ConsentRecord> {
  await ensureAuthSession(userId);
  const { data } = await http.post<ConsentRecord>('/consent', {
    user_id: userId,
    consent_version: consentVersion,
    purpose,
  });
  return data;
}

export async function revokeConsent(userId: string): Promise<ConsentRecord> {
  await ensureAuthSession(userId);
  const { data } = await http.post<ConsentRecord>('/consent/revoke', { user_id: userId });
  return data;
}

export async function requestDeletion(userId: string): Promise<ConsentRecord> {
  await ensureAuthSession(userId);
  const { data } = await http.post<ConsentRecord>('/consent/deletion-request', {
    user_id: userId,
  });
  return data;
}

export async function getConsentStatus(userId: string): Promise<ConsentStatus> {
  const { data } = await http.get<ConsentStatus>('/consent/status', { params: { user_id: userId } });
  return data;
}

// ─── Scans ────────────────────────────────────────────────────────────────────

export async function createScanSession(
  userId: string,
  deviceModel?: string,
  appVersion?: string
): Promise<ScanSession> {
  await ensureAuthSession(userId);
  const { data } = await http.post<ScanSession>('/scans/sessions', {
    user_id: userId,
    device_model: deviceModel,
    app_version: appVersion,
  });
  return data;
}

export async function completeScanSession(
  sessionId: string,
  payload: ScanResultPayload
): Promise<ScanResult> {
  const { data } = await http.put<ScanResult>(
    `/scans/sessions/${sessionId}/complete`,
    payload
  );
  return data;
}

export async function getScanSession(
  sessionId: string,
  userId?: string
): Promise<ScanSessionWithResult> {
  if (userId) {
    await ensureAuthSession(userId);
  }
  const { data } = await http.get<ScanSessionWithResult>(`/scans/sessions/${sessionId}`);
  return data;
}

// ─── Feedback ────────────────────────────────────────────────────────────────

export async function submitScanFeedback(
  userId: string,
  payload: ScanFeedbackPayload
): Promise<ScanFeedback> {
  await ensureAuthSession(userId);
  const { data } = await http.post<ScanFeedback>('/feedback', payload);
  return data;
}

export async function getFeedbackForSession(
  sessionId: string,
  userId: string
): Promise<ScanFeedback | null> {
  await ensureAuthSession(userId);
  try {
    const { data } = await http.get<ScanFeedback>(`/feedback/sessions/${sessionId}`);
    return data;
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      return null;
    }
    throw error;
  }
}
