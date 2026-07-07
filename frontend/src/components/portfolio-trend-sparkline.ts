// 30-day trend sparkline — Changeset C08 §8. Hand-written SVG, no charting
// library (Spec D10 §2's "no new runtime dependencies" rule).
//
// Rendered as per-segment <line> elements rather than a single <polyline> so
// that segments landing on an estimated day can be dashed individually — SVG
// has no way to vary stroke-dasharray within one polyline.

import { BaseComponent } from './common/base-component.js';
import { t } from '../i18n/i18n.js';
import { formatCurrency, formatDate } from '../utils/format.js';
import type { TrendPoint } from '../api/types.js';

const VIEW_W = 120;
const VIEW_H = 40;
const PAD_Y = 4;

interface Coord { x: number; y: number; point: TrendPoint }

export class PortfolioTrendSparkline extends BaseComponent {
  private _points: TrendPoint[] = [];
  private _currency = '';

  set points(value: TrendPoint[]) {
    this._points = value;
    this._rerender();
  }

  set currency(value: string) {
    this._currency = value;
    this._rerender();
  }

  private _rerender(): void {
    if (!this.shadow) return;
    this.shadow.innerHTML = this.render();
    this.afterRender();
  }

  private _coords(): Coord[] {
    const pts = this._points;
    if (pts.length === 0) return [];
    const values = pts.map((p) => Number(p.value));
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    return pts.map((p, i) => {
      const x = pts.length === 1 ? VIEW_W / 2 : (i / (pts.length - 1)) * VIEW_W;
      const norm = (Number(p.value) - min) / range;
      const y = VIEW_H - PAD_Y - norm * (VIEW_H - PAD_Y * 2);
      return { x, y, point: p };
    });
  }

  protected render(): string {
    const style = `
      <style>
        :host { display: block; position: relative; width: 120px; height: 40px; }
        svg { width: 100%; height: 100%; overflow: visible; display: block; }
        .segment { stroke: var(--color-accent); stroke-width: 1.5; stroke-linecap: round; }
        .segment.estimated { stroke-dasharray: 3 2; }
        .hit { fill: transparent; cursor: pointer; }
        .tooltip {
          position: absolute; top: 0; left: 50%; transform: translate(-50%, -100%);
          background: var(--color-text-primary); color: var(--color-bg-primary);
          border-radius: var(--radius-sm); padding: 2px 6px; font-size: var(--font-size-xs);
          white-space: nowrap; pointer-events: none; box-shadow: var(--shadow-md);
          display: none; z-index: var(--z-dropdown);
        }
        .tooltip.visible { display: block; }
      </style>
    `;

    const coords = this._coords();
    if (coords.length < 2) {
      return `${style}<svg viewBox="0 0 ${VIEW_W} ${VIEW_H}"></svg>`;
    }

    const segments = coords.slice(1).map((c, i) => {
      const prev = coords[i];
      const estimated = c.point.estimated ? ' estimated' : '';
      return `<line x1="${prev.x}" y1="${prev.y}" x2="${c.x}" y2="${c.y}" class="segment${estimated}" />`;
    }).join('');

    const dots = coords.map((c, i) =>
      `<circle cx="${c.x}" cy="${c.y}" r="5" class="hit" data-index="${i}" />`
    ).join('');

    return `
      ${style}
      <svg viewBox="0 0 ${VIEW_W} ${VIEW_H}" preserveAspectRatio="none">
        ${segments}
        ${dots}
      </svg>
      <div class="tooltip" id="tooltip"></div>
    `;
  }

  protected afterRender(): void {
    const coords = this._coords();
    const tooltip = this.shadow.getElementById('tooltip');
    if (!tooltip) return;

    const hide = () => tooltip.classList.remove('visible');
    const show = (c: Coord) => {
      const value = formatCurrency(Number(c.point.value), this._currency);
      const date = formatDate(c.point.date);
      const estimatedNote = c.point.estimated ? ` (${t('portfolio_header.tooltip.estimated')})` : '';
      tooltip.textContent = `${date} · ${value}${estimatedNote}`;
      tooltip.style.left = `${(c.x / VIEW_W) * 100}%`;
      tooltip.classList.add('visible');
    };

    this.shadow.querySelectorAll<SVGCircleElement>('.hit').forEach((hit, i) => {
      const c = coords[i];
      if (!c) return;
      hit.addEventListener('mouseenter', () => show(c));
      hit.addEventListener('mouseleave', hide);
      hit.addEventListener('click', (e) => {
        e.stopPropagation();
        tooltip.classList.contains('visible') ? hide() : show(c);
      });
    });

    // Tap outside a point hides the tooltip (mobile tap-to-show/hide). Attached
    // to the freshly-rendered <svg> (not the persistent shadow root) so this
    // listener doesn't accumulate across re-renders.
    this.shadow.querySelector('svg')?.addEventListener('click', hide);
  }
}

customElements.define('pi-portfolio-trend-sparkline', PortfolioTrendSparkline);
