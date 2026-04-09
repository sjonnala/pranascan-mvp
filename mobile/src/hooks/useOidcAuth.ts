import * as AuthSession from 'expo-auth-session';
import * as WebBrowser from 'expo-web-browser';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { configureCoreAccessToken, getCurrentUserProfile, setupAuthInterceptor } from '../api/client';
import {
  clearStoredCoreAuthSession,
  loadStoredCoreAuthSession,
  loadStoredCoreUserProfile,
  persistCoreAuthSession,
  toTokenResponse,
} from '../auth/coreAuthSession';
import { CoreUserProfile } from '../types';

WebBrowser.maybeCompleteAuthSession();

const OIDC_ISSUER =
  process.env.EXPO_PUBLIC_OIDC_ISSUER ?? 'http://localhost:8081/realms/pranapulse';
const OIDC_CLIENT_ID = process.env.EXPO_PUBLIC_OIDC_CLIENT_ID ?? 'pranapulse-mobile';
const OIDC_AUDIENCE = process.env.EXPO_PUBLIC_OIDC_AUDIENCE ?? 'pranapulse-core';
const OIDC_SCOPES = (
  process.env.EXPO_PUBLIC_OIDC_SCOPES ?? 'openid profile email'
)
  .split(/\s+/)
  .filter(Boolean);

const REDIRECT_URI = AuthSession.makeRedirectUri({
  scheme: 'pranascan',
  path: 'auth/callback',
});


type AuthStatus = 'loading' | 'signed_out' | 'signed_in';

export interface UseOidcAuthReturn {
  status: AuthStatus;
  user: CoreUserProfile | null;
  error: string | null;
  isAuthenticating: boolean;
  isReady: boolean;
  signIn: () => Promise<void>;
}

function buildAuthExtraParams(codeVerifier?: string): Record<string, string> | undefined {
  const extraParams: Record<string, string> = {};

  if (OIDC_AUDIENCE) {
    extraParams.audience = OIDC_AUDIENCE;
  }

  if (codeVerifier) {
    extraParams.code_verifier = codeVerifier;
  }

  return Object.keys(extraParams).length > 0 ? extraParams : undefined;
}

