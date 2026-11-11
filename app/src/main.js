/**
 * SGIP - Main Application Bootstrapper & Lifecycle Manager
 */

import { CONFIG } from './config.js';
import { spotsDatabase } from './spots-data.js';
import { Store } from './state.js';
import { mapCameraSpotToSlotId } from './mapping.js';
import { PollingManager, fetchAnalyticsSummary, fetchAnalyticsTimeline } from './api.js';
import { ViewportController, getSpotCentroid } from './viewport.js';
import { initDrawer, openSpot, closeDrawer } from './drawer.js';
import { isAdminRouteRequested, initAdmin } from './admin.js';

document.addEventListener('DOMContentLoaded', () => {
  // 1. Initialize Reactive Store with cloned spots
  const initialSpots = {};
  for (const [id, data] of Object.entries(spotsDatabase)) {
    initialSpots[id] = { ...data };
  }

  const store = new Store({
    spots: initialSpots,
    filter: 'all',
    isConnected: false,
  });

  // 2. Viewport elements
  const mapContainer = document.getElementById('mapContainer');
  const zoomLayer = document.getElementById('zoomLayer');
  const zoomBadge = document.getElementById('zoomBadge');
  const btnZoomIn = document.getElementById('btnZoomIn');
  const btnZoomOut = document.getElementById('btnZoomOut');
  const btnResetZoom = document.getElementById('btnResetZoom');

  const viewport = new ViewportController(mapContainer, null, zoomLayer, zoomBadge);

  if (btnZoomIn) {
    btnZoomIn.addEventListener('click', (e) => {
      e.stopPropagation();
      viewport.zoomIn();
    });
  }
  if (btnZoomOut) {
    btnZoomOut.addEventListener('click', (e) => {
      e.stopPropagation();
      viewport.zoomOut();
    });
  }
  if (btnResetZoom) {
    btnResetZoom.addEventListener('click', (e) => {
      e.stopPropagation();
      viewport.reset();
    });
  }

  // 3. Spot Drawer initialization
  initDrawer({
    onClose: () => {
      store.setState({ activeSpotId: null });
    },
  });

  // 4. Spot Node Clicks
  const spotNodes = document.querySelectorAll('.spot-node');
  spotNodes.forEach((node) => {
    node.addEventListener('click', (e) => {
      e.stopPropagation();
      if (viewport.hasMovedSignificantly) {
        return;
      }
      const spotId = node.getAttribute('data-id');
      const centroid = getSpotCentroid(node);
      viewport.zoomToSpot(centroid.cx, centroid.cy);
      openSpot(spotId, node, store);
    });
  });

  // Clicking neutral canvas background closes drawer & unfocuses
  if (mapContainer) {
    mapContainer.addEventListener('click', (e) => {
      if (viewport.hasMovedSignificantly) return;
      if (e.target.closest('.spot-node') || e.target.closest('.zoom-widget')) return;
      closeDrawer(store);
    });
  }

  // 5. Filter Buttons
  const filterBtns = document.querySelectorAll('.filter-btn');
  filterBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      filterBtns.forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      const nextFilter = btn.getAttribute('data-filter') || 'all';
      store.setState({ filter: nextFilter });
      applyFilterToDOM(nextFilter);
    });
  });

  function applyFilterToDOM(activeFilter) {
    spotNodes.forEach((node) => {
      const st = node.getAttribute('data-status');
      if (activeFilter === 'all') {
        node.classList.remove('dimmed');
      } else if (activeFilter === 'free') {
        node.classList.toggle('dimmed', st !== 'free');
      } else if (activeFilter === 'occupied') {
        node.classList.toggle('dimmed', st !== 'occupied');
      }
    });
  }

  // 6. Locations Search Dropdown
  const searchContainer = document.getElementById('searchContainer');
  const searchWrapper = document.getElementById('searchWrapper');
  const locationInput = document.getElementById('locationInput');
  const locationItems = document.querySelectorAll('.location-item');
  const toast = document.getElementById('toast');
  const toastMsg = document.getElementById('toastMsg');

  let toastTimer;
  function showToast(message) {
    clearTimeout(toastTimer);
    if (toastMsg) toastMsg.textContent = message;
    if (toast) {
      toast.classList.add('show');
      toastTimer = setTimeout(() => {
        toast.classList.remove('show');
      }, 3600);
    }
  }

  if (searchWrapper && searchContainer) {
    searchWrapper.addEventListener('click', (e) => {
      e.stopPropagation();
      searchContainer.classList.toggle('active');
    });

    document.addEventListener('click', (e) => {
      if (!searchContainer.contains(e.target)) {
        searchContainer.classList.remove('active');
      }
    });
  }

  locationItems.forEach((item) => {
    item.addEventListener('click', () => {
      const isActive = item.getAttribute('data-active') === 'true';
      const name = item.getAttribute('data-name');
      if (isActive) {
        if (locationInput) locationInput.value = name;
        locationItems.forEach((i) => i.classList.remove('selected'));
        item.classList.add('selected');
        if (searchContainer) searchContainer.classList.remove('active');
      } else {
        showToast(name + ' estará disponible próximamente. La locación activa es el Campus Principal UCE.');
        if (searchContainer) searchContainer.classList.remove('active');
      }
    });
  });

  // 7. Navbar Telemetry and Status Count Updates
  const apiStatusPill = document.getElementById('apiStatusPill');
  const apiStatusText = document.getElementById('apiStatusText');
  const cntFree = document.getElementById('cntFree');
  const cntOcc = document.getElementById('cntOcc');
  const cntWarn = document.getElementById('cntWarn');

  function renderSpots(state) {
    let freeCount = 0;
    let occCount = 0;
    let warnCount = 0;

    spotNodes.forEach((node) => {
      const spotId = node.getAttribute('data-id');
      const spot = state.spots[spotId];
      if (!spot) return;

      if (spot.status === 'free') freeCount++;
      else if (spot.status === 'occupied') occCount++;
      else warnCount++;

      node.setAttribute('data-status', spot.status);
      node.setAttribute('data-conf', (spot.conf || 94.0).toFixed(1));

      const rect = node.querySelector('rect');
      if (rect) {
        rect.classList.remove('free', 'occupied', 'warning');
        rect.classList.add(spot.status);
      }

      if (state.filter === 'all') {
        node.classList.remove('dimmed');
      } else if (state.filter === 'free') {
        node.classList.toggle('dimmed', spot.status !== 'free');
      } else if (state.filter === 'occupied') {
        node.classList.toggle('dimmed', spot.status !== 'occupied');
      }
    });

    if (cntFree) cntFree.textContent = freeCount;
    if (cntOcc) cntOcc.textContent = occCount;
    if (cntWarn) cntWarn.textContent = warnCount;
  }

  // Subscribe DOM renderer to store updates
  store.subscribe((state) => {
    renderSpots(state);
  });

  // Initial render
  renderSpots(store.getState());

  // 8. Polling Manager Integration
  function handleApiStatusUpdate(data) {
    if (!data || !data.cameras) return;
    const currentSpots = { ...store.getState().spots };
    let hasChanges = false;

    for (const [camId, camData] of Object.entries(data.cameras)) {
      if (!camData.spots) continue;
      camData.spots.forEach((sp) => {
        const slotId = mapCameraSpotToSlotId(camId, sp.spot_id);
        if (slotId && currentSpots[slotId]) {
          const newStatus = sp.occupied ? 'occupied' : 'free';
          const newConf = sp.confidence ? sp.confidence * 100 : 94.0;
          currentSpots[slotId] = {
            ...currentSpots[slotId],
            status: newStatus,
            conf: newConf,
            battery: camData.battery_percentage ?? currentSpots[slotId].battery,
          };
          hasChanges = true;
        }
      });
    }

    if (hasChanges) {
      store.setState({ spots: currentSpots });
    }
  }

  function handleApiConnectionChange(connected) {
    store.setState({ isConnected: connected });
    if (!apiStatusPill || !apiStatusText) return;

    if (connected) {
      apiStatusPill.className = 'api-status-pill connected';
      apiStatusText.textContent = 'En Vivo (API Conectada)';
    } else {
      apiStatusPill.className = 'api-status-pill simulated';
      apiStatusText.textContent = 'Modo Autónomo';
    }
  }

  const polling = new PollingManager();
  polling.start(CONFIG.POLLING_INTERVAL_MS, handleApiStatusUpdate, handleApiConnectionChange);

  // 9. Analytics Modal Controller
  const btnOpenAnalytics = document.getElementById('btnOpenAnalytics');
  const analyticsModal = document.getElementById('analyticsModal');
  const analyticsModalBackdrop = document.getElementById('analyticsModalBackdrop');
  const analyticsModalClose = document.getElementById('analyticsModalClose');
  const statTurnover = document.getElementById('statTurnover');
  const statAvgDuration = document.getElementById('statAvgDuration');
  const statAvgOccupancy = document.getElementById('statAvgOccupancy');
  const timelineChartBox = document.getElementById('timelineChartBox');

  function openAnalytics() {
    if (!analyticsModal) return;
    analyticsModal.classList.add('active');
    if (analyticsModalBackdrop) analyticsModalBackdrop.classList.add('active');
    loadAnalytics();
  }

  function closeAnalytics() {
    if (!analyticsModal) return;
    analyticsModal.classList.remove('active');
    if (analyticsModalBackdrop) analyticsModalBackdrop.classList.remove('active');
  }

  if (btnOpenAnalytics) btnOpenAnalytics.addEventListener('click', openAnalytics);
  if (analyticsModalClose) analyticsModalClose.addEventListener('click', closeAnalytics);
  if (analyticsModalBackdrop) analyticsModalBackdrop.addEventListener('click', closeAnalytics);

  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeAnalytics();
      if (searchContainer) searchContainer.classList.remove('active');
    }
  });

  async function loadAnalytics() {
    const summary = await fetchAnalyticsSummary(2.0);
    const timeline = await fetchAnalyticsTimeline(2.0, 15);

    if (summary) {
      if (statTurnover) statTurnover.textContent = (summary.turnover_rate_per_stall || 0.35).toFixed(2);
      if (statAvgDuration) statAvgDuration.textContent = Math.round(summary.average_duration_minutes || 25) + ' min';
      if (statAvgOccupancy) statAvgOccupancy.textContent = (summary.average_occupancy_percentage || 42.0).toFixed(1) + '%';
    } else {
      const state = store.getState();
      const occ = Object.values(state.spots).filter((s) => s.status === 'occupied').length;
      const pct = (occ / CONFIG.TOTAL_SPOTS_CAMPUS) * 100;
      if (statTurnover) statTurnover.textContent = '0.38';
      if (statAvgDuration) statAvgDuration.textContent = '24 min';
      if (statAvgOccupancy) statAvgOccupancy.textContent = pct.toFixed(1) + '%';
    }

    renderTimelineChart(timeline);
  }

  function renderTimelineChart(timelineData) {
    if (!timelineChartBox) return;

    let data = timelineData;
    if (!data || !Array.isArray(data) || data.length === 0) {
      data = [
        { time_label: '06:00', occupied_avg: 24, free_avg: 195 },
        { time_label: '06:15', occupied_avg: 48, free_avg: 171 },
        { time_label: '06:30', occupied_avg: 82, free_avg: 137 },
        { time_label: '06:45', occupied_avg: 118, free_avg: 101 },
        { time_label: '07:00', occupied_avg: 154, free_avg: 65 },
        { time_label: '07:15', occupied_avg: 146, free_avg: 73 },
        { time_label: '07:30', occupied_avg: 138, free_avg: 81 },
        { time_label: '07:45', occupied_avg: 122, free_avg: 97 },
      ];
    }

    const maxSpots = CONFIG.TOTAL_SPOTS_CAMPUS;
    const chartHeight = 100;
    const barWidth = 24;
    const step = 560 / Math.max(1, data.length);

    let barsHtml = '';
    data.forEach((item, idx) => {
      const x = 30 + idx * step;
      const occH = Math.max(4, Math.round(((item.occupied_avg || 0) / maxSpots) * chartHeight));
      const occY = 10 + (chartHeight - occH);

      barsHtml += `<g class="timeline-bar" transform="translate(${x}, 0)">`;
      barsHtml += `<rect x="0" y="10" width="${barWidth}" height="${chartHeight}" rx="4" fill="#f1f5f9" />`;
      barsHtml += `<rect x="0" y="${occY}" width="${barWidth}" height="${occH}" rx="4" fill="#dc2626" />`;
      barsHtml += `<text x="${barWidth / 2}" y="${chartHeight + 28}" text-anchor="middle" font-size="11" font-weight="600" fill="#64748b">${item.time_label || ''}</text>`;
      barsHtml += `</g>`;
    });

    timelineChartBox.innerHTML =
      `<svg class="timeline-svg" viewBox="0 0 600 145">` +
      `<line x1="15" y1="${chartHeight + 10}" x2="585" y2="${chartHeight + 10}" stroke="#e2e8f0" stroke-width="1" />` +
      barsHtml +
      `</svg>`;
  }

  // 10. Check if hidden /admin route requested
  if (isAdminRouteRequested()) {
    initAdmin(store);
  }
});
