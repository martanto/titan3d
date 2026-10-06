// Results view: opens on the briefing figure (plan view, maximum-depth envelope)
// with playback, readouts, charts, downloads, provenance and presenter mode.
import { api, type Artifact, type Material, type Simulation } from "../api/client";
import { store } from "../app/store";
import { depthTable, loadResult, type Result } from "../data/bundle";
import { toLonLat } from "../geo/utm";
import type { FlowMode } from "../scene/ramps";
import { RAMP_CITATION } from "../scene/ramps";
import { TimeChart } from "./chart";
import { h, icon, svg, ICON, toast } from "./dom";
import { dateTime, duration, lonLat, num, sci } from "./format";
import type { Stage } from "./stage";
import { surfaceNote } from "./terrain";

const WET = 0.1;

const ARTIFACTS: [Artifact, string, string][] = [
  ["max_depth.tif", "Maximum depth", "GeoTIFF, full resolution"],
  ["max_speed.tif", "Maximum speed", "GeoTIFF, full resolution"],
  ["inundation.geojson", "Inundation outline", "GeoJSON, WGS 84"],
  ["inundation.kml", "Inundation outline", "KML for Google Earth"],
  ["scenario.yaml", "Scenario configuration", "YAML, reloadable"],
  ["summary.json", "Run summary", "JSON"],
  ["run.log", "Solver log", "text"],
];

