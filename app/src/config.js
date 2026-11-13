/**
 * SGIP - Global Configuration Constants
 */

function resolveApiBaseUrl() {
  // 1. Explicit environment variable via Vite (.env / VITE_API_BASE_URL)
  if (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL.replace(/\/+$/, '');
  }

  if (typeof window === 'undefined') return '';

  // 2. Explicit runtime override via localStorage
  const stored = window.localStorage.getItem('parqueame_api_url');
  if (stored) return stored.replace(/\/+$/, '');

  // 3. Localhost & local loopback development
  const host = window.location.hostname;
  if (host === 'localhost' || host === '127.0.0.1') {
    return 'http://localhost:8000';
  }

  // 4. Optional global variable injected at runtime
  if (window.__PARQUEAME_API_URL__) {
    return window.__PARQUEAME_API_URL__.replace(/\/+$/, '');
  }

  // 5. Production Cloud Backend (Render default)
  return 'https://parqueame-api.onrender.com';
}

const env = typeof import.meta !== 'undefined' ? import.meta.env || {} : {};

export const CONFIG = {
  API_BASE_URL: resolveApiBaseUrl(),
  POLLING_INTERVAL_MS: Number(env.VITE_POLLING_INTERVAL_MS) || 3000,
  REQUEST_TIMEOUT_MS: Number(env.VITE_REQUEST_TIMEOUT_MS) || 3000,
  DEFAULT_ESTABLISHMENT_ID: env.VITE_DEFAULT_ESTABLISHMENT_ID || 'uce_central',
  TOTAL_SPOTS_CAMPUS: 219,
  DEFAULT_ZOOM_STEP: 0.20,
  MIN_ZOOM: 0.8,
  MAX_ZOOM: 3.5,
  ADMIN_TOKEN_KEY: 'parqueame_admin_token',
};
