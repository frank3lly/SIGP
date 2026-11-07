import asyncio
import logging
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status

from detection.config_loader import CameraConfig
from detection.detector import VehicleDetector
from detection.occupancy import OccupancyResponse, evaluate_occupancy
from detection.visualizer import draw_detection_overlay
from server.schemas import CameraHotConfig, UploadResponse
from server.state import server_state
from storage.repository import record_detection_event

logger = logging.getLogger("parqueame.server.upload")
router = APIRouter(tags=["Ingestion"])


def normalize_frame_to_reference(
    image: np.ndarray,
    reference_resolution: Tuple[int, int],
) -> Tuple[np.ndarray, bool]:
    """Normalizes an incoming image frame to match the camera's calibrated reference resolution.
    
    Args:
        image: Decoded BGR image matrix from camera upload.
        reference_resolution: Expected (width, height) tuple from CameraConfig.
        
    Returns:
        Tuple containing:
            - Normalized image matrix matching (reference_width, reference_height).
            - Boolean flag indicating whether a resize operation was performed.
    """
    ref_w, ref_h = reference_resolution
    curr_h, curr_w = image.shape[:2]

    if (curr_w, curr_h) == (ref_w, ref_h):
        return image, False

    # Choose optimal interpolation method based on scale factor
    if curr_w > ref_w or curr_h > ref_h:
        interpolation = cv2.INTER_AREA
    else:
        interpolation = cv2.INTER_LINEAR

    resized_image = cv2.resize(image, (ref_w, ref_h), interpolation=interpolation)
    return resized_image, True


def process_frame_sync(
    image: np.ndarray,
    camera_cfg: CameraConfig,
    detector: VehicleDetector,
) -> Tuple[OccupancyResponse, bytes]:
    """Synchronous CPU/GPU worker running detection and spatial math with dimension normalization."""
    # 1. Normalize frame to camera calibration reference resolution
    normalized_image, was_resized = normalize_frame_to_reference(
        image, 
        tuple(camera_cfg.reference_resolution)
    )
    if was_resized:
        logger.info(
            f"[{camera_cfg.camera_id}] Ingested frame ({image.shape[1]}x{image.shape[0]}) "
            f"automatically normalized to reference ({camera_cfg.reference_resolution[0]}x{camera_cfg.reference_resolution[1]})."
        )

    # 2. Extract spot definitions in calibrated space
    spots = camera_cfg.to_detection_spots()

    # 3. Execute object detection on normalized image
    detections, latency_ms = detector.detect(normalized_image)

    # 4. Evaluate point-in-polygon occupancy
    occupancy_resp = evaluate_occupancy(
        spots=spots,
        detections=detections,
        camera_id=camera_cfg.camera_id,
        inference_time_ms=latency_ms,
    )

    # 5. Render detection overlay on normalized image
    annotated = draw_detection_overlay(
        image=normalized_image,
        occupancy_response=occupancy_resp,
        spots=spots,
        detections=detections,
        draw_anchors=True,
        draw_hud=True,
    )

    # 6. Encode annotated JPEG for web frontend consumption
    success, buffer = cv2.imencode(
        ".jpg",
        annotated,
        [int(cv2.IMWRITE_JPEG_QUALITY), 85],
    )
    annotated_bytes = buffer.tobytes() if success else b""

    return occupancy_resp, annotated_bytes


