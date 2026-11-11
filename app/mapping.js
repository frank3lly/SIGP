/**
 * SGIP - Mapeo de Identificadores entre Servidor (Cámaras) y Plano Vectorial SVG
 * Conecta los identificadores internos (spot_01, spot_02...) de cam_01, cam_02, cam_03
 * con los identificadores físicos de plazas del plano vectorial del Campus UCE.
 */

(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.SGIPMapping = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // 1. Asignaciones de plazas para cada cámara según calibración física
  // cam_01 (28 plazas): Hilera R1 completa
  const cam01Spots = [];
  for (let i = 1; i <= 14; i++) cam01Spots.push('R1-A' + String(i).padStart(2, '0'));
  for (let i = 1; i <= 14; i++) cam01Spots.push('R1-B' + String(i).padStart(2, '0'));

  // cam_02 (40 plazas): Hileras L1 (18), L2 (18) y LW-top (4)
  const cam02Spots = [];
  for (let i = 1; i <= 9; i++) cam02Spots.push('L1-A' + String(i).padStart(2, '0'));
  for (let i = 1; i <= 9; i++) cam02Spots.push('L1-B' + String(i).padStart(2, '0'));
  for (let i = 1; i <= 9; i++) cam02Spots.push('L2-A' + String(i).padStart(2, '0'));
  for (let i = 1; i <= 9; i++) cam02Spots.push('L2-B' + String(i).padStart(2, '0'));
  for (let i = 1; i <= 4; i++) cam02Spots.push('LW-top-' + String(i).padStart(2, '0'));

  // cam_03 (100 plazas): Hileras R2 (28), R3 (28), R4 (28) y L3 (16)
  const cam03Spots = [];
  for (let i = 1; i <= 14; i++) cam03Spots.push('R2-A' + String(i).padStart(2, '0'));
  for (let i = 1; i <= 14; i++) cam03Spots.push('R2-B' + String(i).padStart(2, '0'));
  for (let i = 1; i <= 14; i++) cam03Spots.push('R3-A' + String(i).padStart(2, '0'));
  for (let i = 1; i <= 14; i++) cam03Spots.push('R3-B' + String(i).padStart(2, '0'));
  for (let i = 1; i <= 14; i++) cam03Spots.push('R4-A' + String(i).padStart(2, '0'));
  for (let i = 1; i <= 14; i++) cam03Spots.push('R4-B' + String(i).padStart(2, '0'));
  for (let i = 1; i <= 8; i++) cam03Spots.push('L3-A' + String(i).padStart(2, '0'));
  for (let i = 1; i <= 8; i++) cam03Spots.push('L3-B' + String(i).padStart(2, '0'));

  const CAMERA_SPOTS_MAP = {
    cam_01: cam01Spots,
    cam_02: cam02Spots,
    cam_03: cam03Spots
  };

  const CAMERA_METADATA = {
    cam_01: { name: 'Cámara 01 - Hilera R1', resolution: '1280x720', sector: 'Sector Este R1' },
    cam_02: { name: 'Cámara 02 - Hileras L1/L2', resolution: '1280x720', sector: 'Sector Oeste L1-L2' },
    cam_03: { name: 'Cámara 03 - Hileras R2/R3/R4/L3', resolution: '1280x720', sector: 'Sector Central UCE' }
  };

  // Construir índice inverso para búsqueda instantánea O(1) por plaza
  const SPOT_TO_CAMERA_MAP = {};
  for (const [camId, spotList] of Object.entries(CAMERA_SPOTS_MAP)) {
    spotList.forEach((slotId, index) => {
      const internalId = 'spot_' + String(index + 1).padStart(2, '0');
      SPOT_TO_CAMERA_MAP[slotId] = {
        cameraId: camId,
        internalId: internalId,
        cameraName: CAMERA_METADATA[camId].name,
        sector: CAMERA_METADATA[camId].sector
      };
    });
  }

  function getSpotCameraInfo(slotId) {
    return SPOT_TO_CAMERA_MAP[slotId] || null;
  }

  function mapCameraSpotToSlotId(cameraId, internalSpotId) {
    const list = CAMERA_SPOTS_MAP[cameraId];
    if (!list) return null;
    // Extraer número de spot_01, spot_02...
    const match = internalSpotId.match(/spot_(\d+)/);
    if (!match) return null;
    const index = parseInt(match[1], 10) - 1;
    if (index >= 0 && index < list.length) {
      return list[index];
    }
    return null;
  }

  return {
    CAMERA_SPOTS_MAP: CAMERA_SPOTS_MAP,
    CAMERA_METADATA: CAMERA_METADATA,
    SPOT_TO_CAMERA_MAP: SPOT_TO_CAMERA_MAP,
    getSpotCameraInfo: getSpotCameraInfo,
    mapCameraSpotToSlotId: mapCameraSpotToSlotId
  };
});
