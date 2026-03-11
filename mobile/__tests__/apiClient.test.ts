/**
 * Tests for mobile API auth wiring.
 *
 * These tests verify the mobile client requests a dev JWT when needed and
 * attaches the bearer token to protected requests.
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
    config: Record<string, unknown>,
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
      interceptors: {
        request: {
          use: jest.fn((interceptor) => {
            requestInterceptors.push(interceptor);
            return requestInterceptors.length;
          }),
          eject: jest.fn(),
          clear: jest.fn(),
        },
      },
      post: jest.fn(async (url: string, data?: unknown, config: Record<string, unknown> = {}) => {
        const finalConfig = await applyRequestInterceptors({
          ...config,
          url,
          method: 'post',
          data,
          headers: { ...(config.headers as Record<string, string> | undefined) },
        });

        requestLog.push({ method: 'post', url, data, config: finalConfig });

        if (url === '/auth/token') {
          const userId = (data as { user_id: string }).user_id;
          return {
            data: {
              access_token: `access-${userId}`,
              refresh_token: `refresh-${userId}`,
              token_type: 'bearer',
              expires_in: 604800,
            },
          };
        }

        if (url === '/consent') {
          const body = data as { user_id: string; consent_version: string; purpose: string };
          return {
            data: {
              id: 'consent-1',
              user_id: body.user_id,
              action: 'granted',
              consent_version: body.consent_version,
              purpose: body.purpose,
              created_at: '2026-03-09T00:00:00Z',
            },
          };
        }

        if (url === '/scans/sessions') {
          const body = data as { user_id: string; device_model?: string; app_version?: string };
          return {
            data: {
              id: 'session-1',
              user_id: body.user_id,
              status: 'initiated',
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
              user_id: 'user-123',
              useful_response: body.useful_response,
              nps_score: body.nps_score ?? null,
              comment: body.comment ?? null,
              created_at: '2026-03-11T00:00:00Z',
            },
          };
        }

        if (url === '/beta/redeem') {
          const body = data as { invite_code: string };
          return {
            data: {
              user_id: 'user-123',
              beta_onboarding_enabled: true,
              enrolled: true,
              invite_required: false,
              cohort_name: 'remote_caregivers',
              invite_code: body.invite_code.toUpperCase(),
              enrolled_at: '2026-03-11T00:00:00Z',
            },
          };
        }

        throw new Error(`Unhandled POST ${url}`);
      }),
      get: jest.fn(async (url: string, config: Record<string, unknown> = {}) => {
        const finalConfig = await applyRequestInterceptors({
          ...config,
          url,
          method: 'get',
          headers: { ...(config.headers as Record<string, string> | undefined) },
        });

        requestLog.push({ method: 'get', url, config: finalConfig });

        if (url.startsWith('/scans/sessions/')) {
          return {
            data: {
              session: {
                id: 'session-1',
                user_id: 'user-123',
                status: 'completed',
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
              user_id: 'user-123',
              useful_response: 'useful',
              nps_score: 8,
              comment: null,
              created_at: '2026-03-11T00:00:00Z',
            },
          };
        }

        if (url === '/beta/status') {
          return {
            data: {
              user_id: 'user-123',
              beta_onboarding_enabled: true,
              enrolled: false,
              invite_required: true,
              cohort_name: null,
              invite_code: null,
              enrolled_at: null,
            },
          };
        }

        throw new Error(`Unhandled GET ${url}`);
      }),
      put: jest.fn(async (url: string, data?: unknown, config: Record<string, unknown> = {}) => {
        const finalConfig = await applyRequestInterceptors({
          ...config,
          url,
          method: 'put',
          data,
          headers: { ...(config.headers as Record<string, string> | undefined) },
        });

        requestLog.push({ method: 'put', url, data, config: finalConfig });
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
    client.resetAuthSession();
  });

  afterEach(() => {
    client.resetAuthSession();
  });

  it('requests a token before granting consent and attaches a bearer token', async () => {
    await client.grantConsent('user-123');

    expect(requestLog.map((entry) => entry.url)).toEqual(['/auth/token', '/consent']);

    const consentRequest = requestLog.find((entry) => entry.url === '/consent');
    expect(consentRequest?.config.headers).toMatchObject({
      Authorization: 'Bearer access-user-123',
    });
  });

  it('reuses the existing auth session for protected scan calls by the same user', async () => {
    await client.createScanSession('user-123');
    await client.getScanSession('session-1');

    const authRequests = requestLog.filter((entry) => entry.url === '/auth/token');
    expect(authRequests).toHaveLength(1);

    const getSessionRequest = requestLog.find(
      (entry) => entry.method === 'get' && entry.url === '/scans/sessions/session-1',
    );
    expect(getSessionRequest?.config.headers).toMatchObject({
      Authorization: 'Bearer access-user-123',
    });
  });

  it('requests a new token when the active mobile user changes', async () => {
    await client.createScanSession('user-123');
    await client.createScanSession('user-456');

    const authRequests = requestLog.filter((entry) => entry.url === '/auth/token');
    expect(authRequests).toHaveLength(2);
    expect(authRequests.map((entry) => entry.data)).toEqual([
      { user_id: 'user-123' },
      { user_id: 'user-456' },
    ]);
  });

  it('submits feedback with a bearer token for the active user', async () => {
    await client.submitScanFeedback('user-123', {
      session_id: 'session-1',
      useful_response: 'useful',
      nps_score: 8,
    });

    expect(requestLog.map((entry) => entry.url)).toEqual(['/auth/token', '/feedback']);

    const feedbackRequest = requestLog.find((entry) => entry.url === '/feedback');
    expect(feedbackRequest?.config.headers).toMatchObject({
      Authorization: 'Bearer access-user-123',
    });
  });

  it('returns null when feedback is not found for a session', async () => {
    const feedback = await client.getFeedbackForSession('missing', 'user-123');
    expect(feedback).toBeNull();
  });

  it('requests beta status with a bearer token for the active user', async () => {
    const status = await client.getBetaStatus('user-123');

    expect(status.invite_required).toBe(true);
    expect(requestLog.map((entry) => entry.url)).toEqual(['/auth/token', '/beta/status']);

    const statusRequest = requestLog.find((entry) => entry.url === '/beta/status');
    expect(statusRequest?.config.headers).toMatchObject({
      Authorization: 'Bearer access-user-123',
    });
  });

  it('redeems a beta invite with a bearer token for the active user', async () => {
    const status = await client.redeemBetaInvite('user-123', { invite_code: 'closed50' });

    expect(status.enrolled).toBe(true);
    expect(status.invite_code).toBe('CLOSED50');
    expect(requestLog.map((entry) => entry.url)).toEqual(['/auth/token', '/beta/redeem']);

    const redeemRequest = requestLog.find((entry) => entry.url === '/beta/redeem');
    expect(redeemRequest?.config.headers).toMatchObject({
      Authorization: 'Bearer access-user-123',
    });
  });
});
