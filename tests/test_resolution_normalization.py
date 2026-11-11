import os
import sys
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from detection.config_loader import CameraConfig, SpotConfig
from detection.occupancy import evaluate_occupancy
from detection.detector import VehicleDetection
from server.main import app
from server.routers.upload import normalize_frame_to_reference


def run_tests() -> int:
    print("=" * 70)
    print("PARQUEAME CAMERA RESOLUTION NORMALIZATION TEST SUITE (SUB-SPEC 603)")
    print("=" * 70)

    ref_res = (1280, 720)

    # -------------------------------------------------------------
    # TC-NORM-01: 1280x720 (HD) -> Pass-through
    # -------------------------------------------------------------
    print("\n[TC-NORM-01] Testing 1280x720 (HD) resolution pass-through...")
    hd_img = np.zeros((720, 1280, 3), dtype=np.uint8)
    out_img, was_resized = normalize_frame_to_reference(hd_img, ref_res)
    assert not was_resized, "TC-NORM-01 failed: was_resized should be False for matching resolution"
    assert out_img.shape == (720, 1280, 3), f"TC-NORM-01 failed: unexpected shape {out_img.shape}"
    assert out_img is hd_img, "TC-NORM-01 failed: image identity should be preserved"
    print("  [✓] TC-NORM-01 passed: Zero overhead pass-through for matching resolution.")

    # -------------------------------------------------------------
    # TC-NORM-02: 1280x1024 (SXGA) -> Downscale height
    # -------------------------------------------------------------
    print("\n[TC-NORM-02] Testing 1280x1024 (SXGA) downscaling...")
    sxga_img = np.zeros((1024, 1280, 3), dtype=np.uint8)
    out_img, was_resized = normalize_frame_to_reference(sxga_img, ref_res)
    assert was_resized, "TC-NORM-02 failed: was_resized should be True"
    assert out_img.shape == (720, 1280, 3), f"TC-NORM-02 failed: expected (720, 1280, 3), got {out_img.shape}"
    print("  [✓] TC-NORM-02 passed: SXGA 1280x1024 downscaled to exactly 1280x720.")

    # -------------------------------------------------------------
    # TC-NORM-03: 640x480 (VGA) -> Upscale
    # -------------------------------------------------------------
    print("\n[TC-NORM-03] Testing 640x480 (VGA) upscaling...")
    vga_img = np.zeros((480, 640, 3), dtype=np.uint8)
    out_img, was_resized = normalize_frame_to_reference(vga_img, ref_res)
    assert was_resized, "TC-NORM-03 failed: was_resized should be True"
    assert out_img.shape == (720, 1280, 3), f"TC-NORM-03 failed: expected (720, 1280, 3), got {out_img.shape}"
    print("  [✓] TC-NORM-03 passed: VGA 640x480 upscaled to exactly 1280x720.")

    # -------------------------------------------------------------
    # TC-NORM-04: 1600x1200 (UXGA) -> Downscale
    # -------------------------------------------------------------
    print("\n[TC-NORM-04] Testing 1600x1200 (UXGA) downscaling...")
    uxga_img = np.zeros((1200, 1600, 3), dtype=np.uint8)
    out_img, was_resized = normalize_frame_to_reference(uxga_img, ref_res)
    assert was_resized, "TC-NORM-04 failed: was_resized should be True"
    assert out_img.shape == (720, 1280, 3), f"TC-NORM-04 failed: expected (720, 1280, 3), got {out_img.shape}"
    print("  [✓] TC-NORM-04 passed: UXGA 1600x1200 downscaled to exactly 1280x720.")

    # -------------------------------------------------------------
    # TC-NORM-05: Spatial Coordinate Consistency
    # -------------------------------------------------------------
    print("\n[TC-NORM-05] Testing spatial coordinate containment preservation...")
    # Calibrated spot in 1280x720 reference space
    spot_poly = [[641, 570], [726, 671], [650, 708], [577, 602]]
    spot = {"id": "spot_01", "polygon": spot_poly}

    # Calculate center in 720p reference space
    pts = np.array(spot_poly, dtype=np.float32)
    center_x = float(pts[:, 0].mean())  # ~648.5
    center_y = float(pts[:, 1].mean())  # ~637.75

    # Simulate vehicle ground anchor in an SXGA (1280x1024) un-normalized frame
    # Vertical coordinate is scaled by (1024 / 720)
    sxga_anchor_y = center_y * (1024.0 / 720.0)  # ~907 px
    
    # In un-normalized SXGA space, evaluate_occupancy with 720p spot polygon FAILS
    unnorm_detection = VehicleDetection(
        box=(center_x - 30, sxga_anchor_y - 60, center_x + 30, sxga_anchor_y),
        class_id=2,
        class_name="car",
        confidence=0.9,
    )
    failed_eval = evaluate_occupancy(
        spots=[spot],
        detections=[unnorm_detection],
        camera_id="test_cam",
    )
    assert failed_eval.occupied_count == 0, (
        "Sanity check failed: un-normalized detection should miss polygon"
    )

    # Now simulate frame normalized back to 720p
    # Normalized detection has coordinates scaled back to reference space
    norm_detection = VehicleDetection(
        box=(center_x - 30, center_y - 60, center_x + 30, center_y),
        class_id=2,
        class_name="car",
        confidence=0.9,
    )
    success_eval = evaluate_occupancy(
        spots=[spot],
        detections=[norm_detection],
        camera_id="test_cam",
    )
    assert success_eval.occupied_count == 1, (
        "TC-NORM-05 failed: normalized detection must fall inside spot polygon"
    )
    print("  [✓] TC-NORM-05 passed: Coordinate normalization resolves vertical coordinate drift.")

    # -------------------------------------------------------------
    # TC-NORM-06: End-to-End API Integration & Annotated Output Shape
    # -------------------------------------------------------------
    print("\n[TC-NORM-06] Testing End-to-End API Upload with multi-resolution frames...")
    with TestClient(app) as client:
        # Load a real sample image if available or generate one
        sample_path = Path("test-samples/cam_01")
        sample_files = list(sample_path.glob("*.jpg")) if sample_path.exists() else []
        if sample_files:
            real_img = cv2.imread(str(sample_files[0]))
        else:
            real_img = np.full((720, 1280, 3), 128, dtype=np.uint8)

        # Test upload in 3 distinct resolutions: VGA, SXGA, UXGA
        test_resolutions = [
            ("VGA", 640, 480),
            ("SXGA", 1280, 1024),
            ("UXGA", 1600, 1200),
        ]

        for name, w, h in test_resolutions:
            resized = cv2.resize(real_img, (w, h))
            ok, buf = cv2.imencode(".jpg", resized)
            assert ok, f"Failed to encode test {name} frame"

            # Upload to cam_01 (calibrated at 1280x720)
            res = client.post(
                "/api/v1/upload/cam_01",
                files={"file": (f"test_{name}.jpg", buf.tobytes(), "image/jpeg")},
            )
            assert res.status_code == 200, f"Upload {name} failed: {res.text}"
            data = res.json()
            assert data["status"] == "success"
            assert data["total_spots"] == 28

            # Fetch annotated output image and verify its dimensions
            img_res = client.get("/api/v1/cameras/cam_01/image")
            assert img_res.status_code == 200, f"Get image failed for {name}"
            assert img_res.headers["content-type"] == "image/jpeg"

            annotated_arr = cv2.imdecode(np.frombuffer(img_res.content, np.uint8), cv2.IMREAD_COLOR)
            assert annotated_arr is not None, "Failed to decode returned annotated image"
            assert annotated_arr.shape == (720, 1280, 3), (
                f"TC-NORM-06 failed for {name}: Expected output shape (720, 1280, 3), got {annotated_arr.shape}"
            )
            print(f"  [✓] TC-NORM-06 ({name} {w}x{h}): Normalized & rendered to exact (1280x720) overlay.")

    print("\n" + "=" * 70)
    print("ALL RESOLUTION NORMALIZATION TESTS PASSED.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(run_tests())
