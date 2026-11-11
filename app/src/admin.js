/**
 * SGIP - Hidden Administrative Portal Controller
 * Camera Fleet Hot-Configuration, Hardware Gallery & Secure Lightbox Inspector.
 */

import { CONFIG } from './config.js';
import {
  adminLogin,
  adminValidateSession,
  adminLogout,
  fetchAdminCameras,
  fetchAdminGallery,
  updateCameraConfig,
  getBaseUrl,
} from './api.js';
import { getMappingEntries, CAMERA_METADATA } from './mapping.js';

export function resolveMediaUrl(url, token) {
  if (!url) return '';
  const base = getBaseUrl() || '';
  let fullUrl = url.startsWith('http') ? url : `${base}${url}`;
  if (token && fullUrl.includes('/api/v1/admin/gallery/image/')) {
    const sep = fullUrl.includes('?') ? '&' : '?';
    fullUrl = `${fullUrl}${sep}token=${encodeURIComponent(token)}`;
  }
  return fullUrl;
}

export function isAdminRouteRequested() {
  if (typeof window === 'undefined') return false;
  const path = window.location.pathname.toLowerCase();
  const hash = window.location.hash.toLowerCase();
  return path === '/admin' || path.startsWith('/admin/') || hash === '#admin';
}

let activeAdminContainer = null;
let activeModalContainer = null;
let activeLightbox = null;

export async function initAdmin(store) {
  if (!isAdminRouteRequested()) {
    cleanupAdminViews();
    return;
  }

  const token = sessionStorage.getItem(CONFIG.ADMIN_TOKEN_KEY);
  if (token) {
    const session = await adminValidateSession(token);
    if (session && session.valid) {
      renderAdminDashboard(store, token);
      return;
    } else {
      sessionStorage.removeItem(CONFIG.ADMIN_TOKEN_KEY);
    }
  }

  renderAdminLoginModal(store);
}

function cleanupAdminViews() {
  if (activeAdminContainer && activeAdminContainer.parentNode) {
    activeAdminContainer.parentNode.removeChild(activeAdminContainer);
    activeAdminContainer = null;
  }
  if (activeModalContainer && activeModalContainer.parentNode) {
    activeModalContainer.parentNode.removeChild(activeModalContainer);
    activeModalContainer = null;
  }
  if (activeLightbox && activeLightbox.parentNode) {
    activeLightbox.parentNode.removeChild(activeLightbox);
    activeLightbox = null;
  }
  document.body.style.overflow = '';
}

function showAdminToast(message, isError = false) {
  let toastEl = document.getElementById('adminToast');
  if (!toastEl) {
    toastEl = document.createElement('div');
    toastEl.id = 'adminToast';
    toastEl.className = 'admin-toast';
    document.body.appendChild(toastEl);
  }

  toastEl.textContent = message;
  toastEl.className = `admin-toast show ${isError ? 'error' : 'success'}`;
  setTimeout(() => {
    toastEl.classList.remove('show');
  }, 3000);
}

/**
 * Render Admin Login Modal with clean, minimal copy
 */