export function useOidcAuth(): UseOidcAuthReturn {
  const discovery = AuthSession.useAutoDiscovery(OIDC_ISSUER);
  const [status, setStatus] = useState<AuthStatus>('loading');
  const [user, setUser] = useState<CoreUserProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isAuthenticating, setIsAuthenticating] = useState(false);


  const authRequestConfig = useMemo<AuthSession.AuthRequestConfig>(
    () => ({
      clientId: OIDC_CLIENT_ID,
      redirectUri: REDIRECT_URI,
      scopes: OIDC_SCOPES,
      responseType: AuthSession.ResponseType.Code,
      usePKCE: true,
      extraParams: buildAuthExtraParams(),
    }),
    []
  );

  const [request, , promptAsync] = AuthSession.useAuthRequest(authRequestConfig, discovery);

  const clearLocalSession = useCallback(async () => {
    configureCoreAccessToken(null);
    setUser(null);
    await clearStoredCoreAuthSession();
  }, []);

  const hydrateAuthenticatedSession = useCallback(
    async (tokenResponse: AuthSession.TokenResponse, fallbackUser?: CoreUserProfile | null) => {
      configureCoreAccessToken(tokenResponse.accessToken);

      try {
        const currentUser = await getCurrentUserProfile();
        await persistCoreAuthSession(tokenResponse, currentUser);
        setUser(currentUser);
        setError(null);
        setStatus('signed_in');
        return;
      } catch (loadError) {
        if (fallbackUser) {
          await persistCoreAuthSession(tokenResponse, fallbackUser);
          setUser(fallbackUser);
          setError('Signed in, but profile refresh failed. The app will retry on your next request.');
          setStatus('signed_in');
          return;
        }

        await clearLocalSession();
        setError('Could not load your account profile from service-core.');
        setStatus('signed_out');
        throw loadError;
      }
    },
    [clearLocalSession]
  );

  const restoreSession = useCallback(async () => {
    const [storedSession, storedUser] = await Promise.all([
      loadStoredCoreAuthSession(),
      loadStoredCoreUserProfile(),
    ]);

    if (!storedSession) {
      configureCoreAccessToken(null);
      setUser(null);
      setStatus('signed_out');
      return;
    }

    let tokenResponse = toTokenResponse(storedSession);
    const tokenIsFresh = AuthSession.TokenResponse.isTokenFresh(tokenResponse, 60);

    if (!tokenIsFresh) {
      if (!tokenResponse.refreshToken || !discovery?.tokenEndpoint) {
        await clearLocalSession();
        setError('Your session expired. Sign in again.');
        setStatus('signed_out');
        return;
      }

      try {
        tokenResponse = await AuthSession.refreshAsync(
          {
            clientId: OIDC_CLIENT_ID,
            refreshToken: tokenResponse.refreshToken,
            scopes: OIDC_SCOPES,
            extraParams: buildAuthExtraParams(),
          },
          discovery
        );
      } catch {
        await clearLocalSession();
        setError('Your session expired. Sign in again.');
        setStatus('signed_out');
        return;
      }
    }

    await hydrateAuthenticatedSession(tokenResponse, storedUser);
  }, [clearLocalSession, discovery, hydrateAuthenticatedSession]);

  const handleSilentRefresh = useCallback(async () => {
    const [storedSession, storedUser] = await Promise.all([
      loadStoredCoreAuthSession(),
      loadStoredCoreUserProfile(),
    ]);

    if (!storedSession || !discovery?.tokenEndpoint) {
      await clearLocalSession();
      setStatus('signed_out');
      return null;
    }

    const tokenResponse = toTokenResponse(storedSession);
    if (!tokenResponse.refreshToken) {
      await clearLocalSession();
      setStatus('signed_out');
      return null;
    }

    try {
      const refreshedResponse = await AuthSession.refreshAsync(
        {
          clientId: OIDC_CLIENT_ID,
          refreshToken: tokenResponse.refreshToken,
          scopes: OIDC_SCOPES,
          extraParams: buildAuthExtraParams(),
        },
        discovery
      );

      configureCoreAccessToken(refreshedResponse.accessToken);
      if (storedUser) {
        await persistCoreAuthSession(refreshedResponse, storedUser);
      }
      return refreshedResponse.accessToken;
    } catch {
      await clearLocalSession();
      setStatus('signed_out');
      return null;
    }
  }, [clearLocalSession, discovery]);

  useEffect(() => {
    setupAuthInterceptor(handleSilentRefresh);
  }, [handleSilentRefresh]);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        await restoreSession();
      } catch {
        if (!cancelled) {
          setStatus('signed_out');
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [restoreSession]);

  const signIn = useCallback(async () => {
    if (!request || !discovery) {
      setError('OIDC discovery is not ready yet. Check your issuer configuration and try again.');
      return;
    }

    setIsAuthenticating(true);
    setError(null);

    try {
      const result = await promptAsync();

      if (result.type === 'dismiss' || result.type === 'cancel') {
        setStatus('signed_out');
        return;
      }

      if (result.type !== 'success' || !result.params.code || !request.codeVerifier) {
        setStatus('signed_out');
        setError('The sign-in flow did not complete successfully.');
        return;
      }

      const tokenResponse = await AuthSession.exchangeCodeAsync(
        {
          clientId: OIDC_CLIENT_ID,
          code: result.params.code,
          redirectUri: REDIRECT_URI,
          scopes: OIDC_SCOPES,
          extraParams: buildAuthExtraParams(request.codeVerifier),
        },
        discovery
      );

      await hydrateAuthenticatedSession(tokenResponse);
    } catch {
      await clearLocalSession();
      setError('Sign-in failed. Verify the OIDC issuer, client ID, and redirect URI configuration.');
      setStatus('signed_out');
    } finally {
      setIsAuthenticating(false);
    }
  }, [clearLocalSession, discovery, hydrateAuthenticatedSession, promptAsync, request]);

  return {
    status,
    user,
    error,
    isAuthenticating,
    isReady: Boolean(request && discovery),
    signIn,
  };
}
