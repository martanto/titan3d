import { h, svg } from "./dom";
import "../styles/visual-guideline.css";

const steps = [
  { title: "Read the terrain", short: "Terrain", lead: "The landscape becomes the bed the flow moves over.", body: "Choose or upload a GeoTIFF digital elevation model (DEM). Tiles are stitched where needed, checked for a coordinate reference system and reprojected into a local UTM domain. Elevation becomes the bed field b(x, y).", input: "DEM elevations · domain extent", output: "Georeferenced terrain in metres", detail: "A DEM describes ground elevation. It does not describe the thickness of the released material." },
  { title: "Define the release", short: "Sources", lead: "Tell the model where material enters the landscape.", body: "Place a paraboloid pile with a radius and height, or prescribe a vent with a start time, duration and discharge. Piles define the initial flow depth; vents add material during the calculation. Initial velocity sets the starting momentum.", input: "Location · pile geometry or vent discharge · velocity", output: "Initial depth and momentum, plus timed sources", detail: "For a circular paraboloid pile, volume = π × radius² × height / 2. The discrete release is represented on the computational grid." },
  { title: "Choose the material", short: "Physics", lead: "The same terrain can produce different flows when resistance changes.", body: "Choose Coulomb basal friction or Voellmy resistance. Coulomb uses a basal friction angle; Voellmy combines a friction coefficient μ with a velocity-dependent resistance controlled by ξ. Earth-pressure closure and the curvature option also affect the momentum balance.", input: "Rheology · friction · earth pressure · curvature", output: "A specified depth-averaged physical model", detail: "The model evolves bulk depth and horizontal momentum. It does not resolve individual grains or the vertical velocity profile." },
  { title: "Discretise the domain", short: "Grid", lead: "A continuous landscape becomes a set of computational cells.", body: "Grid spacing dx controls spatial resolution. Each cell stores bed elevation b, flow depth h and momenta hu and hv. Set the dry-depth threshold, simulated duration and output interval. The uniform grid is the default; experimental AMR can adapt cell resolution.", input: "Cell spacing (m) · dry depth (m) · duration (s)", output: "Cell fields and numerical settings", detail: "Smaller cells increase computational cost. Viewer detail only changes playback; it does not change solver resolution." },
  { title: "Advance the flow", short: "Calculation", lead: "Exchange mass and momentum, then repeat through simulated time.", body: "MUSCL–minmod reconstruction estimates states at cell faces. Hydrostatic reconstruction accounts for bed elevation, and Rusanov fluxes exchange mass and momentum. Gravity, friction and source terms complete the balance. SSP-RK2 advances the state with a CFL-limited time step.", input: "Current cell state · physical and numerical parameters", output: "Updated h, hu and hv at the next time step", detail: "The solver repeats until the requested end time. The CFL time step is chosen for numerical stability; it is different from the saved-frame interval." },
  { title: "Interpret the results", short: "Results", lead: "The calculation becomes a reproducible scenario you can inspect and share.", body: "Saved frames support depth and speed playback. Track maximum depth, maximum speed, inundated area, runout and volume remaining or leaving the domain. Export maximum fields as GeoTIFFs and outlines as GeoJSON or KML, alongside the scenario configuration and run log.", input: "Saved states · statistics · run provenance", output: "Playback, GIS layers and a reproducible scenario", detail: "A scenario is conditional on its inputs and assumptions. Compare mass balance, resolution sensitivity and observations before drawing conclusions. Model output is not an official hazard map." },
];

/** Section jumps should take keyboard readers to the requested content too. */
function reveal(element: HTMLElement | null): void {
  if (!element) return;
  element.tabIndex = -1;
  element.scrollIntoView({ block: "start" });
  element.focus({ preventScroll: true });
}

