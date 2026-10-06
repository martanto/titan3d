// Stage: WebGL scene + map furniture + colourbar + caption + probe + messages.
// Every view is a figure: export composites map, furniture, colourbar and caption.
import { FlowScene, type PickInfo, type SurfaceKind, type ViewKind } from "../scene/engine";
import { drawFurniture } from "../scene/furniture";
import { type FlowMode, RAMP_CITATION, RAMP_NAME, rampBytes, rampCss } from "../scene/ramps";
import { download, h } from "./dom";
import { num } from "./format";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const css = (n: string) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

export interface ColourbarSpec {
  mode: FlowMode;
  vmax: number; // m (depth/max) or m/s (speed)
  plain?: boolean; // presenter wording
  note?: string;
}

export type ProbeRows = [string, string][];

const TITLES: Record<FlowMode, [string, string]> = {
  depth: ["Flow depth h (m)", "Flow thickness (m)"],
  speed: ["Flow speed |u| (m/s)", "Flow speed (m/s)"],
  max: ["Maximum flow depth over the run (m)", "Deepest flow reached (m)"],
};

export class Stage {
  readonly scene: FlowScene;
  private furniture = $<HTMLCanvasElement>("furniture");
  private gl = $<HTMLCanvasElement>("gl");
  private colourbar = $<HTMLDivElement>("colourbar");
  private caption = $<HTMLDivElement>("caption");
  private probeEl = $<HTMLDivElement>("probe");
  private message = $<HTMLDivElement>("stageMessage");
  private badges = $<HTMLDivElement>("badges");
  private pickHandler?: (p: PickInfo) => void;
  private probeProvider?: (p: PickInfo) => ProbeRows | null;
  private cb?: ColourbarSpec;
  private captionText = "";
  private captionActions = h("div", { class: "caption-actions" });
  // Terrain views default to the natural surface; under data layers the hillshade
  // keeps colour reserved for data (each context remembers the user's choice).
  private surfaceContext: "terrain" | "data" = "terrain";
  private surfacePref: Record<"terrain" | "data", SurfaceKind> = {
    terrain: (localStorage.getItem("titan3d.surface") as SurfaceKind) || "natural",
    data: (localStorage.getItem("titan3d.surface.data") as SurfaceKind) || "relief",
  };
  /** Called after the terrain surface changes (views refresh their caption). */
  onSurfaceChange?: () => void;

  constructor() {
    this.scene = new FlowScene(this.gl);
    this.scene.onTick(() => this.drawFurniture());
    const plan = $<HTMLButtonElement>("viewPlan");
    const v3d = $<HTMLButtonElement>("view3d");
    const setView = (v: ViewKind) => {
      this.scene.setView(v);
      plan.setAttribute("aria-pressed", String(v === "plan"));
      v3d.setAttribute("aria-pressed", String(v === "oblique"));
      this.probeEl.hidden = true;
    };
    plan.onclick = () => setView("plan");
    v3d.onclick = () => setView("oblique");
    $<HTMLButtonElement>("surfNatural").onclick = () => this.chooseSurface("natural");
    $<HTMLButtonElement>("surfRelief").onclick = () => this.chooseSurface("relief");
    this.applySurface();
    $<HTMLButtonElement>("zoomIn").onclick = () => this.scene.zoomBy(0.8);
    $<HTMLButtonElement>("zoomOut").onclick = () => this.scene.zoomBy(1.25);
    $<HTMLButtonElement>("zoomFit").onclick = () => this.scene.fit();
    this.installPointer();
    this.gl.tabIndex = 0;
    this.gl.addEventListener("keydown", (e) => {
      if (e.key === "+" || e.key === "=") this.scene.zoomBy(0.8);
      else if (e.key === "-") this.scene.zoomBy(1.25);
      else if (e.key === "0") this.scene.fit();
      else return;
      e.preventDefault();
    });
  }

  private chooseSurface(k: SurfaceKind): void {
    this.surfacePref[this.surfaceContext] = k;
    localStorage.setItem(this.surfaceContext === "data" ? "titan3d.surface.data" : "titan3d.surface", k);
    this.applySurface();
  }

  private applySurface(): void {
    const k = this.surfacePref[this.surfaceContext];
    this.scene.setSurface(k);
    this.scene.setTerrainMute(this.surfaceContext === "data" && k === "natural" ? 0.6 : 0);
    $("surfNatural").setAttribute("aria-pressed", String(k === "natural"));
    $("surfRelief").setAttribute("aria-pressed", String(k === "relief"));
    this.onSurfaceChange?.();
  }

  /** "data" when a flow layer is drawn over the terrain (Results), else "terrain". */
  setSurfaceContext(c: "terrain" | "data"): void {
    this.surfaceContext = c;
    this.applySurface();
  }

  /** Terrain name shown in the top bar. */
  setTerrainLabel(text: string): void {
    const el = document.getElementById("demIndicator");
    if (el) el.textContent = text;
  }

  /** Buttons shown beside the figure caption (export, copy). */
  setCaptionActions(nodes: HTMLElement[]): void {
    this.captionActions.replaceChildren(...nodes);
  }