export function renderAdminLoginModal(store) {
  cleanupAdminViews();

  const backdrop = document.createElement('div');
  backdrop.className = 'modal-backdrop active admin-login-backdrop';

  const modal = document.createElement('div');
  modal.className = 'admin-login-modal';
  modal.innerHTML = `
    <div class="admin-login-header">
      <div class="admin-brand-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
          <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
        </svg>
      </div>
      <h2>Administración</h2>
    </div>

    <form class="admin-login-form" id="adminLoginForm">
      <div class="admin-form-group">
        <label for="adminUsername">Usuario</label>
        <div class="admin-input-wrapper">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
            <circle cx="12" cy="7" r="4"></circle>
          </svg>
          <input type="text" id="adminUsername" placeholder="Usuario" required autofocus autocomplete="username" />
        </div>
      </div>

      <div class="admin-form-group">
        <label for="adminPassword">Contraseña</label>
        <div class="admin-input-wrapper">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
            <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
          </svg>
          <input type="password" id="adminPassword" placeholder="••••••••••••" required autocomplete="current-password" />
        </div>
      </div>

      <div class="admin-login-error" id="adminLoginError" style="display:none;"></div>

      <button type="submit" class="admin-btn-primary" id="adminLoginSubmit">
        <span>Ingresar</span>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
          <line x1="5" y1="12" x2="19" y2="12"></line>
          <polyline points="12 5 19 12 12 19"></polyline>
        </svg>
      </button>

      <button type="button" class="admin-btn-cancel" id="adminLoginCancel">
        Cancelar
      </button>
    </form>
  `;

  backdrop.appendChild(modal);
  document.body.appendChild(backdrop);
  activeModalContainer = backdrop;

  const form = modal.querySelector('#adminLoginForm');
  const userIn = modal.querySelector('#adminUsername');
  const passIn = modal.querySelector('#adminPassword');
  const errorEl = modal.querySelector('#adminLoginError');
  const cancelBtn = modal.querySelector('#adminLoginCancel');
  const submitBtn = modal.querySelector('#adminLoginSubmit');

  cancelBtn.addEventListener('click', () => {
    cleanupAdminViews();
    if (window.location.hash === '#admin') {
      window.location.hash = '';
    } else {
      window.history.pushState(null, '', '/');
    }
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    errorEl.style.display = 'none';
    submitBtn.disabled = true;
    submitBtn.classList.add('loading');

    try {
      const resp = await adminLogin(userIn.value.trim(), passIn.value);
      if (resp && resp.token) {
        sessionStorage.setItem(CONFIG.ADMIN_TOKEN_KEY, resp.token);
        store.setState({ adminToken: resp.token, adminActive: true });
        cleanupAdminViews();
        renderAdminDashboard(store, resp.token);
      } else {
        throw new Error('Respuesta inválida.');
      }
    } catch (err) {
      errorEl.textContent = err.message || 'Credenciales inválidas.';
      errorEl.style.display = 'block';
      modal.classList.add('shake');
      setTimeout(() => modal.classList.remove('shake'), 450);
    } finally {
      submitBtn.disabled = false;
      submitBtn.classList.remove('loading');
    }
  });
}

/**
 * Render Complete Administrative Dashboard
 */
