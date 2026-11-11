/**
 * SGIP - Interactive Map Viewport Controller
 * Free 2D Pan, Cursor-Centered Zoom, Touch Gestures, and Bounds Management.
 */

import { CONFIG } from './config.js';

export function getSpotCentroid(spotElement) {
  try {
    const bbox = spotElement.getBBox();
    return {
      cx: bbox.x + bbox.width / 2,
      cy: bbox.y + bbox.height / 2,
      width: bbox.width,
      height: bbox.height,
    };
  } catch {
    return { cx: 92, cy: 91, width: 8, height: 16 };
  }
}

export class ViewportController {
  constructor(containerEl, svgEl, zoomLayerEl, badgeEl) {
    this.container = containerEl;
    this.svg = svgEl || (containerEl ? containerEl.querySelector('svg.map-svg') : null);
    this.layer = zoomLayerEl;
    this.badge = badgeEl;

    this.scale = 1.0;
    this.minScale = CONFIG.MIN_ZOOM || 0.8;
    this.maxScale = CONFIG.MAX_ZOOM || 3.5;
    this.x = 0;
    this.y = 0;

    this.viewBoxCenterX = 92;
    this.viewBoxCenterY = 91;
    this.viewBoxWidth = 200;
    this.viewBoxHeight = 198;

    this.isDragging = false;
    this.dragStartMouseX = 0;
    this.dragStartMouseY = 0;
    this.dragStartX = 0;
    this.dragStartY = 0;
    this.hasMovedSignificantly = false;

    this.animId = null;
    this.touchStartDist = null;
    this.touchStartCenter = null;
    this.touchStartX = 0;
    this.touchStartY = 0;

    this.init();
  }

  init() {
    if (!this.container || !this.layer) return;

    // Trigger Entrance Animation
    this.container.classList.add('map-viewport-entering');
    const onAnimEnd = () => {
      this.container.classList.remove('map-viewport-entering');
      this.container.removeEventListener('animationend', onAnimEnd);
    };
    this.container.addEventListener('animationend', onAnimEnd);

    this.bindEvents();
    this.applyTransform();
  }

  bindEvents() {
    // Mouse Dragging (Grab & Move)
    this.container.addEventListener('mousedown', (e) => this.handleMouseDown(e));
    window.addEventListener('mousemove', (e) => this.handleMouseMove(e));
    window.addEventListener('mouseup', () => this.handleMouseUp());

    // Wheel zoom towards cursor
    this.container.addEventListener('wheel', (e) => this.handleWheel(e), { passive: false });

    // Touch events (Pan & Pinch)
    this.container.addEventListener('touchstart', (e) => this.handleTouchStart(e), { passive: false });
    this.container.addEventListener('touchmove', (e) => this.handleTouchMove(e), { passive: false });
    this.container.addEventListener('touchend', (e) => this.handleTouchEnd(e));
    this.container.addEventListener('touchcancel', (e) => this.handleTouchEnd(e));
  }

  cancelAnimation() {
    if (this.animId) {
      cancelAnimationFrame(this.animId);
      this.animId = null;
    }
  }

  getSvgRatio() {
    if (!this.svg) return { rx: 0.227, ry: 0.227 };
    const rect = this.svg.getBoundingClientRect();
    const rx = rect.width > 0 ? this.viewBoxWidth / rect.width : 0.227;
    const ry = rect.height > 0 ? this.viewBoxHeight / rect.height : 0.227;
    return { rx, ry };
  }

  screenToSvgPoint(clientX, clientY) {
    if (this.svg && this.svg.createSVGPoint && this.svg.getScreenCTM) {
      try {
        const pt = this.svg.createSVGPoint();
        pt.x = clientX;
        pt.y = clientY;
        const ctm = this.svg.getScreenCTM();
        if (ctm) {
          const inv = ctm.inverse();
          const p = pt.matrixTransform(inv);
          return {
            x: (p.x - this.x) / this.scale,
            y: (p.y - this.y) / this.scale,
          };
        }
      } catch {
        // fallback below
      }
    }
    const rect = this.container.getBoundingClientRect();
    const { rx, ry } = this.getSvgRatio();
    return {
      x: (clientX - rect.left) * rx,
      y: (clientY - rect.top) * ry,
    };
  }

