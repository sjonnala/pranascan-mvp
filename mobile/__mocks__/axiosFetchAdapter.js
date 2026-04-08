/**
 * Stub for axios/lib/adapters/fetch.js
 *
 * Expo SDK 54's ReadableStream polyfill crashes when axios probes for
 * fetch-adapter support at module-load time.  This stub makes the fetch
 * adapter look unsupported so axios falls back to the XHR adapter –
 * which is the adapter React Native actually uses at runtime anyway.
 */

export default null;