export async function renderAdminDashboard(store, token) {
  cleanupAdminViews();
  document.body.style.overflow = 'hidden';

  const container = document.createElement('div');
  container.className = 'admin-dashboard-container';
  container.id = 'adminDashboard';

  container.innerHTML = `
    <!-- Top Administrative Navigation -->
    <header class="admin-navbar">
      <div class="admin-navbar-inner">
        <div class="admin-navbar-brand">
          <img src="/logo.svg" alt="Logo SGIP" class="brand-logo-img" onerror="this.style.display='none';" />
          <div class="brand-text">
            <div class="admin-brand-title-row">
              <span class="brand-title">SGIP</span>
              <span class="admin-tag-badge">Administración</span>
            </div>
            <span class="brand-sub">Sistema de Gestión Inteligente de Parqueos</span>
          </div>
        </div>

        <div class="admin-nav-actions">
          <button class="btn-navbar-action" id="adminReturnMapBtn" title="Volver al mapa">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"></polygon>
              <line x1="8" y1="2" x2="8" y2="18"></line>
              <line x1="16" y1="6" x2="16" y2="22"></line>
            </svg>
            <span class="nav-btn-text">Ver Mapa</span>
          </button>
          <button class="btn-navbar-action btn-logout" id="adminLogoutBtn" title="Cerrar sesión">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
              <polyline points="16 17 21 12 16 7"></polyline>
              <line x1="21" y1="12" x2="9" y2="12"></line>
            </svg>
            <span class="nav-btn-text">Cerrar Sesión</span>
          </button>
        </div>
      </div>
    </header>

    <!-- Main Dashboard Scrollable Content -->
    <main class="admin-content">
      <!-- Section 1: Cameras -->
      <section class="admin-section">
        <div class="admin-section-header">
          <h3>Cámaras</h3>
          <button class="admin-btn-refresh" id="adminRefreshCamerasBtn">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 4v6h-6"></path><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg>
            <span>Actualizar</span>
          </button>
        </div>

        <div class="admin-camera-grid" id="adminCameraGrid">
          <div class="admin-loading-card">Cargando cámaras...</div>
        </div>
      </section>

      <!-- Section 2: Mapeo de Espacios (1:1 Cámaras ↔ Cliente) -->
      <section class="admin-section" id="adminMappingSection">
        <div class="admin-section-header">
          <div>
            <h3>Mapeo de Espacios (1:1 Cámaras ↔ Cliente)</h3>
            <p>Correspondencia directa entre polígonos de @config/cameras/ (spot_01, spot_02...) y el identificador único real en el cliente.</p>
          </div>
          <div class="admin-mapping-controls">
            <input type="text" id="adminMappingSearch" class="admin-input-search" placeholder="Filtrar por spot_01, R1-A01, hilera..." />
            <select id="adminMappingCamFilter" class="admin-select">
              <option value="cam_01">Cámara 01 (Hilera R1 • 28 spots)</option>
              <option value="cam_02">Cámara 02 (Hileras L1-L2 • 40 spots)</option>
              <option value="cam_03">Cámara 03 (Sector Central • 100 spots)</option>
              <option value="all">Todas las plazas mapeadas (168)</option>
            </select>
            <button class="admin-btn-refresh" id="adminRefreshMappingBtn" title="Refrescar tabla">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 4v6h-6"></path><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg>
              <span>Actualizar</span>
            </button>
          </div>
        </div>

        <div class="admin-mapping-stats" id="adminMappingStats">
          <!-- Estadísticas dinámicas -->
        </div>

        <div class="admin-mapping-table-wrap">
          <table class="admin-mapping-table">
            <thead>
              <tr>
                <th>Spot Config (Cámara)</th>
                <th>ID Real Cliente</th>
                <th>Nº UI (Hilera)</th>
                <th>Sector / Ubicación</th>
                <th>Cámara</th>
                <th>Estado Actual</th>
                <th>Acción</th>
              </tr>
            </thead>
            <tbody id="adminMappingTbody">
              <!-- Filas generadas dinámicamente -->
            </tbody>
          </table>
        </div>
      </section>

      <!-- Section 3: Hardware Photo Gallery -->
      <section class="admin-section">
        <div class="admin-section-header">
          <h3>Galería de Capturas</h3>
          <div class="admin-gallery-controls">
            <select id="adminGalleryCamFilter" class="admin-select">
              <option value="">Todas las cámaras</option>
              <option value="cam_01">Cámara 01 (Hilera R1)</option>
              <option value="cam_02">Cámara 02 (Hileras L1-L2)</option>
              <option value="cam_03">Cámara 03 (Central UCE)</option>
            </select>
            <button class="admin-btn-refresh" id="adminRefreshGalleryBtn">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 4v6h-6"></path><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg>
              <span>Actualizar</span>
            </button>
          </div>
        </div>

        <div class="admin-gallery-grid" id="adminGalleryGrid">
          <div class="admin-loading-card">Cargando capturas...</div>
        </div>
      </section>
    </main>
  `;

  document.body.appendChild(container);
  activeAdminContainer = container;

  // Bind Navigation actions
  const returnMapBtn = container.querySelector('#adminReturnMapBtn');
  const logoutBtn = container.querySelector('#adminLogoutBtn');
  const refreshCamBtn = container.querySelector('#adminRefreshCamerasBtn');
  const refreshGalBtn = container.querySelector('#adminRefreshGalleryBtn');
  const camFilterSelect = container.querySelector('#adminGalleryCamFilter');

  returnMapBtn.addEventListener('click', () => {
    cleanupAdminViews();
    if (window.location.hash === '#admin') {
      window.location.hash = '';
    } else {
      window.history.pushState(null, '', '/');
    }
  });

  logoutBtn.addEventListener('click', async () => {
    await adminLogout(token);
    sessionStorage.removeItem(CONFIG.ADMIN_TOKEN_KEY);
    store.setState({ adminToken: null, adminActive: false });
    cleanupAdminViews();
    showAdminToast('Sesión finalizada.');
    if (window.location.hash === '#admin') {
      window.location.hash = '';
    } else {
      window.history.pushState(null, '', '/');
    }
  });

  refreshCamBtn.addEventListener('click', () => loadCameras(token, container));
  refreshGalBtn.addEventListener('click', () => loadGallery(token, container, camFilterSelect.value));
  camFilterSelect.addEventListener('change', () => loadGallery(token, container, camFilterSelect.value));

  // Initial Data Fetch
  loadCameras(token, container);
  renderMappingSection(store, container);
  loadGallery(token, container, '');
}

