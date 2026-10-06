// Map furniture drawn on a 2D canvas over the WebGL stage: UTM graticule with
// edge labels, alternating scale bar, north arrow, and the projection note.
// Drawing on a canvas (not DOM) lets figure export composite it pixel-exact.
import type { FlowScene } from "./engine";

export interface FurnitureStyle {
  ink: string;
  paper: string;
  grid: string;
  font: string;
  /** Width kept clear of labels at the top right (stage toolbar) [px]. */
  reserveTopRight?: number;
}

/** Elevation labels on index contours (plan view), placed along scanlines. */
function drawContourLabels(ctx: CanvasRenderingContext2D, scene: FlowScene, s: FurnitureStyle,
  xAt: (px: number) => number, yAt: (py: number) => number, w: number, h: number): void {
  if (!scene.contoursOn) return;
  const index = scene.contourInterval * 5;
  const placed: [number, number][] = [];
  ctx.font = `600 10.5px ${s.font}`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  for (let py = 70; py < h - 150; py += 64) {
    let prev: number | null = null;
    for (let px = 70; px < w - 40; px += 3) {
      const b = scene.bedAt(xAt(px), yAt(py));
      if (!b) {
        prev = null;
        continue;
      }
      if (prev !== null) {
        const a = Math.floor(prev / index);
        const c = Math.floor(b.z / index);
        if (a !== c) {
          const level = Math.max(a, c) * index;
          const box = labelBox(ctx, `${Math.max(a, c) * index}`, px, py);
          const clear =
            !labelBoxes.some((b) => overlaps(b, box)) &&
            [-18, 0, 18].every((dx) => [-8, 0, 8].every((dy) => !scene.dataAt(xAt(px + dx), yAt(py + dy))));
          if (level > 0 && clear && placed.every(([x, y]) => Math.hypot(x - px, y - py) > 150) && placed.length < 28) {
            halo(ctx, `${level}`, px, py, s);
            placed.push([px, py]);
          }
        }
      }
      prev = b.z;
    }
  }
}

const NICE = [50, 100, 200, 250, 500, 1000, 2000, 2500, 5000, 10000, 20000, 25000, 50000];

function niceStep(span: number, target: number): number {
  const raw = span / target;
  return NICE.find((n) => n >= raw) ?? NICE[NICE.length - 1];
}

/** "708 000" style coordinate labels (thin-space thousands, metres). */
export function coord(v: number): string {
  return Math.round(v)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

function zoneLabel(crs: string | null): string {
  const m = crs ? /^EPSG:32([67])(\d{2})$/.exec(crs) : null;
  return m ? `UTM ${Number(m[2])}${m[1] === "7" ? "S" : "N"} (WGS 84)` : "grid coordinates";
}

type Box = [number, number, number, number]; // x0, y0, x1, y1
let labelBoxes: Box[] = [];

function labelBox(ctx: CanvasRenderingContext2D, text: string, x: number, y: number): Box {
  const m = ctx.measureText(text);
  const w = m.width;
  const left = ctx.textAlign === "center" ? x - w / 2 : ctx.textAlign === "right" ? x - w : x;
  return [left - 4, y - m.actualBoundingBoxAscent - 3, left + w + 4, y + m.actualBoundingBoxDescent + 3];
}

const overlaps = (a: Box, b: Box) => a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];

function halo(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, s: FurnitureStyle): void {
  labelBoxes.push(labelBox(ctx, text, x, y));
  // solid paper chip behind the label: legible over terrain, flow and overlay lines
  const m = ctx.measureText(text);
  const w = m.width;
  const asc = m.actualBoundingBoxAscent;
  const desc = m.actualBoundingBoxDescent;
  const left = ctx.textAlign === "center" ? x - w / 2 : ctx.textAlign === "right" ? x - w : x;
  ctx.save();
  ctx.globalAlpha = 0.86;
  ctx.fillStyle = s.paper;
  ctx.fillRect(left - 3, y - asc - 2, w + 6, asc + desc + 4);
  ctx.restore();
  ctx.fillStyle = s.ink;
  ctx.fillText(text, x, y);
}

function drawNorth(ctx: CanvasRenderingContext2D, x: number, y: number, dir: { x: number; y: number }, s: FurnitureStyle): void {
  const len = 26;
  const ang = Math.atan2(dir.y, dir.x) + Math.PI / 2;
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(ang);
  ctx.beginPath();
  ctx.moveTo(0, -len / 2);
  ctx.lineTo(7, len / 2);
  ctx.lineTo(0, len / 2 - 6);
  ctx.closePath();
  ctx.fillStyle = s.ink;
  ctx.fill();
  ctx.beginPath();
  ctx.moveTo(0, -len / 2);
  ctx.lineTo(-7, len / 2);
  ctx.lineTo(0, len / 2 - 6);
  ctx.closePath();
  ctx.fillStyle = s.paper;
  ctx.fill();
  ctx.strokeStyle = s.ink;
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.font = `600 13px ${s.font}`;
  ctx.textAlign = "center";
  ctx.textBaseline = "bottom";
  halo(ctx, "N", 0, -len / 2 - 3, s);
  ctx.restore();
}