/** Exact isometric projection of a synthetic cell mesh, not a simulation. */
function diagram(step: number): SVGSVGElement {
  const n = 14;
  const bed = (x: number, y: number) => 8 + 62 * Math.exp(-((x - 4) ** 2 + (y - 4) ** 2) / 19) + 12 * Math.sin(y / 3);
  const flow = (x: number, y: number) => step < 1 ? 0 : step < 4
    ? 17 * Math.exp(-((x - 4) ** 2 + (y - 4) ** 2) / 3)
    : 13 * Math.exp(-((x - 6) ** 2 / 5 + (y - 8) ** 2 / 20));
  const point = (x: number, y: number, z: number) => `${320 + (x - y) * 19},${100 + (x + y) * 10 - z}`;
  let mesh = "";
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
    const corners = [[x, y], [x + 1, y], [x + 1, y + 1], [x, y + 1]];
    const wet = flow(x + .5, y + .5) > 2;
    const fill = wet ? "var(--accent)" : bed(x, y) > 44 ? "var(--terrain-high)" : "var(--terrain-mid)";
    mesh += `<polygon points="${corners.map(([a, b]) => point(a!, b!, bed(a!, b!) + flow(a!, b!))).join(" ")}" fill="${fill}" stroke="${step === 3 || step === 4 ? "var(--control)" : fill}" stroke-width="0.7"/>`;
  }
  const edge = Array.from({ length: n + 1 }, (_, i) => point(n, i, bed(n, i))).join(" ");
  const other = Array.from({ length: n + 1 }, (_, i) => point(i, n, bed(i, n))).reverse().join(" ");
  return svg(`<svg viewBox="0 0 640 430" role="img" aria-label="Schematic isometric terrain ${step < 1 ? "before release" : step < 4 ? "with an initial pile" : "with a downslope flow footprint"}">
    <polygon points="${edge} ${point(n, n, -20)} ${point(n, 0, -20)}" fill="var(--terrain-low)"/>
    <polygon points="${other} ${point(0, n, -20)} ${point(n, n, -20)}" fill="var(--control)"/>
    ${mesh}
    <path d="M70 345v-50m0 50 48 25m-48-25-35 19" fill="none" stroke="var(--muted)" stroke-width="1.5"/>
    <g fill="var(--muted)" font-size="14"><text x="64" y="286">z</text><text x="122" y="378">x</text><text x="18" y="377">y</text></g>
    ${step === 4 ? '<path d="M335 225l-35 46m0-14v14h15" fill="none" stroke="var(--on-accent)" stroke-width="3"/>' : ""}
    <g fill="var(--fg)" font-size="15"><text x="365" y="65">${step === 0 ? "Bed elevation b" : step < 4 ? "Release depth h above bed b" : "Depth and momentum evolve"}</text></g>
    <path d="M355 70l-39 38" stroke="var(--muted)" fill="none"/>
  </svg>`);
}