/**
 * Controller for Spot Mapping Section (1:1 Cameras <-> Client)
 */
function renderMappingSection(store, container) {
  const tbody = container.querySelector('#adminMappingTbody');
  const statsEl = container.querySelector('#adminMappingStats');
  const camFilter = container.querySelector('#adminMappingCamFilter');
  const searchInput = container.querySelector('#adminMappingSearch');
  const refreshBtn = container.querySelector('#adminRefreshMappingBtn');
  if (!tbody) return;

  function update() {
    const selectedCam = camFilter ? camFilter.value : 'cam_01';
    const query = (searchInput ? searchInput.value : '').trim().toLowerCase();
    const entries = getMappingEntries(selectedCam);
    const spotsState = store.getState().spots || {};

    const filtered = entries.filter((e) => {
      if (!query) return true;
      return (
        e.internalId.toLowerCase().includes(query) ||
        e.slotId.toLowerCase().includes(query) ||
        e.uiNum.toLowerCase().includes(query) ||
        e.sector.toLowerCase().includes(query) ||
        e.cameraId.toLowerCase().includes(query)
      );
    });

    if (statsEl) {
      const camLabel = selectedCam === 'all' ? 'Todas las plazas mapeadas' : (CAMERA_METADATA[selectedCam]?.name || selectedCam);
      statsEl.innerHTML = `
        <div class="stat-item"><span>Cámara seleccionada:</span> <strong>${camLabel}</strong></div>
        <div class="stat-item"><span>Espacios listados:</span> <strong>${filtered.length} de ${entries.length}</strong></div>
        <div class="stat-item"><span>Mapeo:</span> <strong style="color:#16a34a;">1:1 Directo (spot_XX ↔ ID Real Cliente)</strong></div>
      `;
    }

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:24px; color:#64748b;">No se encontraron espacios que coincidan con la búsqueda.</td></tr>`;
      return;
    }

    tbody.innerHTML = filtered
      .map((entry) => {
        const spotData = spotsState[entry.slotId] || {};
        const status = spotData.status || 'unknown';
        const statusLabel = status === 'free' ? 'Libre' : status === 'occupied' ? 'Ocupado' : (status === 'warning' ? 'Revisión' : 'Sin datos');

        return `
          <tr>
            <td><code class="admin-spot-badge">${entry.internalId}</code></td>
            <td><strong class="admin-slot-id">${entry.slotId}</strong></td>
            <td><span class="admin-ui-num">Plaza ${entry.uiNum}</span></td>
            <td>${entry.sector}</td>
            <td><span class="admin-cam-pill">${entry.cameraId}</span></td>
            <td><span class="admin-status-pill ${status}">${statusLabel}</span></td>
            <td>
              <button class="admin-btn-table-action btn-locate-spot" data-id="${entry.slotId}" title="Ver y centrar en el mapa">Ver en Mapa</button>
              <button class="admin-btn-table-action btn-copy-spot" data-copy="${entry.internalId}" title="Copiar identificador">Copiar ID</button>
            </td>
          </tr>
        `;
      })
      .join('');

    // Bind locate buttons
    tbody.querySelectorAll('.btn-locate-spot').forEach((btn) => {
      btn.addEventListener('click', () => {
        const slotId = btn.getAttribute('data-id');
        cleanupAdminViews();
        if (window.location.hash === '#admin') {
          window.location.hash = '';
        } else {
          window.history.pushState(null, '', '/');
        }
        setTimeout(() => {
          const node = document.querySelector(`.spot-node[data-id="${slotId}"]`);
          if (node) {
            node.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
          }
        }, 90);
      });
    });

    // Bind copy buttons
    tbody.querySelectorAll('.btn-copy-spot').forEach((btn) => {
      btn.addEventListener('click', () => {
        const textToCopy = btn.getAttribute('data-copy');
        if (navigator.clipboard) {
          navigator.clipboard.writeText(textToCopy);
        }
        showAdminToast(`Copiado: ${textToCopy}`);
      });
    });
  }

  if (camFilter) camFilter.addEventListener('change', update);
  if (searchInput) searchInput.addEventListener('input', update);
  if (refreshBtn) refreshBtn.addEventListener('click', update);

  update();
}

