import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, Union

import torch

from detection.config_loader import CameraConfig, load_camera_config
from detection.detector import VehicleDetector
from detection.occupancy import OccupancyResponse
from server.schemas import (
    CameraHotConfig,
    CameraStatusResponse,
    HealthResponse,
    OverallStatusResponse,
    SpotStatusItem,
)

logger = logging.getLogger("parqueame.server.state")


class ServerState:
    def __init__(self) -> None:
        self.start_time: float = time.time()
        self.detector: Optional[VehicleDetector] = None
        self.camera_configs: Dict[str, CameraConfig] = {}
        self.camera_hot_configs: Dict[str, CameraHotConfig] = {}
        self.latest_occupancy: Dict[str, OccupancyResponse] = {}
        self.latest_images: Dict[str, bytes] = {}
        self.latest_raw_images: Dict[str, bytes] = {}
        self.latest_battery: Dict[str, Dict[str, Any]] = {}
        self.sample_indices: Dict[str, int] = {}
        self._test_mode_override: Optional[bool] = None
        self.lock = threading.Lock()

    def initialize(self, config_dir: str = "config/cameras") -> None:
        logger.info("Initializing ServerState: Preloading AI detector and camera configs...")
        # 1. Initialize YOLOv8 Detector in GPU VRAM
        self.detector = VehicleDetector()

        # 2. Preload Camera Configurations
        cfg_path = Path(config_dir)
        with self.lock:
            self.camera_configs.clear()
            self.camera_hot_configs.clear()

        if cfg_path.exists():
            for p in sorted(cfg_path.glob("*.json")):
                try:
                    cfg = load_camera_config(p)
                    with self.lock:
                        self.camera_configs[cfg.camera_id] = cfg
                        hot_data = getattr(cfg, "hot_config", None) or {}
                        self.camera_hot_configs[cfg.camera_id] = (
                            CameraHotConfig(**hot_data)
                            if isinstance(hot_data, dict)
                            else CameraHotConfig()
                        )
                    logger.info(f"Loaded configuration for camera '{cfg.camera_id}' ({len(cfg.spots)} spots)")
                except Exception as e:
                    logger.error(f"Failed to load camera config '{p}': {e}")
        logger.info(f"ServerState initialized with {len(self.camera_configs)} cameras.")

    def get_camera_hot_config(self, camera_id: str) -> CameraHotConfig:
        with self.lock:
            if camera_id in self.camera_hot_configs:
                return self.camera_hot_configs[camera_id]
            return CameraHotConfig()

    def set_camera_hot_config(self, camera_id: str, hot_config: CameraHotConfig) -> None:
        with self.lock:
            self.camera_hot_configs[camera_id] = hot_config

    def record_result(
        self,
        camera_id: str,
        occupancy_resp: OccupancyResponse,
        annotated_jpeg: Optional[bytes] = None,
    ) -> None:
        with self.lock:
            self.latest_occupancy[camera_id] = occupancy_resp
            if annotated_jpeg is not None:
                self.latest_images[camera_id] = annotated_jpeg

    def record_battery(
        self,
        camera_id: str,
        percentage: float,
        voltage: Optional[float] = None,
    ) -> None:
        with self.lock:
            self.latest_battery[camera_id] = {
                "percentage": round(percentage, 2),
                "voltage": round(voltage, 3) if voltage is not None else None,
                "updated_at": time.time(),
            }

    def get_camera_status(self, camera_id: str) -> Optional[CameraStatusResponse]:
        with self.lock:
            cfg = self.camera_configs.get(camera_id)
            if not cfg:
                return None

            latest = self.latest_occupancy.get(camera_id)
            bat = self.latest_battery.get(camera_id, {})
            bat_pct = bat.get("percentage")
            bat_v = bat.get("voltage")
            bat_ts = bat.get("updated_at")
            spots_list = []

            if latest:
                # Map spot occupancy
                latest_map = {s.spot_id: s for s in latest.spots}
                for spot_cfg in cfg.spots:
                    match = latest_map.get(spot_cfg.id)
                    spots_list.append(
                        SpotStatusItem(
                            spot_id=spot_cfg.id,
                            occupied=match.occupied if match else False,
                            confidence=match.confidence if match else 0.0,
                            polygon=spot_cfg.polygon,
                        )
                    )
                tot = len(cfg.spots)
                occ = latest.occupied_count
                rate = round(occ / tot, 4) if tot > 0 else 0.0
                return CameraStatusResponse(
                    camera_id=camera_id,
                    name=cfg.name,
                    total_spots=tot,
                    occupied_spots=occ,
                    free_spots=latest.free_count,
                    occupancy_rate=rate,
                    last_processed_at=latest.timestamp,
                    inference_time_ms=latest.inference_time_ms,
                    battery_percentage=bat_pct,
                    battery_voltage=bat_v,
                    battery_updated_at=bat_ts,
                    spots=spots_list,
                )
            else:
                # No frame received yet; all default to vacant
                for spot_cfg in cfg.spots:
                    spots_list.append(
                        SpotStatusItem(
                            spot_id=spot_cfg.id,
                            occupied=False,
                            confidence=0.0,
                            polygon=spot_cfg.polygon,
                        )
                    )
                return CameraStatusResponse(
                    camera_id=camera_id,
                    name=cfg.name,
                    total_spots=len(cfg.spots),
                    occupied_spots=0,
                    free_spots=len(cfg.spots),
                    occupancy_rate=0.0,
                    last_processed_at=None,
                    inference_time_ms=None,
                    battery_percentage=bat_pct,
                    battery_voltage=bat_v,
                    battery_updated_at=bat_ts,
                    spots=spots_list,
                )

    def get_overall_status(self) -> OverallStatusResponse:
        with self.lock:
            cam_ids = list(self.camera_configs.keys())

        cameras_map: Dict[str, CameraStatusResponse] = {}
        total_spots = 0
        total_occupied = 0
        total_free = 0

        for cid in cam_ids:
            stat = self.get_camera_status(cid)
            if stat:
                cameras_map[cid] = stat
                total_spots += stat.total_spots
                total_occupied += stat.occupied_spots
                total_free += stat.free_spots

        overall_rate = round(total_occupied / total_spots, 4) if total_spots > 0 else 0.0
        return OverallStatusResponse(
            total_spots=total_spots,
            total_occupied=total_occupied,
            total_free=total_free,
            occupied_spots=total_occupied,
            free_spots=total_free,
            occupancy_rate=overall_rate,
            timestamp=time.time(),
            cameras=cameras_map,
        )

    def get_health(self) -> HealthResponse:
        cuda_ok = torch.cuda.is_available()
        dev_name = "CPU"
        if cuda_ok:
            try:
                dev_name = torch.cuda.get_device_name(0)
            except Exception:
                dev_name = "CUDA (Unknown Device)"

        with self.lock:
            reg_count = len(self.camera_configs)

        return HealthResponse(
            status="healthy",
            uptime_seconds=round(time.time() - self.start_time, 1),
            cuda_available=cuda_ok,
            device_name=dev_name,
            registered_cameras=reg_count,
            timestamp=time.time(),
        )

    def get_camera_image(self, camera_id: str) -> Optional[bytes]:
        with self.lock:
            return self.latest_images.get(camera_id)

    @property
    def test_mode_enabled(self) -> bool:
        if self._test_mode_override is not None:
            return self._test_mode_override
        env_val = os.getenv("PARQUEAME_TEST_MODE", "").strip().lower()
        return env_val in ("true", "1", "yes")

    @test_mode_enabled.setter
    def test_mode_enabled(self, value: Optional[bool]) -> None:
        self._test_mode_override = value

    def record_raw_image(self, camera_id: str, raw_jpeg: bytes) -> None:
        with self.lock:
            self.latest_raw_images[camera_id] = raw_jpeg

    def get_camera_raw_image(self, camera_id: str) -> Optional[bytes]:
        with self.lock:
            return self.latest_raw_images.get(camera_id)

    def get_next_sample_frame(
        self,
        camera_id: str,
        sample_dir: Optional[Union[str, Path]] = None,
    ) -> Optional[Path]:
        """Retrieves the next sequential sample frame path for a camera, wrapping around sequentially."""
        if sample_dir:
            dir_path = Path(sample_dir)
        else:
            cfg = self.camera_configs.get(camera_id)
            custom_dir = getattr(cfg, "test_mode_sample_dir", None) if cfg else None
            dir_path = Path(custom_dir) if custom_dir else Path("test-samples") / camera_id

        if not dir_path.exists() or not dir_path.is_dir():
            logger.warning(
                f"Sample frame directory '{dir_path}' does not exist for camera '{camera_id}'"
            )
            return None

        valid_extensions = {".jpg", ".jpeg", ".png"}
        sample_files = sorted(
            [p for p in dir_path.iterdir() if p.is_file() and p.suffix.lower() in valid_extensions]
        )

        if not sample_files:
            logger.warning(f"No sample images found in '{dir_path}' for camera '{camera_id}'")
            return None

        with self.lock:
            idx = self.sample_indices.get(camera_id, 0)
            selected = sample_files[idx % len(sample_files)]
            self.sample_indices[camera_id] = (idx + 1) % len(sample_files)
            return selected


server_state = ServerState()
