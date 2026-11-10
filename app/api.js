/**
 * SGIP - Cliente de Conexión en Tiempo Real y Telemetría Backend (FastAPI)
 * Gestiona el sondeo periódico (polling), obtención de imágenes de cámaras y analíticas.
 */

(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.SGIPApi = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  let baseUrl = 'http://localhost:8000';
  const REQUEST_TIMEOUT_MS = 2500;

  function setBaseUrl(url) {
    baseUrl = url.replace(/\/+$/, '');
  }

  function getBaseUrl() {
    return baseUrl;
  }

  async function fetchWithTimeout(url, options = {}, timeoutMs = REQUEST_TIMEOUT_MS) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal
      });
      clearTimeout(timer);
      return response;
    } catch (err) {
      clearTimeout(timer);
      throw err;
    }
  }

  async function checkHealth() {
    try {
      const res = await fetchWithTimeout(baseUrl + '/api/v1/health', { method: 'GET' });
      if (!res.ok) throw new Error('Health check HTTP ' + res.status);
      return await res.json();
    } catch (err) {
      return null;
    }
  }

  async function fetchOverallStatus() {
    try {
      const res = await fetchWithTimeout(baseUrl + '/api/v1/status', { method: 'GET' });
      if (!res.ok) throw new Error('Status HTTP ' + res.status);
      return await res.json();
    } catch (err) {
      return null;
    }
  }

  function getCameraImageUrl(cameraId) {
    // Añadimos cache-buster para forzar refresco
    return baseUrl + '/api/v1/cameras/' + encodeURIComponent(cameraId) + '/image?t=' + Date.now();
  }

  async function fetchAnalyticsSummary(hours = 2.0) {
    try {
      const res = await fetchWithTimeout(baseUrl + '/api/v1/analytics/summary?hours=' + hours, { method: 'GET' });
      if (!res.ok) throw new Error('Analytics summary HTTP ' + res.status);
      return await res.json();
    } catch (err) {
      return null;
    }
  }

  async function fetchAnalyticsTimeline(hours = 2.0, bucketMinutes = 15) {
    try {
      const res = await fetchWithTimeout(
        baseUrl + '/api/v1/analytics/timeline?hours=' + hours + '&bucket_minutes=' + bucketMinutes,
        { method: 'GET' }
      );
      if (!res.ok) throw new Error('Analytics timeline HTTP ' + res.status);
      return await res.json();
    } catch (err) {
      return null;
    }
  }

  // Servicio de Polling Automático
  class PollingManager {
    constructor() {
      this.timerId = null;
      this.intervalMs = 3000;
      this.isRunning = false;
      this.isConnected = false;
      this.onStatus = null;
      this.onConnectionChange = null;
    }

    start(intervalMs = 3000, onStatus = null, onConnectionChange = null) {
      this.intervalMs = intervalMs;
      this.onStatus = onStatus;
      this.onConnectionChange = onConnectionChange;
      this.isRunning = true;
      this.tick();
    }

    stop() {
      this.isRunning = false;
      if (this.timerId) {
        clearTimeout(this.timerId);
        this.timerId = null;
      }
    }

    async tick() {
      if (!this.isRunning) return;

      const data = await fetchOverallStatus();
      const connectedNow = data !== null;

      if (connectedNow !== this.isConnected) {
        this.isConnected = connectedNow;
        if (this.onConnectionChange) {
          this.onConnectionChange(this.isConnected);
        }
      }

      if (data && this.onStatus) {
        this.onStatus(data);
      }

      if (this.isRunning) {
        this.timerId = setTimeout(() => this.tick(), this.intervalMs);
      }
    }
  }

  return {
    setBaseUrl: setBaseUrl,
    getBaseUrl: getBaseUrl,
    checkHealth: checkHealth,
    fetchOverallStatus: fetchOverallStatus,
    getCameraImageUrl: getCameraImageUrl,
    fetchAnalyticsSummary: fetchAnalyticsSummary,
    fetchAnalyticsTimeline: fetchAnalyticsTimeline,
    PollingManager: PollingManager
  };
});