async function loadCameras(token, container) {
  const grid = container.querySelector('#adminCameraGrid');
  if (!grid) return;

  try {
    const data = await fetchAdminCameras(token);
    const cameras = data.cameras || [];
    if (cameras.length === 0) {
      grid.innerHTML = '<div class="admin-empty">No hay cámaras registradas.</div>';
      return;
    }

    grid.innerHTML = '';
    cameras.forEach((cam) => {
      const card = document.createElement('div');
      card.className = 'admin-camera-card';
      const isOnline = cam.status === 'online';
      const isPaused = !cam.config.active;

      const batPct = cam.battery_percentage != null ? `${Math.round(cam.battery_percentage)}%` : '--';
      const lastSeen = cam.seconds_since_last_seen != null
        ? `hace ${Math.round(cam.seconds_since_last_seen)}s`
        : 'Sin conexión';

      card.innerHTML = `
        <div class="admin-cam-card-top">
          <div>
            <div class="admin-cam-name">${cam.name || cam.camera_id}</div>
            <div class="admin-cam-id">${cam.camera_id}</div>
          </div>
          <span class="admin-status-badge ${isOnline ? 'online' : (isPaused ? 'paused' : 'offline')}">
            ${isPaused ? 'En Pausa' : (isOnline ? 'En Línea' : 'Desconectada')}
          </span>
        </div>

        <div class="admin-cam-telemetry">
          <div class="admin-telem-item">
            <span class="telem-lbl">Batería</span>
            <span class="telem-val">${batPct}</span>
          </div>
          <div class="admin-telem-item">
            <span class="telem-lbl">Último reporte</span>
            <span class="telem-val">${lastSeen}</span>
          </div>
        </div>

        <form class="admin-hotconfig-form" data-cam="${cam.camera_id}">
          <div class="admin-form-row">
            <div class="admin-field">
              <label>Intervalo (seg)</label>
              <input type="number" name="interval_seconds" min="5" max="3600" value="${cam.config.interval_seconds || 30}" required />
            </div>
            <div class="admin-field">
              <label>Calidad</label>
              <input type="number" name="quality" min="1" max="63" value="${cam.config.quality || 12}" required />
            </div>
          </div>

          <div class="admin-field">
            <label>Estado</label>
            <select name="active" class="admin-select">
              <option value="true" ${cam.config.active ? 'selected' : ''}>Activa</option>
              <option value="false" ${!cam.config.active ? 'selected' : ''}>En Pausa</option>
            </select>
          </div>

          <button type="submit" class="admin-btn-save">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path><polyline points="17 21 17 13 7 13 7 21"></polyline><polyline points="7 3 7 8 15 8"></polyline></svg>
            <span>Guardar</span>
          </button>
        </form>
      `;

      const form = card.querySelector('.admin-hotconfig-form');
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = form.querySelector('.admin-btn-save');
        btn.disabled = true;
        btn.classList.add('loading');

        const intervalVal = parseInt(form.interval_seconds.value, 10);
        const qualityVal = parseInt(form.quality.value, 10);
        const activeVal = form.active.value === 'true';

        try {
          await updateCameraConfig(token, cam.camera_id, {
            interval_seconds: intervalVal,
            quality: qualityVal,
            active: activeVal,
            firmware_version: cam.config.firmware_version || '1.0.0',
          });
          showAdminToast(`Guardado.`);
        } catch (err) {
          showAdminToast(err.message || 'Error al guardar.', true);
        } finally {
          btn.disabled = false;
          btn.classList.remove('loading');
        }
      });

      grid.appendChild(card);
    });
  } catch (err) {
    grid.innerHTML = `<div class="admin-error">Error al cargar: ${err.message}</div>`;
  }
}

