// Time-series chart with real axes: labelled y ticks, time axis in seconds,
// a cursor at the current time, click/keyboard to seek.
import { h } from "./dom";

const NS = "http://www.w3.org/2000/svg";

function el(tag: string, attrs: Record<string, string | number>): SVGElement {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  return e;
}

function niceStep(v: number): number {
  if (v <= 0) return 1;
  const e = 10 ** Math.floor(Math.log10(v));
  const f = v / e;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * e;
}

function tickLabel(v: number, step: number): string {
  if (v >= 1000 && step >= 100) {
    const k = v / 1000;
    return `${Number.isInteger(k) ? k : k.toFixed(1)}k`;
  }
  const digits = step >= 1 ? 0 : step >= 0.1 ? 1 : 2;
  return v.toFixed(digits);
}

export interface ChartOptions {
  title: string;
  unit: string;
  digits?: number;
  onSeek?: (t: number) => void;
}

export class TimeChart {
  readonly root: HTMLElement;
  private svgEl: SVGSVGElement;
  private peak: HTMLSpanElement;
  private cursor?: SVGElement;
  private tMax = 1;
  private W = 340;
  private H = 120;
  private pad = { l: 44, r: 8, t: 6, b: 22 };
  private opts: ChartOptions;

  constructor(opts: ChartOptions) {
    this.opts = opts;
    this.peak = h("span");
    this.svgEl = document.createElementNS(NS, "svg") as SVGSVGElement;
    this.svgEl.setAttribute("viewBox", `0 0 ${this.W} ${this.H}`);
    this.svgEl.setAttribute("role", "img");
    this.svgEl.setAttribute("aria-label", `${opts.title} over time`);
    this.root = h(
      "div",
      { class: "chart" },
      h("div", { class: "chart-title" }, h("span", {}, `${opts.title} (${opts.unit})`), this.peak),
      this.svgEl,
    );
    if (opts.onSeek) {
      this.svgEl.addEventListener("click", (e) => {
        const r = this.svgEl.getBoundingClientRect();
        const x = ((e.clientX - r.left) / r.width) * this.W;
        const t = ((x - this.pad.l) / (this.W - this.pad.l - this.pad.r)) * this.tMax;
        opts.onSeek!(Math.min(Math.max(t, 0), this.tMax));
      });
    }
  }

  /** Draw series; tEnd sets the axis even when data so far covers less. */
  setData(t: number[], v: number[], tEnd: number): void {
    const { W, H, pad } = this;
    const s = this.svgEl;
    s.replaceChildren();
    this.tMax = Math.max(tEnd, 1e-9);
    const vstep = niceStep(Math.max(Math.max(...v, 0), 1e-9) / 4);
    const nTicks = Math.max(1, Math.ceil((Math.max(...v, 0) * 1.02) / vstep));
    const vmax = vstep * nTicks;
    const X = (tt: number) => pad.l + (tt / this.tMax) * (W - pad.l - pad.r);
    const Y = (vv: number) => H - pad.b - (vv / vmax) * (H - pad.t - pad.b);
    const d = this.opts.digits ?? 0;
    for (let k = 0; k <= nTicks; k++) {
      const vv = vstep * k;
      const y = Y(vv);
      s.append(el("line", { class: "gridline", x1: pad.l, x2: W - pad.r, y1: y, y2: y }));
      const g = el("g", { class: "tick" });
      const txt = el("text", { x: pad.l - 5, y: y + 3.5, "text-anchor": "end" });
      txt.textContent = tickLabel(vv, vstep);
      g.append(txt);
      s.append(g);
    }
    const tStep = niceStep(this.tMax / 5);
    for (let tt = 0; tt <= this.tMax + 1e-9; tt += tStep) {
      const x = X(tt);
      const g = el("g", { class: "tick" });
      g.append(el("line", { class: "axis", x1: x, x2: x, y1: H - pad.b, y2: H - pad.b + 3 }));
      const txt = el("text", { x, y: H - 6, "text-anchor": "middle" });
      txt.textContent = `${Math.round(tt)}`;
      g.append(txt);
      s.append(g);
    }
    const unit = el("text", { x: W - pad.r, y: H - 6, "text-anchor": "end", class: "tick" });
    unit.setAttribute("style", "fill: var(--muted); font-size: 10.5px");
    unit.textContent = "s";
    s.append(el("line", { class: "axis", x1: pad.l, x2: W - pad.r, y1: H - pad.b, y2: H - pad.b }));
    s.append(el("line", { class: "axis", x1: pad.l, x2: pad.l, y1: pad.t, y2: H - pad.b }));
    if (t.length > 1) {
      const pts = t.map((tt, i) => `${X(tt).toFixed(1)},${Y(v[i]).toFixed(1)}`).join(" ");
      s.append(el("polyline", { class: "series", points: pts }));
    }
    this.cursor = el("line", { class: "cursor", x1: pad.l, x2: pad.l, y1: pad.t, y2: H - pad.b });
    s.append(this.cursor);
    const peak = Math.max(...v, 0);
    this.peak.textContent = v.length ? `peak ${peak.toLocaleString("en-GB", { maximumFractionDigits: d })} ${this.opts.unit}` : "";
  }

  setCursor(t: number | null): void {
    if (!this.cursor) return;
    if (t === null) {
      this.cursor.setAttribute("visibility", "hidden");
      return;
    }
    const x = this.pad.l + (t / this.tMax) * (this.W - this.pad.l - this.pad.r);
    this.cursor.setAttribute("visibility", "visible");
    this.cursor.setAttribute("x1", String(x));
    this.cursor.setAttribute("x2", String(x));
  }
}
