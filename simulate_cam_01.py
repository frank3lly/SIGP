#!/usr/bin/env python3
"""Standalone Camera Simulator for cam_01.

Simulates an ESP32-CAM / IP Camera sending periodic photos from test-samples/cam_01
to the remote ParqueaMe / SGIP central API server every 30 seconds.
"""

import argparse
from datetime import datetime
import os
from pathlib import Path
import sys
import time

try:
    import requests
except ImportError:
    print("[ERROR] 'requests' library is required. Install with: pip install requests")
    sys.exit(1)


DEFAULT_SERVER_URL = os.environ.get(
    "PARQUEAME_SERVER_URL",
    "https://sigp-api-4vi0.onrender.com",
)
DEFAULT_INTERVAL_SECONDS = 30
CAMERA_ID = "cam_01"


def get_sample_images(samples_dir: Path) -> list[Path]:
    """Retrieves sorted list of JPEG images from the cam_01 test samples directory."""
    cam_dir = samples_dir / CAMERA_ID
    if not cam_dir.exists():
        cam_dir = samples_dir

    extensions = ("*.jpg", "*.jpeg", "*.JPG", "*.JPEG")
    images: list[Path] = []
    for ext in extensions:
        images.extend(cam_dir.glob(ext))

    return sorted(list(set(images)))


def send_frame(
    server_url: str,
    image_path: Path,
    battery: float,
    voltage: float,
    timeout: int = 25,
) -> bool:
    """Sends a single image frame to the central server via multipart POST."""
    endpoint = f"{server_url.rstrip('/')}/api/v1/upload/{CAMERA_ID}"
    params = {
        "battery": round(battery, 1),
        "voltage": round(voltage, 2),
    }

    with open(image_path, "rb") as f:
        files = {
            "file": (image_path.name, f, "image/jpeg"),
        }
        t0 = time.time()
        try:
            response = requests.post(
                endpoint,
                files=files,
                params=params,
                timeout=timeout,
            )
            elapsed_ms = (time.time() - t0) * 1000.0

            if response.status_code == 200:
                data = response.json()
                occupied = data.get("occupied_spots", 0)
                free = data.get("free_spots", 0)
                total = data.get("total_spots", occupied + free)
                inf_time = data.get("inference_time_ms", 0.0)

                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] "
                    f"Uploaded {image_path.name} | "
                    f"HTTP 200 ({elapsed_ms:.0f}ms) | "
                    f"Occupied: {occupied}/{total} | "
                    f"Free: {free} | "
                    f"Inference: {inf_time:.1f}ms | "
                    f"Battery: {battery:.1f}% ({voltage:.2f}V)"
                )
                return True
            else:
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] "
                    f"Failed {image_path.name} | "
                    f"HTTP {response.status_code} ({elapsed_ms:.0f}ms): {response.text}"
                )
                return False

        except requests.exceptions.RequestException as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Connection error: {e}")
            return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simulate cam_01 sending photos to the ParqueaMe central server every 30 seconds."
    )
    parser.add_argument(
        "--server",
        default=DEFAULT_SERVER_URL,
        help=f"Target central API server URL (default: {DEFAULT_SERVER_URL})",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL_SECONDS,
        help=f"Seconds between photo uploads (default: {DEFAULT_INTERVAL_SECONDS})",
    )
    parser.add_argument(
        "--samples-dir",
        type=Path,
        default=Path("test-samples/cam_01"),
        help="Path to directory containing sample photos (default: test-samples/cam_01)",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        default=True,
        help="Loop back to the first photo after finishing all images (default: True)",
    )

    args = parser.parse_args()

    # Discover sample images
    images = get_sample_images(args.samples_dir)
    if not images:
        print(f"[ERROR] No sample images found in '{args.samples_dir}'.")
        print("Please verify that test-samples/cam_01 contains .jpg photos.")
        sys.exit(1)

    print("=" * 65)
    print(f"  SGIP / ParqueaMe - Standalone Camera Simulator [{CAMERA_ID}]")
    print("=" * 65)
    print(f"  Target Server:    {args.server}")
    print(f"  Upload Endpoint:  {args.server.rstrip('/')}/api/v1/upload/{CAMERA_ID}")
    print(f"  Images Found:     {len(images)} photos from '{args.samples_dir}'")
    print(f"  Upload Interval:  {args.interval} seconds")
    print("  Press Ctrl+C at any time to stop the simulation.")
    print("=" * 65)
    print()

    battery = 98.5
    idx = 0
    total_images = len(images)

    try:
        while True:
            img_path = images[idx]
            voltage = 3.30 + (0.90 * (battery / 100.0))

            send_frame(
                server_url=args.server,
                image_path=img_path,
                battery=battery,
                voltage=voltage,
            )

            # Realistic slow battery drain (0.05% per upload)
            battery = max(10.0, battery - 0.05)

            # Advance to next image
            idx += 1
            if idx >= total_images:
                if args.loop:
                    idx = 0
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Looping back to the first sample photo.")
                else:
                    print("All sample photos sent. Exiting.")
                    break

            # Sleep in 1-second ticks for clean Ctrl+C response
            for _ in range(args.interval):
                time.sleep(1)

    except KeyboardInterrupt:
        print("\nSimulation stopped by user (Ctrl+C).")


if __name__ == "__main__":
    main()
