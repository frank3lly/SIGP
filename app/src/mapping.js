/**
 * SGIP - Mapeo de Identificadores entre Servidor (Cámaras) y Plano Vectorial SVG
 */

// cam_02 (33 plazas): Hilera L4-B01..B08, L4-A01..A08, L3-B01..B09 y L3-A02..A09
const cam02Spots = [];
for (let i = 1; i <= 8; i++) cam02Spots.push('L4-B' + String(i).padStart(2, '0'));
for (let i = 1; i <= 8; i++) cam02Spots.push('L4-A' + String(i).padStart(2, '0'));
for (let i = 1; i <= 9; i++) cam02Spots.push('L3-B' + String(i).padStart(2, '0'));
for (let i = 2; i <= 9; i++) cam02Spots.push('L3-A' + String(i).padStart(2, '0'));

export const CAMERA_SPOTS_MAP = {
  cam_02: cam02Spots,
};

export const CAMERA_METADATA = {
  cam_02: { name: 'Cámara 02 - Hileras L4/L3', resolution: '1280x1024', sector: 'Sector L4/L3' },
};

// Índice inverso para búsqueda O(1)
export const SPOT_TO_CAMERA_MAP = {};
for (const [camId, spotList] of Object.entries(CAMERA_SPOTS_MAP)) {
  spotList.forEach((slotId, index) => {
    const internalId = 'spot_' + String(index + 1).padStart(2, '0');
    SPOT_TO_CAMERA_MAP[slotId] = {
      cameraId: camId,
      internalId: internalId,
      cameraName: CAMERA_METADATA[camId].name,
      sector: CAMERA_METADATA[camId].sector,
    };
  });
}

export function getSpotCameraInfo(slotId) {
  return SPOT_TO_CAMERA_MAP[slotId] || null;
}

export function mapCameraSpotToSlotId(cameraId, internalSpotId) {
  const list = CAMERA_SPOTS_MAP[cameraId];
  if (!list) return null;
  const match = internalSpotId.match(/spot_(\d+)/);
  if (!match) return null;
  const index = parseInt(match[1], 10) - 1;
  if (index >= 0 && index < list.length) {
    return list[index];
  }
  return null;
}

export function getMappingEntries(filterCameraId = 'all') {
  const entries = [];
  for (const [camId, spotList] of Object.entries(CAMERA_SPOTS_MAP)) {
    if (filterCameraId !== 'all' && filterCameraId !== camId) continue;
    spotList.forEach((slotId, index) => {
      const match = slotId.match(/(\d+)$/);
      const uiNum = match ? match[1] : String(index + 1).padStart(2, '0');
      entries.push({
        internalId: 'spot_' + String(index + 1).padStart(2, '0'),
        slotId: slotId,
        uiNum: uiNum,
        cameraId: camId,
        cameraName: CAMERA_METADATA[camId]?.name || camId,
        sector: CAMERA_METADATA[camId]?.sector || '',
        index: index + 1,
      });
    });
  }
  return entries;
}

if (typeof window !== 'undefined') {
  window.SGIPMapping = {
    CAMERA_SPOTS_MAP,
    CAMERA_METADATA,
    SPOT_TO_CAMERA_MAP,
    getSpotCameraInfo,
    mapCameraSpotToSlotId,
    getMappingEntries,
  };
}
