/**
 * Tests for mobile API client auth wiring after the OIDC cutover.
 */

jest.mock('axios');

type RequestLogEntry = {
  method: 'get' | 'post' | 'put';
  url: string;
  data?: unknown;
  config: Record<string, unknown>;
};

describe('api client auth wiring', () => {
  let requestInterceptors: Array<
    (config: Record<string, unknown>) => Promise<Record<string, unknown>> | Record<string, unknown>
  >;
  let requestLog: RequestLogEntry[];
  let client: typeof import('../src/api/client');

  const applyRequestInterceptors = async (
    config: Record<string, unknown>
  ): Promise<Record<string, unknown>> => {
    let next = config;
    for (const interceptor of requestInterceptors) {
      next = await interceptor(next);
    }
    return next;
  };

  beforeEach(() => {
    jest.resetModules();
    requestInterceptors = [];
    requestLog = [];

    const httpInstance = {
      interceptors: { request: { use: jest.fn(), eject: jest.fn(), clear: jest.fn() } },
      post: jest.fn(async (url: string, data?: unknown, config: Record<string, unknown> = {}) => {
        const finalConfig = await applyRequestInterceptors({ ...config, url, method: 'post', data });

        requestLog.push({ method: 'post', url, data, config: finalConfig });

        if (url === '/consent') {
          const body = data as { consent_version: string; purpose: string };
          return {
            data: {
              id: 'consent-1',
              user_id: 'core-user-123',
              action: 'granted',
              consent_version: body.consent_version,
              purpose: body.purpose,
              created_at: '2026-03-09T00:00:00Z',
            },
          };
        }

        if (url === '/consent/revoke') {
          return {
            data: {
              id: 'consent-2',
              user_id: 'core-user-123',
              action: 'revoked',
              consent_version: '1.0',
              purpose: 'wellness_screening',
              created_at: '2026-03-09T00:00:00Z',
            },
          };
        }

        if (url === '/consent/deletion-request') {
          return {
            data: {
              id: 'consent-3',
              user_id: 'core-user-123',
              action: 'deletion_requested',
              consent_version: '1.0',
              purpose: 'wellness_screening',
              created_at: '2026-03-09T00:00:00Z',
              deletion_scheduled_at: '2026-04-08T00:00:00Z',
            },
          };
        }

        if (url === '/scans/sessions') {
          const body = data as { scan_type?: string; device_model?: string; app_version?: string };
          return {
            data: {
              id: 'session-1',
              user_id: 'core-user-123',
              status: 'initiated',
              scan_type: body.scan_type ?? 'standard',
              device_model: body.device_model ?? null,
              app_version: body.app_version ?? null,
              created_at: '2026-03-09T00:00:00Z',
              completed_at: null,
            },
          };
        }

        if (url === '/feedback') {
          const body = data as {
            session_id: string;
            useful_response: 'useful' | 'needs_work';
            nps_score?: number;
            comment?: string;
          };
          return {
            data: {
              id: 'feedback-1',
              session_id: body.session_id,
              user_id: 'core-user-123',
              useful_response: body.useful_response,
              nps_score: body.nps_score ?? null,
              comment: body.comment ?? null,
              created_at: '2026-03-11T00:00:00Z',
            },
          };
        }

        throw new Error(`Unhandled POST ${url}`);
      }),
      get: jest.fn(async (url: string, config: Record<string, unknown> = {}) => {
        const finalConfig = await applyRequestInterceptors({ ...config, url, method: 'get' });

        requestLog.push({ method: 'get', url, config: finalConfig });

        if (url === '/auth/me') {
          return {
            data: {
              id: 'core-user-123',
              oidcSubject: 'oidc-user-123',
              email: 'user@example.com',
              displayName: 'Prana User',
              phoneE164: null,
              avatarUrl: null,
              active: true,
              lastLoginAt: '2026-03-09T00:00:00Z',
              createdAt: '2026-03-01T00:00:00Z',
              updatedAt: '2026-03-09T00:00:00Z',
            },
          };
        }

        if (url === '/consent/status') {
          return {
            data: {
              user_id: 'core-user-123',
              has_active_consent: true,
              consent_version: '1.0',
              granted_at: '2026-03-09T00:00:00Z',
              revoked_at: null,
              deletion_requested: false,
              deletion_scheduled_at: null,
            },
          };
        }

        if (url.startsWith('/scans/sessions/')) {
          return {
            data: {
              session: {
                id: 'session-1',
                user_id: 'core-user-123',
                status: 'completed',
                scan_type: 'standard',
                device_model: null,
                app_version: null,
                created_at: '2026-03-09T00:00:00Z',
                completed_at: '2026-03-09T00:00:35Z',
              },
              result: null,
            },
          };
        }

        if (url.startsWith('/feedback/sessions/')) {
          if (url.endsWith('/missing')) {
            const error = new Error('Not found') as Error & {
              isAxiosError: boolean;
              response: { status: number };
            };
            error.isAxiosError = true;
            error.response = { status: 404 };
            throw error;
          }

          return {
            data: {
              id: 'feedback-1',
              session_id: 'session-1',
              user_id: 'core-user-123',
              useful_response: 'useful',
              nps_score: 8,
              comment: null,
              created_at: '2026-03-11T00:00:00Z',
            },
          };
        }

        throw new Error(`Unhandled GET ${url}`);
      }),
      put: jest.fn(async (url: string, data?: unknown, config: Record<string, unknown> = {}) => {
        const finalConfig = await applyRequestInterceptors({ ...config, url, method: 'put', data });

        requestLog.push({ method: 'put', url, data, config: finalConfig });

        if (url === '/scans/sessions/session-1/complete') {
          return {
            data: {
              id: 'result-1',
              session_id: 'session-1',
              user_id: 'core-user-123',
              hr_bpm: 72,
              hrv_ms: 42,
              spo2: 97,
              stiffness_index: null,
              respiratory_rate: 15,
              voice_jitter_pct: 0.4,
              voice_shimmer_pct: 1.8,
              quality_score: 0.91,
              flags: [],
              trend_alert: null,
              created_at: '2026-03-09T00:00:35Z',
            },
          };
        }

        throw new Error(`Unhandled PUT ${url}`);
      }),
    };

    const axiosModule = jest.requireMock('axios');
    axiosModule.default.create.mockReturnValue(httpInstance);
    axiosModule.create.mockReturnValue(httpInstance);
    axiosModule.default.isAxiosError = (error: unknown) =>
      Boolean((error as { isAxiosError?: boolean })?.isAxiosError);
    axiosModule.isAxiosError = axiosModule.default.isAxiosError;

    client = jest.requireActual('../src/api/client') as typeof import('../src/api/client');
    client.configureCoreAccessToken(null);
  });

  afterEach(() => {
    client.configureCoreAccessToken(null);
  });

  it('uses the configured core bearer token for auth profile lookups', async () => {
    client.configureCoreAccessToken('core-token-123');
    const user = await client.getCurrentUserProfile();

    expect(user.id).toBe('core-user-123');
    expect(requestLog.map((entry) => entry.url)).toEqual(['/auth/me']);
    expect(requestLog[0]?.config.headers).toMatchObject({
      Authorization: 'Bearer core-token-123',
    });
  });

  it('uses the configured core bearer token for consent routes', async () => {
    client.configureCoreAccessToken('core-token-123');

    await client.grantConsent();
    await client.getConsentStatus();

    expect(requestLog.map((entry) => entry.url)).toEqual(['/consent', '/consent/status']);
    expect(requestLog[0]?.config.headers).toMatchObject({
      Authorization: 'Bearer core-token-123',
    });
  });

  it('uses the configured core bearer token for scan calls', async () => {
    client.configureCoreAccessToken('core-token-123');

    await client.createScanSession('standard');
    await client.getScanSession('session-1');

    const getSessionRequest = requestLog.find(
      (entry) => entry.method === 'get' && entry.url === '/scans/sessions/session-1'
    );
    expect(getSessionRequest?.config.headers).toMatchObject({
      Authorization: 'Bearer core-token-123',
    });
  });

  it('sends frame_data to service-core when completing a scan session', async () => {
    client.configureCoreAccessToken('core-token-123');

    await client.completeScanSession('session-1', {
      scan_type: 'standard',
      quality_score: 0.91,
      flags: [],
      frame_data: [
        { t_ms: 0, r_mean: 150, g_mean: 132, b_mean: 112 },
        { t_ms: 67, r_mean: 149, g_mean: 131, b_mean: 111 },
      ],
      frame_r_mean: 149.5,
      frame_g_mean: 131.5,
      frame_b_mean: 111.5,
    });

    const completionRequest = requestLog.find(
      (entry) => entry.method === 'put' && entry.url === '/scans/sessions/session-1/complete'
    );

    expect(completionRequest?.config.headers).toMatchObject({
      Authorization: 'Bearer core-token-123',
    });
    expect(completionRequest?.data).toMatchObject({
      scan_type: 'standard',
      frame_data: [
        { t_ms: 0, r_mean: 150, g_mean: 132, b_mean: 112 },
        { t_ms: 67, r_mean: 149, g_mean: 131, b_mean: 111 },
      ],
    });
  });

  it('throws a clear error when a core token is not configured', async () => {
    await expect(client.createScanSession('standard')).rejects.toThrow(
      'You are not authenticated. Sign in before using service-core APIs.'
    );
  });

  it('uses the configured core bearer token for feedback routes', async () => {
    client.configureCoreAccessToken('core-token-123');

    await client.submitScanFeedback({
      session_id: 'session-1',
      useful_response: 'useful',
      nps_score: 8,
    });

    expect(requestLog.map((entry) => entry.url)).toEqual(['/feedback']);
    expect(requestLog[0]?.config.headers).toMatchObject({
      Authorization: 'Bearer core-token-123',
    });
  });

  it('returns null when feedback is not found for a session', async () => {
    client.configureCoreAccessToken('core-token-123');
    const feedback = await client.getFeedbackForSession('missing');
    expect(feedback).toBeNull();
  });
});
