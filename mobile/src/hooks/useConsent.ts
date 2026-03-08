/**
 * useConsent hook — manages consent state with AsyncStorage persistence.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { useCallback, useEffect, useState } from 'react';
import { grantConsent, getConsentStatus } from '../api/client';
import { ConsentStatus } from '../types';

const CONSENT_KEY = '@pranascan:consent_status';
const USER_ID_KEY = '@pranascan:user_id';

function generateUserId(): string {
  // Generate a pseudonymous UUID v4 client-side
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export interface UseConsentReturn {
  userId: string | null;
  consentStatus: ConsentStatus | null;
  isLoading: boolean;
  error: string | null;
  grantUserConsent: () => Promise<void>;
  hasActiveConsent: boolean;
}

export function useConsent(): UseConsentReturn {
  const [userId, setUserId] = useState<string | null>(null);
  const [consentStatus, setConsentStatus] = useState<ConsentStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load or generate user ID on mount
  useEffect(() => {
    (async () => {
      try {
        let id = await AsyncStorage.getItem(USER_ID_KEY);
        if (!id) {
          id = generateUserId();
          await AsyncStorage.setItem(USER_ID_KEY, id);
        }
        setUserId(id);

        // Try to fetch latest consent status from server
        try {
          const status = await getConsentStatus(id);
          setConsentStatus(status);
          await AsyncStorage.setItem(CONSENT_KEY, JSON.stringify(status));
        } catch {
          // Fall back to cached status if offline
          const cached = await AsyncStorage.getItem(CONSENT_KEY);
          if (cached) {
            setConsentStatus(JSON.parse(cached) as ConsentStatus);
          }
        }
      } catch (e) {
        setError('Failed to initialise consent state');
      } finally {
        setIsLoading(false);
      }
    })();
  }, []);

  const grantUserConsent = useCallback(async () => {
    if (!userId) return;
    setIsLoading(true);
    setError(null);
    try {
      await grantConsent(userId);
      const status = await getConsentStatus(userId);
      setConsentStatus(status);
      await AsyncStorage.setItem(CONSENT_KEY, JSON.stringify(status));
    } catch (e) {
      setError('Could not save your consent. Please check your connection and try again.');
      throw e;
    } finally {
      setIsLoading(false);
    }
  }, [userId]);

  return {
    userId,
    consentStatus,
    isLoading,
    error,
    grantUserConsent,
    hasActiveConsent: consentStatus?.has_active_consent ?? false,
  };
}
