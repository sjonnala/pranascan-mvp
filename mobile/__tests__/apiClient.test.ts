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

    const axiosModule = require('axios');
    axiosModule.default.create.mockReturnValue(httpInstance);
    axiosModule.create.mockReturnValue(httpInstance);

    client = require('../src/api/client');
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
});
