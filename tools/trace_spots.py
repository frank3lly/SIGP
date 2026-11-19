import argparse
import json
import logging
import mimetypes
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2

logger = logging.getLogger("trace_spots")

PAGE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Trace Spots - __CAMERA__</title>
<style>
  :root { color-scheme: dark; }
  body { margin: 0; font-family: system-ui, sans-serif; background: #121212; color: #eee; }
  #bar { position: sticky; top: 0; z-index: 2; display: flex; gap: 8px; align-items: center; padding: 10px; background: #1e1e1e; flex-wrap: wrap; }
  button { padding: 6px 12px; border: 1px solid #444; border-radius: 5px; background: #2b2b2b; color: #eee; cursor: pointer; }
  button:hover { background: #3a3a3a; }
  #status { margin-left: auto; color: #9ad; }
  #wrap { padding: 10px; overflow: auto; }
  canvas { display: block; max-width: 100%; height: auto; border: 1px solid #333; cursor: crosshair; background: #000; }
  kbd { background: #333; border-radius: 3px; padding: 1px 4px; }
</style>
</head>
<body>
<div id="bar">
  <strong>__CAMERA__</strong>
  <button onclick="save()">Save (S)</button>
  <button onclick="undo()">Undo (U)</button>
  <button onclick="cancelSpot()">Cancel (C)</button>
  <button onclick="reset()">Reset (R)</button>
  <span id="status">Loading...</span>
</div>
<div id="wrap"><canvas id="cv"></canvas></div>
<script>
const camera = "__CAMERA__";
const canvas = document.getElementById("cv");
const ctx = canvas.getContext("2d");
const statusEl = document.getElementById("status");
const img = new Image();
let spots = [];
let inProgress = [];
let mouse = null;
let dirty = false;

function setStatus(extra) {
  statusEl.textContent =
    `Spots: ${spots.length} | In progress: ${inProgress.length}/4 | ` +
    `Click 4 corners | S Save | U Undo | C Cancel | R Reset` + (dirty ? " | UNSAVED" : "") +
    (extra ? " | " + extra : "");
}

function toImage(ev) {
  const r = canvas.getBoundingClientRect();
  return [
    Math.max(0, Math.min(canvas.width - 1, Math.round((ev.clientX - r.left) * canvas.width / r.width))),
    Math.max(0, Math.min(canvas.height - 1, Math.round((ev.clientY - r.top) * canvas.height / r.height)))
  ];
}

function drawPoly(poly, isActive) {
  ctx.beginPath();
  ctx.moveTo(poly[0][0], poly[0][1]);
  for (let i = 1; i < poly.length; i++) ctx.lineTo(poly[i][0], poly[i][1]);
  if (poly.length === 4) ctx.closePath();
  if (poly.length === 4) {
    ctx.fillStyle = isActive ? "rgba(0,140,255,0.25)" : "rgba(0,188,212,0.25)";
    ctx.fill();
  }
  ctx.strokeStyle = isActive ? "#008cff" : "#00e5ff";
  ctx.lineWidth = 2;
  ctx.stroke();
}

function draw() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(img, 0, 0);

  for (const spot of spots) {
    if (!spot.polygon || spot.polygon.length < 3) continue;
    drawPoly(spot.polygon, false);
    const [x, y] = spot.polygon[0];
    ctx.font = "13px sans-serif";
    const w = ctx.measureText(spot.id).width + 10;
    ctx.fillStyle = "#141414";
    ctx.fillRect(x, y - 20, w, 18);
    ctx.fillStyle = "#fff";
    ctx.fillText(spot.id, x + 5, y - 6);
  }

  if (inProgress.length > 0) {
    if (mouse && inProgress.length < 4) {
      drawPoly([...inProgress, mouse], true);
    }
    drawPoly(inProgress, true);
    inProgress.forEach((p, i) => {
      ctx.beginPath();
      ctx.arc(p[0], p[1], 6, 0, Math.PI * 2);
      ctx.fillStyle = "#008cff";
      ctx.fill();
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.fillStyle = "#fff";
      ctx.font = "bold 13px sans-serif";
      ctx.fillText(String(i + 1), p[0] + 9, p[1] - 8);
    });
  }

  setStatus();
}

canvas.addEventListener("mousemove", (ev) => {
  mouse = toImage(ev);
  draw();
});

canvas.addEventListener("click", (ev) => {
  inProgress.push(toImage(ev));
  dirty = true;
  if (inProgress.length === 4) {
    const used = new Set(spots.map((s) => s.id));
    let n = spots.length + 1;
    let defaultId = "spot_" + String(n).padStart(2, "0");
    while (used.has(defaultId)) {
      n++;
      defaultId = "spot_" + String(n).padStart(2, "0");
    }
    const answer = prompt("Spot ID:", defaultId);
    if (answer === null) {
      inProgress = [];
      draw();
      return;
    }
    let id = (answer || defaultId).trim() || defaultId;
    if (used.has(id)) id = defaultId;
    spots.push({ id, polygon: inProgress });
    inProgress = [];
  }
  draw();
});

function save() {
  fetch("/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ spots })
  }).then(async (r) => {
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "Save failed");
    dirty = false;
    setStatus("Saved to " + data.path);
  }).catch((e) => setStatus("ERROR: " + e.message));
}

function undo() {
  if (inProgress.length) inProgress.pop();
  else if (spots.length) spots.pop();
  dirty = true;
  draw();
}

function cancelSpot() {
  inProgress = [];
  dirty = true;
  draw();
}

function reset() {
  if (!confirm("Remove all spots from the canvas? (Nothing is saved until you press S.)")) return;
  spots = [];
  inProgress = [];
  dirty = true;
  draw();
}

window.addEventListener("keydown", (ev) => {
  const k = ev.key.toLowerCase();
  if (k === "s") { ev.preventDefault(); save(); }
  else if (k === "u") { ev.preventDefault(); undo(); }
  else if (k === "c") { ev.preventDefault(); cancelSpot(); }
  else if (k === "r") { ev.preventDefault(); reset(); }
});

img.onload = () => {
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;
  fetch("/state").then((r) => r.json()).then((data) => {
    spots = data.spots || [];
    draw();
  }).catch((e) => setStatus("ERROR: " + e.message));
};
img.onerror = () => setStatus("ERROR: could not load image");
img.src = "/image?t=" + Date.now();
</script>
</body>
</html>
"""


def load_existing(config_file: Path) -> Dict[str, Any]:
    if not config_file.exists():
        return {}
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"Could not load existing config '{config_file}': {e}")
        return {}


def save_spots(config_file: Path, existing: Dict[str, Any], camera_id: str, width: int, height: int, spots: List[Dict[str, Any]]) -> None:
    for spot in spots:
        polygon = spot.get("polygon", [])
        if len(polygon) != 4:
            raise ValueError(f"Spot '{spot.get('id')}' must have exactly 4 vertices")
        for point in polygon:
            if not (isinstance(point, list) and len(point) == 2 and all(isinstance(v, int) for v in point)):
                raise ValueError(f"Spot '{spot.get('id')}' has an invalid vertex: {point}")

    payload = dict(existing)
    payload["camera_id"] = camera_id
    payload.setdefault("name", f"Camera {camera_id}")
    payload.setdefault("description", "Configured via trace_spots.py")
    payload["reference_resolution"] = [width, height]
    payload["spots"] = spots
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"[✓] Saved {len(spots)} spots to '{config_file}'", flush=True)


def serve(
    image_path: Path,
    camera_id: str,
    config_dir: Path,
    host: str,
    port: int,
    open_browser: bool,
    clean: bool = False,
) -> None:
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Failed to read image at '{image_path}'")
    height, width = image.shape[:2]

    config_file = config_dir / f"{camera_id}.json"
    existing = load_existing(config_file)
    existing_spots = [] if clean else existing.get("spots", [])
    if not isinstance(existing_spots, list):
        existing_spots = []
    image_bytes = Path(image_path).read_bytes()
    image_type = mimetypes.guess_type(str(image_path))[0] or "image/png"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            logger.info(fmt % args)

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, data: Dict[str, Any]) -> None:
            self._send(code, json.dumps(data).encode("utf-8"), "application/json")

        def do_GET(self) -> None:
            if self.path.startswith("/image"):
                self._send(200, image_bytes, image_type)
            elif self.path == "/state":
                self._json(200, {
                    "camera_id": camera_id,
                    "width": width,
                    "height": height,
                    "spots": existing_spots,
                })
            elif self.path in ("/", "/index.html"):
                html = PAGE.replace("__CAMERA__", camera_id).encode("utf-8")
                self._send(200, html, "text/html; charset=utf-8")
            else:
                self._json(404, {"detail": "Not found"})

        def do_POST(self) -> None:
            if self.path != "/save":
                self._json(404, {"detail": "Not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                data = json.loads(self.rfile.read(length) or b"{}")
                spots = data.get("spots")
                if not isinstance(spots, list):
                    raise ValueError("Payload must contain a 'spots' list")
                save_spots(config_file, existing, camera_id, width, height, spots)
                nonlocal existing_spots
                existing_spots = spots
                self._json(200, {"status": "ok", "path": str(config_file.resolve()), "count": len(spots)})
            except Exception as e:
                self._json(400, {"detail": str(e)})

    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host if host not in ('0.0.0.0', '::') else '127.0.0.1'}:{port}/"
    print(f"[✓] Camera: {camera_id} | Image: {image_path} ({width}x{height})", flush=True)
    print(f"[✓] Loaded existing spots: {len(existing_spots)}", flush=True)
    print(f"[✓] Open in your browser: {url}", flush=True)
    print("[i] Press Ctrl+C here to stop the server.", flush=True)

    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[i] Stopping server.", flush=True)
    finally:
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Browser-based parking spot tracer")
    parser.add_argument("source", help="Reference image (e.g. samples/cam_01.png)")
    parser.add_argument("-c", "--camera", required=True, help="Camera ID (e.g. cam_01)")
    parser.add_argument("--config-dir", default="config/cameras", help="Config output directory")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="Open the browser automatically")
    parser.add_argument("--clean", action="store_true", help="Start without loading existing spots")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    image_path = Path(args.source)
    if not image_path.is_file():
        logger.error(f"Image not found: '{image_path}'")
        return 1

    try:
        serve(
            image_path=image_path,
            camera_id=args.camera,
            config_dir=Path(args.config_dir),
            host=args.host,
            port=args.port,
            open_browser=args.open,
            clean=args.clean,
        )
        return 0
    except OSError as e:
        logger.error(f"Could not start server on {args.host}:{args.port}: {e}")
        return 1
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
