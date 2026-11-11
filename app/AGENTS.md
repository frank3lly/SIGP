---
name: sgip-web-reproduction
description: Skill and master specification for an AI agent to reproduce pixel-perfect the SGIP web interface (app/index.html) and its 2D parking lot SVG canvas.
---

# SGIP Web Reproduction Skill

This specification enables any autonomous AI agent to reconstruct or verify `app/index.html` with pixel-perfect precision. It defines design tokens, layout hierarchy, exact SVG coordinates and transforms, the uniform zoom engine, and interactive behavior.

---

## 1. Core Directives and Hard Constraints

1. **Strictly Zero Emojis**: Never output, render, or inject emojis into HTML, CSS, JavaScript, attributes, or text content. Use clean SVG micro-icons with a consistent stroke style.
2. **Project Identity**: The project name is **SGIP** (Sistema de Gestión Inteligente de Parqueos), not *parqueame*.
3. **Single File Web Architecture**: The entire application is self-contained in `app/index.html` (embedded CSS in `<style>` and embedded JS in `<script>`), consuming only `logo.svg` and favicon assets.
4. **Source of Truth for Geometry**: The 2D parking map follows the physical layout of the central parking lot at Universidad Central del Este (UCE), San Pedro de Macorís.

---

## 2. Design System and Token Specification

All visual styles must use the following CSS custom properties defined in `:root`:

```css
:root {
  /* Page and Surface */
  --bg-page: #ffffff;
  --bg-surface: #f8fafc;
  --bg-card: #ffffff;

  /* Brand Secondary */
  --color-secondary: #20124d;          /* HEX #20124d | RGB(32, 18, 77) */
  --color-secondary-light: #311c75;
  --color-secondary-subtle: #f0eef8;

  /* Parking Spot Statuses */
  --color-free: #16a34a;
  --color-free-bg: #dcfce7;
  --color-free-border: #86efac;

  --color-occupied: #dc2626;
  --color-occupied-bg: #fee2e2;
  --color-occupied-border: #fca5a5;

  --color-warning: #d97706;
  --color-warning-bg: #fef3c7;
  --color-warning-border: #fcd34d;

  /* Asphalt Polygon */
  --color-asphalt: #556274;           /* Uniform lighter slate asphalt */
  --color-asphalt-edge: #3a4554;      /* Perimeter stroke border */

  /* Neutral Typography and Borders */
  --text-main: #0f172a;
  --text-muted: #64748b;
  --text-subtle: #94a3b8;
  --border-color: #e2e8f0;
  --border-dark: #cbd5e1;

  /* Elevations and Radii */
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
  --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.08), 0 2px 4px -2px rgba(0, 0, 0, 0.04);
  --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.08), 0 4px 6px -4px rgba(0, 0, 0, 0.03);

  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 16px;
}
```

### Tree and Foliage Palette (Volume via 3 Flat Shades)
Trees are rendered as flat vector circles without gradients, using overlapping circles to produce visual volume:
* **Verde Oliva Oscuro**: `#196F3D` (Base shadows and lower clusters)
* **Verde Pino Medio**: `#27AE60` (Mid canopy and body)
* **Esmeralda Suave**: `#1ABC9C` (Top highlights and accents)

---

## 3. DOM Layout Structure

The document follows a vertical flex column layout on `body`:

```html
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SGIP - Sistema de Gestión Inteligente de Parqueos | UCE</title>
  <link rel="icon" type="image/svg+xml" href="public/logo.svg">
  <link rel="alternate icon" type="image/png" href="public/favicon.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
</head>
<body>
  <!-- 1. Top Navbar (height: 64px, sticky, z-index: 60) -->
  <header class="navbar"> ... </header>

  <!-- 2. Subheader Bar (height: 64px, z-index: 50, metrics & filter buttons) -->
  <section class="subheader"> ... </section>

  <!-- 3. Canvas Viewport (flex: 1, overflow: hidden, background: #f8fafc) -->
  <main class="canvas-viewport" id="mapContainer">
    <div class="zoom-widget"> ... </div>
    <div class="zoom-badge" id="zoomBadge">100%</div>
    <svg class="map-svg" viewBox="-8 -8 200 198">
      <g id="zoomLayer">
        <!-- Layer 1: Perimeter Foliage (222 circles) -->
        <g id="perimeterTrees"> ... </g>
        <!-- Layer 2: Asphalt Polygon -->
        <path id="perimetro" class="perimeter-asphalt" d="..." />
        <!-- Layer 3: Central Gap Foliage on top of asphalt (142 circles) -->
        <g id="centralTrees"> ... </g>
        <!-- Layer 4: 12 Aisle Groups (219 standardized spots) -->
        <g id="parkingLots"> ... </g>
      </g>
    </svg>
  </main>

  <!-- 4. Spot Details Drawer Modal (slide-in from right, max-width: 380px, z-index: 160) -->
  <div class="drawer-backdrop" id="drawerBackdrop"></div>
  <aside class="drawer" id="spotDrawer"> ... </aside>

  <!-- 5. Toast Notification for Coming Soon Locations -->
  <div class="toast" id="toast"> ... </div>
</body>
</html>
```

