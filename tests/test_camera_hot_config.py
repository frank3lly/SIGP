import os
import sys
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from server.main import app
from server.schemas import CameraHotConfig
from server.state import server_state


def run_tests() -> int:
    print("=" * 70)
    print("PARQUEAME CAMERA HOT-CONFIG & BIDIRECTIONAL PROTOCOL TEST SUITE")
    print("=" * 70)

    with TestClient(app) as client:
        # 1. Verify Default Hot-Config Endpoint
        print("\n[Phase 1] Verifying GET /api/v1/cameras/cam_01/config...")
        res = client.get("/api/v1/cameras/cam_01/config")
        assert res.status_code == 200, f"Failed to get camera config: {res.text}"
        data = res.json()
        assert "interval_seconds" in data, "Missing interval_seconds"
        assert "active" in data, "Missing active"
        assert "quality" in data, "Missing quality"
        assert "firmware_version" in data, "Missing firmware_version"
        assert data["interval_seconds"] == 30
        assert data["active"] is True
        print(f"  [✓] Default hot-config verified: interval={data['interval_seconds']}s, active={data['active']}.")

        # 2. Ingest Sample Frame and Verify Response Payload includes config
        print("\n[Phase 2] Verifying POST /api/v1/upload/cam_01 returns config payload...")
        sample_path = Path("test-samples/cam_01")
        sample_files = list(sample_path.glob("*.jpg")) if sample_path.exists() else []
        if sample_files:
            img_bytes = sample_files[0].read_bytes()
        else:
            dummy = np.zeros((720, 1280, 3), dtype=np.uint8)
            _, buf = cv2.imencode(".jpg", dummy)
            img_bytes = buf.tobytes()

        up_res = client.post(
            "/api/v1/upload/cam_01?battery=95.0&voltage=4.15",
            files={"file": ("frame.jpg", img_bytes, "image/jpeg")},
        )
        assert up_res.status_code == 200, f"Upload failed: {up_res.text}"
        up_data = up_res.json()
        assert "config" in up_data, "UploadResponse missing 'config' attribute"
        assert up_data["config"]["interval_seconds"] == 30
        assert up_data["config"]["active"] is True
        print("  [✓] Upload response embeds valid hot-config object.")

        # 3. Dynamic Hot-Configuration Update via Authenticated Admin PUT
        print("\n[Phase 3] Updating hot-config dynamically via Authenticated Admin PUT...")
        new_config = {
            "interval_seconds": 45,
            "active": False,
            "quality": 15,
            "firmware_version": "1.0.1",
        }
        # Verify unauthenticated direct PUT is blocked
        unauth_put = client.put("/api/v1/cameras/cam_01/config", json=new_config)
        assert unauth_put.status_code in [404, 405]
        print("  [✓] Unauthenticated direct PUT /api/v1/cameras/cam_01/config rejected as expected.")

        # Authenticate via admin
        os.environ["PARQUEAME_ADMIN_USER"] = "admin"
        os.environ["PARQUEAME_ADMIN_PASSWORD"] = "parqueame_secret_2026"
        login_res = client.post(
            "/api/v1/admin/login",
            json={"username": "admin", "password": "parqueame_secret_2026"},
        )
        assert login_res.status_code == 200
        admin_token = login_res.json()["token"]
        auth_headers = {"Authorization": f"Bearer {admin_token}"}

        put_res = client.put(
            "/api/v1/admin/cameras/cam_01/config",
            json=new_config,
            headers=auth_headers,
        )
        assert put_res.status_code == 200, f"PUT config failed: {put_res.text}"
        put_data = put_res.json()
        assert put_data["interval_seconds"] == 45
        assert put_data["active"] is False
        assert put_data["quality"] == 15
        assert put_data["firmware_version"] == "1.0.1"
        print("  [✓] Configuration updated dynamically: interval=45s, active=False.")

        # 4. Verify Next Upload reflects Updated Hot-Config
        print("\n[Phase 4] Ingesting next upload and verifying updated response...")
        up2_res = client.post(
            "/api/v1/upload/cam_01?battery=94.5&voltage=4.14",
            files={"file": ("frame2.jpg", img_bytes, "image/jpeg")},
        )
        assert up2_res.status_code == 200
        up2_data = up2_res.json()
        assert up2_data["config"]["interval_seconds"] == 45
        assert up2_data["config"]["active"] is False
        assert up2_data["config"]["quality"] == 15
        assert up2_data["config"]["firmware_version"] == "1.0.1"
        print("  [✓] Subsequent upload immediately reflected updated hot-config values.")

        # 5. Verify 404 for Unregistered Camera
        print("\n[Phase 5] Verifying 404 for unknown camera ID...")
        err_res = client.get("/api/v1/cameras/unknown_cam/config")
        assert err_res.status_code == 404
        err_put = client.put("/api/v1/admin/cameras/unknown_cam/config", json=new_config, headers=auth_headers)
        assert err_put.status_code == 404
        print("  [✓] Non-existent camera IDs properly rejected with 404.")

        # Reset cam_01 back to defaults
        server_state.set_camera_hot_config("cam_01", CameraHotConfig())

    print("\n" + "=" * 70)
    print("ALL CAMERA HOT-CONFIG TESTS PASSED.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(run_tests())