async function loadGallery(token, container, cameraIdFilter = '') {
  const grid = container.querySelector('#adminGalleryGrid');
  if (!grid) return;

  grid.innerHTML = '<div class="admin-loading-card">Cargando capturas...</div>';

  try {
    const data = await fetchAdminGallery(token, cameraIdFilter || null, 36, 0);
    const items = data.items || [];
    if (items.length === 0) {
      grid.innerHTML = '<div class="admin-empty">No hay capturas disponibles.</div>';
      return;
    }

    grid.innerHTML = '';
    items.forEach((item) => {
      const card = document.createElement('div');
      card.className = 'admin-gallery-card';

      const isAnnotated = item.filename.includes('annotated') || item.filename.startsWith('latest_');
      const rawUrl = resolveMediaUrl(item.url_raw, token);

      card.innerHTML = `
        <div class="admin-gal-thumb-wrapper">
          <img src="${rawUrl}" alt="${item.filename}" class="admin-gal-thumb" loading="lazy" />
          <span class="admin-gal-badge ${isAnnotated ? 'annotated' : 'raw'}">
            ${isAnnotated ? 'Detecciones' : 'Original'}
          </span>
          <button class="admin-gal-zoom-btn" title="Ver imagen">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
              <line x1="11" y1="8" x2="11" y2="14"></line>
              <line x1="8" y1="11" x2="14" y2="11"></line>
            </svg>
          </button>
        </div>
        <div class="admin-gal-meta">
          <div class="admin-gal-cam">${item.camera_id}</div>
          <div class="admin-gal-file">${item.date_str}</div>
        </div>
      `;

      const zoomTrigger = card.querySelector('.admin-gal-thumb-wrapper');
      zoomTrigger.addEventListener('click', () => {
        openLightbox(item, token);
      });

      grid.appendChild(card);
    });
  } catch (err) {
    grid.innerHTML = `<div class="admin-error">Error al cargar: ${err.message}</div>`;
  }
}

/**
 * Open Lightbox Modal
 */
function openLightbox(item, token) {
  if (activeLightbox && activeLightbox.parentNode) {
    activeLightbox.parentNode.removeChild(activeLightbox);
  }

  const rawUrl = resolveMediaUrl(item.url_raw, token);
  const annotatedUrl = resolveMediaUrl(item.url_annotated, token);

  const lightbox = document.createElement('div');
  lightbox.className = 'admin-lightbox active';
  lightbox.innerHTML = `
    <div class="admin-lightbox-content">
      <div class="admin-lightbox-header">
        <div class="admin-lightbox-title">
          <h4>Fotograma &bull; ${item.camera_id}</h4>
          <span>${item.date_str}</span>
        </div>
        <button class="admin-lightbox-close" id="adminLightboxClose" title="Cerrar (Esc)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      </div>

      <div class="admin-lightbox-body">
        <img src="${rawUrl}" alt="${item.filename}" class="admin-lightbox-img" />
      </div>

      <div class="admin-lightbox-footer">
        <a href="${rawUrl}" target="_blank" download="${item.filename}" class="admin-lightbox-action">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
          <span>Descargar</span>
        </a>
        <a href="${annotatedUrl}" target="_blank" class="admin-lightbox-action">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>
          <span>Ver con detecciones</span>
        </a>
      </div>
    </div>
  `;

  document.body.appendChild(lightbox);
  activeLightbox = lightbox;

  const closeBtn = lightbox.querySelector('#adminLightboxClose');
  const close = () => {
    if (lightbox.parentNode) {
      lightbox.parentNode.removeChild(lightbox);
    }
    activeLightbox = null;
  };

  closeBtn.addEventListener('click', close);
  lightbox.addEventListener('click', (e) => {
    if (e.target === lightbox) close();
  });

  const onKey = (e) => {
    if (e.key === 'Escape') {
      close();
      window.removeEventListener('keydown', onKey);
    }
  };
  window.addEventListener('keydown', onKey);
}
