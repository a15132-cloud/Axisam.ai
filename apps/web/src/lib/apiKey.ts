// Bring-your-own-key storage: each browser holds its own Anthropic API key
// so whoever operates this Axiscam deployment never has to pay for every
// client's Claude usage out of one shared key. Lives only in this
// browser's localStorage - sent as a header on API calls (see api.ts's
// axios interceptor) and used server-side to build a throwaway Anthropic
// client for that single request only (app/api/routes_projects.py). It is
// never written to project storage or logs on the backend.

const STORAGE_KEY = "axiscam_anthropic_api_key";

export function obtenerApiKey(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function guardarApiKey(key: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, key.trim());
  } catch {
    // localStorage unavailable (private mode, disabled) - the key just
    // won't persist across reloads; the request-time header still works
    // for the current page session via the in-memory value the caller holds.
  }
}

export function borrarApiKey(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // no-op
  }
}
