import React, { createContext, ReactNode, useContext, useMemo } from 'react';
import { useConsent, UseConsentReturn } from '../hooks/useConsent';
import { useOidcAuth, UseOidcAuthReturn } from '../hooks/useOidcAuth';

interface AppSessionContextValue {
  auth: UseOidcAuthReturn;
  consent: UseConsentReturn;
  isBootstrapping: boolean;
  hasAccess: boolean;
}

const AppSessionContext = createContext<AppSessionContextValue | null>(null);

export function AppSessionProvider({ children }: { children: ReactNode }) {
  const auth = useOidcAuth();
  const consent = useConsent(auth.status === 'signed_in');
  const isBootstrapping = auth.status === 'loading' || (auth.status === 'signed_in' && consent.isLoading);
  const hasAccess = auth.status === 'signed_in' && consent.hasActiveConsent;

  const value = useMemo(
    () => ({
      auth,
      consent,
      isBootstrapping,
      hasAccess,
    }),
    [auth, consent, hasAccess, isBootstrapping]
  );

  return <AppSessionContext.Provider value={value}>{children}</AppSessionContext.Provider>;
}

export function useAppSession(): AppSessionContextValue {
  const context = useContext(AppSessionContext);
  if (!context) {
    throw new Error('useAppSession must be used within AppSessionProvider.');
  }
  return context;
}
