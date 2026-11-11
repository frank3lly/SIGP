#!/usr/bin/env python3
"""Parqueame - Servidor de prueba para cámara ESP32-CAM / XIAO ESP32S3.

Recibe fotos en: POST /api/v1/upload/{camera_id}
Soporta el formato de respuesta oficial con Hot-Configuration (UploadResponse / CameraHotConfig).
Ofrece endpoints REST de configuración:
  - GET  /api/v1/cameras/{camera_id}/config
  - PUT  /api/v1/cameras/{camera_id}/config
  - GET  /api/v1/cameras/{camera_id}/raw
  - GET  /api/v1/cameras/{camera_id}/image
  - GET  /api/v1/health
Ofrece galería web en http://localhost:8000

No requiere librerías externas (usa exclusivamente la librería estándar de Python).
"""

import argparse
from datetime import datetime
import email
from email.parser import BytesFeedParser
import json
import mimetypes
import os
from pathlib import Path
import time
from urllib.parse import parse_qs, urlparse
from http.server import HTTPServer, BaseHTTPRequestHandler

FOTOS_DIR = Path(__file__).resolve().parent / "fotos"


class CameraUploadHandler(BaseHTTPRequestHandler):
    fotos_dir = FOTOS_DIR
    camera_configs = {}
    camera_telemetry = {}
    default_interval = 30
    default_quality = 12
    default_active = True
    default_firmware = "1.0.0"

    @classmethod
    def get_camera_config(cls, camera_id: str) -> dict:
        if camera_id not in cls.camera_configs:
            cls.camera_configs[camera_id] = {
                "interval_seconds": cls.default_interval,
                "active": cls.default_active,
                "quality": cls.default_quality,
                "firmware_version": cls.default_firmware,
            }
        return cls.camera_configs[camera_id]

    @classmethod
    def set_camera_config(cls, camera_id: str, updates: dict) -> dict:
        cfg = cls.get_camera_config(camera_id)
        if "interval_seconds" in updates:
            cfg["interval_seconds"] = max(5, min(3600, int(updates["interval_seconds"])))
        if "active" in updates:
            cfg["active"] = bool(updates["active"])
        if "quality" in updates:
            cfg["quality"] = max(1, min(63, int(updates["quality"])))
        if "firmware_version" in updates:
            cfg["firmware_version"] = str(updates["firmware_version"])
        cls.camera_configs[camera_id] = cfg
        return cfg

    def log_message(self, format, *args):
        # Silenciamos el log genérico por defecto para mantener la consola limpia
        pass

    def send_json_response(self, status_code: int, data: dict):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # 1. Servir archivos estáticos de la carpeta fotos: /fotos/<nombre>
        if path.startswith("/fotos/"):
            filename = os.path.basename(path)
            file_path = self.fotos_dir / filename
            if file_path.exists() and file_path.is_file():
                self.send_response(200)
                content_type, _ = mimetypes.guess_type(str(file_path))
                self.send_header("Content-Type", content_type or "image/jpeg")
                self.send_header("Content-Length", str(file_path.stat().st_size))
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
                return
            else:
                self.send_error(404, "Foto no encontrada")
                return

        # 2. Obtener imagen actual de cámara: /api/v1/cameras/{id}/image o /raw
        for prefix in ("/api/v1/cameras/", "/cameras/"):
            if path.startswith(prefix):
                suffix = path[len(prefix):]
                parts = suffix.split("/")
                if len(parts) == 2 and parts[1] in ("raw", "image"):
                    camera_id = parts[0]
                    latest_file = self.fotos_dir / f"{camera_id}_latest.jpg"
                    if latest_file.exists():
                        self.send_response(200)
                        self.send_header("Content-Type", "image/jpeg")
                        self.send_header("Content-Length", str(latest_file.stat().st_size))
                        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.end_headers()
                        with open(latest_file, "rb") as f:
                            self.wfile.write(f.read())
                        return
                    else:
                        self.send_json_response(404, {"detail": f"No se ha recibido ninguna foto para la cámara '{camera_id}'."})
                        return

        # 3. Obtener configuración dinámica: GET /api/v1/cameras/{id}/config
        for prefix in ("/api/v1/cameras/", "/cameras/"):
            if path.startswith(prefix) and path.endswith("/config"):
                camera_id = path[len(prefix):-len("/config")].strip("/")
                config = self.get_camera_config(camera_id)
                self.send_json_response(200, config)
                return

        # 4. Dashboard / Galería web en /
        if path in ("/", "/index.html"):
            self.serve_gallery()
            return

        # 5. Endpoint de salud
        if path in ("/health", "/api/v1/health"):
            self.send_json_response(200, {
                "status": "healthy",
                "uptime_seconds": round(time.time() - SERVER_START_TIME, 1),
                "server": "Parqueame Test Server",
                "registered_cameras": len(self.camera_configs),
                "timestamp": time.time(),
            })
            return

        self.send_error(404, "Ruta no encontrada")

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Modificar configuración dinámica: PUT /api/v1/cameras/{id}/config
        for prefix in ("/api/v1/cameras/", "/cameras/"):
            if path.startswith(prefix) and path.endswith("/config"):
                camera_id = path[len(prefix):-len("/config")].strip("/")
                content_length = int(self.headers.get("Content-Length", 0))
                if content_length <= 0:
                    self.send_json_response(400, {"detail": "Cuerpo JSON vacío"})
                    return
                try:
                    payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                except Exception as e:
                    self.send_json_response(400, {"detail": f"JSON inválido: {e}"})
                    return

                updated = self.set_camera_config(camera_id, payload)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] [HOT-CONFIG ACTUALIZADO] '{camera_id}': interval={updated['interval_seconds']}s, active={updated['active']}, quality={updated['quality']}")
                self.send_json_response(200, updated)
                return

        self.send_error(404, "Ruta no encontrada")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Procesar actualización desde formulario web en /config-update
        if path == "/config-update":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length).decode("utf-8")
            params = parse_qs(post_data)
            cid = params.get("camera_id", ["cam_01"])[0]
            interval = int(params.get("interval_seconds", [30])[0])
            active = params.get("active", ["true"])[0].lower() in ("true", "1", "on")
            quality = int(params.get("quality", [12])[0])

            self.set_camera_config(cid, {
                "interval_seconds": interval,
                "active": active,
                "quality": quality,
            })
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [HOT-CONFIG WEB] '{cid}' -> interval={interval}s, active={active}, quality={quality}")
            self.send_response(303)
            self.send_header("Location", "/#config")
            self.end_headers()
            return

        # Esperamos ruta de subida: /api/v1/upload/{camera_id} o /upload/{camera_id}
        camera_id = None
        for prefix in ("/api/v1/upload/", "/upload/"):
            if path.startswith(prefix):
                camera_id = path[len(prefix):].strip("/ ")
                break

        if not camera_id:
            self.send_json_response(404, {"detail": f"Endpoint inválido. Usar /api/v1/upload/<camera_id>"})
            return

        query_params = parse_qs(parsed.query)
        battery_pct = query_params.get("battery", [None])[0]
        voltage = query_params.get("voltage", [None])[0]
        device_token = self.headers.get("X-Device-Token", None)

        try:
            battery_val = float(battery_pct) if battery_pct is not None else None
        except ValueError:
            battery_val = None

        try:
            voltage_val = float(voltage) if voltage is not None else None
        except ValueError:
            voltage_val = None

        content_type = self.headers.get("Content-Type", "")
        content_length = int(self.headers.get("Content-Length", 0))

        if not content_type.startswith("multipart/form-data") or content_length <= 0:
            self.send_json_response(400, {"detail": "Content-Type debe ser multipart/form-data con cuerpo válido"})
            return

        body = self.rfile.read(content_length)

        # Parsear multipart/form-data usando email.parser
        parser = BytesFeedParser()
        parser.feed(b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + body)
        msg = parser.close()

        image_data = None
        for part in msg.walk():
            filename = part.get_filename()
            name = part.get_param("name", header="content-disposition")
            if name == "file" or (filename and filename.lower().endswith((".jpg", ".jpeg", ".png"))):
                image_data = part.get_payload(decode=True)
                break

        if not image_data:
            # Respaldo: si el multipart vino plano o con formato simple, buscar bytes JPEG (\xFF\xD8 ... \xFF\xD9)
            start = body.find(b"\xff\xd8")
            end = body.rfind(b"\xff\xd9")
            if start != -1 and end != -1 and end > start:
                image_data = body[start : end + 2]

        if not image_data:
            print(f"[ERROR] No se pudo extraer la imagen del payload de '{camera_id}' ({content_length} bytes)")
            self.send_json_response(422, {"detail": "No se encontró archivo de imagen válido en la petición multipart"})
            return

        # Asegurar directorio ./fotos
        self.fotos_dir.mkdir(parents=True, exist_ok=True)

        # Guardar imagen con marca de tiempo
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        saved_filename = f"{camera_id}_{now_str}.jpg"
        saved_path = self.fotos_dir / saved_filename

        with open(saved_path, "wb") as f:
            f.write(image_data)

        # Actualizar copia 'latest'
        latest_filename = f"{camera_id}_latest.jpg"
        latest_path = self.fotos_dir / latest_filename
        with open(latest_path, "wb") as f:
            f.write(image_data)

        # Registrar telemetría de hardware
        now_ts = time.time()
        self.camera_telemetry[camera_id] = {
            "battery_percentage": battery_val,
            "battery_voltage": voltage_val,
            "last_upload": now_ts,
            "latest_filename": saved_filename,
            "bytes_received": len(image_data),
        }

        # Obtener la hot-config actual asignada a esta cámara
        current_cfg = self.get_camera_config(camera_id)

        # Registro en consola
        info_bat = f" | Batería: {battery_val}% ({voltage_val}V)" if battery_val is not None else ""
        info_tok = f" | Token: {device_token}" if device_token else ""
        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] [FOTO RECIBIDA] Cámara: '{camera_id}' | "
            f"{len(image_data):,} bytes -> {saved_filename}{info_bat}{info_tok} | "
            f"Config retornada: [interval={current_cfg['interval_seconds']}s, active={current_cfg['active']}, quality={current_cfg['quality']}]"
        )

        # Formato de respuesta oficial UploadResponse con CameraHotConfig embebido
        response_payload = {
            "status": "success",
            "camera_id": camera_id,
            "processed_at": round(now_ts, 3),
            "inference_time_ms": 14.5,
            "total_spots": 28,
            "occupied_spots": 0,
            "free_spots": 28,
            "config": {
                "interval_seconds": current_cfg["interval_seconds"],
                "active": current_cfg["active"],
                "quality": current_cfg["quality"],
                "firmware_version": current_cfg["firmware_version"],
            },
        }

        self.send_json_response(200, response_payload)

    def serve_gallery(self):
        self.fotos_dir.mkdir(parents=True, exist_ok=True)
        files = sorted(
            [f for f in self.fotos_dir.glob("*.jpg") if not f.name.endswith("_latest.jpg")],
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )

        # Generar tarjetas de cámaras registradas con su Hot-Config y Telemetría
        cams = sorted(list(set(list(self.camera_configs.keys()) + list(self.camera_telemetry.keys()))))
        if not cams:
            cams = ["cam_01"]

        config_cards_html = ""
        for cid in cams:
            cfg = self.get_camera_config(cid)
            telem = self.camera_telemetry.get(cid, {})
            bat_str = f"{telem.get('battery_percentage', 'N/D')}%" if telem.get('battery_percentage') is not None else "N/D"
            volt_str = f"{telem.get('battery_voltage', 'N/D')} V" if telem.get('battery_voltage') is not None else "N/D"
            last_seen = (
                datetime.fromtimestamp(telem["last_upload"]).strftime("%H:%M:%S")
                if "last_upload" in telem
                else "Esperando primera subida..."
            )
            active_badge = (
                '<span style="background:#059669; padding:2px 8px; border-radius:8px; font-size:11px; font-weight:bold;">ACTIVA</span>'
                if cfg["active"]
                else '<span style="background:#dc2626; padding:2px 8px; border-radius:8px; font-size:11px; font-weight:bold;">PAUSADA</span>'
            )

            config_cards_html += f"""
            <div style="background:#1e293b; border:1px solid #334155; border-radius:8px; padding:16px; margin-bottom:14px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                    <strong style="color:#38bdf8; font-size:16px;">{cid}</strong>
                    {active_badge}
                </div>
                <div style="font-size:13px; color:#cbd5e1; line-height:1.6; margin-bottom:12px;">
                    <div><strong>Última transmisión:</strong> {last_seen}</div>
                    <div><strong>Batería reportada:</strong> {bat_str} ({volt_str})</div>
                    <div><strong>Firmware objetivo:</strong> <code>{cfg['firmware_version']}</code></div>
                </div>
                <form method="POST" action="/config-update" style="display:grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)) 100px; gap:8px; align-items:end;">
                    <input type="hidden" name="camera_id" value="{cid}">
                    <div>
                        <label style="font-size:11px; color:#94a3b8; display:block;">Intervalo (s)</label>
                        <input type="number" name="interval_seconds" value="{cfg['interval_seconds']}" min="5" max="3600" style="width:100%; padding:6px; background:#0f172a; border:1px solid #475569; color:#fff; border-radius:4px; box-sizing:border-box;">
                    </div>
                    <div>
                        <label style="font-size:11px; color:#94a3b8; display:block;">Calidad JPEG (1-63)</label>
                        <input type="number" name="quality" value="{cfg['quality']}" min="1" max="63" style="width:100%; padding:6px; background:#0f172a; border:1px solid #475569; color:#fff; border-radius:4px; box-sizing:border-box;">
                    </div>
                    <div>
                        <label style="font-size:11px; color:#94a3b8; display:block;">Estado</label>
                        <select name="active" style="width:100%; padding:6px; background:#0f172a; border:1px solid #475569; color:#fff; border-radius:4px; box-sizing:border-box;">
                            <option value="true" {"selected" if cfg["active"] else ""}>Activa</option>
                            <option value="false" {"selected" if not cfg["active"] else ""}>Pausada</option>
                        </select>
                    </div>
                    <button type="submit" style="background:#2563eb; color:#fff; border:none; padding:8px 12px; border-radius:4px; font-weight:bold; cursor:pointer; height:34px;">
                        Guardar
                    </button>
                </form>
            </div>
            """

        items_html = ""
        for f in files[:30]:  # Mostrar últimas 30 fotos
            mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            size_kb = f.stat().st_size / 1024
            items_html += f"""
            <div style="background:#1e293b; border-radius:8px; overflow:hidden; box-shadow:0 4px 6px -1px rgba(0,0,0,0.3);">
                <a href="/fotos/{f.name}" target="_blank">
                    <img src="/fotos/{f.name}" style="width:100%; height:200px; object-fit:cover; display:block;" loading="lazy">
                </a>
                <div style="padding:10px; font-size:13px; color:#cbd5e1;">
                    <strong style="color:#38bdf8;">{f.name}</strong><br>
                    <span>{mtime} &bull; {size_kb:.1f} KB</span>
                </div>
            </div>
            """

        if not items_html:
            items_html = "<p style='color:#94a3b8; grid-column:1/-1; text-align:center;'>Aún no se han recibido fotos. Cuando la cámara envíe una foto aparecerá aquí automáticamente.</p>"

        html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="6">
    <title>Parqueame - Servidor de Prueba de Cámara</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background:#0f172a; color:#f8fafc; margin:0; padding:20px; }}
        h1 {{ margin:0 0 6px 0; color:#38bdf8; font-size:22px; }}
        h2 {{ margin:20px 0 10px 0; color:#94a3b8; font-size:15px; text-transform:uppercase; letter-spacing:0.05em; }}
        .header {{ display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #334155; padding-bottom:14px; margin-bottom:16px; }}
        .badge {{ background:#059669; padding:4px 10px; border-radius:12px; font-size:12px; font-weight:bold; }}
        .grid {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(260px, 1fr)); gap:16px; }}
        .curl-box {{ background:#1e293b; padding:10px 14px; border-radius:6px; font-family:monospace; font-size:12px; color:#a5f3fc; overflow-x:auto; margin-bottom:16px; border:1px solid #334155; }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>Parqueame &bull; Servidor de Prueba de Cámara</h1>
            <span style="color:#94a3b8; font-size:13px;">Auto-recarga cada 6s &bull; Directorio: <code>{self.fotos_dir}</code> &bull; Protocolo: <code>UploadResponse + CameraHotConfig</code></span>
        </div>
        <span class="badge">ONLINE &bull; {len(files)} fotos</span>
    </div>

    <div class="curl-box">
        <strong>Ejemplo de actualización remota vía PUT:</strong><br>
        curl -X PUT http://localhost:8000/api/v1/cameras/cam_01/config -H "Content-Type: application/json" -d '{{"interval_seconds": 60, "active": true, "quality": 10}}'
    </div>

    <div id="config">
        <h2>Hot-Configuration y Estado de Cámaras</h2>
        {config_cards_html}
    </div>

    <h2>Fotogramas Recibidos (Últimos 30)</h2>
    <div class="grid">
        {items_html}
    </div>
</body>
</html>"""

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))


SERVER_START_TIME = time.time()


def run(host="0.0.0.0", port=8000, fotos_dir=None, interval=30, quality=12, inactive=False):
    if fotos_dir:
        CameraUploadHandler.fotos_dir = Path(fotos_dir).resolve()
    CameraUploadHandler.fotos_dir.mkdir(parents=True, exist_ok=True)
    CameraUploadHandler.default_interval = interval
    CameraUploadHandler.default_quality = quality
    CameraUploadHandler.default_active = not inactive

    HTTPServer.allow_reuse_address = True
    server = HTTPServer((host, port), CameraUploadHandler)
    print("=" * 70)
    print("  PARQUEAME - Servidor de prueba para fotos de cámara")
    print(f"  Escuchando en:          http://{host}:{port}")
    print(f"  Endpoint POST subida:   http://{host}:{port}/api/v1/upload/<camera_id>")
    print(f"  Endpoint GET config:    http://{host}:{port}/api/v1/cameras/<camera_id>/config")
    print(f"  Endpoint PUT config:    http://{host}:{port}/api/v1/cameras/<camera_id>/config")
    print(f"  Endpoint GET raw/image: http://{host}:{port}/api/v1/cameras/<camera_id>/raw")
    print(f"  Configuración inicial:  interval={interval}s, active={not inactive}, quality={quality}")
    print(f"  Directorio fotos:       {CameraUploadHandler.fotos_dir}")
    print(f"  Galería web:            http://localhost:{port}")
    print("=" * 70)
    print("Esperando conexiones de la cámara... (Presiona Ctrl+C para detener)")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Servidor de prueba Parqueame")
    parser.add_argument("--host", default="0.0.0.0", help="Host/IP de escucha (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Puerto (default: 8000)")
    parser.add_argument("--dir", default=str(FOTOS_DIR), help="Directorio donde guardar fotos")
    parser.add_argument("--interval", type=int, default=30, help="Intervalo dinámico por defecto en segundos (default: 30)")
    parser.add_argument("--quality", type=int, default=12, help="Calidad JPEG por defecto (default: 12)")
    parser.add_argument("--inactive", action="store_true", help="Iniciar cámara como inactiva (pause)")
    args = parser.parse_args()

    run(
        host=args.host,
        port=args.port,
        fotos_dir=args.dir,
        interval=args.interval,
        quality=args.quality,
        inactive=args.inactive,
    )