@router.post(
    "/api/v1/upload/{camera_id}",
    response_model=UploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload image from camera and trigger detection",
)
@router.post(
    "/upload/{camera_id}",
    response_model=UploadResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def upload_camera_frame(
    camera_id: str,
    file: UploadFile = File(..., description="JPEG or PNG image frame from camera"),
    battery: Optional[float] = None,
    voltage: Optional[float] = None,
) -> UploadResponse:
    # 1. Validate camera configuration exists
    camera_cfg = server_state.camera_configs.get(camera_id)
    if not camera_cfg:
        logger.warning(f"Upload rejected: camera '{camera_id}' is not registered.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found in server configuration.",
        )

    if server_state.detector is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Detection engine is not yet initialized.",
        )

    # 2. Read bytes into RAM and decode directly via OpenCV
    contents = await file.read()
    if not contents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Received empty file payload.",
        )

    nparr = np.frombuffer(contents, dtype=np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image encoding. File could not be decoded as an image.",
        )

    # 3. Hardware Audit: Store real hardware frame for diagnostic inspection
    raw_hardware_path = Path(f"storage/cameras/raw_{camera_id}.jpg")
    try:
        raw_hardware_path.parent.mkdir(parents=True, exist_ok=True)
        raw_hardware_path.write_bytes(contents)
    except Exception as e:
        logger.warning(f"Failed to save raw hardware frame for '{camera_id}': {e}")
    server_state.record_raw_image(camera_id, contents)

    # 4. Decoupled Test Mode: Check if test mode is enabled globally or per-camera
    is_test_mode = server_state.test_mode_enabled or getattr(camera_cfg, "test_mode_enabled", False)
    if is_test_mode:
        custom_dir = getattr(camera_cfg, "test_mode_sample_dir", None)
        sample_path = server_state.get_next_sample_frame(camera_id, sample_dir=custom_dir)
        if sample_path and sample_path.exists():
            detection_image = cv2.imread(str(sample_path))
            if detection_image is None or detection_image.size == 0:
                logger.warning(
                    f"[{camera_id}] Failed to decode sample image {sample_path}. Falling back to live image."
                )
                detection_image = image
            else:
                logger.info(
                    f"[{camera_id}] Hardware-decoupled test mode active: swapped live frame with sample {sample_path.name}"
                )
        else:
            logger.warning(
                f"[{camera_id}] Test mode active but no sample frames found. Falling back to live image."
            )
            detection_image = image
    else:
        detection_image = image

    # 5. Dispatch synchronous vision workload to threadpool
    try:
        occupancy_resp, annotated_bytes = await asyncio.to_thread(
            process_frame_sync,
            detection_image,
            camera_cfg,
            server_state.detector,
        )
    except Exception as e:
        logger.error(f"Inference pipeline failed for '{camera_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inference pipeline error: {str(e)}",
        )

    # 4. Record detection result and battery telemetry to state cache
    server_state.record_result(
        camera_id=camera_id,
        occupancy_resp=occupancy_resp,
        annotated_jpeg=annotated_bytes,
    )
    if battery is not None:
        server_state.record_battery(
            camera_id=camera_id,
            percentage=battery,
            voltage=voltage,
        )

    logger.info(
        f"Camera '{camera_id}' processed in {occupancy_resp.inference_time_ms:.1f}ms: "
        f"{occupancy_resp.occupied_count} occupied, {occupancy_resp.free_count} free."
    )

    # 5. Maintain rolling annotated JPEG buffer on disk
    image_path = None
    if annotated_bytes:
        try:
            images_dir = Path("storage/images")
            images_dir.mkdir(parents=True, exist_ok=True)
            saved_file = images_dir / f"latest_{camera_id}.jpg"
            saved_file.write_bytes(annotated_bytes)
            image_path = str(saved_file)
        except Exception as e:
            logger.warning(f"Failed to save rolling annotated frame for '{camera_id}': {e}")

    # 6. Persist detection event to SQLite database
    try:
        await asyncio.to_thread(
            record_detection_event,
            camera_id=camera_cfg.camera_id,
            timestamp=occupancy_resp.timestamp,
            inference_time_ms=occupancy_resp.inference_time_ms,
            total_spots=occupancy_resp.total_spots,
            occupied_spots=occupancy_resp.occupied_count,
            spots=occupancy_resp.spots,
            battery_percentage=battery,
            battery_voltage=voltage,
            image_path=image_path,
        )
    except Exception as e:
        logger.error(f"Failed to record detection event to SQLite: {e}")

    # 7. Return summary with dynamic hot-config
    hot_config = server_state.get_camera_hot_config(camera_id)
    return UploadResponse(
        status="success",
        camera_id=camera_id,
        processed_at=occupancy_resp.timestamp,
        inference_time_ms=occupancy_resp.inference_time_ms,
        total_spots=occupancy_resp.total_spots,
        occupied_spots=occupancy_resp.occupied_count,
        free_spots=occupancy_resp.free_count,
        config=hot_config,
    )


@router.get(
    "/api/v1/cameras/{camera_id}/config",
    response_model=CameraHotConfig,
    status_code=status.HTTP_200_OK,
    summary="Get dynamic hot-configuration for camera",
)
def get_camera_hot_config(camera_id: str) -> CameraHotConfig:
    if camera_id not in server_state.camera_configs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found in registered configurations.",
        )
    return server_state.get_camera_hot_config(camera_id)


@router.put(
    "/api/v1/cameras/{camera_id}/config",
    response_model=CameraHotConfig,
    status_code=status.HTTP_200_OK,
    summary="Update dynamic hot-configuration for camera",
)
def update_camera_hot_config(
    camera_id: str,
    payload: CameraHotConfig,
) -> CameraHotConfig:
    if camera_id not in server_state.camera_configs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found in registered configurations.",
        )
    server_state.set_camera_hot_config(camera_id, payload)
    logger.info(
        f"Updated hot-config for camera '{camera_id}': interval={payload.interval_seconds}s, "
        f"active={payload.active}, quality={payload.quality}"
    )
    return payload


@router.get(
    "/api/v1/cameras/{camera_id}/raw",
    status_code=status.HTTP_200_OK,
    summary="Get latest raw uploaded camera image without annotations",
    responses={
        200: {
            "content": {"image/jpeg": {}},
            "description": "Latest raw camera JPEG image.",
        },
        404: {"description": "Camera not found or no raw image uploaded yet."},
    },
)
@router.get(
    "/cameras/{camera_id}/raw",
    include_in_schema=False,
)
def get_camera_raw_image(camera_id: str) -> Response:
    if camera_id not in server_state.camera_configs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found in registered configurations.",
        )

    raw_bytes = server_state.get_camera_raw_image(camera_id)
    if not raw_bytes:
        raw_path = Path(f"storage/cameras/raw_{camera_id}.jpg")
        if raw_path.exists():
            try:
                raw_bytes = raw_path.read_bytes()
            except Exception:
                pass

    if not raw_bytes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No raw image has been uploaded yet for camera '{camera_id}'.",
        )

    return Response(
        content=raw_bytes,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
