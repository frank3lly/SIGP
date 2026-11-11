# Parqueame Frontend API Data Contract & Integration Guide

## 1. Overview & Connection Architecture

This specification formalizes the REST data exchange contract between the **Parqueame Backend Engine** and the **Frontend Web Application** (`/app`).

### Base Server Endpoints
- **Local Development:** `http://localhost:8000`
- **LAN Access (Wi-Fi):** `http://<WSL_HOST_LAN_IP>:8000`
- **Interactive Documentation:** `http://localhost:8000/docs` (Swagger UI)

### Cross-Origin Resource Sharing (CORS)
The backend enforces permissive CORS across all endpoints:
- `Access-Control-Allow-Origin: *`
- `Access-Control-Allow-Methods: GET, POST, OPTIONS, PUT, DELETE`
- `Access-Control-Allow-Headers: *`

Frontend clients hosted on Vite (`http://localhost:5173`), local preview servers, or LAN mobile devices can query all endpoints directly without browser blocking or proxying.

---

## 2. API Endpoints Specification

### 1. `GET /api/v1/status` (Aggregated Parking Grid State)
- **Role:** Polled by the frontend every **3–5 seconds** to refresh the global parking grid, total availability counts, and per-camera spot polygon overlays.
- **Cache-Control:** `no-cache`
- **Success Response (200 OK):**
```json
{
  "total_spots": 28,
  "occupied_spots": 12,
  "free_spots": 16,
  "occupancy_rate": 0.4286,
  "timestamp": 1700000000.0,
  "cameras": {
    "cam_01": {
      "camera_id": "cam_01",
      "name": "UFPR04 Campus Lot - Cam 01",
      "total_spots": 28,
      "occupied_spots": 12,
      "free_spots": 16,
      "occupancy_rate": 0.4286,
      "last_processed_at": 1700000000.0,
      "battery_percentage": 94.5,
      "battery_voltage": 4.12,
      "spots": [
        {
          "spot_id": "spot_01",
          "occupied": true,
          "confidence": 0.88,
          "polygon": [[641, 570], [726, 671], [650, 708], [577, 602]]
        },
        {
          "spot_id": "spot_02",
          "occupied": false,
          "confidence": 0.0,
          "polygon": [[577, 602], [650, 708], [580, 740], [512, 630]]
        }
      ]
    }
  }
}
```

#### Field Dictionary (`/api/v1/status`):
| Field | Type | Description |
| :--- | :--- | :--- |
| `total_spots` | integer | Total parking stalls across all active cameras. |
| `occupied_spots` | integer | Total currently occupied stalls. |
| `free_spots` | integer | Total currently vacant stalls. |
| `occupancy_rate` | float | System-wide occupancy ratio (`0.0000` to `1.0000`). |
| `timestamp` | float | Server epoch timestamp in seconds. |
| `cameras` | object | Dictionary mapping each `camera_id` to its detailed camera status. |
| `cameras.{id}.battery_percentage` | float | Latest reported battery charge (e.g. `94.5`%). |
| `cameras.{id}.battery_voltage` | float | Latest reported battery voltage in Volts (e.g. `4.12`). |
| `cameras.{id}.spots` | array | Array of calibrated parking spots with polygon bounds and occupancy status. |
| `cameras.{id}.spots[].polygon` | array of [x, y] | Ordered 4-point polygon coordinates in image pixel space. |

---

### 2. `GET /api/v1/cameras/{camera_id}/status` (Single Camera State)
- **Role:** Fetches detailed spot status, battery telemetry, and metadata for a single camera.
- **Success Response (200 OK):**
```json
{
  "camera_id": "cam_01",
  "name": "UFPR04 Campus Lot - Cam 01",
  "total_spots": 28,
  "occupied_spots": 12,
  "free_spots": 16,
  "occupancy_rate": 0.4286,
  "last_processed_at": 1700000000.0,
  "battery_percentage": 94.5,
  "battery_voltage": 4.12,
  "spots": [
    {
      "spot_id": "spot_01",
      "occupied": true,
      "confidence": 0.88,
      "polygon": [[641, 570], [726, 671], [650, 708], [577, 602]]
    }
  ]
}
```

---

