import AsyncStorage from '@react-native-async-storage/async-storage';
import { useCallback, useEffect, useState } from 'react';
import { getBetaStatus, redeemBetaInvite } from '../api/client';
import { BetaStatus } from '../types';
import { getOrCreateUserId } from '../utils/identity';

const BETA_STATUS_KEY = '@pranascan:beta_status';

export interface UseBetaAccessReturn {
  userId: string | null;
  betaStatus: BetaStatus | null;
  isLoading: boolean;
  error: string | null;
  redeemInvite: (inviteCode: string) => Promise<BetaStatus>;
}

export function useBetaAccess(): UseBetaAccessReturn {
  const [userId, setUserId] = useState<string | null>(null);
  const [betaStatus, setBetaStatus] = useState<BetaStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const id = await getOrCreateUserId();
        setUserId(id);

        try {
          const status = await getBetaStatus(id);
          setBetaStatus(status);
          await AsyncStorage.setItem(BETA_STATUS_KEY, JSON.stringify(status));
        } catch {
          const cached = await AsyncStorage.getItem(BETA_STATUS_KEY);
          if (cached) {
            setBetaStatus(JSON.parse(cached) as BetaStatus);
          } else {
            setError('Could not verify beta access. Please check your connection and try again.');
          }
        }
      } catch {
        setError('Failed to initialise beta onboarding.');
      } finally {
        setIsLoading(false);
      }
    })();
  }, []);

  const redeemInviteCode = useCallback(
    async (inviteCode: string) => {
      if (!userId) {
        throw new Error('User identity is not ready.');
      }

      setIsLoading(true);
      setError(null);

      try {
        const status = await redeemBetaInvite(userId, { invite_code: inviteCode });
        setBetaStatus(status);
        await AsyncStorage.setItem(BETA_STATUS_KEY, JSON.stringify(status));
        return status;
      } catch (err) {
        setError('Invite code could not be redeemed. Please check the code and try again.');
        throw err;
      } finally {
        setIsLoading(false);
      }
    },
    [userId]
  );

  return {
    userId,
    betaStatus,
    isLoading,
    error,
    redeemInvite: redeemInviteCode,
  };
}
