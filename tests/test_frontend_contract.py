import os
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from server.main import app


def run_contract_verification() -> int:
    print("=" * 70)
    print("PARQUEAME FRONTEND API CONTRACT VERIFICATION (SUB-SPEC 602)")
    print("=" * 70)

    with TestClient(app) as client:
        # 1. Verify CORS Preflight Header
        print("\n[Phase 1] Testing CORS Permissiveness...")
        cors_res = client.options(
            "/api/v1/status",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        origin_header = cors_res.headers.get("access-control-allow-origin")
        assert origin_header in ["*", "http://localhost:5173"], (
            f"CORS header missing or restrictive: {origin_header}"
        )
        print(f"  [✓] CORS active: Access-Control-Allow-Origin = {origin_header}")

        # 2. Verify Overall Status Contract
        print("\n[Phase 2] Verifying GET /api/v1/status Contract...")
        st_res = client.get("/api/v1/status")
        assert st_res.status_code == 200, f"Status failed: {st_res.text}"
        st_data = st_res.json()
        
        required_root_keys = ["total_spots", "occupied_spots", "free_spots", "occupancy_rate", "cameras"]
        for k in required_root_keys:
            assert k in st_data, f"Missing required key '{k}' in /api/v1/status"
        
        assert isinstance(st_data["cameras"], dict)
        print(f"  [✓] /api/v1/status matches contract schema ({st_data['total_spots']} spots).")

        # 3. Ingest Sample Frame to populate camera state
        print("\n[Phase 3] Populating camera state with test upload...")
        sample_img_path = Path("test-samples/cam_01")
        img_files = list(sample_img_path.glob("*.jpg")) if sample_img_path.exists() else []
        if not img_files:
            img_files = list(Path("test-samples").glob("*.jpg"))
        
        assert img_files, "No test image found for ingestion"
        with open(img_files[0], "rb") as f:
            img_bytes = f.read()

        up_res = client.post(
            "/api/v1/upload/cam_01?battery=91.0&voltage=4.08",
            files={"file": (img_files[0].name, img_bytes, "image/jpeg")},
        )
        assert up_res.status_code == 200, f"Upload failed: {up_res.text}"

        # 4. Verify Camera Status and Spots Item Contract
        print("\n[Phase 4] Verifying GET /api/v1/cameras/cam_01/status Contract...")
        c1_res = client.get("/api/v1/cameras/cam_01/status")
        assert c1_res.status_code == 200
        c1_data = c1_res.json()
        
        required_cam_keys = [
            "camera_id", "total_spots", "occupied_spots", "free_spots",
            "occupancy_rate", "battery_percentage", "battery_voltage", "spots"
        ]
        for k in required_cam_keys:
            assert k in c1_data, f"Missing key '{k}' in camera status"
        
        assert len(c1_data["spots"]) > 0, "Spots list is empty"
        spot0 = c1_data["spots"][0]
        assert "spot_id" in spot0 and "occupied" in spot0 and "confidence" in spot0
        print(f"  [✓] Camera status and spots item match contract ({len(c1_data['spots'])} spots).")

        # 5. Verify Visual Stream Image Contract
        print("\n[Phase 5] Verifying GET /api/v1/cameras/cam_01/image Contract...")
        img_res = client.get(f"/api/v1/cameras/cam_01/image?t={int(time.time()*1000)}")
        assert img_res.status_code == 200, f"Image stream failed: {img_res.text}"
        assert img_res.headers.get("content-type") == "image/jpeg"
        assert len(img_res.content) > 1000
        assert img_res.content[:2] == b"\xff\xd8", "Not a valid JPEG buffer"
        print(f"  [✓] Image stream returns valid JPEG buffer ({len(img_res.content)} bytes).")

        # 6. Verify Analytics Summary Contract
        print("\n[Phase 6] Verifying GET /api/v1/analytics/cameras/cam_01/summary Contract...")
        an_res = client.get("/api/v1/analytics/cameras/cam_01/summary")
        assert an_res.status_code == 200
        an_data = an_res.json()
        
        required_an_keys = [
            "camera_id", "total_observations", "peak_occupied_spots", "total_turnovers"
        ]
        for k in required_an_keys:
            assert k in an_data, f"Missing key '{k}' in analytics summary"
        print("  [✓] Analytics summary matches contract schema.")

    print("\n" + "=" * 70)
    print("ALL FRONTEND API CONTRACT CHECKS PASSED.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(run_contract_verification())
