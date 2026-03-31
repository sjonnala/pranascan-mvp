/**
 * useScan hook — orchestrates the full scan flow.
 *
 * Sequence:
 *   1. createScanSession (backend)
 *   2. Run camera + voice capture (on-device)
 *   3. completeScanSession (backend) — submits metrics only, no raw media
 *   4. Returns wellness indicator result
 */

import { useCallback, useState } from 'react';
import { createScanSession, completeScanSession, getScanSession } from '../api/client';
import { ScanResult, ScanResultPayload, ScanSessionWithResult } from '../types';

interface ScanErrorDetail {
  message?: string;
  rejection_reason?: string;
}

export type ScanPhase =
  | 'idle'
  | 'creating_session'
  | 'camera'
  | 'voice'
  | 'submitting'
  | 'complete'
  | 'error';

export interface UseScanReturn {
  phase: ScanPhase;
  sessionId: string | null;
  result: ScanResult | null;
  error: string | null;
  startScan: (userId: string) => Promise<string>;
  submitResults: (payload: ScanResultPayload) => Promise<ScanResult>;
  fetchResult: (sessionId: string) => Promise<ScanSessionWithResult>;
  setPhase: (phase: ScanPhase) => void;
  reset: () => void;
}

export function useScan(): UseScanReturn {
  const [phase, setPhase] = useState<ScanPhase>('idle');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const startScan = useCallback(async (userId: string): Promise<string> => {
    setPhase('creating_session');
    setError(null);
    try {
      const session = await createScanSession(userId);
      setSessionId(session.id);
      setPhase('camera');
      return session.id;
    } catch (e) {
      const msg = 'Could not start scan session. Please check your connection.';
      setError(msg);
      setPhase('error');
      throw new Error(msg);
    }
  }, []);

  const submitResults = useCallback(
    async (payload: ScanResultPayload): Promise<ScanResult> => {
      if (!sessionId) throw new Error('No active session');
      setPhase('submitting');
      setError(null);
      try {
        const scanResult = await completeScanSession(sessionId, payload);
        setResult(scanResult);
        setPhase('complete');
        return scanResult;
      } catch (e: unknown) {
        const axiosErr = e as { response?: { data?: { detail?: string | ScanErrorDetail } } };
        const detail = axiosErr?.response?.data?.detail;
        const msg =
          typeof detail === 'object' && detail?.rejection_reason
            ? detail.rejection_reason
            : typeof detail === 'object' && detail?.message
              ? detail.message
              : typeof detail === 'string'
                ? detail
                : 'Scan could not be processed. Please ensure good lighting and minimal movement.';
        setError(msg);
        setPhase('error');
        throw new Error(msg);
      }
    },
    [sessionId]
  );

  const fetchResult = useCallback(async (sid: string): Promise<ScanSessionWithResult> => {
    return getScanSession(sid);
  }, []);

  const reset = useCallback(() => {
    setPhase('idle');
    setSessionId(null);
    setResult(null);
    setError(null);
  }, []);

  return {
    phase,
    sessionId,
    result,
    error,
    startScan,
    submitResults,
    fetchResult,
    setPhase,
    reset,
  };
}
