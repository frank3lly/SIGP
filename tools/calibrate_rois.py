import argparse
import json
import logging
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Force Qt to use X11 (xcb) under WSL/Linux to prevent blank/frozen Wayland windows
if "QT_QPA_PLATFORM" not in os.environ and os.environ.get("DISPLAY"):
    os.environ["QT_QPA_PLATFORM"] = "xcb"

import cv2
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("calibrate_rois")

COLOR_COMPLETED_OUTLINE = (255, 220, 0)     # Cyan
COLOR_COMPLETED_FILL = (180, 140, 0)        # Translucent Cyan
COLOR_IN_PROGRESS = (0, 140, 255)           # Bright Orange
COLOR_TEXT = (255, 255, 255)                # White
COLOR_BAR_BG = (30, 30, 30)                 # Dark Charcoal


def detect_camera_id(path: Path) -> str:
    """Extracts camera ID from path (e.g. cam_02 from test-samples/cam_02), defaulting to folder name."""
    match = re.search(r"cam_\d+", str(path))
    if match:
        return match.group(0)
    if path.is_dir() and path.name.startswith("cam_"):
        return path.name
    return path.stem if path.is_file() else "cam_01"


def import_from_xml(
    target_path: Path,
    camera_id: Optional[str] = None,
    config_dir: str = "config/cameras",
    dry_run: bool = False,
) -> Path:
    """
    Auto-extracts parking spot polygons from PKLot XML files into a camera JSON config.
    target_path can be a directory containing .xml files or a specific .xml file.
    """
    if target_path.is_dir():
        xml_files = sorted(target_path.glob("*.xml"))
        if not xml_files:
            raise FileNotFoundError(f"No .xml ground-truth files found in '{target_path}'")
        xml_file = xml_files[0]
        sample_dir = target_path
    elif target_path.is_file() and target_path.suffix.lower() == ".xml":
        xml_file = target_path
        sample_dir = target_path.parent
    else:
        raise ValueError(f"Target '{target_path}' is neither a directory nor an XML file.")

    cam_id = camera_id or detect_camera_id(sample_dir)
    dest_dir = Path(config_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / f"{cam_id}.json"

    # Determine reference image resolution
    width, height = 1280, 720
    img_files = sorted(sample_dir.glob("*.jpg")) or sorted(sample_dir.glob("*.jpeg"))
    if img_files:
        sample_img = cv2.imread(str(img_files[0]))
        if sample_img is not None:
            height, width = sample_img.shape[:2]

    # Parse XML spaces
    tree = ET.parse(xml_file)
    root = tree.getroot()
    spaces = root.findall("space")
    if not spaces:
        raise ValueError(f"No <space> elements found in XML '{xml_file}'")

    # Sort numerically by space ID
    spaces.sort(key=lambda s: int(re.sub(r"[^0-9]", "", s.attrib.get("id", "0")) or 0))

    spots: List[Dict[str, Any]] = []
    for s in spaces:
        raw_id = s.attrib.get("id", "0")
        num = int(re.sub(r"[^0-9]", "", raw_id) or 0)
        spot_id = f"spot_{num:02d}"

        contour = s.find("contour")
        if contour is None:
            continue
        points = contour.findall("point")
        if len(points) != 4:
            continue

        polygon = [[int(p.attrib["x"]), int(p.attrib["y"])] for p in points]
        spots.append({
            "id": spot_id,
            "polygon": polygon,
        })

    payload = {
        "camera_id": cam_id,
        "name": f"Camera {cam_id.upper()}",
        "description": f"Auto-calibrated from XML ground-truth ({xml_file.name})",
        "reference_resolution": [width, height],
        "spots": spots,
    }

    if dry_run:
        print(f"[Dry Run] Successfully parsed {len(spots)} spots from '{xml_file.name}' for '{cam_id}' ({width}x{height})")
        return dest_file

    with open(dest_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"\n[✓] Successfully imported {len(spots)} spots from '{xml_file.name}'")
    print(f"[✓] Saved configuration to: {dest_file.resolve()} (Resolution: {width}x{height})")
    return dest_file


def preview_cuts(
    camera_id: str,
    image_path: Optional[Path] = None,
    config_dir: str = "config/cameras",
    output_path: Optional[Path] = None,
    no_gui: bool = False,
) -> Path:
    """
    Renders all parking spot cuts on a reference frame, saves a snapshot to tests/output/<camera_id>_cuts.jpg,
    and displays a temporary OpenCV window that closes as soon as any key is pressed.
    """
    cfg_file = Path(config_dir) / f"{camera_id}.json"
    if not cfg_file.is_file():
        raise FileNotFoundError(
            f"Configuration '{cfg_file}' not found. Please calibrate or import spots first."
        )

    with open(cfg_file, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    spots = cfg.get("spots", [])
    if not spots:
        raise ValueError(f"No spots defined in '{cfg_file}'.")

    # Locate reference image
    if image_path and Path(image_path).is_file():
        ref_img_path = Path(image_path)
    else:
        cam_sample_dir = Path("test-samples") / camera_id
        candidate_images = sorted(cam_sample_dir.glob("*.jpg")) or sorted(cam_sample_dir.glob("*.jpeg"))
        if not candidate_images:
            candidate_images = sorted(Path("test-samples").glob("*.jpg"))
        if not candidate_images:
            raise FileNotFoundError(f"No reference image found to preview cuts for '{camera_id}'.")
        ref_img_path = candidate_images[0]

    img = cv2.imread(str(ref_img_path))
    if img is None:
        raise ValueError(f"Failed to read image at '{ref_img_path}'.")

    h, w = img.shape[:2]
    overlay = img.copy()

    # Draw all calibrated spot polygons
    for s in spots:
        poly = s.get("polygon", [])
        if len(poly) >= 3:
            cnt = np.array(poly, dtype=np.int32).reshape((-1, 1, 2))
            cv2.fillPoly(overlay, [cnt], COLOR_COMPLETED_FILL)
            cv2.polylines(img, [cnt], isClosed=True, color=COLOR_COMPLETED_OUTLINE, thickness=2)

            v0 = poly[0]
            label = s.get("id", "spot")
            # Pill label background
            cv2.rectangle(img, (v0[0], v0[1] - 18), (v0[0] + 62, v0[1] + 2), (20, 20, 20), -1)
            cv2.putText(img, label, (v0[0] + 3, v0[1] - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.42, COLOR_TEXT, 1, cv2.LINE_AA)

    # Blend translucent fill
    cv2.addWeighted(overlay, 0.35, img, 0.65, 0, img)

    # Bottom status bar
    bar_h = 28
    cv2.rectangle(img, (0, h - bar_h), (w, h), COLOR_BAR_BG, -1)
    status_txt = f"Camera: {camera_id} | Total Spots: {len(spots)} | Reference: {ref_img_path.name} | [Press ANY KEY to close]"
    cv2.putText(img, status_txt, (10, h - 9), cv2.FONT_HERSHEY_SIMPLEX, 0.40, COLOR_TEXT, 1, cv2.LINE_AA)

    # Save snapshot image
    out_file = output_path or Path(f"tests/output/{camera_id}_cuts.jpg")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_file), img)
    print(f"\n[✓] Snapshot of cuts saved to: {out_file.resolve()}")

    # Display in interactive window if GUI is enabled
    if not no_gui:
        win_name = f"Parqueame Cuts Preview - {camera_id} ({len(spots)} spots)"
        try:
            cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(win_name, w, h)
            cv2.imshow(win_name, img)
            print("[ℹ] Displaying cuts window on screen. Press ANY KEY (or ESC) to close and dismiss...")
            cv2.waitKey(0)
            cv2.destroyAllWindows()
            print("[✓] Window closed and dismissed.")
        except cv2.error as e:
            print(f"[ℹ] No active display server detected: {e}. Snapshot saved to disk.")

    return out_file


class ROICalibrator:
    """Interactive OpenCV GUI calibrator for defining parking spot ROIs on reference frames."""

    def __init__(
        self,
        image_path: str,
        camera_id: str,
        config_dir: str = "config/cameras",
        clean_start: bool = False,
    ) -> None:
        self.image_path = image_path
        self.camera_id = camera_id
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.config_dir / f"{camera_id}.json"

        self.base_image = cv2.imread(image_path)
        if self.base_image is None:
            raise FileNotFoundError(f"Failed to read image at '{image_path}'")

        self.h, self.w = self.base_image.shape[:2]
        self.spots: List[Dict[str, Any]] = []
        self.in_progress_points: List[List[int]] = []
        self.mouse_pos: Tuple[int, int] = (0, 0)
        self.window_name = f"Parqueame Calibration - {self.camera_id} ({self.w}x{self.h})"
        self.base_annotated_frame: np.ndarray = self.base_image.copy()

        if not clean_start:
            self._load_existing_config()
        self._update_spots_cache()

    def _load_existing_config(self) -> None:
        """Loads spots from an existing JSON configuration file if present."""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "spots" in data:
                    self.spots = data["spots"]
                    logger.info(f"Loaded {len(self.spots)} existing spots from '{self.config_file}'")
            except Exception as e:
                logger.warning(f"Could not load existing config '{self.config_file}': {e}")

    def _update_spots_cache(self) -> None:
        """Pre-renders all saved spots onto the cached base frame for instant rendering."""
        frame = self.base_image.copy()
        if not self.spots:
            self.base_annotated_frame = frame
            return

        overlay = frame.copy()
        for spot in self.spots:
            poly = spot.get("polygon", [])
            if len(poly) >= 3:
                cnt = np.array(poly, dtype=np.int32).reshape((-1, 1, 2))
                cv2.fillPoly(overlay, [cnt], COLOR_COMPLETED_FILL)
                cv2.polylines(frame, [cnt], isClosed=True, color=COLOR_COMPLETED_OUTLINE, thickness=2)
                v0 = poly[0]
                label = spot.get("id", "spot")
                cv2.putText(frame, label, (v0[0] + 4, v0[1] - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_TEXT, 1, cv2.LINE_AA)

        cv2.addWeighted(overlay, 0.25, frame, 0.75, 0, frame)
        self.base_annotated_frame = frame

    def on_mouse(self, event: int, x: int, y: int, flags: int, param: Any) -> None:
        """Mouse event handler for drawing quadrilateral corners."""
        self.mouse_pos = (x, y)

        if event == cv2.EVENT_LBUTTONDOWN:
            self.in_progress_points.append([int(x), int(y)])
            print(f"\r[+] Corner {len(self.in_progress_points)}/4 clicked at ({x}, {y})", flush=True)

            if len(self.in_progress_points) == 4:
                default_id = f"spot_{len(self.spots) + 1:02d}"
                print(f"\n[?] Enter ID for completed spot [Default: {default_id}]: ", end="", flush=True)
                user_id = default_id
                try:
                    import select
                    if sys.stdin in select.select([sys.stdin], [], [], 0.05)[0]:
                        line = sys.stdin.readline().strip()
                        if line:
                            user_id = line
                except Exception:
                    pass

                self.spots.append({
                    "id": user_id,
                    "polygon": list(self.in_progress_points)
                })
                self._update_spots_cache()
                print(f"\n[✓] Recorded '{user_id}' with 4 vertices. Press 'S' to save.", flush=True)
                self.in_progress_points.clear()

    def save(self) -> None:
        """Saves current spot definitions to the target camera JSON configuration file."""
        payload = {
            "camera_id": self.camera_id,
            "name": f"Camera {self.camera_id}",
            "description": "Configured via calibrate_rois.py",
            "reference_resolution": [self.w, self.h],
            "spots": self.spots,
        }
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"\n[✓] Successfully saved {len(self.spots)} spots to '{self.config_file}'", flush=True)

    def undo(self) -> None:
        """Reverts the last clicked vertex or completed spot."""
        if self.in_progress_points:
            popped = self.in_progress_points.pop()
            print(f"\n[-] Undid in-progress point {popped}", flush=True)
        elif self.spots:
            popped_spot = self.spots.pop()
            self._update_spots_cache()
            print(f"\n[-] Undid spot '{popped_spot.get('id')}'", flush=True)
        else:
            logger.info("Nothing to undo.")

    def render(self) -> np.ndarray:
        """Renders cached spots with in-progress lines, high-contrast vertices, and status bar."""
        frame = self.base_annotated_frame.copy()

        num_pts = len(self.in_progress_points)
        for i, pt in enumerate(self.in_progress_points):
            cv2.circle(frame, (pt[0], pt[1]), 8, (255, 255, 255), 2)
            cv2.circle(frame, (pt[0], pt[1]), 6, COLOR_IN_PROGRESS, -1)
            label = str(i + 1)
            cv2.putText(frame, label, (pt[0] + 9, pt[1] - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 0, 0), 2, cv2.LINE_AA)
            cv2.putText(frame, label, (pt[0] + 8, pt[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1, cv2.LINE_AA)

        if num_pts > 1:
            for i in range(num_pts - 1):
                p1 = self.in_progress_points[i]
                p2 = self.in_progress_points[i + 1]
                cv2.line(frame, (p1[0], p1[1]), (p2[0], p2[1]), (0, 0, 0), 3)
                cv2.line(frame, (p1[0], p1[1]), (p2[0], p2[1]), COLOR_IN_PROGRESS, 2)

        if num_pts in (1, 2, 3):
            last_pt = self.in_progress_points[-1]
            cv2.line(frame, (last_pt[0], last_pt[1]), self.mouse_pos, (0, 220, 255), 2)

        bar_h = 28
        cv2.rectangle(frame, (0, self.h - bar_h), (self.w, self.h), COLOR_BAR_BG, -1)
        status_txt = f"Spots: {len(self.spots)} | In-Progress: {num_pts}/4 | [Click] Add Pt | [U] Undo | [C] Cancel | [R] Reset | [S] Save | [Q] Quit"
        cv2.putText(frame, status_txt, (10, self.h - 9), cv2.FONT_HERSHEY_SIMPLEX, 0.38, COLOR_TEXT, 1, cv2.LINE_AA)

        return frame

    def run(self) -> None:
        """Runs the interactive OpenCV calibration GUI event loop."""
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, self.w, self.h)
        cv2.setMouseCallback(self.window_name, self.on_mouse)

        logger.info("=" * 60)
        logger.info(f"Started ROI Calibration for {self.camera_id}")
        logger.info("Click 4 corners for each spot (clockwise/counter-clockwise).")
        logger.info("Keys: [S] Save | [U] Undo | [C] Cancel Spot | [R] Reset | [Q] Quit")
        logger.info("=" * 60)

        try:
            while True:
                display_frame = self.render()
                cv2.imshow(self.window_name, display_frame)

                key = cv2.waitKey(20) & 0xFF
                if key in [ord("q"), ord("Q"), 27]:  # 27 = ESC
                    logger.info("Exiting calibration tool.")
                    break
                elif key in [ord("s"), ord("S")]:
                    self.save()
                elif key in [ord("u"), ord("U")]:
                    self.undo()
                elif key in [ord("c"), ord("C")]:
                    self.in_progress_points.clear()
                    print("\n[!] Cancelled in-progress spot points.", flush=True)
                elif key in [ord("r"), ord("R")]:
                    self.spots.clear()
                    self.in_progress_points.clear()
                    self._update_spots_cache()
                    print("\n[!] Reset all spots.", flush=True)
        finally:
            cv2.destroyAllWindows()


class TkinterROICalibrator:
    """Tkinter fallback calibrator for OpenCV builds without GUI support."""

    def __init__(
        self,
        image_path: str,
        camera_id: str,
        config_dir: str = "config/cameras",
        clean_start: bool = False,
    ) -> None:
        import tkinter as tk
        from PIL import Image, ImageTk

        self.tk = tk
        self.Image = Image
        self.ImageTk = ImageTk
        self.camera_id = camera_id
        self.config_file = Path(config_dir) / f"{camera_id}.json"
        self.config_file.parent.mkdir(parents=True, exist_ok=True)

        self.base_bgr = cv2.imread(image_path)
        if self.base_bgr is None:
            raise FileNotFoundError(f"Failed to read image at '{image_path}'")
        self.h, self.w = self.base_bgr.shape[:2]

        self.existing_config: Dict[str, Any] = {}
        self.spots: List[Dict[str, Any]] = []
        if not clean_start and self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    self.existing_config = loaded
                    self.spots = list(loaded.get("spots", []))
                    logger.info(f"Loaded {len(self.spots)} existing spots from '{self.config_file}'")
            except Exception as e:
                logger.warning(f"Could not load existing config '{self.config_file}': {e}")

        self.in_progress_points: List[List[int]] = []
        self.mouse_pos: Tuple[int, int] = (0, 0)

        self.root = tk.Tk()
        self.root.title(f"Parqueame Calibration - {self.camera_id} ({self.w}x{self.h})")

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.scale = min(1.0, max(screen_w - 100, 320) / self.w, max(screen_h - 180, 240) / self.h)
        disp_w = max(1, int(self.w * self.scale))
        disp_h = max(1, int(self.h * self.scale))

        rgb = cv2.cvtColor(self.base_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        if (disp_w, disp_h) != (self.w, self.h):
            pil_img = pil_img.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
        self.tk_image = ImageTk.PhotoImage(pil_img)

        self.canvas = tk.Canvas(self.root, width=disp_w, height=disp_h, highlightthickness=0)
        self.canvas.pack()
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_image)

        self.status_var = tk.StringVar()
        tk.Label(
            self.root,
            textvariable=self.status_var,
            anchor="w",
            bg="#1e1e1e",
            fg="white",
            padx=6,
            pady=4,
        ).pack(fill="x")

        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Motion>", self.on_motion)
        self.root.bind_all("<KeyPress>", self.on_key)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        self.root.after(100, lambda: self.root.focus_force())

        self._draw_overlay()

    def _to_canvas(self, pt: List[int]) -> Tuple[float, float]:
        return float(pt[0]) * self.scale, float(pt[1]) * self.scale

    def _to_image(self, x: float, y: float) -> List[int]:
        ix = int(round(x / self.scale))
        iy = int(round(y / self.scale))
        return [max(0, min(self.w - 1, ix)), max(0, min(self.h - 1, iy))]

    def _draw_overlay(self) -> None:
        c = self.canvas
        c.delete("overlay")

        for spot in self.spots:
            poly = spot.get("polygon", [])
            if len(poly) < 3:
                continue
            pts = [self._to_canvas(p) for p in poly]
            flat = [coord for pt in pts for coord in pt]
            c.create_polygon(flat, fill="#00bcd4", stipple="gray25", outline="#00e5ff", width=2, tags="overlay")
            lx, ly = pts[0]
            label = str(spot.get("id", "spot"))
            c.create_rectangle(lx, ly - 18, lx + 74, ly + 2, fill="#141414", outline="", tags="overlay")
            c.create_text(lx + 4, ly - 8, anchor="w", text=label, fill="white", font=("TkDefaultFont", 9), tags="overlay")

        for i, pt in enumerate(self.in_progress_points):
            cx, cy = self._to_canvas(pt)
            c.create_oval(cx - 7, cy - 7, cx + 7, cy + 7, outline="white", width=2, tags="overlay")
            c.create_oval(cx - 5, cy - 5, cx + 5, cy + 5, fill="#008cff", outline="", tags="overlay")
            c.create_text(cx + 9, cy - 9, anchor="w", text=str(i + 1), fill="white", font=("TkDefaultFont", 9, "bold"), tags="overlay")

        if len(self.in_progress_points) > 1:
            for i in range(len(self.in_progress_points) - 1):
                p1 = self._to_canvas(self.in_progress_points[i])
                p2 = self._to_canvas(self.in_progress_points[i + 1])
                c.create_line(*p1, *p2, fill="#008cff", width=2, tags="overlay")
        if 1 <= len(self.in_progress_points) <= 3:
            last = self._to_canvas(self.in_progress_points[-1])
            c.create_line(*last, *self.mouse_pos, fill="#00dcff", width=1, dash=(4, 3), tags="overlay")

        self.status_var.set(
            f"Spots: {len(self.spots)} | In progress: {len(self.in_progress_points)}/4 | "
            "Click 4 corners | S Save | U Undo | C Cancel | R Reset | Q Quit"
        )

    def on_motion(self, event: Any) -> None:
        self.mouse_pos = (event.x, event.y)
        self._draw_overlay()

    def on_click(self, event: Any) -> None:
        self.in_progress_points.append(self._to_image(event.x, event.y))
        print(f"[+] Corner {len(self.in_progress_points)}/4 clicked at {self.in_progress_points[-1]}", flush=True)

        if len(self.in_progress_points) == 4:
            used_ids = {s.get("id") for s in self.spots}
            n = len(self.spots) + 1
            default_id = f"spot_{n:02d}"
            while default_id in used_ids:
                n += 1
                default_id = f"spot_{n:02d}"

            from tkinter import simpledialog

            user_id = simpledialog.askstring(
                "Spot ID",
                "Identifier for this spot:",
                initialvalue=default_id,
                parent=self.root,
            )
            spot_id = (user_id or default_id).strip() or default_id
            if spot_id in used_ids:
                spot_id = default_id

            self.spots.append({"id": spot_id, "polygon": list(self.in_progress_points)})
            print(f"[✓] Recorded '{spot_id}' with 4 vertices. Press S to save.", flush=True)
            self.in_progress_points.clear()

        self._draw_overlay()

    def on_key(self, event: Any) -> None:
        key = (event.keysym or "").lower()
        if key in ("q", "escape"):
            self.root.destroy()
        elif key == "s":
            self.save()
        elif key == "u":
            self.undo()
        elif key == "c":
            self.in_progress_points.clear()
            print("[!] Cancelled in-progress spot points.", flush=True)
            self._draw_overlay()
        elif key == "r":
            self.spots.clear()
            self.in_progress_points.clear()
            print("[!] Reset all spots.", flush=True)
            self._draw_overlay()

    def save(self) -> None:
        payload = dict(self.existing_config)
        payload["camera_id"] = self.camera_id
        payload.setdefault("name", f"Camera {self.camera_id}")
        payload.setdefault("description", "Configured via calibrate_rois.py")
        payload["reference_resolution"] = [self.w, self.h]
        payload["spots"] = self.spots
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"[✓] Successfully saved {len(self.spots)} spots to '{self.config_file}'", flush=True)

    def undo(self) -> None:
        if self.in_progress_points:
            popped = self.in_progress_points.pop()
            print(f"[-] Undid in-progress point {popped}", flush=True)
        elif self.spots:
            popped_spot = self.spots.pop()
            print(f"[-] Undid spot '{popped_spot.get('id')}'", flush=True)
        else:
            logger.info("Nothing to undo.")
        self._draw_overlay()

    def run(self) -> None:
        logger.info("=" * 60)
        logger.info(f"Started Tkinter ROI Calibration for {self.camera_id}")
        logger.info("Click 4 corners for each spot. Keys: S Save | U Undo | C Cancel | R Reset | Q Quit")
        logger.info("=" * 60)
        self.root.mainloop()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Parqueame ROI Calibrator: auto-cut from XML directory, draw via GUI, or preview cuts",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "source",
        nargs="?",
        default=None,
        help="Path to an image (.jpg/.png), an .xml file, a directory containing .xml files, or camera ID"
    )
    parser.add_argument("-i", "--image", type=str, default=None, help="Reference snapshot image for manual GUI drawing")
    parser.add_argument("-d", "--dir", "--xml", dest="xml_source", type=str, default=None, help="Directory containing .xml files or path to a specific .xml file")
    parser.add_argument("-c", "--camera", type=str, default=None, help="Camera ID (e.g. cam_02). Auto-detected if omitted")
    parser.add_argument("-p", "--preview", "--view", dest="preview_mode", action="store_true", help="Preview calibrated cuts (saves snapshot image and displays temporary window)")
    parser.add_argument("--no-gui", action="store_true", help="When using --preview, save the snapshot without opening an on-screen window")
    parser.add_argument("--config-dir", type=str, default="config/cameras", help="Directory where JSON configs are saved (default: config/cameras)")
    parser.add_argument("--clean", action="store_true", help="Start blank canvas without loading existing spots")
    parser.add_argument("--dry-run", action="store_true", help="Validate without launching GUI or writing files")

    args = parser.parse_args()

    # Determine input path
    raw_path_str = args.source or args.xml_source or args.image

    # Mode A: Preview existing cuts
    if args.preview_mode:
        # Determine camera ID from source or argument
        if raw_path_str and Path(raw_path_str).exists():
            target_p = Path(raw_path_str)
            cam_id = args.camera or detect_camera_id(target_p)
            img_p = target_p if (target_p.is_file() and target_p.suffix.lower() in [".jpg", ".jpeg", ".png"]) else None
        elif raw_path_str and not Path(raw_path_str).exists():
            # Might be passed directly as camera ID (e.g. `calibrate_rois.py cam_02 --preview`)
            cam_id = raw_path_str
            img_p = None
        else:
            cam_id = args.camera or "cam_01"
            img_p = None

        try:
            preview_cuts(
                camera_id=cam_id,
                image_path=img_p,
                config_dir=args.config_dir,
                no_gui=args.no_gui,
            )
            return 0
        except Exception as e:
            logger.error(f"Error previewing cuts: {e}")
            return 1

    if not raw_path_str:
        parser.print_help()
        print("\nExamples:")
        print("  # Auto-import spots from XML directory:")
        print("  .venv/bin/python tools/calibrate_rois.py test-samples/cam_02")
        print("\n  # See a snapshot of the cuts (and view then close):")
        print("  .venv/bin/python tools/calibrate_rois.py cam_02 --preview")
        print("\n  # Interactively draw spots on an image:")
        print("  .venv/bin/python tools/calibrate_rois.py test-samples/cam_01/ref.jpg -c cam_01")
        return 1

    target = Path(raw_path_str)
    if not target.exists():
        logger.error(f"Provided path does not exist: '{target}'")
        return 1

    # Mode 1: Directory with XML files OR a direct .xml file
    has_xmls = (target.is_dir() and len(list(target.glob("*.xml"))) > 0)
    is_xml_file = (target.is_file() and target.suffix.lower() == ".xml")

    if has_xmls or is_xml_file:
        try:
            import_from_xml(
                target_path=target,
                camera_id=args.camera,
                config_dir=args.config_dir,
                dry_run=args.dry_run,
            )
            return 0
        except Exception as e:
            logger.error(f"Error during XML spot import: {e}")
            return 1

    # Mode 2: Interactive GUI with Image File
    if target.is_file() and target.suffix.lower() in [".jpg", ".jpeg", ".png", ".bmp"]:
        camera_id = args.camera or detect_camera_id(target)
        if args.dry_run:
            logger.info(f"[Dry Run] Validated image='{target}', camera='{camera_id}'")
            return 0

        try:
            calibrator = ROICalibrator(
                image_path=str(target),
                camera_id=camera_id,
                config_dir=args.config_dir,
                clean_start=args.clean,
            )
            calibrator.run()
            return 0
        except cv2.error as e:
            logger.warning(f"OpenCV GUI unavailable ({e}). Falling back to Tkinter calibration window.")
            try:
                calibrator = TkinterROICalibrator(
                    image_path=str(target),
                    camera_id=camera_id,
                    config_dir=args.config_dir,
                    clean_start=args.clean,
                )
                calibrator.run()
                return 0
            except Exception as tk_error:
                logger.error(f"Tkinter GUI error (a graphical display is required): {tk_error}")
                return 1
        except Exception as e:
            logger.error(f"Error during calibration: {e}")
            return 1

    logger.error(f"Cannot process '{target}': not an image, XML file, or folder containing XML files.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