export function mountVisualGuideline(root: HTMLElement): () => void {
  let disposed = false;
  let cleanup3d: (() => void) | undefined;
  const interactive = h("div", { class: "model3d-host" }, h("p", { role: "status", class: "guide-note" }, "Loading interactive 3D guide…"));
  let selected = 0;
  const visual = h("div", { class: "guide-visual" });
  const content = h("section", { class: "guide-explanation", "aria-live": "polite", "aria-atomic": "true" });
  const next = h("button", { class: "btn primary", type: "button", onclick: () => select(selected + 1) }, "Next stage");
  const previous = h("button", { class: "btn", type: "button", onclick: () => select(selected - 1) }, "Previous");
  const count = h("span", { class: "text-muted" });
  const buttons = steps.map((s, i) => h("button", { type: "button", class: "guide-step", onclick: () => select(i) }, h("span", { class: "guide-index" }, String(i + 1)), s.short));
  function select(index: number): void {
    selected = Math.max(0, Math.min(steps.length - 1, index));
    const s = steps[selected]!;
    buttons.forEach((b, i) => { b.setAttribute("aria-pressed", String(i === selected)); });
    visual.replaceChildren(diagram(selected));
    content.replaceChildren(h("h2", {}, s.title), h("p", { class: "guide-lead" }, s.lead), h("p", {}, s.body),
      h("dl", { class: "guide-io" }, h("dt", {}, "Input"), h("dd", {}, s.input), h("dt", {}, "Produces"), h("dd", {}, s.output)), h("p", { class: "guide-note" }, s.detail));
    if (selected === 4) content.append(h("p", { class: "guide-note" }, "Flux means material or momentum crossing a cell boundary. CFL limits the time step for stability; SSP-RK2 advances the state using two stages."));
    if (selected === 2 || selected === 4) content.append(h("button", { type: "button", class: "btn friction-jump", onclick: () => reveal(root.querySelector("#frictionTitle")) }, "Explore friction and calculation below"));
    previous.disabled = selected === 0;
    next.disabled = selected === steps.length - 1;
    count.textContent = `Stage ${selected + 1} of ${steps.length}`;
  }
  root.replaceChildren(h("div", { class: "guide-shell" },
    h("header", { class: "guide-header" }, h("div", {}, h("h1", {}, "From landscape to flow model"), h("p", {}, "Explore how titan3d turns terrain, a release and physical assumptions into a calculated flow.")), h("span", { class: "badge" }, "Experimental page")),
    h("nav", { class: "guide-contents", "aria-label": "On this page" }, ...[["pipelineTitle", "Data pipeline"], ["modelBasics", "Model essentials"], ["interactiveModelTitle", "Interactive 3D"], ["stageTitle", "Explore the stages"], ["rheologyTitle", "Coulomb vs Voellmy"], ["frictionTitle", "Friction and calculation"], ["resultChecks", "Read the results"]].map(([id, label]) => h("button", { type: "button", onclick: () => reveal(root.querySelector(`#${id}`)) }, label))),
    pipelineExplorer(),
    beginnerEssentials(),
    interactive,
    h("h2", { id: "stageTitle", class: "guide-section-title" }, "Explore the modelling stages"),
    h("p", { class: "guide-note" }, "The pipeline above follows eight data-processing stages. These six stages group the decisions and calculations you make when building a scenario."),
    h("nav", { class: "guide-steps", "aria-label": "Modelling stages" }, buttons),
    h("div", { class: "guide-body" }, h("figure", {}, visual, h("figcaption", {}, "Isometric schematic · synthetic terrain · geometry and depth are illustrative, not to scale. Blue marks material; grey marks the bed. This diagram does not run the solver.")), content),
    h("footer", { class: "guide-footer" }, h("a", { href: "#/setup" }, "Build a scenario in Setup"), h("div", { class: "guide-controls" }, count, previous, next)),
    rheologyComparison(),
    frictionExplorer(),
    h("section", { class: "guide-learning", "aria-labelledby": "resultChecks" }, h("h2", { id: "resultChecks" }, "Before you interpret a result"),
      h("ul", {}, h("li", {}, h("strong", {}, "Check the released volume. "), "Account for material remaining in the domain and material leaving through its edges. A visually plausible flow still needs a mass-balance check."),
        h("li", {}, h("strong", {}, "Compare resolution and assumptions. "), "Repeat with a different cell spacing or friction choice. Changes show sensitivity; they do not establish which scenario matches reality."),
        h("li", {}, h("strong", {}, "Read the time and field. "), "A maximum-depth map combines peaks reached at different times. It is different from a single playback frame."),
        h("li", {}, h("strong", {}, "Keep the scenario with its results. "), "Retain the DEM reference, configuration and run provenance. Model output is not an official hazard map.")),
      h("a", { class: "btn primary", href: "#/setup" }, "Build a scenario in Setup")),
  ));
  select(0);
  void import("./interactive-model").then(({ mountInteractiveModel }) => {
    if (!disposed) { interactive.replaceChildren(); cleanup3d = mountInteractiveModel(interactive); }
  }).catch(() => {
    if (!disposed) interactive.replaceChildren(h("p", { role: "alert", class: "guide-note" }, "The interactive guide could not load. Reload to retry, or use the visual stages below."));
  });
  return () => { disposed = true; cleanup3d?.(); root.replaceChildren(); };
}