  handleMouseDown(e) {
    if (e.button !== 0) return;
    this.cancelAnimation();

    this.isDragging = true;
    this.hasMovedSignificantly = false;
    this.dragStartMouseX = e.clientX;
    this.dragStartMouseY = e.clientY;
    this.dragStartX = this.x;
    this.dragStartY = this.y;

    this.container.classList.add('is-dragging');
  }

  handleMouseMove(e) {
    if (!this.isDragging) return;

    const deltaPixelX = e.clientX - this.dragStartMouseX;
    const deltaPixelY = e.clientY - this.dragStartMouseY;

    if (!this.hasMovedSignificantly && Math.hypot(deltaPixelX, deltaPixelY) > 4) {
      this.hasMovedSignificantly = true;
    }

    const { rx, ry } = this.getSvgRatio();
    this.x = this.dragStartX + deltaPixelX * rx;
    this.y = this.dragStartY + deltaPixelY * ry;

    this.clampBounds();
    this.applyTransform();
  }

  handleMouseUp() {
    if (!this.isDragging) return;
    this.isDragging = false;
    this.container.classList.remove('is-dragging');
  }

  handleWheel(e) {
    e.preventDefault();
    this.cancelAnimation();

    const zoomStep = 0.15;
    const zoomFactor = e.deltaY < 0 ? (1 + zoomStep) : (1 - zoomStep);
    const nextScale = Math.max(this.minScale, Math.min(this.maxScale, this.scale * zoomFactor));

    if (nextScale === this.scale) return;

    const pt = this.screenToSvgPoint(e.clientX, e.clientY);

    this.x = this.x - pt.x * (nextScale - this.scale);
    this.y = this.y - pt.y * (nextScale - this.scale);
    this.scale = nextScale;

    this.clampBounds();
    this.applyTransform();
  }

