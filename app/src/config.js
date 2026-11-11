/**
 * SGIP - Global Configuration Constants
 */

export const CONFIG = {
  API_BASE_URL: (typeof window !== 'undefined' && window.location.hostname === 'localhost')
    ? 'http://localhost:8000'
    : '',
  POLLING_INTERVAL_MS: 3000,
  REQUEST_TIMEOUT_MS: 3000,
  TOTAL_SPOTS_CAMPUS: 219,
  DEFAULT_ZOOM_STEP: 0.20,
  MIN_ZOOM: 0.8,
  MAX_ZOOM: 3.5,
  ADMIN_TOKEN_KEY: 'parqueame_admin_token',
};