function rheologyComparison(): HTMLElement {
  const speed = h("input", { id: "rheologySpeed", type: "range", min: 0, max: 30, step: 1, value: 10 });
  const speedValue = h("output", { for: "rheologySpeed" });
  const chart = h("div", { class: "rheology-chart" });
  const numbers = h("div", { class: "rheology-readout", "aria-live": "polite" });
  // Isolate speed dependence using matched constant friction and a flat bed.
  const mu = Math.tan(24 * Math.PI / 180), depth = 2, xi = 120;
  const basal = 9.81 * mu;
  const extra = (v: number) => 9.81 * v * v / (xi * depth);
  const px = (v: number) => 70 + v / 30 * 470;
  const py = (a: number) => 310 - a / 45 * 250;
  function update(): void {
    const v = Number(speed.value), turbulent = extra(v), total = basal + turbulent;
    speedValue.textContent = `${v} m/s`;
    const curve = Array.from({ length: 61 }, (_, i) => `${i ? "L" : "M"}${px(i / 2)},${py(basal + extra(i / 2))}`).join(" ");
    chart.replaceChildren(svg(`<svg viewBox="0 0 600 390" role="img" aria-label="Resistance acceleration versus speed: Coulomb is constant at ${basal.toFixed(2)} metres per second squared; Voellmy rises with speed squared. At ${v} metres per second Voellmy is ${total.toFixed(2)} metres per second squared.">
      <g stroke="var(--line)" fill="none">${[0, 10, 20, 30, 40].map(a => `<path d="M70 ${py(a)}H540"/>`).join("")}</g>
      <path d="M70 50v260h470" fill="none" stroke="var(--muted)"/>
      <g fill="var(--muted)" font-size="15">${[0, 10, 20, 30, 40].map(a => `<text x="55" y="${py(a) + 5}" text-anchor="end">${a}</text>`).join("")}${[0, 10, 20, 30].map(s => `<text x="${px(s)}" y="335" text-anchor="middle">${s}</text>`).join("")}<text x="70" y="28">Resistance acceleration (m/s²)</text><text x="300" y="370" text-anchor="middle">Flow speed (m/s)</text></g>
      <path d="M70 ${py(basal)}H540" fill="none" stroke="var(--fg)" stroke-width="3" stroke-dasharray="8 5"/>
      <path d="${curve}" fill="none" stroke="var(--accent)" stroke-width="3"/>
      <path d="M${px(v)} 50V310" fill="none" stroke="var(--muted)" stroke-dasharray="3 4"/>
      <circle cx="${px(v)}" cy="${py(basal)}" r="5" fill="var(--fg)"/>
      <circle cx="${px(v)}" cy="${py(total)}" r="5" fill="var(--accent)"/>
    </svg>`));
    numbers.replaceChildren(h("dl", { class: "guide-io" }, h("dt", {}, "Coulomb"), h("dd", {}, `${basal.toFixed(2)} m/s²`), h("dt", {}, "Voellmy"), h("dd", {}, `${basal.toFixed(2)} + ${turbulent.toFixed(2)} = ${total.toFixed(2)} m/s²`)),
      h("p", { class: "guide-note" }, v === 0 ? "At zero speed the added Voellmy term is zero. The constant resistance sets a stopping threshold; it does not accelerate resting material backwards." : "The curves show the magnitude of resistance opposing motion. They do not show net acceleration: gravity and pressure also act in a full simulation."));
  }
  speed.addEventListener("input", update);
  update();
  return h("section", { class: "rheology-comparison guide-learning", "aria-labelledby": "rheologyTitle" }, h("h2", { id: "rheologyTitle" }, "Coulomb or Voellmy?"),
    h("p", {}, "Both laws resist motion at the bed. Coulomb uses a basal friction angle. Voellmy adds resistance that grows with the square of speed, so doubling speed quadruples that extra term."),
    h("div", { class: "rheology-layout" }, h("figure", {}, chart, h("figcaption", {}, "Dashed ink: Coulomb. Solid blue: Voellmy. The curves use the same constant friction to isolate the added speed-dependent term. Illustrative flat-bed calculation; not a simulated trajectory.")),
      h("div", { class: "rheology-controls" }, h("label", { for: "rheologySpeed" }, "Flow speed", speedValue), speed,
        h("p", { class: "guide-note" }, "Fixed example: depth h = 2 m, effective gravity = 9.81 m/s², Coulomb φ_bed = 24°, Voellmy μ = tan(24°) ≈ 0.445, ξ = 120 m/s²."), numbers)),
    h("div", { class: "rheology-table-wrap" }, h("table", { class: "rheology-table" }, h("caption", {}, "How the two basal resistance laws differ"),
      h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Property"), h("th", { scope: "col" }, "Coulomb"), h("th", { scope: "col" }, "Voellmy"))),
      h("tbody", {},
        ...[
          ["Parameters", "Basal angle φ_bed; friction coefficient = tan(φ_bed).", "Dimensionless friction coefficient μ and resistance parameter ξ (m/s²)."],
          ["Resistance / density", "h × g_eff × tan(φ_bed)", "h × g_eff × μ + g × speed² / ξ"],
          ["Acceleration magnitude", "g_eff × tan(φ_bed)", "g_eff × μ + g × speed² / (ξ × h), for wet cells"],
          ["Speed effect", "No explicit speed term; effective gravity can still change with speed when curvature is enabled.", "Extra resistance grows as speed². Higher ξ reduces that extra resistance; lower ξ increases it."],
          ["Depth effect", "At fixed effective gravity, resistance acceleration does not explicitly depend on depth.", "At the same speed, the extra resistance acceleration is stronger for shallower flow."],
          ["Internal friction", "With Savage–Hutter pressure, φ_int and φ_bed determine pressure coefficients.", "With Savage–Hutter pressure, φ_int and φ_bed still determine pressure coefficients; μ and ξ set basal drag."],
        ].map(([property, coulomb, voellmy]) => h("tr", {}, h("th", { scope: "row" }, property), h("td", {}, coulomb), h("td", {}, voellmy)))))),
    h("p", { class: "guide-note" }, "Changing the basal law changes the assumed resistance, not the terrain or release volume. Neither choice guarantees a realistic runout. Compare scenarios with observations and parameter sensitivity; these example values are not a recommendation."));
}

