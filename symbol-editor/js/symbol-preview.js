// <symbol-preview>: draws the symbol as SVG, with zoom (mouse wheel), pan (drag) and "Fit view".
//
// Call preview.show(units, settings) with the result of layoutSymbol().
// Clicking a pin fires a "pin-click" event with the pin in event.detail.
//
// Coordinates are mil, like in layout.js, but SVG's y axis points down, so every y is flipped.

import { propertyPositions } from './layout.js';

const UNIT_SPACING = 600; // mil between units
const FONT_SIZE = 50;
const NAME_OFFSET = 30; // gap between body edge and pin name

// Unit vector from a pin's connection point towards the body, in SVG coordinates.
const TOWARDS_BODY = { 0: [1, 0], 180: [-1, 0], 90: [0, -1], 270: [0, 1] };

class SymbolPreview extends HTMLElement {
  connectedCallback() {
    this.innerHTML = `
      <div class="toolbar"><button class="fit">Fit view</button></div>
      <svg><g class="content"></g></svg>`;
    this.svg = this.querySelector('svg');
    this.content = this.querySelector('.content');
    this.view = null; // { x, y, scale }: top left corner in mil, and mil per screen pixel
    this.shownPins = [];

    this.querySelector('.fit').addEventListener('click', () => this.fit());
    this.svg.addEventListener('wheel', event => this.onWheel(event), { passive: false });
    this.svg.addEventListener('pointerdown', event => this.onPointerDown(event));
    this.svg.addEventListener('pointermove', event => this.onPointerMove(event));
    this.svg.addEventListener('pointerup', event => this.onPointerUp(event));
    new ResizeObserver(() => this.applyView()).observe(this.svg);
  }

  // --- Drawing ---

  show(units, settings) {
    this.shownPins = [];
    let cursor = 0; // left edge of the next unit, including its pins
    let svg = '';
    for (const unit of units) {
      const centerX = cursor + unit.pinLength + unit.width / 2;
      svg += this.unitSvg(unit, centerX, units.length > 1, unit.unit === 1 ? settings : null);
      cursor = centerX + unit.width / 2 + unit.pinLength + UNIT_SPACING;
    }
    this.content.innerHTML = svg;
    if (!this.view && units.length > 0) this.fit();
  }

  // `settings` is only given for unit 1, which shows the Reference and Value texts.
  unitSvg(unit, centerX, showUnitName, settings) {
    const w = unit.width;
    const h = unit.height;
    const label = showUnitName
      ? `<text class="unit-label" x="${-w / 2}" y="${-h / 2 - unit.pinLength - 220}">Unit ${String.fromCharCode(64 + unit.unit)}</text>`
      : '';
    let properties = '';
    if (settings) {
      const { reference, value } = propertyPositions(unit);
      properties = `
        <text class="property" x="${reference.x}" y="${-reference.y}" dominant-baseline="central" font-size="${FONT_SIZE}">${escapeXml(settings.reference)}?</text>
        <text class="property" x="${value.x}" y="${-value.y}" dominant-baseline="central" font-size="${FONT_SIZE}">${escapeXml(settings.name)}</text>`;
    }
    const pins = unit.pins.filter(placed => !placed.stacked).map(placed => this.pinSvg(placed, unit.pinLength));
    return `<g transform="translate(${centerX} 0)">
      ${label}
      ${properties}
      <rect class="body" x="${-w / 2}" y="${-h / 2}" width="${w}" height="${h}"/>
      ${pins.join('')}
    </g>`;
  }

  pinSvg({ pin, x, y, angle, stackNumbers }, length) {
    const index = this.shownPins.push(pin) - 1;
    const [dx, dy] = TOWARDS_BODY[angle];
    const start = { x, y: -y };
    const end = { x: start.x + dx * length, y: start.y + dy * length };
    const middle = { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 };
    const vertical = dx === 0;
    const rotate = vertical ? 'rotate(-90)' : '';

    // The name sits inside the body, the number above the pin line.
    const nameX = end.x + dx * NAME_OFFSET;
    const nameY = end.y + dy * NAME_OFFSET;
    const nameAnchor = dx > 0 || dy < 0 ? 'start' : 'end';

    return `<g class="pin${pin.hidden ? ' hidden' : ''}" data-index="${index}">
      <line x1="${start.x}" y1="${start.y}" x2="${end.x}" y2="${end.y}"/>
      <text class="pin-name" transform="translate(${nameX} ${nameY}) ${rotate}" text-anchor="${nameAnchor}"
            dominant-baseline="central" font-size="${FONT_SIZE}">${escapeXml(pin.name)}</text>
      <text class="pin-number" transform="translate(${middle.x} ${middle.y}) ${rotate}" y="-12" text-anchor="middle"
            font-size="${FONT_SIZE}">${escapeXml(stackNumbers.join(','))}</text>
    </g>`;
  }

  // --- Zoom and pan ---

  applyView() {
    if (!this.view) return;
    const { x, y, scale } = this.view;
    const box = this.svg.getBoundingClientRect();
    this.svg.setAttribute('viewBox', `${x} ${y} ${box.width * scale} ${box.height * scale}`);
  }

  fit() {
    const content = this.content.getBBox();
    const box = this.svg.getBoundingClientRect();
    if (content.width === 0 || box.width === 0) return;
    const scale = 1.1 * Math.max(content.width / box.width, content.height / box.height);
    this.view = {
      x: content.x + content.width / 2 - box.width * scale / 2,
      y: content.y + content.height / 2 - box.height * scale / 2,
      scale,
    };
    this.applyView();
  }

  onWheel(event) {
    event.preventDefault();
    if (!this.view) return;
    const box = this.svg.getBoundingClientRect();
    const px = event.clientX - box.left;
    const py = event.clientY - box.top;
    // Keep the point under the mouse where it is.
    const pointX = this.view.x + px * this.view.scale;
    const pointY = this.view.y + py * this.view.scale;
    const scale = this.view.scale * (event.deltaY > 0 ? 1.15 : 1 / 1.15);
    this.view = { x: pointX - px * scale, y: pointY - py * scale, scale };
    this.applyView();
  }

  onPointerDown(event) {
    if (!this.view) return;
    this.svg.setPointerCapture(event.pointerId);
    this.drag = {
      clientX: event.clientX,
      clientY: event.clientY,
      view: { ...this.view },
      pinElement: event.target.closest('.pin'),
      moved: false,
    };
  }

  onPointerMove(event) {
    if (!this.drag) return;
    const dx = event.clientX - this.drag.clientX;
    const dy = event.clientY - this.drag.clientY;
    if (Math.abs(dx) + Math.abs(dy) > 3) this.drag.moved = true;
    const { x, y, scale } = this.drag.view;
    this.view = { x: x - dx * scale, y: y - dy * scale, scale };
    this.applyView();
  }

  onPointerUp() {
    const drag = this.drag;
    this.drag = null;
    if (drag && !drag.moved && drag.pinElement) {
      const pin = this.shownPins[drag.pinElement.dataset.index];
      this.dispatchEvent(new CustomEvent('pin-click', { detail: pin, bubbles: true }));
    }
  }
}

function escapeXml(text) {
  return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

customElements.define('symbol-preview', SymbolPreview);