---

## 4. SVG Vector Map Geometry and Aisle Transforms

### 4.1 SVG Root Parameters
* Element: `<svg class="map-svg" viewBox="-8 -8 200 198">`
* CSS dimensions: `width: 880px; height: 866px; overflow: visible; display: block;`
* Aspect ratio: $200 / 198 \approx 1.01$
* True geometric center of coordinate space: $(cx, cy) = (92.0, 91.0)$

### 4.2 Asphalt Perimeter Path
```xml
<path id="perimetro" class="perimeter-asphalt" d="M 4.492,83.943 A 4.500,4.500 0 0,1 6.195,78.052 L 126.134,6.193 A 4.500,4.500 0 0,1 132.613,8.351 L 180.383,125.262 A 4.500,4.500 0 0,1 177.830,131.166 L 56.448,177.743 A 4.500,4.500 0 0,1 50.820,175.572 Z" />
```

### 4.3 Standard Spot Rect Specification
Every single spot in the entire map must strictly have:
* Width: `3.300`
* Height: `7.800`
* Corner radii: `rx="0.550" ry="0.550"`
* Stroke: `stroke: #ffffff; stroke-width: 0.35;`
* Column pitch: `3.540` (horizontal spacing between adjacent stalls in an aisle)
* Double-row side offset: $Y = 0.000$ for Side A, $Y = 8.600$ for Side B
* Centered spot number:
  `<text class="spot-num" x="{x + 1.650}" y="{y + 4.250}">{number}</text>`

### 4.4 The 12 Aisle Group Definitions and Transforms

| Group ID | Aisle Name | Stall Count | Double Row? | Transform String |
| :--- | :--- | :--- | :--- | :--- |
| `L1` | Hilera L1 | 18 (9x2) | Yes | `translate(14.490, 93.520) rotate(-31.50)` |
| `L2` | Hilera L2 | 18 (9x2) | Yes | `rotate(-31.5, 219.57772, 10.365522)` |
| `L3` | Hilera L3 | 18 (9x2) | Yes | `rotate(-31.5, 261.90956, -0.12037212)` |
| `L4` | Hilera L4 | 18 (9x2) | Yes | `rotate(-31.5, 303.64197, -12.047235)` |
| `LW-top` | Hilera Superior Oeste | 11 (11x1) | No | `translate(29.050, 64.150) rotate(-30.70)` |
| `LE-top` | Hilera Superior Este | 11 (11x1) | No | `translate(86.830, 29.460) rotate(-30.70)` |
| `R1` | Hilera R1 | 28 (14x2) | Yes | `rotate(-31.5, 138.08264, -111.79919)` |
| `R2` | Hilera R2 | 28 (14x2) | Yes | `translate(91.570, 76.600) rotate(-31.50)` |
| `R3` | Hilera R3 | 28 (14x2) | Yes | `rotate(-31.5, 229.92611, -132.23128)` |
| `R4` | Hilera R4 | 28 (14x2) | Yes | `rotate(-25.5, 324.57991, -193.00244)` |
| `R-bot` | Hilera Inferior Este | 10 (10x1) | No | `rotate(-22, 423.25634, -276.39562)` |
| `R-aux` | Hilera Auxiliar Sur | 3 (3x1) | No | `translate(121.085, 143.691) rotate(-21.48)` |
| **Total** | | **219 Plazas** | | |

---

## 5. Pure Uniform Zoom Engine

The zoom engine scales the map smoothly and symmetrically from the true geometric center $(92, 91)$. Scrolling the mouse wheel displaces the page naturally, while holding `Ctrl` + wheel or using the zoom widget scales the map.

### 5.1 CSS Zoom Setup
```css
.canvas-viewport {
  position: relative;
  flex: 1;
  width: 100%;
  min-height: calc(100vh - 128px);
  background-color: #f8fafc;
  overflow: visible;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 24px 20px 48px;
}

.map-svg {
  width: 880px;
  height: 866px;
  display: block;
  user-select: none;
  overflow: visible; /* Prevents viewport boundary clipping */
}

#zoomLayer {
  transform-origin: 92px 91px;
  will-change: transform;
  transition: transform 0.18s cubic-bezier(0.16, 1, 0.3, 1);
}
```