  handleTouchStart(e) {
    this.cancelAnimation();
    if (e.touches.length === 1) {
      this.isDragging = true;
      this.hasMovedSignificantly = false;
      this.dragStartMouseX = e.touches[0].clientX;
      this.dragStartMouseY = e.touches[0].clientY;
      this.dragStartX = this.x;
      this.dragStartY = this.y;
    } else if (e.touches.length === 2) {
      e.preventDefault();
      this.isDragging = false;
      const t1 = e.touches[0];
      const t2 = e.touches[1];
      this.touchStartDist = Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY);
      this.touchStartCenter = {
        x: (t1.clientX + t2.clientX) / 2,
        y: (t1.clientY + t2.clientY) / 2,
      };
      this.touchStartX = this.x;
      this.touchStartY = this.y;
    }
  }

  handleTouchMove(e) {
    if (e.touches.length === 1 && this.isDragging) {
      const deltaPixelX = e.touches[0].clientX - this.dragStartMouseX;
      const deltaPixelY = e.touches[0].clientY - this.dragStartMouseY;

      if (!this.hasMovedSignificantly && Math.hypot(deltaPixelX, deltaPixelY) > 5) {
        this.hasMovedSignificantly = true;
      }

      const { rx, ry } = this.getSvgRatio();
      this.x = this.dragStartX + deltaPixelX * rx;
      this.y = this.dragStartY + deltaPixelY * ry;
      this.clampBounds();
      this.applyTransform();
    } else if (e.touches.length === 2 && this.touchStartDist) {
      e.preventDefault();
      this.hasMovedSignificantly = true;
      const t1 = e.touches[0];
      const t2 = e.touches[1];
      const currentDist = Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY);
      const ratio = currentDist / this.touchStartDist;
      const nextScale = Math.max(this.minScale, Math.min(this.maxScale, this.scale * ratio));

      const center = {
        x: (t1.clientX + t2.clientX) / 2,
        y: (t1.clientY + t2.clientY) / 2,
      };

      const pt = this.screenToSvgPoint(center.x, center.y);
      this.x = this.x - pt.x * (nextScale - this.scale);
      this.y = this.y - pt.y * (nextScale - this.scale);
      this.scale = nextScale;
      this.touchStartDist = currentDist;

      this.clampBounds();
      this.applyTransform();
    }
  }

  handleTouchEnd(e) {
    if (e.touches.length === 0) {
      this.isDragging = false;
      this.touchStartDist = null;
    } else if (e.touches.length === 1) {
      this.touchStartDist = null;
      this.isDragging = true;
      this.dragStartMouseX = e.touches[0].clientX;
      this.dragStartMouseY = e.touches[0].clientY;
      this.dragStartX = this.x;
      this.dragStartY = this.y;
    }
  }

  clampBounds() {
    const maxPanX = this.viewBoxWidth * 0.75 * this.scale;
    const maxPanY = this.viewBoxHeight * 0.75 * this.scale;
    this.x = Math.max(-maxPanX, Math.min(maxPanX, this.x));
    this.y = Math.max(-maxPanY, Math.min(maxPanY, this.y));
  }

  applyTransform() {
    if (!this.layer) return;
    this.layer.setAttribute(
      'transform',
      `translate(${this.x.toFixed(2)}, ${this.y.toFixed(2)}) scale(${this.scale.toFixed(4)})`
    );
    if (this.badge) {
      this.badge.textContent = Math.round(this.scale * 100) + '%';
    }
  }

  zoomIn(step = CONFIG.DEFAULT_ZOOM_STEP) {
    this.animateToScale(this.scale + step);
  }

  zoomOut(step = CONFIG.DEFAULT_ZOOM_STEP) {
    this.animateToScale(this.scale - step);
  }

  animateToScale(targetScale) {
    this.cancelAnimation();
    const clampedScale = Math.max(this.minScale, Math.min(this.maxScale, targetScale));
    const startScale = this.scale;
    const startX = this.x;
    const startY = this.y;

    const cx = this.viewBoxCenterX;
    const cy = this.viewBoxCenterY;
    const targetX = startX - cx * (clampedScale - startScale);
    const targetY = startY - cy * (clampedScale - startScale);

    const startTime = performance.now();
    const duration = 240;

    const animate = (now) => {
      const elapsed = now - startTime;
      const t = Math.min(1.0, elapsed / duration);
      const ease = 1 - Math.pow(1 - t, 3);

      this.scale = startScale + (clampedScale - startScale) * ease;
      this.x = startX + (targetX - startX) * ease;
      this.y = startY + (targetY - startY) * ease;

      this.clampBounds();
      this.applyTransform();

      if (t < 1.0) {
        this.animId = requestAnimationFrame(animate);
      } else {
        this.animId = null;
      }
    };
    this.animId = requestAnimationFrame(animate);
  }

  zoomToSpot(cx, cy, targetScale = 2.25, durationMs = 450) {
    this.cancelAnimation();

    const startScale = this.scale;
    const startX = this.x;
    const startY = this.y;

    let effectiveCenterY = this.viewBoxCenterY;
    if (typeof window !== 'undefined' && window.innerWidth <= 768) {
      // Offset visible center upwards to account for mobile bottom drawer
      effectiveCenterY = this.viewBoxCenterY - 14;
    }

    const targetX = this.viewBoxCenterX - cx * targetScale;
    const targetY = effectiveCenterY - cy * targetScale;

    const startTime = performance.now();

    const animate = (now) => {
      const elapsed = now - startTime;
      const progress = Math.min(1.0, elapsed / durationMs);
      const ease = 1 - Math.pow(1 - progress, 3); // cubic ease out

      this.scale = startScale + (targetScale - startScale) * ease;
      this.x = startX + (targetX - startX) * ease;
      this.y = startY + (targetY - startY) * ease;

      this.clampBounds();
      this.applyTransform();

      if (progress < 1.0) {
        this.animId = requestAnimationFrame(animate);
      } else {
        this.animId = null;
      }
    };

    this.animId = requestAnimationFrame(animate);
  }

  reset(duration = 320) {
    this.cancelAnimation();
    const startScale = this.scale;
    const startX = this.x;
    const startY = this.y;
    const targetScale = 1.0;
    const targetX = 0;
    const targetY = 0;

    const startTime = performance.now();

    const animate = (now) => {
      const elapsed = now - startTime;
      const t = Math.min(1.0, elapsed / duration);
      const ease = 1 - Math.pow(1 - t, 3);

      this.scale = startScale + (targetScale - startScale) * ease;
      this.x = startX + (targetX - startX) * ease;
      this.y = startY + (targetY - startY) * ease;

      this.applyTransform();

      if (t < 1.0) {
        this.animId = requestAnimationFrame(animate);
      } else {
        this.animId = null;
      }
    };
    this.animId = requestAnimationFrame(animate);
  }
}
