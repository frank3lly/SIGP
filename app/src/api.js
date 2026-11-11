/**
 * SGIP - Cliente API y Gestor de Polling en Tiempo Real
 */

import { CONFIG } from './config.js';

let baseUrl = CONFIG.API_BASE_URL;

export function setBaseUrl(url) {
  baseUrl = url ? url.replace(/\/+$/, '') : '';
}

export function getBaseUrl() {
  return baseUrl;
}

async function fetchWithTimeout(url, options = {}, timeoutMs = CONFIG.REQUEST_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
    });
    clearTimeout(timer);
    return response;
  } catch (err) {
    clearTimeout(timer);
    throw err;
  }
}

function getAuthHeaders(token) {
  const stored = token || (typeof sessionStorage !== 'undefined' ? sessionStorage.getItem(CONFIG.ADMIN_TOKEN_KEY) : null);
  const headers = { 'Content-Type': 'application/json' };
  if (stored) {
    headers['Authorization'] = `Bearer ${stored}`;
  }
  return headers;
}

export async function checkHealth() {
  try {
    const res = await fetchWithTimeout(baseUrl + '/api/v1/health', { method: 'GET' });
    if (!res.ok) throw new Error('Health check HTTP ' + res.status);
    return await res.json();
  } catch {
    return null;
  }
}

export async function fetchOverallStatus() {
  try {
    const res = await fetchWithTimeout(baseUrl + '/api/v1/status', { method: 'GET' });
    if (!res.ok) throw new Error('Status HTTP ' + res.status);
    return await res.json();
  } catch {
    return null;
  }
}

export function getCameraImageUrl(cameraId) {
  return baseUrl + '/api/v1/cameras/' + encodeURIComponent(cameraId) + '/image?t=' + Date.now();
}

export async function fetchAnalyticsSummary(hours = 2.0) {
  try {
    const res = await fetchWithTimeout(baseUrl + '/api/v1/analytics/summary?hours=' + hours, { method: 'GET' });
    if (!res.ok) throw new Error('Analytics summary HTTP ' + res.status);
    return await res.json();
  } catch {
    return null;
  }
}

export async function fetchAnalyticsTimeline(hours = 2.0, bucketMinutes = 15) {
  try {
    const res = await fetchWithTimeout(
      baseUrl + '/api/v1/analytics/timeline?hours=' + hours + '&bucket_minutes=' + bucketMinutes,
      { method: 'GET' }
    );
    if (!res.ok) throw new Error('Analytics timeline HTTP ' + res.status);
    return await res.json();
  } catch {
    return null;
  }
}

// Administrative API
export async function adminLogin(username, password) {
  const res = await fetchWithTimeout(baseUrl + '/api/v1/admin/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || 'Credenciales inválidas.');
  }
  return await res.json();
}

export async function adminValidateSession(token) {
  try {
    const res = await fetchWithTimeout(baseUrl + '/api/v1/admin/me', {
      method: 'GET',
      headers: getAuthHeaders(token),
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function adminLogout(token) {
  try {
    await fetchWithTimeout(baseUrl + '/api/v1/admin/logout', {
      method: 'POST',
      headers: getAuthHeaders(token),
    });
  } catch {
    // ignore
  }
}

export async function fetchAdminGallery(token, cameraId = null, limit = 30, offset = 0) {
  let url = `${baseUrl}/api/v1/admin/gallery?limit=${limit}&offset=${offset}`;
  if (cameraId) {
    url += `&camera_id=${encodeURIComponent(cameraId)}`;
  }
  const res = await fetchWithTimeout(url, {
    method: 'GET',
    headers: getAuthHeaders(token),
  });
  if (!res.ok) throw new Error('Error al cargar galería: ' + res.status);
  return await res.json();
}

export async function fetchAdminCameras(token) {
  const res = await fetchWithTimeout(baseUrl + '/api/v1/admin/cameras', {
    method: 'GET',
    headers: getAuthHeaders(token),
  });
  if (!res.ok) throw new Error('Error al consultar cámaras: ' + res.status);
  return await res.json();
}

export async function updateCameraConfig(token, cameraId, config) {
  const res = await fetchWithTimeout(baseUrl + `/api/v1/admin/cameras/${encodeURIComponent(cameraId)}/config`, {
    method: 'PUT',
    headers: getAuthHeaders(token),
    body: JSON.stringify(config),
  });
  if (!res.ok) throw new Error('Error al actualizar configuración: ' + res.status);
  return await res.json();
}

export class PollingManager {
  constructor() {
    this.timerId = null;
    this.intervalMs = CONFIG.POLLING_INTERVAL_MS;
    this.isRunning = false;
    this.isConnected = false;
    this.onStatus = null;
    this.onConnectionChange = null;
  }

  start(intervalMs, onStatus, onConnectionChange) {
    if (intervalMs) this.intervalMs = intervalMs;
    if (onStatus) this.onStatus = onStatus;
    if (onConnectionChange) this.onConnectionChange = onConnectionChange;

    this.isRunning = true;
    this.poll();
  }

  stop() {
    this.isRunning = false;
    if (this.timerId) {
      clearTimeout(this.timerId);
      this.timerId = null;
    }
  }

  async poll() {
    if (!this.isRunning) return;

    try {
      const data = await fetchOverallStatus();
      if (data) {
        if (!this.isConnected) {
          this.isConnected = true;
          if (this.onConnectionChange) this.onConnectionChange(true);
        }
        if (this.onStatus) this.onStatus(data);
      } else {
        if (this.isConnected) {
          this.isConnected = false;
          if (this.onConnectionChange) this.onConnectionChange(false);
        }
      }
    } catch {
      if (this.isConnected) {
        this.isConnected = false;
        if (this.onConnectionChange) this.onConnectionChange(false);
      }
    } finally {
      if (this.isRunning) {
        this.timerId = setTimeout(() => this.poll(), this.intervalMs);
      }
    }
  }
}

if (typeof window !== 'undefined') {
  window.SGIPApi = {
    setBaseUrl,
    getBaseUrl,
    checkHealth,
    fetchOverallStatus,
    getCameraImageUrl,
    fetchAnalyticsSummary,
    fetchAnalyticsTimeline,
    adminLogin,
    adminValidateSession,
    adminLogout,
    fetchAdminGallery,
    fetchAdminCameras,
    updateCameraConfig,
    PollingManager,
  };
}
