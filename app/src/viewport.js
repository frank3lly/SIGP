/**
 * SGIP - 2D Viewport & Transform Controller
 */

import { CONFIG } from './config.js';

export class ViewportController {
  constructor(containerEl, svgEl, zoomLayerEl, badgeEl) {
    this.container = containerEl;
    this.svg = svgEl;
    this.layer = zoomLayerEl;
    this.badge = badgeEl;

    this.scale = 1.0;
    this.minScale = CONFIG.MIN_ZOOM || 0.8;
    this.maxScale = CONFIG.MAX_ZOOM || 3.5;
    this.x = 0;
    this.y = 0;

    this.isDragging = false;
    this.dragStartX = 0;
    this.dragStartY = 0;
    this.hasMovedSignificantly = false;
    this.animId = null;

    this.init();
  }

  init() {
    this.applyTransform();
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
    this.setScale(this.scale + step);
  }

  zoomOut(step = CONFIG.DEFAULT_ZOOM_STEP) {
    this.setScale(this.scale - step);
  }

  setScale(newScale) {
    this.scale = Math.max(this.minScale, Math.min(this.maxScale, newScale));
    this.applyTransform();
  }

  reset() {
    this.scale = 1.0;
    this.x = 0;
    this.y = 0;
    this.applyTransform();
  }
}