### 5.2 JavaScript Zoom Implementation
```javascript
let currentZoom = 1.0;
const minZoom = 1.0;
const maxZoom = 2.4;
const zoomStep = 0.20;

const zoomLayer = document.getElementById('zoomLayer');
const zoomBadge = document.getElementById('zoomBadge');

function updateZoom(newZoom) {
  currentZoom = Math.max(minZoom, Math.min(maxZoom, newZoom));
  zoomLayer.setAttribute('transform', 'translate(92, 91) scale(' + currentZoom.toFixed(3) + ') translate(-92, -91)');
  zoomBadge.textContent = Math.round(currentZoom * 100) + '%';
}

document.getElementById('btnZoomIn').addEventListener('click', (e) => {
  e.stopPropagation();
  updateZoom(currentZoom + zoomStep);
});

document.getElementById('btnZoomOut').addEventListener('click', (e) => {
  e.stopPropagation();
  updateZoom(currentZoom - zoomStep);
});

document.getElementById('btnResetZoom').addEventListener('click', (e) => {
  e.stopPropagation();
  updateZoom(1.0);
});

// Wheel scroll: natural page scroll. Zoom via wheel only with Ctrl/Cmd.
document.getElementById('mapContainer').addEventListener('wheel', (e) => {
  if (e.ctrlKey || e.metaKey) {
    e.preventDefault();
    const delta = e.deltaY < 0 ? zoomStep : -zoomStep;
    updateZoom(currentZoom + delta);
  }
}, { passive: false });
```

---

## 6. Interactive Behavior Specifications

### 6.1 Spot Selection and Modal Drawer
* Clicking any `.spot-node` reads `data-id`.
* Removes `.selected` from the previously active spot and adds `.selected` to the current one.
* Updates drawer fields:
  * Title: `Espacio {id}`
  * Sector: `{zone} ({side})`
  * Sensor confidence: `{conf}% (Modelo Óptico)`
  * GPS coordinates: `{lat}, {lng}`
  * Card status class: `free`, `occupied`, or `warning`
  * Google Maps routing URL:
    `https://www.google.com/maps/dir/?api=1&destination={lat},{lng}`
* Adds class `.active` to `#spotDrawer` and `#drawerBackdrop`.

### 6.2 Status Filter Toggle
Buttons in `.filters-group`:
* `data-filter="all"`: Removes `.dimmed` from all `.spot-node` elements.
* `data-filter="free"`: Adds `.dimmed` (opacity 0.18, `pointer-events: none`) to nodes where `data-status !== 'free'`.
* `data-filter="occupied"`: Adds `.dimmed` to nodes where `data-status !== 'occupied'`.

### 6.3 Covered Locations Dropdown
* Clicking `#searchWrapper` toggles `.active` on `#searchContainer`.
* 8 locations in list:
  1. `Campus Principal UCE (San Pedro de Macorís)`: `data-active="true"` (Active).
  2. `Multiplaza Higüey`: `data-active="false"` (Próximamente).
  3. `Plaza de la Restauración`: `data-active="false"` (Próximamente).
  4. `Parqueo de la Basílica de Higüey`: `data-active="false"` (Próximamente).
  5. `Jumbo San Pedro`: `data-active="false"` (Próximamente).
  6. `Multiplaza La Romana`: `data-active="false"` (Próximamente).
  7. `Jumbo La Romana`: `data-active="false"` (Próximamente).
  8. `Bávaro City Center`: `data-active="false"` (Próximamente).
* Selecting an inactive location triggers `#toast` with: `"{name} estará disponible próximamente. La locación activa es el Campus Principal UCE."` for 3.6 seconds.

---

## 7. Automated Reproduction Workflow for Agents

An agent can reconstruct `app/index.html` from scratch by executing the generator script:
```bash
python3 /home/thegxnster/.gemini/antigravity-cli/brain/e209f0a4-0d4a-4168-80b6-3b087668a2f6/scratch/generate_final_app.py
```

### Verification Checklist:
* `node --check` passes with return code 0 on the embedded `<script>`.
* Tree circles strictly use `#196F3D`, `#27AE60`, or `#1ABC9C`.
* Regex check `[\U00010000-\U0010ffff]` returns 0 emojis.
* Total spot nodes in SVG exactly equals 219.
* `zoomLayer` transform origin is `(92, 91)`.
* `logo.svg` has transparent background and `#20124d` fill.
