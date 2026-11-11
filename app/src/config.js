/**
 * SGIP - Global Configuration Constants
 */

function resolveApiBaseUrl() {
  if (typeof window === 'undefined') return '';
  // 1. Explicit runtime override via localStorage
  const stored = window.localStorage.getItem('parqueame_api_url');
  if (stored) return stored.replace(/\/+$/, '');

  // 2. Localhost & local loopback development
  const host = window.location.hostname;
  if (host === 'localhost' || host === '127.0.0.1') {
    return 'http://localhost:8000';
  }

  // 3. Optional global variable injected at runtime
  if (window.__PARQUEAME_API_URL__) {
    return window.__PARQUEAME_API_URL__.replace(/\/+$/, '');
  }

  // 4. Production Cloud Backend (Hugging Face Spaces default)
  return 'https://thegxnster-parqueame-server.hf.space';
}

export const CONFIG = {
  API_BASE_URL: resolveApiBaseUrl(),
  POLLING_INTERVAL_MS: 3000,
  REQUEST_TIMEOUT_MS: 3000,
  TOTAL_SPOTS_CAMPUS: 219,
  DEFAULT_ZOOM_STEP: 0.20,
  MIN_ZOOM: 0.8,
  MAX_ZOOM: 3.5,
  ADMIN_TOKEN_KEY: 'parqueame_admin_token',
};