  setView(v: ViewKind): void {
    (v === "plan" ? $("viewPlan") : $("view3d")).click();
  }

  private installPointer(): void {
    let down: { x: number; y: number; t: number } | null = null;
    let raf = 0;
    let last: PointerEvent | null = null;
    this.gl.addEventListener("pointerdown", (e) => {
      down = { x: e.clientX, y: e.clientY, t: performance.now() };
    });
    this.gl.addEventListener("pointerup", (e) => {
      if (!down) return;
      const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y);
      const quick = performance.now() - down.t < 600;
      down = null;
      if (moved > 5 || !quick) return;
      const p = this.scene.pick(e.clientX, e.clientY);
      if (!p) return;
      if (this.pickHandler) this.pickHandler(p);
      else if (e.pointerType !== "mouse") this.showProbe(p, e.clientX, e.clientY);
    });
    this.gl.addEventListener("pointermove", (e) => {
      if (e.pointerType !== "mouse" || down) return;
      last = e;
      if (!raf)
        raf = requestAnimationFrame(() => {
          raf = 0;
          if (!last) return;
          const p = this.scene.pick(last.clientX, last.clientY);
          if (p) this.showProbe(p, last.clientX, last.clientY);
          else this.probeEl.hidden = true;
        });
    });
    this.gl.addEventListener("pointerleave", () => {
      this.probeEl.hidden = true;
    });
  }

  private showProbe(p: PickInfo, cx: number, cy: number): void {
    const rows = this.probeProvider?.(p);
    if (!rows) {
      this.probeEl.hidden = true;
      return;
    }
    this.probeEl.replaceChildren(h("dl", {}, rows.flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, v)])));
    const r = this.gl.getBoundingClientRect();
    const x = cx - r.left;
    const y = cy - r.top;
    this.probeEl.hidden = false;
    const w = this.probeEl.offsetWidth;
    const hh = this.probeEl.offsetHeight;
    this.probeEl.style.left = `${Math.min(x + 16, r.width - w - 8)}px`;
    this.probeEl.style.top = `${Math.max(8, Math.min(y + 16, r.height - hh - 8))}px`;
  }

  onPick(f: ((p: PickInfo) => void) | undefined): void {
    this.pickHandler = f;
  }

  setProbe(f: ((p: PickInfo) => ProbeRows | null) | undefined): void {
    this.probeProvider = f;
    if (!f) this.probeEl.hidden = true;
  }

  private furnitureStyle() {
    const tools = document.querySelector<HTMLElement>(".stage-tools");
    return {
      ink: css("--fg") || "#15181c",
      paper: css("--panel") || "#fff",
      grid: css("--grid-line") || "rgba(0,0,0,.35)",
      font: css("--font") || "sans-serif",
      reserveTopRight: tools && tools.offsetTop < 40 ? tools.offsetWidth + 24 : 0,
    };
  }

  private drawFurniture(): void {
    const c = this.furniture;
    const dpr = Math.min(devicePixelRatio, 2);
    const w = Math.round(c.clientWidth * dpr);
    const hh = Math.round(c.clientHeight * dpr);
    if (c.width !== w || c.height !== hh) {
      c.width = w;
      c.height = hh;
    }
    const ctx = c.getContext("2d");
    if (ctx) drawFurniture(ctx, this.scene, this.furnitureStyle());
  }

  // ---------------------------------------------------------------- chrome
  showMessage(kind: "loading" | "error" | "empty", title: string, body?: string, action?: HTMLElement): void {
    this.message.className = `stage-message ${kind}`;
    this.message.replaceChildren(
      h(
        "div",
        { class: "box", role: kind === "error" ? "alert" : "status" },
        h("h2", {}, title),
        body ? h("p", { class: "text-muted" }, body) : null,
        action ?? null,
      ),
    );
    this.message.hidden = false;
  }

  hideMessage(): void {
    this.message.hidden = true;
  }

  setBadges(items: { text: string; warn?: boolean }[]): void {
    this.badges.replaceChildren(...items.map((b) => h("span", { class: `badge${b.warn ? " warn" : ""}` }, b.text)));
  }

  setColourbar(spec: ColourbarSpec | null): void {
    this.cb = spec ?? undefined;
    if (!spec) {
      this.colourbar.hidden = true;
      return;
    }
    const sqrtScale = spec.mode !== "speed";
    const value = (q: number) => (sqrtScale ? q * q : q) * spec.vmax;
    const qs = [0, 0.25, 0.5, 0.75, 1];
    const digits = spec.vmax < 10 ? 1 : 0;
    this.colourbar.replaceChildren(
      h("div", { class: "cb-title" }, TITLES[spec.mode][spec.plain ? 1 : 0]),
      h("div", { class: "cb-bar", style: `background:${rampCss(spec.mode)}` }),
      h(
        "div",
        { class: "cb-ticks" },
        qs.map((q) => h("span", { style: `left:${q * 100}%` }, num(value(q), q === 0 ? 0 : digits))),
      ),
      h(
        "div",
        { class: "cb-note" },
        spec.plain
          ? "Left of the scale: little; right: a lot."
          : `${sqrtScale ? "Square-root scale" : "Linear scale"} · ${RAMP_NAME[spec.mode]} (Crameri 2018)${spec.mode === "speed" ? "" : (this.scene.view === "plan" ? " · outlined" : " · hidden") + " below " + (spec.mode === "max" ? "0.1" : "0.05") + " m"}${spec.note ? " · " + spec.note : ""}`,
      ),
    );
    this.colourbar.hidden = false;
  }

  setCaption(text: string, strongLead?: string): void {
    this.captionText = (strongLead ? `${strongLead} ` : "") + text;
    this.caption.replaceChildren(h("p", {}, strongLead ? h("strong", {}, strongLead + " ") : null, text), this.captionActions);
  }

  get captionPlain(): string {
    return this.captionText;
  }

  // ---------------------------------------------------------------- export
  /** Export the current view as a PNG figure (map + furniture + colourbar + caption). */
  async exportFigure(filename: string): Promise<void> {
    const src = this.scene.snapshot();
    this.drawFurniture();
    const W = src.width;
    const H = src.height;
    const s = W / (src.clientWidth || W);
    const pad = 16 * s;
    const font = this.furnitureStyle().font;
    const ink = css("--fg");
    const paper = css("--panel");
    const muted = css("--muted");
    const meas = document.createElement("canvas").getContext("2d")!;
    meas.font = `${13 * s}px ${font}`;
    const lines = wrap(meas, this.captionText, W - 2 * pad);
    const capH = pad + lines.length * 18 * s + pad;
    const out = document.createElement("canvas");
    out.width = W;
    out.height = H + capH;
    const ctx = out.getContext("2d")!;
    ctx.fillStyle = paper;
    ctx.fillRect(0, 0, out.width, out.height);
    ctx.drawImage(src, 0, 0);
    ctx.drawImage(this.furniture, 0, 0, W, H);
    if (this.cb) this.drawColourbar(ctx, W - 290 * s, H - 84 * s, 270 * s, s, ink, paper, muted, font);
    ctx.fillStyle = ink;
    ctx.font = `${13 * s}px ${font}`;
    ctx.textBaseline = "top";
    lines.forEach((l, i) => ctx.fillText(l, pad, H + pad + i * 18 * s));
    const blob = await new Promise<Blob | null>((r) => out.toBlob(r, "image/png"));
    if (blob) download(blob, filename);
  }

  private drawColourbar(
    ctx: CanvasRenderingContext2D,
    x: number,
    y: number,
    w: number,
    s: number,
    ink: string,
    paper: string,
    muted: string,
    font: string,
  ): void {
    const spec = this.cb!;
    ctx.fillStyle = paper;
    ctx.fillRect(x - 10 * s, y - 24 * s, w + 20 * s, 76 * s);
    ctx.fillStyle = ink;
    ctx.font = `600 ${12 * s}px ${font}`;
    ctx.textBaseline = "alphabetic";
    ctx.fillText(TITLES[spec.mode][spec.plain ? 1 : 0], x, y - 8 * s);
    const bytes = rampBytes(spec.mode);
    for (let i = 0; i < w; i++) {
      const q = Math.round((i / (w - 1)) * 255) * 4;
      ctx.fillStyle = `rgb(${bytes[q]},${bytes[q + 1]},${bytes[q + 2]})`;
      ctx.fillRect(x + i, y, 1.5, 12 * s);
    }
    ctx.strokeStyle = ink;
    ctx.lineWidth = s;
    ctx.strokeRect(x, y, w, 12 * s);
    const sqrtScale = spec.mode !== "speed";
    ctx.font = `${11 * s}px ${font}`;
    ctx.textBaseline = "top";
    [0, 0.25, 0.5, 0.75, 1].forEach((q, i) => {
      const v = (sqrtScale ? q * q : q) * spec.vmax;
      ctx.textAlign = i === 0 ? "left" : i === 4 ? "right" : "center";
      ctx.fillStyle = ink;
      ctx.fillRect(x + q * w - (i === 4 ? s : 0), y + 12 * s, s, 4 * s);
      ctx.fillText(num(v, q === 0 ? 0 : spec.vmax < 10 ? 1 : 0), x + q * w, y + 18 * s);
    });
    ctx.textAlign = "left";
    ctx.fillStyle = muted;
    ctx.fillText(sqrtScale ? "Square-root scale" : "Linear scale", x, y + 34 * s);
    ctx.textAlign = "right";
    ctx.fillText(RAMP_CITATION.replace("Colour maps: ", ""), x + w, y + 34 * s);
    ctx.textAlign = "left";
  }
}

function wrap(ctx: CanvasRenderingContext2D, text: string, width: number): string[] {
  const words = text.split(/\s+/);
  const lines: string[] = [];
  let line = "";
  for (const w of words) {
    const t = line ? `${line} ${w}` : w;
    if (ctx.measureText(t).width > width && line) {
      lines.push(line);
      line = w;
    } else line = t;
  }
  if (line) lines.push(line);
  return lines;
}