export function mountResults(stage: Stage, panel: HTMLElement, job: Simulation): () => void {
  let disposed = false;
  let result: Result | null = null;
  let mode: FlowMode = "max";
  let t = 0;
  let playing = false;
  let rate = 10;
  let boost = 1;
  let vex = 1;
  let detail = 640;
  let presenter = false;
  const app = document.getElementById("app")!;
  const ctrl = new AbortController();
  const frontCache = new Map<number, { L: number; z: number }>();
  // envelope with the release footprint masked: the t = 0 pile is not flow depth
  let envQ: Uint8Array = new Uint8Array(0);
  let envMax = 0;
  let depthMax = 0; // colour scale for depth playback: flow outside the release area

  function maskRelease(r: Result): void {
    const m = r.meta;
    const tab = depthTable(m.hmax);
    envQ = r.hmaxQ.slice();
    envMax = 0;
    const piles = m.sources.filter((s) => s.kind === "pile");
    for (let j = 0; j < m.ny; j++) {
      const y = m.y0 + j * m.dx;
      for (let i = 0; i < m.nx; i++) {
        const x = m.x0 + i * m.dx;
        const k = j * m.nx + i;
        if (piles.some((p) => Math.hypot(x - p.x, y - p.y) <= p.radius)) envQ[k] = 0;
        else if (tab[envQ[k]] > envMax) envMax = tab[envQ[k]];
      }
    }
    // largest depth outside the release footprint over all frames (one pass over the bytes)
    const n = m.nx * m.ny;
    const outside = new Uint8Array(n);
    for (let k = 0; k < n; k++) outside[k] = envQ[k] > 0 || r.hmaxQ[k] === 0 ? 1 : 0;
    let qmax = 0;
    for (let f = 0; f < m.nframes; f++) {
      const o = f * n;
      for (let k = 0; k < n; k++) if (outside[k] && r.depthQ[o + k] > qmax) qmax = r.depthQ[o + k];
    }
    depthMax = Math.max(tab[qmax], 0.1);
  }

  const charts = {
    runout: new TimeChart({ title: "Runout", unit: "m", onSeek: (v) => seek(v) }),
    umax: new TimeChart({ title: "Maximum speed", unit: "m/s", digits: 1, onSeek: (v) => seek(v) }),
    area: new TimeChart({ title: "Inundated area", unit: "km²", digits: 2, onSeek: (v) => seek(v) }),
  };

  // ------------------------------------------------------------ analysis
  function zSource(r: Result): number {
    const m = r.meta;
    const src = m.sources[0];
    const i = Math.round((m.ref.x - m.x0) / m.dx);
    const j = Math.round((m.ref.y - m.y0) / m.dx);
    const k = Math.min(Math.max(j, 0), m.ny - 1) * m.nx + Math.min(Math.max(i, 0), m.nx - 1);
    return r.bed[k] + (src?.kind === "pile" ? (src.height ?? 0) : 0);
  }

  /** Farthest inundated cell from the source in frame f (-1 = envelope). */
  function front(r: Result, f: number): { L: number; z: number } {
    const hit = frontCache.get(f);
    if (hit) return hit;
    const m = r.meta;
    const n = m.nx * m.ny;
    const tab = depthTable(m.hmax);
    const q = f < 0 ? envQ : r.depthQ.subarray(f * n, (f + 1) * n);
    let best = 0;
    let z = zSource(r);
    for (let j = 0; j < m.ny; j++) {
      const dy = m.y0 + j * m.dx - m.ref.y;
      for (let i = 0; i < m.nx; i++) {
        const k = j * m.nx + i;
        if (tab[q[k]] < WET) continue;
        const dx = m.x0 + i * m.dx - m.ref.x;
        const d2 = dx * dx + dy * dy;
        if (d2 > best) {
          best = d2;
          z = r.bed[k];
        }
      }
    }
    const out = { L: Math.sqrt(best), z };
    frontCache.set(f, out);
    return out;
  }

  const tEnd = () => result?.stats[result.stats.length - 1]?.t ?? job.scenario.t_end ?? 1;
  const frameIndex = () => (result ? Math.min(Math.round(t / result.meta.every), result.stats.length - 1) : 0);

  // ------------------------------------------------------------- caption
  function caption(): string {
    if (!result) return "";
    const m = result.meta;
    const s = job.scenario;
    const mat: Partial<Material> = s.material ?? {};
    const src = m.sources
      .map((x) =>
        x.kind === "pile"
          ? `pile H = ${num(x.height ?? 0)} m, R = ${num(x.radius)} m at ${lonLat(x.lon, x.lat)}`
          : `vent R = ${num(x.radius)} m, influx ${num(x.influx ?? 0, 2)} m/s for ${num(x.duration ?? 0)} s from t = ${num(x.start ?? 0)} s at ${lonLat(x.lon, x.lat)}`,
      )
      .join("; ");
    const last = result.stats[result.stats.length - 1];
    const env = front(result, -1);
    const what =
      mode === "max"
        ? `Maximum flow depth over 0–${num(tEnd())} s outside the release footprint (outlined)`
        : mode === "depth"
          ? `Flow depth at t = ${num(t, 1)} s`
          : `Flow speed at t = ${num(t, 1)} s`;
    const rheo =
      mat.rheology === "voellmy"
        ? `Voellmy basal friction (μ = ${mat.mu}, ξ = ${mat.xi} m/s²)`
        : `Coulomb basal friction φ_bed = ${mat.phi_bed_deg ?? 24}°`;
    const prov = job.provenance ?? {};
    const sha = typeof prov.dem_sha256 === "string" ? prov.dem_sha256.slice(0, 12) : "—";
    return (
      `${what} for “${m.title}” on ${m.dem} (${m.crs}). ${rheo}, φ_int = ${mat.phi_int_deg ?? 34}°, ` +
      `${m.pressure === "hydrostatic" ? "hydrostatic" : "Savage–Hutter"} earth pressure, curvature ${m.curvature ? "on" : "off"}; ` +
      `${src}; released ${sci(m.volume_m3)} m³. Grid ${num(m.grid_dx)} m (${num(m.grid_shape[1])} × ${num(m.grid_shape[0])} cells), ` +
      `${num(m.steps)} steps. Inundated (h_max > ${WET} m) ${num(Math.max(...result.stats.map((x) => x.area)), 2)} km², ` +
      `runout ${num(env.L)} m, mass in domain ${num(last.vol * 100, 2)} %. Display: ${mode === "speed" ? "imola" : mode === "max" ? "lajolla" : "batlow"} colour map, ` +
      `${stage.scene.view === "plan" ? "plan view" : `perspective view, vertical exaggeration ${vex.toFixed(1)}×`}; terrain ${surfaceNote(stage.scene.surface)}` +
      `${boost > 1 ? `, flow depth exaggerated ${boost}× in the first 10 m` : ""}. ` +
      `titan3d ${prov.titan3d_version ?? ""} (${prov.git_commit ?? "—"}), DEM sha256 ${sha}…, run ${job.id}. Model output, not an official hazard map.`
    );
  }

  // --------------------------------------------------------------- stage
  function applyStage(): void {
    if (!result) return;
    stage.scene.setMode(mode);
    stage.scene.setTime(mode === "max" ? 0 : t);
    stage.scene.setThinBoost(boost);
    stage.setColourbar({
      mode,
      vmax: mode === "speed" ? result.meta.vmax : mode === "max" ? envMax : depthMax,
      plain: presenter,
      note: mode === "speed" ? undefined : "release area excluded from the scale",
    });
    const badges: { text: string; warn?: boolean }[] = [];
    if (stage.scene.view === "oblique" && vex !== 1) badges.push({ text: `Vertical exaggeration ${vex.toFixed(1)}×`, warn: true });
    if (boost > 1) badges.push({ text: `Flow depth ×${boost} (first 10 m)`, warn: true });
    if (mode === "max") badges.push({ text: `Envelope, 0–${num(tEnd())} s` });
    stage.setBadges(badges);
    stage.setCaption(caption(), "Figure.");
  }

  function seek(v: number): void {
    playing = false;
    t = Math.min(Math.max(v, 0), tEnd());
    if (mode === "max") mode = "depth";
    update();
  }

  // --------------------------------------------------------------- panel
  const clock = h("span", { class: "clock" });
  const slider = h("input", { type: "range", min: 0, max: 1000, step: 1, value: 0, "aria-label": "Simulation time" });
  const playBtn = h("button", { type: "button", class: "iconbtn primary", "aria-label": "Play" });
  const readouts = h("div", { class: "readouts", "aria-live": "off" });
  const transport = h(
    "div",
    { class: "transport" },
    h(
      "button",
      { type: "button", class: "iconbtn", "aria-label": "Previous frame", onclick: () => seek(t - (result?.meta.every ?? 1)) },
      svg(ICON.back),
    ),
    playBtn,
    slider,
    clock,
  );
  const rateSel = h(
    "select",
    {
      "aria-label": "Playback rate",
      onchange: (e: Event) => {
        rate = Number((e.target as HTMLSelectElement).value);
      },
    },
    [1, 2, 5, 10, 20, 40].map((r) => h("option", { value: r, selected: r === rate }, r === 1 ? "1× (real time)" : `${r}×`)),
  );
  const modeSeg = h("div", { class: "seg", role: "group", "aria-label": "Quantity shown" });

  function setPlaying(p: boolean): void {
    playing = p;
    if (p && mode === "max") mode = "depth";
    if (p && t >= tEnd() - 1e-6) t = 0;
    update();
  }
  playBtn.onclick = () => setPlaying(!playing);
  slider.oninput = () => seek((Number(slider.value) / 1000) * tEnd());

  function renderModes(): void {
    modeSeg.replaceChildren(
      ...([
        ["max", "Maximum depth", "envelope"],
        ["depth", "Depth", "h at t"],
        ["speed", "Speed", "|u| at t"],
      ] as [FlowMode, string, string][]).map(([k, label, small]) =>
        h(
          "button",
          {
            type: "button",
            "aria-pressed": String(mode === k),
            onclick: () => {
              mode = k;
              if (k === "max") playing = false;
              update();
            },
          },
          label,
          h("small", {}, small),
        ),
      ),
    );
  }

  function renderReadouts(): void {
    if (!result) return;
    const m = result.meta;
    const tanBed = Math.tan(((job.scenario.material?.phi_bed_deg ?? 24) * Math.PI) / 180);
    const r = (k: string, v: string, n?: string) =>
      h("div", { class: "readout" }, h("span", { class: "k" }, k), h("span", { class: "v" }, v), n ? h("span", { class: "n" }, n) : null);
    if (mode === "max") {
      const env = front(result, -1);
      const H = zSource(result) - env.z;
      const st = result.stats;
      readouts.replaceChildren(
        r("Maximum runout", `${num(env.L)} m`, "from the first source"),
        r("Mobility H/L", env.L > 2 * m.dx ? num(H / env.L, 2) : "—", `tan φ_bed = ${num(tanBed, 2)}`),
        r("Peak flow depth", `${num(envMax, 1)} m`, "outside the release area"),
        r("Peak speed", `${num(Math.max(...st.map((x) => x.umax)), 1)} m/s`, "h > 0.1 m"),
        r("Inundated area", `${num(Math.max(...st.map((x) => x.area)), 2)} km²`, "largest at one time"),
        r("Mass in domain", `${num(st[st.length - 1].vol * 100, 2)} %`, `${num(st[st.length - 1].vol_out * 100, 2)} % left the domain`),
      );
      return;
    }
    const f = frameIndex();
    const s = result.stats[f];
    const fr = front(result, f);
    const H = zSource(result) - fr.z;
    readouts.replaceChildren(
      r("Runout", `${num(fr.L)} m`, `frame at ${num(s.t, 1)} s`),
      r("Mobility H/L", fr.L > 2 * m.dx ? num(H / fr.L, 2) : "—", `tan φ_bed = ${num(tanBed, 2)}`),
      r("Maximum depth", `${num(s.hmax, 1)} m`),
      r("Maximum speed", `${num(s.umax, 1)} m/s`, "h > 0.1 m"),
      r("Inundated area", `${num(s.area, 2)} km²`, "h > 0.1 m"),
      r("Mass in domain", `${num(s.vol * 100, 2)} %`, s.vol_out ? `${num(s.vol_out * 100, 2)} % left the domain` : "of released volume"),
    );
  }

  let lastReadout = -2;
  let lastKey = "";
  function update(): void {
    if (!result) return;
    const env = mode === "max";
    clock.textContent = env ? "envelope" : `${num(t, 1)} s`;
    slider.value = String(Math.round((t / tEnd()) * 1000));
    slider.setAttribute("aria-valuetext", env ? "Envelope over the whole run" : `${num(t, 1)} seconds of ${num(tEnd())}`);
    stage.scene.setTime(env ? 0 : t);
    for (const c of Object.values(charts)) c.setCursor(env ? null : t);
    const f = env ? -1 : frameIndex();
    // heavier DOM work only when something visible changed (not every animation frame)
    const key = `${mode}|${playing}|${f}|${boost}|${vex}|${presenter}|${stage.scene.view}|${rate}`;
    if (key === lastKey) return;
    lastKey = key;
    playBtn.replaceChildren(svg(playing ? ICON.pause : ICON.play));
    playBtn.setAttribute("aria-label", playing ? "Pause" : "Play");
    renderModes();
    if (f !== lastReadout) {
      renderReadouts();
      lastReadout = f;
    }
    applyStage();
    if (presenterBar) renderPresenter();
  }

  // ------------------------------------------------------------ presenter
  let presenterBar: HTMLElement | null = null;
  function renderPresenter(): void {
    if (!presenterBar) return;
    presenterBar.replaceChildren(
      h("button", { type: "button", class: "iconbtn primary", "aria-label": playing ? "Pause" : "Play", onclick: () => setPlaying(!playing) }, svg(playing ? ICON.pause : ICON.play)),
      h("span", { class: "big" }, mode === "max" ? "whole run" : `${num(t, 0)} s`),
      h(
        "div",
        { class: "seg", role: "group", "aria-label": "Quantity shown" },
        ([
          ["depth", "Thickness"],
          ["speed", "Speed"],
          ["max", "Deepest"],
        ] as [FlowMode, string][]).map(([k, l]) =>
          h("button", { type: "button", "aria-pressed": String(mode === k), onclick: () => ((mode = k), k === "max" && (playing = false), update()) }, l),
        ),
      ),
      h(
        "div",
        { class: "seg", role: "group", "aria-label": "Playback speed" },
        [1, 2, 5].map((r) => h("button", { type: "button", "aria-pressed": String(rate === r), onclick: () => ((rate = r), renderPresenter()) }, r === 1 ? "Real time" : `${r}×`)),
      ),
      h("button", { type: "button", class: "btn small", onclick: () => setPresenter(false) }, "Exit"),
    );
  }

  function setPresenter(on: boolean): void {
    presenter = on;
    app.classList.toggle("presenter", on);
    presenterBar?.remove();
    presenterBar = null;
    if (on) {
      rate = 1;
      presenterBar = h("div", { class: "presenter-bar", role: "toolbar", "aria-label": "Presenter controls" });
      document.getElementById("stageView")!.append(presenterBar);
      stage.setView("oblique");
      stage.scene.setVex(1.5);
      vex = 1.5;
      renderPresenter();
    }
    update();
  }

  const onKey = (e: KeyboardEvent) => {
    const tag = (e.target as HTMLElement).tagName;
    if (["INPUT", "SELECT", "TEXTAREA", "BUTTON", "A"].includes(tag)) return;
    if (e.key === "Escape" && presenter) setPresenter(false);
    else if (e.key === " ") {
      e.preventDefault();
      setPlaying(!playing);
    } else if (e.key === "ArrowRight") seek(t + (result?.meta.every ?? 1));
    else if (e.key === "ArrowLeft") seek(t - (result?.meta.every ?? 1));
  };
  addEventListener("keydown", onKey);

  // --------------------------------------------------------------- render
  function renderPanel(): void {
    const s = job.scenario;
    const prov = job.provenance ?? {};
    const m = result?.meta;
    const vexInput = h("input", {
      type: "range",
      id: "vex",
      min: 1,
      max: 3,
      step: 0.1,
      value: vex,
      oninput: (e: Event) => {
        vex = Number((e.target as HTMLInputElement).value);
        vexOut.textContent = `${vex.toFixed(1)}×`;
        stage.scene.setVex(vex);
        update();
      },
    });
    const vexOut = h("output", { for: "vex" }, `${vex.toFixed(1)}×`);
    const boostInput = h("input", {
      type: "range",
      id: "boost",
      min: 1,
      max: 8,
      step: 1,
      value: boost,
      oninput: (e: Event) => {
        boost = Number((e.target as HTMLInputElement).value);
        boostOut.textContent = boost === 1 ? "true depth" : `${boost}×`;
        update();
      },
    });
    const boostOut = h("output", { for: "boost" }, boost === 1 ? "true depth" : `${boost}×`);
    const dl = (rows: [string, string][]) => h("dl", { class: "params" }, rows.flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, v)]));
    const mat: Partial<Material> = s.material ?? {};
    panel.replaceChildren(
      h(
        "div",
        { class: "panel-head" },
        h("h1", {}, job.name),
        h(
          "span",
          { class: "sub" },
          h("span", { class: "status completed" }, "completed"),
          ` ${dateTime(job.finished_at)} · ${duration(job.progress.elapsed_s)} solver time`,
        ),
        h(
          "div",
          { class: "btn-row", style: "margin-top: 8px" },
          h("button", { type: "button", class: "btn small", onclick: () => setPresenter(true) }, "Presenter mode"),
          h(
            "button",
            {
              type: "button",
              class: "btn small",
              onclick: async () => {
                const d = await api.duplicate(job.id);
                store.lastRun = d.id;
                location.hash = `#/run/${d.id}`;
              },
            },
            "Run again",
          ),
          h(
            "button",
            {
              type: "button",
              class: "btn small",
              onclick: () => {
                store.scenario = structuredClone(job.scenario);
                store.saveDraft();
                location.hash = "#/setup";
              },
            },
            "Edit as new",
          ),
        ),
      ),
      h(
        "div",
        { class: "panel-body" },
        h("section", { class: "section" }, h("h2", {}, "Shown on the map"), modeSeg, transport, h("div", { class: "field" }, h("label", {}, "Playback rate"), rateSel)),
        h("section", { class: "section" }, h("h2", {}, "Flow"), readouts),
        h("section", { class: "section" }, h("h2", {}, "Time series"), charts.runout.root, charts.umax.root, charts.area.root),
        h(
          "section",
          { class: "section" },
          h("h2", {}, "Figure and data"),
          h(
            "div",
            { class: "btn-row" },
            h(
              "button",
              {
                type: "button",
                class: "btn small",
                onclick: () => stage.exportFigure(`titan3d_${job.id}_${mode}${mode === "max" ? "" : `_t${Math.round(t)}s`}.png`),
              },
              icon("image"),
              "Export figure (PNG)",
            ),
            h(
              "button",
              {
                type: "button",
                class: "btn small",
                onclick: async () => {
                  await navigator.clipboard.writeText(stage.captionPlain);
                  toast("Figure caption copied.");
                },
              },
              icon("copy"),
              "Copy caption",
            ),
          ),
          h(
            "ul",
            { class: "list" },
            ARTIFACTS.filter(([name]) => job.artifacts?.includes(name)).map(([name, label, kind]) =>
              h(
                "li",
                {},
                h(
                  "a",
                  { class: "option", href: api.fileUrl(job.id, name), download: `${job.id}_${name}`, style: "grid-template-columns:auto 1fr auto" },
                  icon("download"),
                  h("span", { class: "name" }, label),
                  h("span", { class: "muted", style: "font-size:12px" }, kind),
                ),
              ),
            ),
          ),
        ),
        h(
          "section",
          { class: "section" },
          h("h2", {}, "Display"),
          h("div", { class: "field" }, h("label", { for: "vex" }, "Vertical exaggeration (3D view) ", vexOut), vexInput),
          h("div", { class: "field" }, h("label", { for: "boost" }, "Thin-flow exaggeration ", boostOut), boostInput, h("span", { class: "help" }, "Thickens the first 10 m of flow so thin margins stay visible; always badged on the map.")),
          h(
            "label",
            { class: "check" },
            h("input", { type: "checkbox", checked: true, onchange: (e: Event) => stage.scene.setContours((e.target as HTMLInputElement).checked) }),
            `Contours every ${stage.scene.contourInterval} m`,
          ),
          h(
            "div",
            { class: "field" },
            h("label", { for: "detail" }, "Playback detail"),
            h(
              "select",
              {
                id: "detail",
                onchange: (e: Event) => {
                  detail = Number((e.target as HTMLSelectElement).value);
                  load();
                },
              },
              [320, 640, 1024].map((v) => h("option", { value: v, selected: v === detail }, `${v} cells per side${v === 640 ? " (default)" : ""}`)),
            ),
            h("span", { class: "help" }, "Affects the 3D playback only; downloads keep the full computed resolution."),
          ),
        ),
        h(
          "section",
          { class: "section" },
          h("h2", {}, "Parameters"),
          dl([
            ["Terrain", m?.dem ?? s.dem_id ?? ""],
            ["Rheology", mat.rheology === "voellmy" ? `Voellmy (μ ${mat.mu}, ξ ${mat.xi} m/s²)` : "Coulomb"],
            ["Basal friction φ_bed", `${mat.phi_bed_deg ?? 24}°`],
            ["Internal friction φ_int", `${mat.phi_int_deg ?? 34}°`],
            ["Earth pressure", (mat.earth_pressure ?? "savage-hutter") === "hydrostatic" ? "hydrostatic" : "Savage–Hutter"],
            ["Curvature term", mat.curvature === false ? "off" : "on"],
            ["Released volume", m ? `${sci(m.volume_m3)} m³` : "—"],
            ["Grid", job.grid ? `${num(job.grid.nx)} × ${num(job.grid.ny)} @ ${num(job.grid.dx)} m` : "—"],
            ["CRS", job.grid?.crs ?? "—"],
            ["Simulated time", `${num(s.t_end ?? 0)} s, output every ${num(s.output_every ?? 0, 1)} s`],
            ["Time steps", m ? num(m.steps) : "—"],
            ["Numerics", `${s.numerics?.backend ?? "numba"}, ${s.numerics?.precision ?? "float64"}, CFL ${s.numerics?.cfl ?? 0.4}`],
          ]),
        ),
        h(
          "section",
          { class: "section" },
          h("h2", {}, "Provenance"),
          dl([
            ["titan3d", `${prov.titan3d_version ?? "—"} (${prov.git_commit ?? "—"})`],
            ["DEM sha256", typeof prov.dem_sha256 === "string" ? `${prov.dem_sha256.slice(0, 16)}…` : "—"],
            ["NumPy / Numba", `${prov.numpy ?? "—"} / ${prov.numba ?? "—"}`],
            ["Python", String(prov.python ?? "—")],
            ["Run id", job.id],
            ["Parent run", job.parent_job_id ?? "—"],
          ]),
        ),
        h(
          "section",
          { class: "section" },
          h("h2", {}, "Model notes"),
          h(
            "p",
            { class: "note" },
            "Depth-averaged granular flow (Savage–Hutter) solved by finite volumes: MUSCL–minmod reconstruction, hydrostatic reconstruction, Rusanov flux, SSP-RK2, implicit basal friction. Not modelled: adaptive mesh refinement, two-phase (Pitman–Le) flow, the internal-friction shear term, erosion and entrainment. ",
            h("strong", {}, "Results are model output, not an official hazard map."),
          ),
          h("p", { class: "note" }, RAMP_CITATION + "."),
        ),
      ),
    );
    renderReadouts();
    update();
  }

  function setCharts(): void {
    if (!result) return;
    const st = result.stats;
    const tt = st.map((x) => x.t);
    charts.runout.setData(tt, st.map((x) => x.runout), tEnd());
    charts.umax.setData(tt, st.map((x) => x.umax), tEnd());
    charts.area.setData(tt, st.map((x) => x.area), tEnd());
  }

  async function load(): Promise<void> {
    stage.showMessage("loading", "Loading results…", "Decoding the playback frames.");
    try {
      const r = await loadResult(api.resultUrl(job.id, detail), ctrl.signal);
      if (disposed) return;
      result = r;
      frontCache.clear();
      lastReadout = -2;
      maskRelease(r);
      stage.scene.setResult(r);
      stage.scene.setEnvelope(envQ, envMax);
      stage.scene.setDepthScale(depthMax);
      stage.scene.setMarkers(r.meta.sources.map((s) => ({ kind: s.kind, x: s.x, y: s.y, radius: s.radius, pin: false })));
      stage.scene.setVex(vex);
      stage.setTerrainLabel(`Terrain: ${r.meta.dem}`);
      stage.setCaptionActions([
        h(
          "button",
          { type: "button", class: "btn small", onclick: () => stage.exportFigure(`titan3d_${job.id}_${mode}${mode === "max" ? "" : `_t${Math.round(t)}s`}.png`) },
          icon("image"),
          "Export figure",
        ),
        h(
          "button",
          {
            type: "button",
            class: "btn small",
            onclick: async () => {
              await navigator.clipboard.writeText(stage.captionPlain);
              toast("Figure caption copied.");
            },
          },
          icon("copy"),
          "Copy caption",
        ),
      ]);
      stage.setView("plan");
      stage.hideMessage();
      setCharts();
      renderPanel();
    } catch (e) {
      if (disposed) return;
      stage.showMessage(
        "error",
        "Could not load the results",
        (e as Error).message,
        h("button", { type: "button", class: "btn", onclick: () => load() }, "Try again"),
      );
    }
  }

  stage.onPick(undefined);
  stage.setSurfaceContext("data");
  stage.onSurfaceChange = () => {
    lastKey = "";
    update();
  };
  stage.setProbe((p) => {
    if (!result) return null;
    const crs = result.meta.crs;
    const smp = stage.scene.sample(p.k, t);
    if (!smp) return null;
    const rows: [string, string][] = [
      ["Easting / northing", `${num(p.x)} / ${num(p.y)} m`],
    ];
    if (crs) {
      const [lon, lat] = toLonLat(crs, p.x, p.y);
      rows.push(["Position", lonLat(lon, lat)]);
    }
    rows.push(["Elevation", `${num(p.z)} m a.s.l.`]);
    if (mode === "max") rows.push(["Maximum depth", smp.hmax >= WET ? `${num(smp.hmax, 1)} m` : "not reached"]);
    if (mode === "max" && result.meta.sources.some((s) => s.kind === "pile" && Math.hypot(p.x - s.x, p.y - s.y) <= s.radius))
      rows.push(["", "inside the release area"]);
    else {
      rows.push([`Depth at ${num(t, 1)} s`, smp.h >= 0.05 ? `${num(smp.h, 2)} m` : "dry"]);
      rows.push(["Speed", smp.h >= 0.05 ? `${num(smp.u, 1)} m/s` : "—"]);
    }
    return rows;
  });
  const untick = stage.scene.onTick((dt) => {
    if (!playing || !result) return;
    t += dt * rate;
    if (t >= tEnd()) {
      t = tEnd();
      playing = false; // hold on the final deposit
    }
    update();
  });

  panel.replaceChildren(h("div", { class: "panel-head" }, h("h1", {}, job.name), h("span", { class: "sub" }, "Loading results…")));
  load();

  return () => {
    disposed = true;
    ctrl.abort();
    untick();
    removeEventListener("keydown", onKey);
    if (presenter) setPresenter(false);
    stage.setProbe(undefined);
    stage.setCaptionActions([]);
    stage.setSurfaceContext("terrain");
  };
}