function drawScaleBar(ctx: CanvasRenderingContext2D, x: number, y: number, mPerPx: number, s: FurnitureStyle): void {
  const target = 150 * mPerPx;
  const L = NICE.find((n) => n >= target * 0.6) ?? 50000;
  const px = L / mPerPx;
  const h = 6;
  ctx.save();
  ctx.globalAlpha = 0.86;
  ctx.fillStyle = s.paper;
  ctx.fillRect(x - 6, y - 20, px + 46, h + 26);
  ctx.restore();
  for (let k = 0; k < 4; k++) {
    ctx.fillStyle = k % 2 ? s.paper : s.ink;
    ctx.fillRect(x + (k * px) / 4, y, px / 4, h);
  }
  ctx.strokeStyle = s.ink;
  ctx.lineWidth = 1;
  ctx.strokeRect(x + 0.5, y + 0.5, px, h);
  ctx.font = `12px ${s.font}`;
  ctx.textBaseline = "bottom";
  const label = (v: number) => (L >= 2000 ? `${v / 1000}` : `${v}`);
  ctx.textAlign = "left";
  halo(ctx, "0", x, y - 3, s);
  ctx.textAlign = "center";
  halo(ctx, label(L / 2), x + px / 2, y - 3, s);
  ctx.textAlign = "left";
  halo(ctx, `${label(L)} ${L >= 2000 ? "km" : "m"}`, x + px - 4, y - 3, s);
}

export function drawFurniture(ctx: CanvasRenderingContext2D, scene: FlowScene, s: FurnitureStyle): void {
  const { width: W, height: H } = ctx.canvas;
  const dpr = W / (ctx.canvas.clientWidth || W);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const w = W / dpr;
  const h = H / dpr;
  ctx.clearRect(0, 0, w, h);
  labelBoxes = [];
  const b = scene.bounds;
  const meta = scene.gridMeta;
  if (!b || !meta) return;

  if (scene.view === "plan") {
    // plan view is linear: derive the visible CRS window from two projected points
    const p0 = scene.worldToScreen(b.west, b.south, meta.zmin);
    const p1 = scene.worldToScreen(b.east, b.north, meta.zmin);
    const sx = (p1.x - p0.x) / (b.east - b.west);
    const sy = (p1.y - p0.y) / (b.north - b.south);
    const xAt = (px: number) => b.west + (px - p0.x) / sx;
    const yAt = (py: number) => b.south + (py - p0.y) / sy;
    const x0 = Math.max(xAt(0), b.west);
    const x1 = Math.min(xAt(w), b.east);
    const y0 = Math.max(yAt(h), b.south);
    const y1 = Math.min(yAt(0), b.north);
    const step = niceStep(Math.max(x1 - x0, y1 - y0), 6);
    ctx.font = `11px ${s.font}`;
    ctx.lineWidth = 1;
    ctx.strokeStyle = s.grid;
    ctx.setLineDash([2, 4]);
    for (let x = Math.ceil(x0 / step) * step; x <= x1; x += step) {
      const px = p0.x + (x - b.west) * sx;
      ctx.beginPath();
      ctx.moveTo(Math.round(px) + 0.5, 0);
      ctx.lineTo(Math.round(px) + 0.5, h);
      ctx.stroke();
    }
    for (let y = Math.ceil(y0 / step) * step; y <= y1; y += step) {
      const py = p0.y + (y - b.south) * sy;
      ctx.beginPath();
      ctx.moveTo(0, Math.round(py) + 0.5);
      ctx.lineTo(w, Math.round(py) + 0.5);
      ctx.stroke();
    }
    ctx.setLineDash([]);
    ctx.textBaseline = "top";
    ctx.textAlign = "center";
    const reserve = s.reserveTopRight ?? 0;
    for (let x = Math.ceil(x0 / step) * step; x <= x1; x += step) {
      const px = p0.x + (x - b.west) * sx;
      // labels under the stage toolbar drop below it instead of disappearing
      if (px > 60 && px < w - 40) halo(ctx, coord(x), px, px > w - reserve ? 56 : 6, s);
    }
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    for (let y = Math.ceil(y0 / step) * step; y <= y1; y += step) {
      const py = p0.y + (y - b.south) * sy;
      if (py > 24 && py < h - 150) halo(ctx, coord(y), 6, py, s);
    }
    drawContourLabels(ctx, scene, s, xAt, yAt, w, h);
    drawNorth(ctx, 28, h - 100, { x: 0, y: -1 }, s);
    const mpp = scene.planMetresPerPixel();
    if (mpp) drawScaleBar(ctx, 16, h - 54, mpp, s);
    ctx.font = `11px ${s.font}`;
    ctx.textAlign = "left";
    ctx.textBaseline = "bottom";
    const ci = scene.contoursOn ? ` · contours ${scene.contourInterval} m, index ${scene.contourInterval * 5} m (m a.s.l.)` : "";
    halo(ctx, `${zoneLabel(scene.crs)} · grid ${coord(step)} m${ci}`, 16, h - 26, s);
  } else {
    drawNorth(ctx, 28, h - 100, scene.northDirection(), s);
    ctx.font = `11px ${s.font}`;
    ctx.textAlign = "left";
    ctx.textBaseline = "bottom";
    const ve = scene.verticalExaggeration;
    halo(ctx, `Perspective view, not to scale · vertical exaggeration ${ve.toFixed(1)}×`, 16, h - 26, s);
  }
}
