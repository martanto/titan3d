// Setup view: DEM, sources (click to place), domain, material, resolution, run.
import { ApiError, api, type Dem, type Estimate, type FluxSource, type Pile, type Scenario } from "../api/client";
import { store } from "../app/store";
import type { Preview } from "../data/bundle";
import { toLonLat } from "../geo/utm";
import { debounce, download, h, icon, kids, toast } from "./dom";
import { num, sci } from "./format";
import type { Stage } from "./stage";
import { domainBox, ensurePreview, showScenario, terrainCaption, terrainProbe } from "./terrain";

const PRESETS: [string, string, number][] = [
  ["quick", "Quick", 40],
  ["standard", "Standard", 20],
  ["fine", "Fine", 10],
];

interface NumOpts {
  min?: number;
  max?: number;
  step?: number;
  help?: string;
  digits?: number;
}

export function mountSetup(stage: Stage, panel: HTMLElement): () => void {
  const ctrl = new AbortController();
  let disposed = false;
  let estimate: Estimate | null = null;
  let estimateError: string | null = null;
  let runError: string | null = null;
  let pendingFiles: File[] = [];
  let uploadState: { loaded: number; total: number; stage: string } | null = null;
  const sc = (): Scenario => store.scenario!;
  const keepFixed = new Map<number, "radius" | "height">();

  const refreshEstimate = debounce(async () => {
    if (disposed) return;
    try {
      estimate = await api.estimate(sc());
      estimateError = null;
    } catch (e) {
      estimate = null;
      estimateError = (e as Error).message;
    }
    renderEstimate();
  }, 350);

  function changed(structural = false): void {
    store.saveDraft();
    if (structural) render();
    refreshStage();
    refreshEstimate();
  }

  function refreshStage(): void {
    if (store.preview && store.previewFor === sc().dem_id) {
      showScenario(stage, sc(), store.preview, store.selected);
      const piles = sc().piles ?? [];
      const vents = sc().flux_sources ?? [];
      const vol = estimate?.released_m3;
      stage.setCaption(
        `${terrainCaption(store.preview, stage.scene.surface)} Sources: ${piles.length} pile${piles.length === 1 ? "" : "s"}, ${vents.length} vent${vents.length === 1 ? "" : "s"}${vol ? ` (${sci(vol)} m³ released)` : ""}. Dashed box: computational domain.`,
        "Setup.",
      );
    }
  }

  // --------------------------------------------------------------- fields
  function numField(label: string, unit: string, get: () => number, set: (v: number) => void, o: NumOpts = {}): HTMLElement {
    const id = `f-${label.replace(/\W+/g, "-").toLowerCase()}-${Math.random().toString(36).slice(2, 7)}`;
    const err = h("span", { class: "error-text", id: `${id}-err` });
    const input = h("input", {
      id,
      type: "number",
      inputmode: "decimal",
      value: String(get()),
      min: o.min,
      max: o.max,
      step: o.step ?? "any",
      "aria-describedby": o.help ? `${id}-help ${id}-err` : `${id}-err`,
    });
    const wrapEl = h(
      "div",
      { class: "field" },
      h("label", { for: id }, label),
      h("div", { class: "input-unit" }, input, unit ? h("span", {}, unit) : null),
      o.help ? h("span", { class: "help", id: `${id}-help` }, o.help) : null,
      err,
    );
    input.addEventListener("input", () => {
      const v = Number(input.value);
      const bad =
        input.value === "" || !Number.isFinite(v) || (o.min !== undefined && v < o.min) || (o.max !== undefined && v > o.max);
      wrapEl.classList.toggle("invalid", bad);
      input.setAttribute("aria-invalid", String(bad));
      err.textContent = bad ? `Enter a value${o.min !== undefined ? ` from ${o.min}` : ""}${o.max !== undefined ? ` to ${o.max}` : ""}${unit ? ` ${unit}` : ""}.` : "";
      if (!bad) {
        set(v);
        changed(false);
      }
    });
    return wrapEl;
  }

  function seg<T extends string>(label: string, options: [T, string, string?][], value: T, onPick: (v: T) => void): HTMLElement {
    // aria-labelledby takes space-separated ids, so the label text must be slugged
    const lblId = `seg-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
    return h(
      "div",
      { class: "field" },
      h("span", { class: "label", id: lblId }, label),
      h(
        "div",
        { class: "seg", role: "group", "aria-labelledby": lblId },
        options.map(([v, text, small]) =>
          h(
            "button",
            { type: "button", "aria-pressed": String(v === value), onclick: () => onPick(v) },
            text,
            small ? h("small", {}, small) : null,
          ),
        ),
      ),
    );
  }

  // ------------------------------------------------------------------ DEM
  function demOption(d: Dem): HTMLElement {
    const info = d.info;
    const meta =
      d.status === "ready" && info
        ? `${info.tiles} tile${info.tiles === 1 ? "" : "s"} · ${num(info.res_m, 1)} m pixels · ${num(info.shape[1])} × ${num(info.shape[0])} px · ${num(info.nan_fraction * 100, 1)} % no data`
        : d.status === "failed"
          ? d.error ?? "Stitching failed"
          : "Stitching tiles…";
    return h(
      "label",
      { class: "option" },
      h("input", {
        type: "radio",
        name: "dem",
        value: d.id,
        checked: d.id === sc().dem_id,
        disabled: d.status !== "ready",
        onchange: () => selectDem(d),
      }),
      h("span", { class: "name" }, d.name),
      h("span", { class: `status ${d.status}` }, d.status === "ready" ? (d.source === "builtin" ? "built-in" : "ready") : d.status),
      h("span", { class: "meta" }, meta),
    );
  }

  async function selectDem(d: Dem): Promise<void> {
    sc().dem_id = d.id;
    store.saveDraft();
    try {
      const p = await ensurePreview(stage, d.id, ctrl.signal);
      fitSourcesToDem(p);
      stage.setProbe(terrainProbe(p));
      stage.setTerrainLabel(`Terrain: ${d.name}`);
      changed(true);
      stage.scene.focus(domainBox(sc(), p.meta.crs ?? "EPSG:32749"));
      store.emit();
    } catch (e) {
      if (!disposed) stage.showMessage("error", "Could not load the terrain", (e as Error).message);
    }
  }

  function fitSourcesToDem(p: Preview): void {
    const b = p.meta.bounds_lonlat;
    const s = p.meta.summit;
    if (!b || !s) return;
    const inside = (lon?: number, lat?: number) =>
      lon !== undefined && lat !== undefined && lon >= b[0] && lon <= b[2] && lat >= b[1] && lat <= b[3];
    const all = [...(sc().piles ?? []), ...(sc().flux_sources ?? [])];
    if (all.length && all.every((x) => inside(x.lon, x.lat))) return;
    // sources outside this DEM: start from a pile at the highest point
    sc().piles = [{ lon: s.lon, lat: s.lat, height: 60, radius: 300 }];
    sc().flux_sources = [];
    sc().domain = { ...(sc().domain ?? {}), center_lon: null, center_lat: null } as Scenario["domain"];
    store.selected = 0;
    toast("Sources moved to the highest point of this DEM.");
  }

  async function startUpload(name: string): Promise<void> {
    if (!pendingFiles.length) return;
    uploadState = { loaded: 0, total: pendingFiles.reduce((a, f) => a + f.size, 0), stage: "Uploading" };
    render();
    try {
      const dem = await api.uploadDem(pendingFiles, name, (loaded, total) => {
        uploadState = { loaded, total, stage: "Uploading" };
        renderUpload();
      });
      pendingFiles = [];
      uploadState = { loaded: 1, total: 1, stage: "Stitching tiles on the server" };
      store.dems = await api.listDems();
      render();
      let d = dem;
      while (!disposed && d.status === "processing") {
        await new Promise((r) => setTimeout(r, 1500));
        d = await api.getDem(dem.id);
      }
      uploadState = null;
      store.dems = await api.listDems();
      if (d.status === "ready") {
        toast(`DEM "${d.name}" is ready.`);
        await selectDem(d);
      } else {
        render();
      }
    } catch (e) {
      uploadState = null;
      runError = `Upload failed: ${(e as Error).message}`;
      render();
    }
  }

  let uploadBox: HTMLElement | null = null;
  function renderUpload(): void {
    if (!uploadBox) return;
    const list = h(
      "ul",
      { class: "filelist" },
      pendingFiles.map((f) => h("li", {}, h("span", {}, f.name), h("span", { class: "text-muted" }, `${num(f.size / 1e6, 1)} MB`))),
    );
    const nameInput = h("input", {
      type: "text",
      "aria-label": "Name for the uploaded DEM",
      placeholder: "DEM name, e.g. Merapi DEMNAS",
      value: pendingFiles[0]?.name.replace(/\.(tif|tiff)$/i, "") ?? "",
    });
    const fileInput = h("input", {
      type: "file",
      accept: ".tif,.tiff,image/tiff",
      multiple: true,
      class: "sr-only",
      id: "demFiles",
      onchange: (e: Event) => {
        pendingFiles = [...((e.target as HTMLInputElement).files ?? [])];
        renderUpload();
      },
    });
    const progress = uploadState
      ? h(
          "div",
          { class: "progress w-full" },
          h("span", { class: "note" }, `${uploadState.stage}${uploadState.stage === "Uploading" ? ` · ${num((100 * uploadState.loaded) / Math.max(uploadState.total, 1))} %` : "…"}`),
          h(
            "div",
            { class: `progress-track active${uploadState.stage === "Uploading" ? "" : " indeterminate"}` },
            h("div", { class: "progress-fill", style: `--p:${uploadState.loaded / Math.max(uploadState.total, 1)}` }),
          ),
        )
      : null;
    uploadBox.replaceChildren(...kids(
      h("strong", {}, "Upload your own DEM"),
      h("span", { class: "note" }, "Drop one or more GeoTIFF tiles here. They are stitched on the server; tiles without a CRS are read as WGS 84 longitude/latitude."),
      fileInput,
      h("label", { for: "demFiles", class: "btn small" }, icon("upload"), "Choose GeoTIFF files"),
      pendingFiles.length ? list : null,
      pendingFiles.length && !uploadState
        ? h(
            "div",
            { class: "field w-full" },
            nameInput,
            h(
              "button",
              { type: "button", class: "btn small", onclick: () => startUpload(nameInput.value) },
              `Upload ${pendingFiles.length} file${pendingFiles.length === 1 ? "" : "s"}`,
            ),
          )
        : null,
      progress,
    ));
  }

  // -------------------------------------------------------------- sources
  function sourceCard(kind: "pile" | "flux", i: number): HTMLElement {
    const np = sc().piles?.length ?? 0;
    const idx = kind === "pile" ? i : np + i;
    const isSel = store.selected === idx;
    const src = (kind === "pile" ? sc().piles![i] : sc().flux_sources![i]) as Pile & FluxSource;
    const vol =
      kind === "pile"
        ? (Math.PI * (src.radius ?? 300) ** 2 * (src.height ?? 60)) / 2
        : (Math.PI * (src.radius ?? 100) ** 2 * (src.influx ?? 1) * (src.duration ?? 60)) / 2;
    const set = (k: keyof (Pile & FluxSource)) => (v: number) => {
      (src as Record<string, unknown>)[k] = v;
    };
    const get = (k: keyof (Pile & FluxSource), d: number) => () => (src[k] as number | undefined) ?? d;
    const fields =
      kind === "pile"
        ? pileFields(i, src)
        : [
            numField("Footprint radius", "m", get("radius", 100), set("radius"), { min: 1, max: 5000 }),
            numField("Peak influx", "m/s", get("influx", 1), set("influx"), { min: 0.001, max: 50, help: "Depth added per second at the centre." }),
            numField("Start", "s", get("start", 0), set("start"), { min: 0 }),
            numField("Duration", "s", get("duration", 60), set("duration"), { min: 0.1 }),
            numField("Initial speed", "m/s", get("speed", 0), set("speed"), { min: 0, max: 200 }),
            numField("Direction", "°", get("direction_deg", 0), set("direction_deg"), { min: 0, max: 359.9, help: "Azimuth, clockwise from north." }),
          ];
    return h(
      "div",
      { class: "source", "aria-current": String(isSel) },
      h(
        "div",
        { class: "source-head" },
        h("span", { class: `swatch${kind === "flux" ? " vent" : ""}`, "aria-hidden": "true" }),
        h("span", { class: "title" }, `${kind === "pile" ? "Pile" : "Vent"} ${i + 1}`, h("span", { class: "text-muted" }, ` · ${sci(vol)} m³`)),
        h(
          "button",
          {
            type: "button",
            class: "btn small",
            "aria-pressed": String(isSel),
            title: "Select, then click the map to move this source",
            onclick: () => {
              store.selected = idx;
              changed(true);
            },
          },
          icon("target"),
          isSel ? "Placing" : "Place",
        ),
        h(
          "button",
          {
            type: "button",
            class: "btn small danger",
            "aria-label": `Remove ${kind === "pile" ? "pile" : "vent"} ${i + 1}`,
            disabled: np + (sc().flux_sources?.length ?? 0) <= 1,
            onclick: () => {
              if (kind === "pile") sc().piles!.splice(i, 1);
              else sc().flux_sources!.splice(i, 1);
              store.selected = 0;
              changed(true);
            },
          },
          icon("trash"),
        ),
      ),
      h(
        "div",
        { class: "grid grid-cols-2 gap-3" },
        numField("Longitude", "°E", get("lon", 0), set("lon"), { min: -180, max: 180, digits: 5 }),
        numField("Latitude", "°N", get("lat", 0), set("lat"), { min: -90, max: 90, digits: 5 }),
        ...fields,
      ),
    );
  }

  // ------------------------------------------------------- pile volume
  // Titan2D paraboloid pile: V = π R² H / 2. Volume, H and R stay consistent; editing the
  // volume rescales H (radius fixed) or R (thickness fixed).
  const pileVolume = (p: Pile) => (Math.PI * (p.radius ?? 300) ** 2 * (p.height ?? 60)) / 2;

  function volText(v: number): string {
    return Number(v.toPrecision(4)).toExponential().replace("e+", "e");
  }

  function pileFields(i: number, src: Pile): HTMLElement[] {
    const keep = keepFixed.get(i) ?? "radius";
    const id = `vol-${i}`;
    const volInput = h("input", {
      id,
      type: "text",
      inputmode: "decimal",
      autocomplete: "off",
      value: volText(pileVolume(src)),
      "aria-describedby": `${id}-help ${id}-err`,
    });
    const help = h("span", { class: "help", id: `${id}-help` }, `= ${sci(pileVolume(src))} m³ · V = π R² H / 2`);
    const err = h("span", { class: "error-text", id: `${id}-err` });
    const volField = h(
      "div",
      { class: "field col-span-full" },
      h("label", { for: id }, "Volume"),
      h("div", { class: "input-unit" }, volInput, h("span", {}, "m³")),
      help,
      err,
    );
    const refreshVolume = () => {
      if (document.activeElement !== volInput) volInput.value = volText(pileVolume(src));
      help.textContent = `= ${sci(pileVolume(src))} m³ · V = π R² H / 2`;
    };
    const applyVolume = () => {
      const v = Number(volInput.value.replace(/[\s,_]/g, ""));
      let msg = "";
      if (!Number.isFinite(v) || v <= 0) msg = "Enter a volume in m³, e.g. 8.5e6.";
      else if (keep === "radius") {
        const hgt = (2 * v) / (Math.PI * (src.radius ?? 300) ** 2);
        if (hgt < 0.1 || hgt > 1000) msg = `That needs H = ${num(hgt, 1)} m (allowed 0.1–1,000 m); change the radius or keep thickness fixed.`;
        else src.height = Number(hgt.toPrecision(6));
      } else {
        const r = Math.sqrt((2 * v) / (Math.PI * (src.height ?? 60)));
        if (r < 1 || r > 10000) msg = `That needs R = ${num(r)} m (allowed 1–10,000 m); change the thickness or keep radius fixed.`;
        else src.radius = Number(r.toPrecision(6));
      }
      volField.classList.toggle("invalid", Boolean(msg));
      volInput.setAttribute("aria-invalid", String(Boolean(msg)));
      err.textContent = msg;
      if (!msg) changed(true); // re-render so H, R and the card header show the new values
    };
    volInput.addEventListener("change", applyVolume);
    volInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") applyVolume();
    });
    const onDim = (k: "height" | "radius") => (v: number) => {
      src[k] = v;
      refreshVolume();
    };
    return [
      volField,
      h(
        "div",
        { class: "col-span-full" },
        seg(
          `Keep fixed when the volume changes (pile ${i + 1})`,
          [
            ["radius", "Radius"],
            ["height", "Thickness"],
          ],
          keep,
          (k) => {
            keepFixed.set(i, k);
            changed(true);
          },
        ),
      ),
      numField("Peak thickness H", "m", () => src.height ?? 60, onDim("height"), { min: 0.1, max: 1000 }),
      numField("Radius R", "m", () => src.radius ?? 300, onDim("radius"), { min: 1, max: 10000 }),
    ];
  }

  function addSource(kind: "pile" | "flux"): void {
    const s = store.preview?.meta.summit;
    const base = { lon: s?.lon ?? 112.9225, lat: s?.lat ?? -8.108 };
    if (kind === "pile") {
      sc().piles = [...(sc().piles ?? []), { ...base, height: 60, radius: 300 }];
      store.selected = sc().piles!.length - 1;
    } else {
      sc().flux_sources = [...(sc().flux_sources ?? []), { ...base, radius: 100, influx: 1, start: 0, duration: 60, speed: 0, direction_deg: 0 }];
      store.selected = (sc().piles?.length ?? 0) + sc().flux_sources!.length - 1;
    }
    changed(true);
  }

  // ------------------------------------------------------------- estimate
  let estimateBox: HTMLElement | null = null;
  function renderEstimate(): void {
    if (!estimateBox) return;
    if (estimateError) {
      estimateBox.replaceChildren(h("div", { class: "alert", role: "alert" }, h("strong", {}, "Check the scenario: "), estimateError));
      return;
    }
    if (!estimate) {
      estimateBox.replaceChildren(h("p", { class: "note" }, "Estimating…"));
      return;
    }
    const e = estimate;
    const r = (k: string, v: string, n?: string) =>
      h("div", { class: "readout" }, h("span", { class: "k" }, k), h("span", { class: "v" }, v), n ? h("span", { class: "n" }, n) : null);
    estimateBox.replaceChildren(
      h(
        "div",
        { class: "estimate" },
        r("Grid", `${num(e.grid_shape[1])} × ${num(e.grid_shape[0])}`, `${num(e.cells)} cells`),
        r("Released volume", `${sci(e.released_m3)} m³`),
        r(store.scenario?.numerics?.amr ? "Uniform memory reference" : "Solver memory", `≈ ${num(e.memory_mb)} MB`),
        r(store.scenario?.numerics?.amr ? "Uniform runtime reference" : "Runtime", e.runtime_class, `${num(e.frames)} output frames`),
      ),
    );
    refreshStage();
  }

  // ---------------------------------------------------------------- render
  function render(): void {
    if (disposed || !store.scenario) return;
    const s = sc();
    // the scenario always comes from the API defaults, so every section exists
    const m = s.material!;
    const n = s.numerics!;
    const d = s.domain!;
    const dx = n.dx ?? 20;
    const preset = PRESETS.find((p) => p[2] === dx)?.[0] ?? "custom";

    const nameInput = h("input", {
      type: "text",
      id: "scName",
      value: s.name ?? "",
      maxlength: 120,
      oninput: (e: Event) => {
        s.name = (e.target as HTMLInputElement).value;
        store.saveDraft();
      },
    });

    uploadBox = h("div", { class: "dropzone" });
    uploadBox.addEventListener("dragover", (e) => {
      e.preventDefault();
      uploadBox!.classList.add("over");
    });
    uploadBox.addEventListener("dragleave", () => uploadBox!.classList.remove("over"));
    uploadBox.addEventListener("drop", (e) => {
      e.preventDefault();
      uploadBox!.classList.remove("over");
      pendingFiles = [...(e.dataTransfer?.files ?? [])].filter((f) => /\.(tif|tiff)$/i.test(f.name));
      if (!pendingFiles.length) toast("Only .tif / .tiff files can be uploaded.");
      renderUpload();
    });
    renderUpload();

    estimateBox = h("div", { "aria-live": "polite" });

    const yamlInput = h("input", {
      type: "file",
      accept: ".yaml,.yml,text/yaml,application/x-yaml",
      class: "sr-only",
      id: "yamlFile",
      onchange: async (e: Event) => {
        const f = (e.target as HTMLInputElement).files?.[0];
        if (!f) return;
        const res = await api.importYaml(f);
        if (res.ok && res.scenario) {
          store.scenario = res.scenario;
          store.selected = 0;
          runError = null;
          toast(`Loaded "${res.scenario.name}".`);
          const dem = store.dems.find((x) => x.id === res.scenario!.dem_id);
          if (dem?.status === "ready") await selectDem(dem);
          else changed(true);
        } else {
          runError = `The config has problems: ${res.errors?.map((x) => `${x.loc}: ${x.msg}`).join("; ")}`;
          render();
        }
      },
    });

    const runBtn = h(
      "button",
      {
        type: "button",
        class: "btn primary",
        disabled: !store.preview || store.previewFor !== s.dem_id,
        onclick: async () => {
          runBtn.setAttribute("disabled", "");
          runBtn.textContent = "Submitting…";
          try {
            const created = await api.createSimulation(s);
            store.lastRun = created.id;
            location.hash = `#/run/${created.id}`;
          } catch (e) {
            runError = e instanceof ApiError ? e.message : String(e);
            render();
          }
        },
      },
      "Run simulation",
    );

    panel.replaceChildren(
      h(
        "div",
        { class: "panel-head" },
        h("h1", {}, "New simulation"),
        h("span", { class: "sub" }, "Place the release on the map, check the estimate, then run."),
      ),
      h(
        "div",
        { class: "panel-body" },
        h("div", { class: "section" }, h("div", { class: "field" }, h("label", { for: "scName" }, "Scenario name"), nameInput)),
        h(
          "fieldset",
          { class: "section" },
          h("legend", {}, "Terrain"),
          h("ul", { class: "list" }, store.dems.map((x) => h("li", {}, demOption(x)))),
          uploadBox,
        ),
        h(
          "fieldset",
          { class: "section" },
          h("legend", {}, "Release"),
          h("p", { class: "hint" }, "Select a source and click the map to place it. Piles release at t = 0; vents add material over time."),
          (s.piles ?? []).map((_, i) => sourceCard("pile", i)),
          (s.flux_sources ?? []).map((_, i) => sourceCard("flux", i)),
          h(
            "div",
            { class: "flex flex-wrap gap-2" },
            h("button", { type: "button", class: "btn small", onclick: () => addSource("pile") }, icon("plus"), "Add pile"),
            h("button", { type: "button", class: "btn small", onclick: () => addSource("flux") }, icon("plus"), "Add vent"),
          ),
        ),
        h(
          "fieldset",
          { class: "section" },
          h("legend", {}, "Computational domain"),
          h("p", { class: "hint" }, "Distances from the first source. Keep the runout path inside the DEM."),
          h(
            "div",
            { class: "grid grid-cols-2 gap-3" },
            numField("West", "km", () => d.west_km ?? 6, (v) => (d.west_km = v), { min: 0.5, max: 100 }),
            numField("East", "km", () => d.east_km ?? 16, (v) => (d.east_km = v), { min: 0.5, max: 100 }),
            numField("South", "km", () => d.south_km ?? 14, (v) => (d.south_km = v), { min: 0.5, max: 100 }),
            numField("North", "km", () => d.north_km ?? 6, (v) => (d.north_km = v), { min: 0.5, max: 100 }),
          ),
        ),
        h(
          "fieldset",
          { class: "section" },
          h("legend", {}, "Material"),
          seg(
            "Basal rheology",
            [
              ["coulomb", "Coulomb"],
              ["voellmy", "Voellmy"],
            ],
            (m.rheology ?? "coulomb") as "coulomb" | "voellmy",
            (v) => {
              m.rheology = v;
              changed(true);
            },
          ),
          h(
            "div",
            { class: "grid grid-cols-2 gap-3" },
            numField("Basal friction φ_bed", "°", () => m.phi_bed_deg ?? 24, (v) => (m.phi_bed_deg = v), { min: 1, max: 59 }),
            numField("Internal friction φ_int", "°", () => m.phi_int_deg ?? 34, (v) => (m.phi_int_deg = v), { min: 1, max: 59 }),
            m.rheology === "voellmy"
              ? numField("Friction μ", "", () => m.mu ?? 0.12, (v) => (m.mu = v), { min: 0.001, max: 0.999 })
              : null,
            m.rheology === "voellmy"
              ? numField("Turbulence ξ", "m/s²", () => m.xi ?? 1000, (v) => (m.xi = v), { min: 1, max: 10000 })
              : null,
          ),
          h(
            "div",
            { class: "field" },
            h("label", { for: "ep" }, "Earth pressure"),
            h(
              "select",
              {
                id: "ep",
                onchange: (e: Event) => {
                  m.earth_pressure = (e.target as HTMLSelectElement).value as "hydrostatic" | "savage-hutter";
                  changed();
                },
              },
              h("option", { value: "savage-hutter", selected: (m.earth_pressure ?? "savage-hutter") === "savage-hutter" }, "Savage–Hutter active/passive"),
              h("option", { value: "hydrostatic", selected: m.earth_pressure === "hydrostatic" }, "Hydrostatic (k = 1)"),
            ),
          ),
          h(
            "label",
            { class: "check" },
            h("input", {
              type: "checkbox",
              checked: m.curvature ?? true,
              onchange: (e: Event) => {
                m.curvature = (e.target as HTMLInputElement).checked;
                changed();
              },
            }),
            "Bed-curvature term (centripetal normal stress)",
          ),
        ),
        h(
          "fieldset",
          { class: "section" },
          h("legend", {}, "Resolution and time"),
          seg(
            "Grid spacing",
            [...PRESETS.map(([k, t, v]) => [k, t, `${v} m`] as [string, string, string]), ["custom", "Custom", `${preset === "custom" ? dx + " m" : "10–500 m"}`]],
            preset,
            (v) => {
              const p = PRESETS.find((x) => x[0] === v);
              if (p) n.dx = p[2];
              changed(true);
            },
          ),
          numField(n.amr ? "Finest grid spacing Δx" : "Grid spacing Δx", "m", () => n.dx ?? 20, (v) => (n.dx = v), {
            min: 10,
            max: 500,
            help: "DEMNAS pixels are ≈ 8.3 m; halving Δx costs about 8× the runtime.",
          }),
          h("label", { class: "check" },
            h("input", {
              id: "amr-enabled",
              type: "checkbox",
              checked: n.amr ?? false,
              onchange: (e: Event) => {
                n.amr = (e.target as HTMLInputElement).checked;
                changed(true);
                panel.querySelector<HTMLInputElement>("#amr-enabled")?.focus({ preventScroll: true });
              },
            }),
            "Adaptive mesh refinement (experimental)",
          ),
          n.amr ? h("p", { class: "sub" },
            `Cells adapt between ${dx} and ${2 * dx} m. Outputs use a ${dx} m raster; coarse cells contain less flow detail. Runtime and memory estimates describe the uniform solver.`,
          ) : null,
          h(
            "div",
            { class: "grid grid-cols-2 gap-3" },
            numField("Simulated time", "s", () => s.t_end ?? 300, (v) => (s.t_end = v), { min: 1, max: 86400 }),
            numField("Output every", "s", () => s.output_every ?? 2, (v) => (s.output_every = v), { min: 0.5, max: 3600 }),
          ),
          h(
            "details",
            { class: "more" },
            h("summary", {}, "Numerics"),
            h(
              "div",
              {},
              seg(
                "Precision",
                [
                  ["float64", "float64", "reference"],
                  ["float32", "float32", "≈ 2× faster"],
                ],
                (n.precision ?? "float64") as "float64" | "float32",
                (v) => {
                  n.precision = v;
                  changed(true);
                },
              ),
              seg(
                "Kernels",
                [
                  ["numba", "Numba", "compiled"],
                  ["numpy", "NumPy", "reference"],
                ],
                (n.backend ?? "numba") as "numba" | "numpy",
                (v) => {
                  n.backend = v;
                  changed(true);
                },
              ),
              numField("Courant number", "", () => n.cfl ?? 0.4, (v) => (n.cfl = v), { min: 0.05, max: 0.9 }),
              n.amr ? h("div", {},
                numField("Relative gradient trigger", "", () => n.amr_gradient ?? 0.05, (v) => (n.amr_gradient = v), {
                  min: 0.001, max: 1, help: "Smaller values refine more regions; fronts and vent footprints also trigger refinement.",
                }),
                numField("Refinement buffer", "parent cells", () => n.amr_buffer ?? 2, (v) => (n.amr_buffer = v), { min: 1, max: 8, step: 1 }),
                numField("Regrid every", "steps", () => n.amr_regrid_every ?? 4, (v) => (n.amr_regrid_every = v), { min: 1, max: 32, step: 1 }),
                numField("Coarsen after", "quiet updates", () => n.amr_coarsen_delay ?? 3, (v) => (n.amr_coarsen_delay = v), { min: 1, max: 16, step: 1 }),
              ) : null,
            ),
          ),
        ),
        h("div", { class: "section" }, h("h2", {}, "Estimate"), estimateBox),
      ),
      h(
        "div",
        { class: "panel-foot" },
        runError ? h("div", { class: "alert", role: "alert" }, h("strong", {}, "Cannot run: "), runError) : null,
        h(
          "div",
          { class: "flex flex-wrap gap-2" },
          yamlInput,
          h("label", { for: "yamlFile", class: "btn small" }, icon("upload"), "Load config"),
          h(
            "button",
            {
              type: "button",
              class: "btn small",
              onclick: async () => {
                try {
                  download(await api.exportYaml(s), `${(s.name ?? "scenario").replace(/[^\w-]+/g, "_")}.yaml`);
                } catch (e) {
                  toast((e as Error).message);
                }
              },
            },
            icon("download"),
            "Download config",
          ),
        ),
        runBtn,
      ),
    );
    renderEstimate();
  }

  // ----------------------------------------------------------------- init
  (async () => {
    try {
      const [dems, def] = await Promise.all([api.listDems(), api.defaultScenario()]);
      if (disposed) return;
      store.dems = dems;
      store.scenario ??= store.loadDraft(def);
      let dem = dems.find((x) => x.id === sc().dem_id && x.status === "ready") ?? dems.find((x) => x.status === "ready");
      render();
      if (!dem) {
        const processing = dems.find((x) => x.status === "processing");
        stage.showMessage(
          processing ? "loading" : "empty",
          processing ? "Preparing the built-in DEM…" : "No terrain yet",
          processing
            ? "The Semeru DEMNAS tiles are being stitched (first start only, about 20 s)."
            : "Upload GeoTIFF tiles in the Terrain section to begin.",
        );
        while (!disposed && processing && !dem) {
          await new Promise((r) => setTimeout(r, 2000));
          store.dems = await api.listDems();
          dem = store.dems.find((x) => x.status === "ready");
        }
        if (!dem || disposed) return;
      }
      await selectDem(dem);
    } catch (e) {
      if (!disposed)
        stage.showMessage("error", "The titan3d server is not reachable", `${(e as Error).message}. Start it with "uv run titan3d serve" in backend/.`);
    }
  })();

  stage.setView("plan");
  stage.setColourbar(null);
  stage.setBadges([]);
  stage.onSurfaceChange = () => refreshStage();
  stage.onPick((p) => {
    const crs = store.preview?.meta.crs;
    if (!crs || !store.scenario || !store.preview?.valid[p.k]) return;
    const [lon, lat] = toLonLat(crs, p.x, p.y);
    const np = sc().piles?.length ?? 0;
    const target = store.selected < np ? sc().piles![store.selected] : sc().flux_sources?.[store.selected - np];
    if (!target) return;
    target.lon = Number(lon.toFixed(6));
    target.lat = Number(lat.toFixed(6));
    changed(true);
  });

  return () => {
    disposed = true;
    ctrl.abort();
    stage.onPick(undefined);
    stage.setProbe(undefined);
  };
}
