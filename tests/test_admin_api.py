#!/usr/bin/env python3
"""Automated verification suite for Stage 551: Admin Authentication & Hardware Gallery API."""

import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest
from fastapi.testclient import TestClient

from server.main import app
from server.state import server_state


class TestAdminAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["PARQUEAME_ADMIN_USER"] = "admin"
        os.environ["PARQUEAME_ADMIN_PASSWORD"] = "parqueame_secret_2026"
        server_state.initialize(config_dir="config/cameras")
        if not server_state.camera_configs:
            from detection.config_loader import CameraConfig, SpotConfig
            dummy_cfg = CameraConfig(
                camera_id="cam_01",
                name="Test Camera 01",
                reference_resolution=[1280, 720],
                spots=[
                    SpotConfig(
                        id="A-01",
                        polygon=[[10, 10], [100, 10], [100, 100], [10, 100]],
                    )
                ],
            )
            server_state.camera_configs["cam_01"] = dummy_cfg
        cls.client = TestClient(app)

    def test_01_unauthenticated_access_rejected(self):
        # Accessing protected endpoints without header returns 401
        res = self.client.get("/api/v1/admin/me")
        self.assertEqual(res.status_code, 401)

        res = self.client.get("/api/v1/admin/gallery")
        self.assertEqual(res.status_code, 401)

        res = self.client.get("/api/v1/admin/cameras")
        self.assertEqual(res.status_code, 401)

    def test_02_invalid_credentials_rejected(self):
        res = self.client.post(
            "/api/v1/admin/login",
            json={"username": "admin", "password": "wrong_password"},
        )
        self.assertEqual(res.status_code, 401)
        self.assertIn("Invalid administrative credentials", res.json()["detail"])

    def test_03_valid_login_and_session_validation(self):
        res = self.client.post(
            "/api/v1/admin/login",
            json={"username": "admin", "password": "parqueame_secret_2026"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "authenticated")
        self.assertIn("token", data)
        self.assertIn("expires_at", data)
        self.assertEqual(data["user"], "admin")

        token = data["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Verify /api/v1/admin/me
        me_res = self.client.get("/api/v1/admin/me", headers=headers)
        self.assertEqual(me_res.status_code, 200)
        me_data = me_res.json()
        self.assertEqual(me_data["user"], "admin")
        self.assertTrue(me_data["valid"])

    def test_04_gallery_endpoint(self):
        # Login
        login_res = self.client.post(
            "/api/v1/admin/login",
            json={"username": "admin", "password": "parqueame_secret_2026"},
        )
        token = login_res.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Request gallery
        gallery_res = self.client.get("/api/v1/admin/gallery?limit=10", headers=headers)
        self.assertEqual(gallery_res.status_code, 200)
        data = gallery_res.json()
        self.assertIn("total", data)
        self.assertIn("items", data)
        self.assertLessEqual(len(data["items"]), 10)

        if data["items"]:
            item = data["items"][0]
            self.assertIn("camera_id", item)
            self.assertIn("timestamp", item)
            self.assertIn("date_str", item)
            self.assertIn("url_raw", item)
            self.assertIn("url_annotated", item)

    def test_05_admin_cameras_and_config_update(self):
        # Login
        login_res = self.client.post(
            "/api/v1/admin/login",
            json={"username": "admin", "password": "parqueame_secret_2026"},
        )
        token = login_res.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # List cameras
        cams_res = self.client.get("/api/v1/admin/cameras", headers=headers)
        self.assertEqual(cams_res.status_code, 200)
        cameras = cams_res.json()["cameras"]
        self.assertGreater(len(cameras), 0)

        target_cam = cameras[0]["camera_id"]

        # Update hot-config
        new_config = {
            "interval_seconds": 45,
            "active": True,
            "quality": 14,
            "firmware_version": "1.0.1",
        }
        put_res = self.client.put(
            f"/api/v1/admin/cameras/{target_cam}/config",
            json=new_config,
            headers=headers,
        )
        self.assertEqual(put_res.status_code, 200)
        updated = put_res.json()
        self.assertEqual(updated["interval_seconds"], 45)
        self.assertEqual(updated["quality"], 14)

        # Verify state reflected
        hot_cfg = server_state.get_camera_hot_config(target_cam)
        self.assertEqual(hot_cfg.interval_seconds, 45)
        self.assertEqual(hot_cfg.quality, 14)

    def test_06_logout_invalidates_token(self):
        # Login
        login_res = self.client.post(
            "/api/v1/admin/login",
            json={"username": "admin", "password": "parqueame_secret_2026"},
        )
        token = login_res.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Logout
        logout_res = self.client.post("/api/v1/admin/logout", headers=headers)
        self.assertEqual(logout_res.status_code, 200)
        self.assertEqual(logout_res.json()["status"], "logged_out")

        # Subsequent requests with same token should fail
        me_res = self.client.get("/api/v1/admin/me", headers=headers)
        self.assertEqual(me_res.status_code, 401)

    def test_07_gallery_image_query_token_auth(self):
        # 1. Unauthenticated request without token returns 401
        res = self.client.get("/api/v1/admin/gallery/image/test_sample.jpg")
        self.assertEqual(res.status_code, 401)

        # 2. Login to get token
        login_res = self.client.post(
            "/api/v1/admin/login",
            json={"username": "admin", "password": "parqueame_secret_2026"},
        )
        token = login_res.json()["token"]

        # 3. Request with query param ?token=
        # Since 'nonexistent_test_123.jpg' doesn't exist, it should pass auth and return 404 (Not Found), not 401
        res_with_token = self.client.get(f"/api/v1/admin/gallery/image/nonexistent_test_123.jpg?token={token}")
        self.assertEqual(res_with_token.status_code, 404)
        self.assertIn("Image not found in gallery", res_with_token.json()["detail"])

    def test_08_sqlite_session_persistence(self):
        # 1. Login
        login_res = self.client.post(
            "/api/v1/admin/login",
            json={"username": "admin", "password": "parqueame_secret_2026"},
        )
        token = login_res.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Simulate server worker restart / cache eviction by wiping in-memory dictionary
        server_state.admin_sessions.clear()

        # 3. Request should still succeed via SQLite backing store
        me_res = self.client.get("/api/v1/admin/me", headers=headers)
        self.assertEqual(me_res.status_code, 200)
        self.assertEqual(me_res.json()["user"], "admin")

    def test_09_in_memory_gallery_upload_and_retrieval(self):
        import cv2
        import numpy as np

        # 1. Login
        login_res = self.client.post(
            "/api/v1/admin/login",
            json={"username": "admin", "password": "parqueame_secret_2026"},
        )
        token = login_res.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Ingest camera upload
        dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)
        _, buf = cv2.imencode(".jpg", dummy_img)
        raw_bytes = buf.tobytes()

        up_res = self.client.post(
            "/api/v1/upload/cam_01",
            files={"file": ("snap.jpg", raw_bytes, "image/jpeg")},
        )
        self.assertEqual(up_res.status_code, 200)

        # 3. Query gallery
        gallery_res = self.client.get("/api/v1/admin/gallery", headers=headers)
        self.assertEqual(gallery_res.status_code, 200)
        items = gallery_res.json()["items"]
        self.assertGreater(len(items), 0)

        top_item = items[0]
        self.assertEqual(top_item["camera_id"], "cam_01")

        # 4. Fetch raw image from in-memory gallery
        raw_filename = top_item["filename"]
        img_res = self.client.get(f"/api/v1/admin/gallery/image/{raw_filename}", headers=headers)
        self.assertEqual(img_res.status_code, 200)
        self.assertEqual(img_res.content, raw_bytes)

        # 5. Verify zero disk writes
        disk_files = list(Path("storage/cameras").glob("*.jpg"))
        self.assertEqual(len(disk_files), 0, "No raw frames should be written to storage/cameras")


if __name__ == "__main__":
    unittest.main()
