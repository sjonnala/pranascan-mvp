/**
 * useConsent hook — manages consent state with AsyncStorage persistence.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { useCallback, useEffect, useState } from 'react';
import { getConsentStatus, grantConsent } from '../api/client';
import { ConsentStatus } from '../types';

const CONSENT_KEY = '@pranascan:consent_status';

export interface UseConsentReturn {
  consentStatus: ConsentStatus | null;
  isLoading: boolean;
  error: string | null;
  grantUserConsent: () => Promise<void>;
  hasActiveConsent: boolean;
}

export function useConsent(enabled = true): UseConsentReturn {
  const [consentStatus, setConsentStatus] = useState<ConsentStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refreshConsentStatus = useCallback(async () => {
    try {
      const status = await getConsentStatus();
      setConsentStatus(status);
      await AsyncStorage.setItem(CONSENT_KEY, JSON.stringify(status));
      setError(null);
    } catch {
      const cached = await AsyncStorage.getItem(CONSENT_KEY);
      if (cached) {
        setConsentStatus(JSON.parse(cached) as ConsentStatus);
      } else {
        throw new Error('Consent status unavailable.');
      }
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      setConsentStatus(null);
      setError(null);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    (async () => {
      try {
        await refreshConsentStatus();
      } catch {
        setError('Failed to initialise consent state');
      } finally {
        setIsLoading(false);
      }
    })();
  }, [enabled, refreshConsentStatus]);

  const grantUserConsent = useCallback(async () => {
    if (!enabled) {
      throw new Error('Cannot grant consent before the user is authenticated.');
    }

    setIsLoading(true);
    setError(null);
    try {
      await grantConsent();
      await refreshConsentStatus();
    } catch (error) {
      setError('Could not save your consent. Please check your connection and try again.');
      throw error;
    } finally {
      setIsLoading(false);
    }
  }, [enabled, refreshConsentStatus]);

  return {
    consentStatus,
    isLoading,
    error,
    grantUserConsent,
    hasActiveConsent: consentStatus?.has_active_consent ?? false,
  };
}
