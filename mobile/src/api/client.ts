/**
 * PranaScan API client.
 * Wraps all backend calls with typed request/response shapes.
 */

import axios, { AxiosInstance } from 'axios';
import {
  ConsentRecord,
  ConsentStatus,
  ScanResult,
  ScanResultPayload,
  ScanSession,
  ScanSessionWithResult,
} from '../types';

// In production, pull from expo-constants or environment config
const BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000';

const http: AxiosInstance = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  timeout: 15_000, // 15s matches latency budget
  headers: { 'Content-Type': 'application/json' },
});

// ─── Consent ─────────────────────────────────────────────────────────────────

export async function grantConsent(
  userId: string,
  consentVersion = '1.0',
  purpose = 'wellness_screening'
): Promise<ConsentRecord> {
  const { data } = await http.post<ConsentRecord>('/consent', {
    user_id: userId,
    consent_version: consentVersion,
    purpose,
  });
  return data;
}

export async function revokeConsent(userId: string): Promise<ConsentRecord> {
  const { data } = await http.post<ConsentRecord>('/consent/revoke', { user_id: userId });
  return data;
}

export async function requestDeletion(userId: string): Promise<ConsentRecord> {
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

export async function getScanSession(sessionId: string): Promise<ScanSessionWithResult> {
  const { data } = await http.get<ScanSessionWithResult>(`/scans/sessions/${sessionId}`);
  return data;
}
