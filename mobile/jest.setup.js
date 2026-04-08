/**
 * Global Jest setup for PranaScan mobile tests.
 *
 * Expo SDK 54 ships a ReadableStream polyfill (`expo/virtual/streams.js`)
 * whose `.cancel()` throws "Cannot cancel a stream that already has a reader"
 * when axios probes for fetch-adapter support at module-load time.
 *
 * We patch the `Request` constructor so that it never locks the body stream,
 * which lets `body.cancel()` succeed without throwing.
 */

const OriginalRequest = globalThis.Request;

if (OriginalRequest) {
  globalThis.Request = class PatchedRequest extends OriginalRequest {
    constructor(input, init) {
      // Strip the body from the init so the underlying Request implementation
      // never locks the ReadableStream.  Axios only uses this path for a
      // feature-detection probe — the result is discarded immediately.
      if (init && init.body && typeof init.body.cancel === 'function') {
        const { body, ...rest } = init;
        super(input, rest);
        return;
      }
      super(input, init);
    }
  };
  // Preserve .prototype identity for instanceof checks
  Object.defineProperty(globalThis.Request, 'name', { value: 'Request' });
}

