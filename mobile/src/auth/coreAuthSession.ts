import * as AuthSession from 'expo-auth-session';
import { TokenType } from 'expo-auth-session';
import * as SecureStore from 'expo-secure-store';
import { CoreUserProfile } from '../types';

const CORE_AUTH_SESSION_KEY = 'pranascan_core_auth_session';
const CORE_AUTH_USER_KEY = 'pranascan_core_auth_user';

export interface StoredCoreAuthSession {
  accessToken: string;
  tokenType?: TokenType;
  expiresIn?: number;
  refreshToken?: string;
  scope?: string;
  idToken?: string;
  issuedAt: number;
}

async function readJson<T>(key: string): Promise<T | null> {
  const raw = await SecureStore.getItemAsync(key);
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw) as T;
  } catch {
    await SecureStore.deleteItemAsync(key);
    return null;
  }
}

async function writeJson(key: string, value: unknown): Promise<void> {
  await SecureStore.setItemAsync(key, JSON.stringify(value));
}

export function toStoredCoreAuthSession(tokenResponse: AuthSession.TokenResponse): StoredCoreAuthSession {
  return {
    accessToken: tokenResponse.accessToken,
    tokenType: tokenResponse.tokenType,
    expiresIn: tokenResponse.expiresIn,
    refreshToken: tokenResponse.refreshToken,
    scope: tokenResponse.scope,
    idToken: tokenResponse.idToken,
    issuedAt: tokenResponse.issuedAt,
  };
}

export function toTokenResponse(session: StoredCoreAuthSession): AuthSession.TokenResponse {
  return new AuthSession.TokenResponse(session);
}

export async function loadStoredCoreAuthSession(): Promise<StoredCoreAuthSession | null> {
  return readJson<StoredCoreAuthSession>(CORE_AUTH_SESSION_KEY);
}

export async function loadStoredCoreUserProfile(): Promise<CoreUserProfile | null> {
  return readJson<CoreUserProfile>(CORE_AUTH_USER_KEY);
}

export async function persistCoreAuthSession(
  tokenResponse: AuthSession.TokenResponse,
  userProfile: CoreUserProfile
): Promise<void> {
  await Promise.all([
    writeJson(CORE_AUTH_SESSION_KEY, toStoredCoreAuthSession(tokenResponse)),
    writeJson(CORE_AUTH_USER_KEY, userProfile),
  ]);
}

export async function clearStoredCoreAuthSession(): Promise<void> {
  await Promise.all([
    SecureStore.deleteItemAsync(CORE_AUTH_SESSION_KEY),
    SecureStore.deleteItemAsync(CORE_AUTH_USER_KEY),
  ]);
}
