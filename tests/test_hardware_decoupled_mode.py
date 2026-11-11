import os
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from server.main import app
from server.state import server_state


def create_synthetic_frame(color: tuple, text: str) -> bytes:
    """Creates a synthetic BGR image frame and encodes it to JPEG bytes."""
    img = np.full((720, 1280, 3), color, dtype=np.uint8)
    cv2.putText(
        img,
        text,
        (100, 360),
        cv2.FONT_HERSHEY_SIMPLEX,
        2.0,
        (255, 255, 255),
        3,
        cv2.LINE_AA,
    )
    success, buffer = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    assert success, "Failed to encode synthetic JPEG frame"
    return buffer.tobytes()


def run_tests() -> int:
    print("=" * 70)
    print("PARQUEAME HARDWARE-DECOUPLED TEST MODE VERIFICATION SUITE")
    print("=" * 70)

    # Clean any leftover disk artifacts
    raw_disk_check = Path("storage/cameras/raw_cam_01.jpg")
    if raw_disk_check.exists():
        raw_disk_check.unlink()

    with TestClient(app) as client:
        # -------------------------------------------------------------
        # TC-HDM-01: Baseline Live Mode (PARQUEAME_TEST_MODE = False)
        # -------------------------------------------------------------
        print("\n[TC-HDM-01] Verifying baseline live mode with indoor frame...")
        server_state.test_mode_enabled = False
        blank_frame_bytes = create_synthetic_frame((50, 50, 50), "Indoor Lab Desk - Blank Frame")

        up_res = client.post(
            "/api/v1/upload/cam_01?battery=88.5&voltage=3.98",
            files={"file": ("indoor_desk.jpg", blank_frame_bytes, "image/jpeg")},
        )
        assert up_res.status_code == 200, f"Upload failed: {up_res.text}"
        data = up_res.json()
        assert data["camera_id"] == "cam_01"
        assert data["occupied_spots"] == 0, f"Expected 0 occupied spots on blank frame, got {data['occupied_spots']}"
        print(f"  [✓] Baseline upload processed: {data['occupied_spots']} occupied spots on blank frame.")

        # Verify raw image endpoint returns exact uploaded frame
        raw_res = client.get("/api/v1/cameras/cam_01/raw")
        assert raw_res.status_code == 200, f"Raw endpoint failed: {raw_res.text}"
        assert raw_res.headers["content-type"] == "image/jpeg"
        assert raw_res.content == blank_frame_bytes, "Raw endpoint bytes do not match uploaded frame"
        print("  [✓] GET /api/v1/cameras/cam_01/raw returned exact raw hardware bytes.")

        # Verify no disk file was written (memory-only retention policy)
        raw_disk_path = Path("storage/cameras/raw_cam_01.jpg")
        assert not raw_disk_path.exists(), "storage/cameras/raw_cam_01.jpg should NOT be written to disk"
        print("  [✓] Zero disk writes verified: frame held exclusively in RAM cache.")

        # -------------------------------------------------------------
        # TC-HDM-02: Hardware-Decoupled Test Mode Activation
        # -------------------------------------------------------------
        print("\n[TC-HDM-02] Verifying decoupled test mode with indoor mug photo...")
        server_state.test_mode_enabled = True

        mug_frame_bytes = create_synthetic_frame((80, 40, 20), "Lab Indoor Coffee Mug")
        up_res2 = client.post(
            "/api/v1/upload/cam_01?battery=82.0&voltage=3.85",
            files={"file": ("coffee_mug.jpg", mug_frame_bytes, "image/jpeg")},
        )
        assert up_res2.status_code == 200, f"Upload failed in test mode: {up_res2.text}"
        data2 = up_res2.json()

        # Telemetry should be updated from the real camera
        status_res = client.get("/api/v1/cameras/cam_01/status")
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert status_data["battery_percentage"] == 82.0
        assert status_data["battery_voltage"] == 3.85

        # Raw endpoint must return the indoor coffee mug photo
        raw_res2 = client.get("/api/v1/cameras/cam_01/raw")
        assert raw_res2.status_code == 200
        assert raw_res2.content == mug_frame_bytes, "Raw endpoint did not preserve indoor coffee mug bytes"
        print("  [✓] Real indoor frame preserved at /api/v1/cameras/cam_01/raw.")

        # Annotated image served at /api/v1/cameras/cam_01/image must NOT be the blank mug frame
        annotated_res = client.get("/api/v1/cameras/cam_01/image")
        assert annotated_res.status_code == 200
        assert annotated_res.content != mug_frame_bytes, "Annotated frame must reflect decoupled sample frame"
        print("  [✓] Decoupled detection overlay served at /api/v1/cameras/cam_01/image.")

        # -------------------------------------------------------------
        # TC-HDM-03: Sequential Sample Frame Progression
        # -------------------------------------------------------------
        print("\n[TC-HDM-03] Verifying sequential sample frame rotation...")
        server_state.sample_indices["cam_01"] = 0
        p1 = server_state.get_next_sample_frame("cam_01")
        p2 = server_state.get_next_sample_frame("cam_01")
        p3 = server_state.get_next_sample_frame("cam_01")
        assert p1 is not None and p2 is not None and p3 is not None
        assert p1 != p2, f"Expected sequential frame rotation, got same path: {p1}"
        assert p2 != p3, f"Expected sequential frame rotation, got same path: {p2}"
        print(f"  [✓] Sequential frames advanced: {p1.name} -> {p2.name} -> {p3.name}.")

        # -------------------------------------------------------------
        # TC-HDM-04: Dynamic Runtime Switching back to Live Inference
        # -------------------------------------------------------------
        print("\n[TC-HDM-04] Switching test mode back to False at runtime...")
        server_state.test_mode_enabled = False

        blank_white_frame = create_synthetic_frame((255, 255, 255), "Indoor Wall Photo")
        up_res3 = client.post(
            "/api/v1/upload/cam_01",
            files={"file": ("wall.jpg", blank_white_frame, "image/jpeg")},
        )
        assert up_res3.status_code == 200
        data3 = up_res3.json()
        assert data3["occupied_spots"] == 0, "Expected live inference to revert to 0 occupied spots"

        raw_res3 = client.get("/api/v1/cameras/cam_01/raw")
        assert raw_res3.status_code == 200
        assert raw_res3.content == blank_white_frame, "Raw image not updated to latest wall frame"
        print("  [✓] Live inference reverted immediately on test_mode_enabled = False.")

        # -------------------------------------------------------------
        # TC-HDM-05: Environment Variable Activation
        # -------------------------------------------------------------
        print("\n[TC-HDM-05] Verifying PARQUEAME_TEST_MODE environment variable control...")
        server_state.test_mode_enabled = None  # Clear runtime override
        os.environ["PARQUEAME_TEST_MODE"] = "true"
        assert server_state.test_mode_enabled is True, "Expected test_mode_enabled=True via env var"

        os.environ["PARQUEAME_TEST_MODE"] = "1"
        assert server_state.test_mode_enabled is True, "Expected test_mode_enabled=True via '1'"

        os.environ["PARQUEAME_TEST_MODE"] = "false"
        assert server_state.test_mode_enabled is False, "Expected test_mode_enabled=False via env var"

        os.environ["PARQUEAME_TEST_MODE"] = "0"
        assert server_state.test_mode_enabled is False, "Expected test_mode_enabled=False via '0'"

        del os.environ["PARQUEAME_TEST_MODE"]
        assert server_state.test_mode_enabled is False, "Expected test_mode_enabled=False with no env var"
        print("  [✓] Environment variable toggle validated.")

        # -------------------------------------------------------------
        # TC-HDM-06: Per-Camera Test Mode Configuration
        # -------------------------------------------------------------
        print("\n[TC-HDM-06] Verifying camera-specific test mode config...")
        server_state.test_mode_enabled = False  # Global disabled
        cam_cfg = server_state.camera_configs.get("cam_01")
        assert cam_cfg is not None

        # Temporarily enable test mode on cam_01 config
        original_test_mode = cam_cfg.test_mode
        cam_cfg.test_mode = {"enabled": True, "sample_dir": "test-samples/cam_01"}
        assert cam_cfg.test_mode_enabled is True
        assert cam_cfg.test_mode_sample_dir == "test-samples/cam_01"

        test_frame = create_synthetic_frame((10, 10, 10), "Per-Camera Test Frame")
        up_cam = client.post(
            "/api/v1/upload/cam_01",
            files={"file": ("test.jpg", test_frame, "image/jpeg")},
        )
        assert up_cam.status_code == 200
        cam_cfg.test_mode = original_test_mode  # Restore original
        print("  [✓] Camera-specific test mode configuration evaluated correctly.")

        # -------------------------------------------------------------
        # TC-HDM-07: Error Handling & Edge Cases
        # -------------------------------------------------------------
        print("\n[TC-HDM-07] Verifying error handling on raw camera endpoints...")
        # Unregistered camera
        res_404 = client.get("/api/v1/cameras/non_existent_camera/raw")
        assert res_404.status_code == 404, f"Expected 404 for unregistered camera, got {res_404.status_code}"

        # Registered camera with no uploads
        with server_state.lock:
            server_state.latest_raw_images.pop("cam_02", None)
        raw_cam2_file = Path("storage/cameras/raw_cam_02.jpg")
        if raw_cam2_file.exists():
            raw_cam2_file.unlink()

        res_cam2 = client.get("/api/v1/cameras/cam_02/raw")
        assert res_cam2.status_code == 404, f"Expected 404 for camera with no uploads, got {res_cam2.status_code}"

        # Graceful fallback when sample directory is missing or empty
        with tempfile.TemporaryDirectory() as empty_dir:
            fallback_sample = server_state.get_next_sample_frame("cam_01", sample_dir=empty_dir)
            assert fallback_sample is None, "Expected None for empty sample directory"

        print("  [✓] Error responses and missing directory fallbacks verified.")

    print("\n" + "=" * 70)
    print("ALL HARDWARE-DECOUPLED TEST MODE CHECKS PASSED SUCCESSFULLY (7/7)")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(run_tests())
