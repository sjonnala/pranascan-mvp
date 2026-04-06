/**
 * PranaScan API client.
 * Wraps all service-core calls with typed request/response shapes.
 */

import axios, { AxiosInstance } from 'axios';
import {
  ConsentRecord,
  ConsentStatus,
  CoreUserProfile,
  ScanHistoryPage,
  ScanFeedback,
  ScanFeedbackPayload,
  ScanResult,
  ScanResultPayload,
  ScanSession,
  ScanType,
  ScanSessionWithResult,
  SocialConnection,
  VitalityReport,
  VitalityStreak,
} from '../types';

const CORE_BASE_URL =
  process.env.EXPO_PUBLIC_CORE_API_URL ??
  process.env.EXPO_PUBLIC_API_URL ??
  'http://localhost:8080';

let coreAccessToken: string | null = null;

const coreHttp: AxiosInstance = axios.create({
  baseURL: `${CORE_BASE_URL}/api/v1`,
  timeout: 15_000,
  headers: { 'Content-Type': 'application/json' },
});

type RequestConfig = {
  headers: {
    Authorization?: string;
  };
};

function authConfig(accessToken: string | null): RequestConfig {
  return accessToken ? { headers: { Authorization: `Bearer ${accessToken}` } } : { headers: {} };
}

function requireCoreAccessToken(): string {
  if (coreAccessToken) {
    return coreAccessToken;
  }
  throw new Error('You are not authenticated. Sign in before using service-core APIs.');
}

export function configureCoreAccessToken(accessToken: string | null): void {
  coreAccessToken = accessToken?.trim() ? accessToken.trim() : null;
}

let onTokenRefresh: (() => Promise<string | null>) | null = null;
let isRefreshing = false;
let failedQueue: { resolve: (value: string | null) => void; reject: (reason?: unknown) => void }[] = [];

const processQueue = (error: Error | null, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

export function setupAuthInterceptor(refreshCallback: () => Promise<string | null>) {
  onTokenRefresh = refreshCallback;
}

coreHttp.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && originalRequest && !originalRequest._retry) {
      if (isRefreshing) {
        return new Promise<string | null>((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        })
          .then((token) => {
            if (token) {
              originalRequest.headers.Authorization = `Bearer ${token}`;
            }
            return coreHttp(originalRequest);
          })
          .catch((err) => Promise.reject(err));
      }

      originalRequest._retry = true;
      isRefreshing = true;

      if (!onTokenRefresh) {
        isRefreshing = false;
        return Promise.reject(error);
      }

      try {
        const token = await onTokenRefresh();
        if (token) {
          processQueue(null, token);
          originalRequest.headers.Authorization = `Bearer ${token}`;
          return coreHttp(originalRequest);
        } else {
          processQueue(new Error('Refresh failed'));
          return Promise.reject(error);
        }
      } catch (err) {
        processQueue(err as Error);
        return Promise.reject(err);
      } finally {
        isRefreshing = false;
      }
    }
    return Promise.reject(error);
  }
);

// ─── Auth ────────────────────────────────────────────────────────────────────

export async function getCurrentUserProfile(): Promise<CoreUserProfile> {
  const { data } = await coreHttp.get<CoreUserProfile>(
    '/auth/me',
    authConfig(requireCoreAccessToken())
  );
  return data;
}

// ─── Consent ─────────────────────────────────────────────────────────────────

export async function grantConsent(
  consentVersion = '1.0',
  purpose = 'wellness_screening'
): Promise<ConsentRecord> {
  const { data } = await coreHttp.post<ConsentRecord>(
    '/consent',
    {
      consent_version: consentVersion,
      purpose,
    },
    authConfig(requireCoreAccessToken())
  );
  return data;
}

export async function revokeConsent(): Promise<ConsentRecord> {
  const { data } = await coreHttp.post<ConsentRecord>(
    '/consent/revoke',
    {},
    authConfig(requireCoreAccessToken())
  );
  return data;
}

export async function requestDeletion(): Promise<ConsentRecord> {
  const { data } = await coreHttp.post<ConsentRecord>(
    '/consent/deletion-request',
    {},
    authConfig(requireCoreAccessToken())
  );
  return data;
}

export async function getConsentStatus(): Promise<ConsentStatus> {
  const { data } = await coreHttp.get<ConsentStatus>(
    '/consent/status',
    authConfig(requireCoreAccessToken())
  );
  return data;
}

// ─── Scans ────────────────────────────────────────────────────────────────────

export async function createScanSession(
  scanType: ScanType,
  deviceModel?: string,
  appVersion?: string
): Promise<ScanSession> {
  const { data } = await coreHttp.post<ScanSession>(
    '/scans/sessions',
    {
      scan_type: scanType,
      device_model: deviceModel,
      app_version: appVersion,
    },
    authConfig(requireCoreAccessToken())
  );
  return data;
}

export async function completeScanSession(
  sessionId: string,
  payload: ScanResultPayload
): Promise<ScanResult> {
  const { data } = await coreHttp.put<ScanResult>(
    `/scans/sessions/${sessionId}/complete`,
    payload,
    authConfig(requireCoreAccessToken())
  );
  return data;
}

export async function getScanSession(sessionId: string): Promise<ScanSessionWithResult> {
  const { data } = await coreHttp.get<ScanSessionWithResult>(
    `/scans/sessions/${sessionId}`,
    authConfig(requireCoreAccessToken())
  );
  return data;
}

export async function getScanHistory(
  page = 1,
  pageSize = 20
): Promise<ScanHistoryPage> {
  const { data } = await coreHttp.get<ScanHistoryPage>('/scans/sessions/history', {
    ...authConfig(requireCoreAccessToken()),
    params: {
      page,
      page_size: pageSize,
    },
  });
  return data;
}

export async function getCurrentVitalityStreak(): Promise<VitalityStreak> {
  const { data } = await coreHttp.get<VitalityStreak>(
    '/business/vitality-streak',
    authConfig(requireCoreAccessToken())
  );
  return data;
}

export async function getLatestVitalityReport(): Promise<VitalityReport | null> {
  try {
    const { data } = await coreHttp.get<VitalityReport>(
      '/reports/latest',
      authConfig(requireCoreAccessToken())
    );
    return data;
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      return null;
    }
    throw error;
  }
}

export async function listSocialConnections(): Promise<SocialConnection[]> {
  const { data } = await coreHttp.get<SocialConnection[]>(
    '/social/connections',
    authConfig(requireCoreAccessToken())
  );
  return data;
}

// ─── Feedback ────────────────────────────────────────────────────────────────

export async function submitScanFeedback(payload: ScanFeedbackPayload): Promise<ScanFeedback> {
  const { data } = await coreHttp.post<ScanFeedback>(
    '/feedback',
    payload,
    authConfig(requireCoreAccessToken())
  );
  return data;
}

export async function getFeedbackForSession(sessionId: string): Promise<ScanFeedback | null> {
  try {
    const { data } = await coreHttp.get<ScanFeedback>(
      `/feedback/sessions/${sessionId}`,
      authConfig(requireCoreAccessToken())
    );
    return data;
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      return null;
    }
    throw error;
  }
}