function beginnerEssentials(): HTMLElement {
  return h("section", { class: "guide-learning", "aria-labelledby": "modelBasics" }, h("h2", { id: "modelBasics" }, "Model essentials"),
    h("p", {}, "A scenario asks: if this amount of material is released here, on this terrain, with these material properties, where does it travel and how deep and fast is the flow?"),
    h("dl", { class: "guide-glossary" },
      h("dt", {}, "Terrain and release"), h("dd", {}, "The DEM is ground elevation. The pile or vent supplies the moving material. Raising the terrain does not add released volume."),
      h("dt", {}, "Depth-averaged state"), h("dd", {}, "Each cell stores material thickness h and two horizontal momentum fields hu and hv. The calculation represents bulk motion across the landscape; it does not track individual grains."),
      h("dt", {}, "Parameters and results"), h("dd", {}, "You choose sources, friction and grid spacing. The solver calculates depth and momentum through time. Depth, speed and runout are results of those choices."),
      h("dt", {}, "Two different clocks"), h("dd", {}, "The solver takes small stable time steps. Frames are saved at the output interval. A 1 s frame interval does not mean a 1 s solver time step.")),
    h("details", { class: "guide-example" }, h("summary", {}, "Follow one illustrative pile example"),
      h("p", {}, "A circular paraboloid pile with radius 50 m and peak height 10 m has an ideal volume of π × 50² × 10 / 2 ≈ 39,270 m³. On a 20 m grid, its depth is sampled into cells. With zero initial velocity, the momenta start at zero; terrain gradients, pressure and resistance determine the subsequent motion."),
      h("p", {}, "Choosing 60 s of simulated duration and saving every 1 s gives frames from t = 0 to t = 60 s. The solver usually takes many steps between those frames. These numbers illustrate the workflow; they are not a calibrated scenario or a predicted runout.")),
  );
}

const pipeline = [
  { name: "Terrain data", field: "GeoTIFF · elevation + CRS", description: "Upload a DEM or select built-in terrain. GeoTIFF elevations and coordinate metadata describe the ground surface.", input: "DEM tiles", transform: "Check coverage and CRS; stitch tiles where needed.", output: "Prepared DEM", source: "core/dem.py" },
  { name: "Scenario configuration", field: "Sources · physics · numerics", description: "The scenario combines a DEM reference, domain extent, piles or vents, material parameters and numerical settings. YAML provides a shareable configuration.", input: "Setup form or scenario YAML", transform: "Validate the scenario against the API schema.", output: "Validated scenario request", source: "api/schemas/scenario.py" },
  { name: "Computational grid", field: "b: bed elevation · dx: cell spacing", description: "The selected domain is represented in projected metres on a computational grid. b[j, i] is bed elevation in metres at row j (north–south) and column i (east–west). dx is cell spacing in metres. Local UTM is the projected coordinate system used to locate cells in metres.", input: "Prepared DEM + domain + cell spacing dx (m)", transform: "Build the local UTM grid and bed geometry.", output: "Bed elevation array and georeference", source: "core/grid.py · core/dem.py" },
  { name: "Initial state", field: "h: depth · hu, hv: momentum", description: "Pile geometry creates initial material depth h (m). u and v are the eastward and northward velocities (m/s); hu and hv are depth × velocity, the momentum fields per unit density (m²/s). Vent footprints and release schedules provide sources during the run.", input: "Grid + release configuration", transform: "Rasterise piles; prepare timed flux sources.", output: "Initial state and source schedule", source: "core/sources.py · core/scenario.py" },
  { name: "Solver loop", field: "Cell exchanges · forces · time update", description: "The solver repeatedly exchanges mass and momentum between cells, applies resistance and sources, and advances simulated time. A flux is material or momentum crossing a cell boundary. CFL limits the time-step size for stability; SSP-RK2 is the two-stage method used to advance the state. The uniform solver is the default; adaptive mesh refinement (AMR) is experimental.", input: "State + terrain + material + numerical settings", transform: "Choose stable Δt (time-step duration); reconstruct faces; calculate fluxes; advance the state.", output: "Updated states through simulated time", source: "core/solver.py · core/numerics.py · core/rheology.py" },
  { name: "Frames & statistics", field: "Time series · volume · runout", description: "The scenario runner saves states at the output interval and calculates frame statistics. Frame cadence is independent of the solver time step.", input: "Solver states + output interval", transform: "Save frames; measure depth, speed, area, runout and volume.", output: "Saved frames and statistical time series", source: "core/scenario.py · core/stats.py" },
  { name: "Playback", field: "Browser bundle · 3D / plan", description: "A playback bundle lets the browser display saved depth and speed fields over terrain. Viewer detail changes display resolution, not the numerical solution.", input: "Saved frames + terrain", transform: "Package playback data; render the selected frame and field.", output: "Interactive plan and 3D views", source: "core/export.py · frontend/src/scene/engine.ts" },
  { name: "GIS & provenance", field: "GeoTIFF · outlines · YAML · log", description: "Export maximum depth and speed fields and inundation outlines for GIS work. Keep the configuration and run provenance alongside the results for interpretation and reproduction.", input: "Maximum fields + georeference + run configuration", transform: "Write geospatial products and retain run metadata.", output: "GeoTIFF, GeoJSON/KML, scenario YAML and run log", source: "core/export.py" },
];

