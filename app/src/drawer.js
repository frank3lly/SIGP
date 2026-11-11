/**
 * SGIP - Spot Details Drawer & Inspection Modal
 */

import { getSpotCameraInfo } from './mapping.js';
import { getCameraImageUrl } from './api.js';

let selectedSpotNode = null;

export function getSelectedSpotNode() {
  return selectedSpotNode;
}

export function setSelectedSpotNode(node) {
  selectedSpotNode = node;
}

export function initDrawer({ onClose } = {}) {
  const drawer = document.getElementById('spotDrawer');
  const drawerBackdrop = document.getElementById('drawerBackdrop');
  const drawerClose = document.getElementById('drawerClose');

  function close() {
    closeDrawer();
    if (onClose) onClose();
  }

  if (drawerClose) drawerClose.addEventListener('click', close);
  if (drawerBackdrop) drawerBackdrop.addEventListener('click', close);

  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && drawer && drawer.classList.contains('active')) {
      close();
    }
  });
}

export function openSpot(spotId, node, store) {
  const state = store.getState();
  const spot = state.spots[spotId];
  if (!spot) return;

  const drawer = document.getElementById('spotDrawer');
  const drawerBackdrop = document.getElementById('drawerBackdrop');
  const drawerTitle = document.getElementById('drawerTitle');
  const drawerZone = document.getElementById('drawerZone');
  const drawerCard = document.getElementById('drawerCard');
  const drawerCardIcon = document.getElementById('drawerCardIcon');
  const drawerStatusText = document.getElementById('drawerStatusText');
  const drawerStatusDesc = document.getElementById('drawerStatusDesc');
  const drawerId = document.getElementById('drawerId');
  const drawerLoc = document.getElementById('drawerLoc');
  const drawerConf = document.getElementById('drawerConf');
  const drawerGps = document.getElementById('drawerGps');
  const drawerMapsBtn = document.getElementById('drawerMapsBtn');

  const drawerCameraSection = document.getElementById('drawerCameraSection');
  const drawerCamName = document.getElementById('drawerCamName');
  const drawerCamBattery = document.getElementById('drawerCamBattery');
  const drawerCamBatteryVal = document.getElementById('drawerCamBatteryVal');
  const drawerCameraImg = document.getElementById('drawerCameraImg');
  const drawerCameraEmpty = document.getElementById('drawerCameraEmpty');
  const drawerCameraMsg = document.getElementById('drawerCameraMsg');

  if (selectedSpotNode) {
    selectedSpotNode.classList.remove('selected');
    selectedSpotNode.classList.remove('active-spot');
  }
  selectedSpotNode = node;
  if (node) {
    node.classList.add('selected');
    node.classList.add('active-spot');
  }

  store.setState({ activeSpotId: spotId });

  if (drawerTitle) drawerTitle.textContent = 'Espacio ' + spot.id;
  if (drawerZone) drawerZone.textContent = spot.zone;
  if (drawerId) drawerId.textContent = spot.id;
  if (drawerLoc) drawerLoc.textContent = spot.zone + ' (' + spot.side + ')';
  if (drawerConf) drawerConf.textContent = (spot.conf || 94.0).toFixed(0) + '%';
  if (drawerGps) drawerGps.textContent = spot.lat.toFixed(6) + ', ' + spot.lng.toFixed(6);

  if (drawerCard) {
    drawerCard.className = 'drawer-card ' + spot.status;
  }

  if (spot.status === 'free') {
    if (drawerStatusText) drawerStatusText.textContent = 'Disponible';
    if (drawerStatusDesc) drawerStatusDesc.textContent = 'Espacio libre para estacionar';
    if (drawerCardIcon) drawerCardIcon.innerHTML = '<svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"></polyline></svg>';
  } else if (spot.status === 'occupied') {
    if (drawerStatusText) drawerStatusText.textContent = 'Ocupado';
    if (drawerStatusDesc) drawerStatusDesc.textContent = 'Espacio ocupado';
    if (drawerCardIcon) drawerCardIcon.innerHTML = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>';
  } else {
    if (drawerStatusText) drawerStatusText.textContent = 'Por confirmar';
    if (drawerStatusDesc) drawerStatusDesc.textContent = 'Estado en verificación';
    if (drawerCardIcon) drawerCardIcon.innerHTML = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>';
  }

  if (drawerMapsBtn) {
    drawerMapsBtn.href = 'https://www.google.com/maps/dir/?api=1&destination=' + spot.lat + ',' + spot.lng;
  }

  // Camera preview
  const camInfo = getSpotCameraInfo(spotId);
  if (camInfo && drawerCameraSection) {
    drawerCameraSection.style.display = 'flex';
    if (drawerCamName) drawerCamName.textContent = camInfo.cameraName;
    if (spot.battery !== undefined && spot.battery !== null) {
      if (drawerCamBattery) drawerCamBattery.style.display = 'flex';
      if (drawerCamBatteryVal) drawerCamBatteryVal.textContent = Math.round(spot.battery) + '%';
    } else {
      if (drawerCamBattery) drawerCamBattery.style.display = 'none';
    }

    if (state.isConnected) {
      if (drawerCameraImg) drawerCameraImg.style.display = 'none';
      if (drawerCameraEmpty) drawerCameraEmpty.style.display = 'flex';
      if (drawerCameraMsg) drawerCameraMsg.textContent = 'Cargando imagen...';

      const imgUrl = getCameraImageUrl(camInfo.cameraId);
      const testImg = new Image();
      testImg.onload = function () {
        if (drawerCameraImg) {
          drawerCameraImg.src = imgUrl;
          drawerCameraImg.style.display = 'block';
        }
        if (drawerCameraEmpty) drawerCameraEmpty.style.display = 'none';
      };
      testImg.onerror = function () {
        if (drawerCameraImg) drawerCameraImg.style.display = 'none';
        if (drawerCameraEmpty) {
          drawerCameraEmpty.style.display = 'flex';
          drawerCameraMsg.textContent = 'Sin imagen disponible';
        }
      };
      testImg.src = imgUrl;
    } else {
      if (drawerCameraImg) drawerCameraImg.style.display = 'none';
      if (drawerCameraEmpty) drawerCameraEmpty.style.display = 'flex';
      if (drawerCameraMsg) drawerCameraMsg.textContent = 'Sin imagen disponible';
    }
  } else if (drawerCameraSection) {
    drawerCameraSection.style.display = 'none';
  }

  if (drawer) drawer.classList.add('active');
  if (drawerBackdrop) drawerBackdrop.classList.add('active');
}

export function closeDrawer(store) {
  const drawer = document.getElementById('spotDrawer');
  const drawerBackdrop = document.getElementById('drawerBackdrop');

  if (drawer) drawer.classList.remove('active');
  if (drawerBackdrop) drawerBackdrop.classList.remove('active');

  if (selectedSpotNode) {
    selectedSpotNode.classList.remove('selected');
    selectedSpotNode.classList.remove('active-spot');
    selectedSpotNode = null;
  }

  if (store) {
    store.setState({ activeSpotId: null });
  }
}