### 3. `GET /api/v1/cameras/{camera_id}/image` (Live Annotated Stream)
- **Role:** Serves the latest rolling visual JPEG frame annotated with green/red spot polygons and vehicle bounding boxes.
- **Content-Type:** `image/jpeg`
- **Cache-Busting Requirement:** Browsers cache image endpoints by default. The frontend **must** append a dynamic timestamp query parameter on every reload:
```javascript
// React / Vanilla JS usage:
const imageUrl = `http://localhost:8000/api/v1/cameras/cam_01/image?t=${Date.now()}`;
```
- **Error Response:**
  - `404 Not Found` if no image has been processed yet for the given camera.

---

### 4. `GET /api/v1/cameras/{camera_id}/raw` (Raw Hardware Capture)
- **Role:** Serves the latest unannotated raw camera image as received directly over HTTP from the physical camera microcontroller. Used for optical calibration, lens diagnostics, and indoor hardware testing verification.
- **Content-Type:** `image/jpeg`
- **Error Response:**
  - `404 Not Found` if no raw image has been uploaded yet for the given camera.

---

### 5. `GET /api/v1/analytics/cameras/{camera_id}/summary` (KPI Summary)
- **Role:** Supplies turnover, peak occupancy, and utilization metrics for dashboard cards and summary widgets.
- **Query Parameters:**
  - `hours` (float, optional, default: `2.0`): Historical analysis window in hours.
- **Success Response (200 OK):**
```json
{
  "camera_id": "cam_01",
  "total_observations": 120,
  "peak_occupied_spots": 24,
  "peak_occupancy_rate": 0.857,
  "total_turnovers": 45,
  "average_turnover_rate": 22.5
}
```

#### Field Dictionary (`/analytics/cameras/{camera_id}/summary`):
| Field | Type | Description |
| :--- | :--- | :--- |
| `camera_id` | string | Target camera identifier. |
| `total_observations` | integer | Number of processed frames analyzed in the time window. |
| `peak_occupied_spots` | integer | Highest occupied stall count recorded during the window. |
| `peak_occupancy_rate` | float | Peak occupancy ratio (`0.0` to `1.0`). |
| `total_turnovers` | integer | Total vehicle arrival and departure transition events. |
| `average_turnover_rate`| float | Average turnover rate per stall or hour. |

---

### 5. `GET /api/v1/analytics/cameras/{camera_id}/timeline` (Occupancy Timeline Series)
- **Role:** Supplies time-bucketed occupancy data points for line and bar charts (e.g., Chart.js, Recharts).
- **Query Parameters:**
  - `hours` (float, optional, default: `2.0`): Historical time window in hours.
  - `bucket_minutes` (integer, optional, default: `15`): Duration of each aggregate bucket.
- **Success Response (200 OK):**
```json
[
  {
    "timestamp": 1700000000.0,
    "time_label": "12:00",
    "occupied_spots": 12,
    "free_spots": 16,
    "occupancy_rate": 0.4286
  },
  {
    "timestamp": 1700000900.0,
    "time_label": "12:15",
    "occupied_spots": 14,
    "free_spots": 14,
    "occupancy_rate": 0.5000
  }
]
```

---

## 3. Frontend Polling & Performance Recommendations

1. **Occupancy Polling Frequency:**
   - Interval: **3 to 5 seconds** via `setInterval` or React `useQuery` / `swr`.
   - Polling endpoint: `GET /api/v1/status` (returns all cameras in a single round-trip).
2. **Visual Feed Refresh:**
   - Refresh the image only when `last_processed_at` in the status response changes, or periodically every 5 seconds with `?t=${Date.now()}`.
3. **Graceful Fallbacks:**
   - When the backend is offline, the frontend should display offline badge telemetry and preserve the last known state.

---

## 4. Offline Mock Fixtures for Standalone Frontend Development

For offline frontend UI design and unit testing, mock fixtures can be used directly:

```json
{
  "total_spots": 28,
  "occupied_spots": 10,
  "free_spots": 18,
  "occupancy_rate": 0.3571,
  "timestamp": 1700000000.0,
  "cameras": {
    "cam_01": {
      "camera_id": "cam_01",
      "name": "North Parking Stalls",
      "total_spots": 28,
      "occupied_spots": 10,
      "free_spots": 18,
      "occupancy_rate": 0.3571,
      "last_processed_at": 1700000000.0,
      "battery_percentage": 98.0,
      "battery_voltage": 4.18,
      "spots": [
        {
          "spot_id": "spot_01",
          "occupied": true,
          "confidence": 0.92,
          "polygon": [[100, 150], [200, 150], [200, 300], [100, 300]]
        },
        {
          "spot_id": "spot_02",
          "occupied": false,
          "confidence": 0.0,
          "polygon": [[210, 150], [310, 150], [310, 300], [210, 300]]
        }
      ]
    }
  }
}
```

---

## 5. Administrative & Fleet Management API

The administrative layer provides authenticated fleet control, dynamic camera reconfigurations, and a hardware photo gallery buffered strictly in memory (zero persistent disk writes).

### Authentication
Protected endpoints require an `Authorization: Bearer <token>` header or query param `?token=<token>` (for image elements). Tokens are verified against SQLite-backed persistent sessions.

| Endpoint | Method | Role | Auth Required |
|:---|:---|:---|:---|
| `/api/v1/admin/login` | `POST` | Authenticate administrator credentials | No |
| `/api/v1/admin/me` | `GET` | Validate active session token | Yes (`Bearer`) |
| `/api/v1/admin/logout` | `POST` | Invalidate session token | Yes (`Bearer`) |
| `/api/v1/admin/cameras` | `GET` | List camera fleet status and hot-configs | Yes (`Bearer`) |
| `/api/v1/admin/cameras/{id}/config` | `PUT` | Update camera interval, quality, and active state | Yes (`Bearer`) |
| `/api/v1/admin/gallery` | `GET` | Retrieve in-memory rolling photo gallery items | Yes (`Bearer`) |
| `/api/v1/admin/gallery/image/{name}` | `GET` | Stream raw or annotated frame bytes from RAM | Yes (`Bearer` / `?token=`) |