function pipelineExplorer(): HTMLElement {
  const detail = h("section", { class: "pipeline-detail", "aria-live": "polite", "aria-atomic": "true" });
  const list = h("div", { class: "pipeline-list", "aria-label": "Pipeline step descriptions" });
  const diagram = h("div", { class: "pipeline-diagram", role: "group", "aria-label": "Clickable data pipeline" });
  const positions = [[30, 35], [340, 35], [30, 180], [340, 180], [185, 325], [185, 470], [30, 615], [340, 615]];
  diagram.append(svg('<svg class="pipeline-lines" viewBox="0 0 620 750" aria-hidden="true"><defs><marker id="pipelineArrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0l10 5-10 5" fill="var(--muted)"/></marker></defs><g fill="none" stroke="var(--muted)" stroke-width="1.3" marker-end="url(#pipelineArrow)"><path d="M140 120v60"/><path d="M450 120v60"/><path d="M340 78H280V150H155v30"/><path d="M250 222h90"/><path d="M450 265v30H295v30"/><path d="M140 265v30H280v30"/><path d="M295 410v60"/><path d="M295 555v30H140v30"/><path d="M295 555v30h155v30"/></g></svg>'));
  const nodes = pipeline.map((s, i) => {
    const [x, y] = positions[i]!;
    return h("button", { type: "button", class: "pipeline-node", style: `--node-x:${x};--node-y:${y}`, onclick: () => choose(i, true), "aria-controls": "pipelineDetail" },
      h("span", { class: "pipeline-number" }, `${i + 1}`), h("strong", {}, s.name), h("span", {}, s.field));
  });
  const rows = pipeline.map((s, i) => h("button", { type: "button", class: "pipeline-row", onclick: () => choose(i, true), "aria-controls": "pipelineDetail" }, h("span", { class: "pipeline-number" }, `${i + 1}`), h("span", {}, h("strong", {}, s.name), h("span", {}, s.field))));
  function choose(index: number, reveal = false): void {
    nodes.forEach((node, i) => node.setAttribute("aria-pressed", String(i === index)));
    rows.forEach((row, i) => row.setAttribute("aria-pressed", String(i === index)));
    const s = pipeline[index]!;
    detail.replaceChildren(h("h3", {}, `${index + 1}. ${s.name}`), h("p", {}, s.description),
      h("dl", { class: "guide-io" }, h("dt", {}, "Receives"), h("dd", {}, s.input), h("dt", {}, "Operation"), h("dd", {}, s.transform), h("dt", {}, "Produces"), h("dd", {}, s.output)),
      h("details", { class: "pipeline-source" }, h("summary", {}, "Implementation reference"), h("code", {}, s.source)));
    if (reveal && matchMedia("(max-width: 900px)").matches) {
      detail.scrollIntoView({ block: "start" });
      detail.focus({ preventScroll: true });
    }
  }
  detail.id = "pipelineDetail";
  detail.tabIndex = -1;
  diagram.append(...nodes);
  list.append(...rows);
  choose(0);
  return h("section", { class: "pipeline-section", "aria-labelledby": "pipelineTitle" }, h("h2", { id: "pipelineTitle" }, "The data pipeline"),
    h("p", {}, "Follow the data from an elevation file to calculated states and usable results. Select a box or a description to inspect that step."),
    h("p", { class: "pipeline-mobile-hint" }, "Swipe the diagram sideways to see both inputs and output branches. The descriptions below offer the same steps."),
    h("div", { class: "pipeline-layout" }, h("figure", {}, diagram, h("figcaption", {}, "Boxes are processing stages; arrows show data dependencies. Configuration feeds terrain preparation, initialisation and solver settings. The branches represent inputs and outputs of one scenario, not separate simulations.")), h("aside", { class: "pipeline-sidebar", "aria-label": "Selected pipeline stage" }, detail, list)));
}

function frictionExplorer(): HTMLElement {
  const bed = h("input", { id: "guideBed", type: "range", min: 0, max: 45, step: 1, value: 24 });
  const internal = h("input", { id: "guideInternal", type: "range", min: 0, max: 50, step: 1, value: 34 });
  const bedValue = h("output", { for: "guideBed" });
  const internalValue = h("output", { for: "guideInternal" });
  const picture = h("div", { class: "friction-picture" });
  const values = h("div", { class: "friction-values", "aria-live": "polite" });
  const pressure = h("div", { class: "friction-pressure" });
  function update(): void {
    const delta = Number(bed.value), phi = Number(internal.value);
    const rad = Math.PI / 180;
    const mu = Math.tan(delta * rad);
    const ci = Math.cos(phi * rad) ** 2, cb = Math.cos(delta * rad) ** 2;
    const root = Math.sqrt(Math.max(1 - ci / cb, 0));
    const active = 2 * (1 - root) / ci - 1, passive = 2 * (1 + root) / ci - 1;
    // Flat bed, no curvature, h=2 m and speed=10 m/s: same stopping operation as apply_friction.
    const resistance = 2 * 9.81 * mu;
    const momentum = Math.max(20 - .1 * resistance, 0);
    bedValue.textContent = `${delta}°`;
    internalValue.textContent = `${phi}°`;
    const length = 30 + mu * 110;
    picture.replaceChildren(svg(`<svg viewBox="0 0 600 330" role="img" aria-label="Isometric material block: internal friction acts within the material; basal friction opposes motion at the bed contact">
      <polygon points="65,215 285,95 540,230 320,320" fill="var(--terrain-mid)"/>
      <polygon points="190,154 285,103 405,167 310,218" fill="var(--accent-weak)" stroke="var(--accent)"/>
      <polygon points="190,154 310,218 310,259 190,195" fill="var(--accent)"/>
      <polygon points="310,218 405,167 405,208 310,259" fill="var(--accent-weak)" stroke="var(--accent)"/>
      <path d="M215 151l45 24m-12-20 12 20-24-1 M370 170l-45-24m12 20-12-20 24 1" fill="none" stroke="var(--accent)" stroke-width="2"/>
      <path d="M320 266l${-length} ${-length * .53}m12 0-12 0 6 12" fill="none" stroke="var(--fg)" stroke-width="3"/>
      <path d="M412 154l62 33m-14-23 14 23-27-1" fill="none" stroke="var(--accent)" stroke-width="3"/>
      <g font-size="17" fill="var(--fg)"><text x="75" y="45">Within the material: φ_int = ${phi}°</text><text x="75" y="75">At the bed contact: φ_bed = ${delta}°</text><text x="422" y="133">Motion</text><text x="65" y="290">Basal resistance</text></g>
      <path d="M245 82l40 60M170 277l60-45" fill="none" stroke="var(--muted)"/>
    </svg>`));
    values.replaceChildren(h("h3", {}, "Basal friction: a stopping step"),
      h("p", {}, `μ_bed = tan(${delta}°) = ${mu.toFixed(3)}`),
      h("p", {}, `Resistance / density = h × g_eff × μ_bed = ${resistance.toFixed(3)} m²/s²`),
      h("p", {}, `New momentum magnitude = max(20 − 0.1 × ${resistance.toFixed(3)}, 0) = ${momentum.toFixed(3)} m²/s`),
      h("p", {}, `New speed = momentum / depth = ${(momentum / 2).toFixed(3)} m/s`));
    pressure.replaceChildren(h("h3", {}, "Internal friction: earth pressure"),
      h("p", { class: "guide-note" }, "k scales the horizontal pressure contribution to momentum exchange. r is an intermediate value calculated from the two friction angles. Spreading and converging describe whether neighbouring velocities move apart or come together."),
      h("p", {}, "r = √max(1 − cos²(φ_int) / cos²(φ_bed), 0)"),
      h("p", {}, "k_active = 2(1 − r) / cos²(φ_int) − 1"),
      h("p", {}, "k_passive = 2(1 + r) / cos²(φ_int) − 1"),
      h("dl", { class: "guide-io" }, h("dt", {}, "Spreading"), h("dd", {}, `k_active = ${active.toFixed(3)}`), h("dt", {}, "Converging"), h("dd", {}, `k_passive = ${passive.toFixed(3)}`)),
      h("p", { class: "guide-note" }, delta > phi ? "Here φ_bed exceeds φ_int. The implementation clamps the square-root argument to zero, so both coefficients coincide." : "The solver selects active pressure where horizontal velocity divergence is nonnegative, and passive pressure where it is negative."));
  }
  bed.addEventListener("input", update);
  internal.addEventListener("input", update);
  update();
  return h("section", { class: "friction-explorer", "aria-labelledby": "frictionTitle" },
    h("h2", { id: "frictionTitle" }, "Two friction angles, two roles"),
    h("p", { class: "guide-lead" }, "Change an angle to see where it acts and how the numbers change."),
    h("p", {}, "Basal friction resists sliding at the ground. Internal friction represents resistance within the bulk material and enters the Savage–Hutter earth-pressure coefficients. It is not a second basal drag term; a separate internal shear-friction term is not implemented."),
    h("div", { class: "friction-layout" }, h("div", {}, picture, h("p", { class: "guide-note" }, "Schematic geometry, not to scale. The resistance arrow length varies with tan(φ_bed); internal arrows show the location of internal stresses.")),
      h("div", { class: "friction-settings" },
        h("label", { for: "guideBed" }, "Basal friction φ_bed", bedValue), bed,
        h("label", { for: "guideInternal" }, "Internal friction φ_int", internalValue), internal,
        h("p", { class: "guide-note" }, "Illustrative Coulomb + Savage–Hutter values, initially 24° and 34°. These controls only change this explanation."),
        h("button", { class: "btn", type: "button", onclick: () => { bed.value = "24"; internal.value = "34"; update(); } }, "Reset angles"))),
    h("p", { class: "guide-note" }, "With hydrostatic earth pressure, k = 1 and φ_int does not change the closure. Voellmy basal resistance instead uses μ and ξ: resistance / density = h × g_eff × μ + g × speed² / ξ. With Savage–Hutter enabled, both angles still enter k."),
    h("h3", { class: "friction-cycle-title" }, "Where these values enter each time step"),
    h("p", { class: "guide-note" }, "A flux measures mass or momentum crossing a cell boundary. The CFL condition limits the time step for stability. SSP-RK2 combines two stages to update the flow state."),
    h("ol", { class: "friction-cycle" },
      h("li", {}, h("strong", {}, "Choose pressure and time step. "), "Derive velocity from momentum / depth; select k from spreading or convergence. The CFL condition limits Δt using velocity and wave speed, including √(k × g × h)."),
      h("li", {}, h("strong", {}, "Exchange mass and momentum. "), "Reconstruct face states and calculate fluxes. The momentum flux contains a pressure contribution ½ × k × g × h²; bed gradients provide the gravity contribution."),
      h("li", {}, h("strong", {}, "Advance and apply resistance. "), "SSP-RK2 combines two stages. The basal stopping operation reduces the momentum magnitude without reversing its direction; dry cells have zero momentum."),
      h("li", {}, h("strong", {}, "Repeat and save. "), "Update source release and time, check the next stable time step, and write frames at the requested output interval.")),
    h("details", { class: "guide-example friction-formulas" },
      h("summary", {}, "Show the friction formulas and worked calculation"),
      h("p", { class: "guide-note" }, "The angle controls above update these calculations, even when this section is closed."),
      h("div", { class: "friction-calculations" }, h("div", {}, h("p", { class: "guide-note" }, "Worked example: flat bed, curvature off, depth h = 2 m, incoming speed = 10 m/s, Δt = 0.1 s, g_eff = 9.81 m/s². Δt is the time-step duration; g_eff is effective gravity normal to the bed, which sets the contact loading. Only the friction operation is shown."), values), pressure)),
  );
}
