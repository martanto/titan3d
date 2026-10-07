import { api, type Scenario } from "../api/client";
import { store } from "../app/store";
import { h } from "./dom";

const REV = "b86f17412fe4dd180c2125eabd85bf6554328a79";
const ROOT = `https://github.com/TITAN2D/titan2d/blob/${REV}/share/titan2d_examples`;
const DEM = `https://raw.githubusercontent.com/TITAN2D/titan2d/${REV}/share/titan2d_examples/dem/colimafinemini.geotiff`;

/** Volume-preserving adaptation of the upstream cylindrical release. */
function colima(demId: string, voellmy: boolean): Scenario {
  return {
    schema_version: 1, name: `Colima · ${voellmy ? "Voellmy" : "Coulomb"} example`, dem_id: demId,
    piles: [{ lon: -103.61857604070536, lat: 19.511146722180904, height: 60, radius: 55 }],
    flux_sources: [],
    domain: { center_lon: null, center_lat: null, west_km: 3.4, east_km: 1, south_km: 3.4, north_km: 1 },
    material: { rheology: voellmy ? "voellmy" : "coulomb", phi_bed_deg: 27, phi_int_deg: 37,
      mu: 0.35, xi: 120, earth_pressure: "savage-hutter", curvature: true },
    numerics: { dx: 10, cfl: 0.4, backend: "numba", precision: "float64", h_dry: 0.001,
      amr: false, amr_gradient: 0.05, amr_buffer: 2, amr_regrid_every: 4, amr_coarsen_delay: 3 },
    t_end: 300, output_every: 1,
  };
}

export function mountExamples(root: HTMLElement): () => void {
  let disposed = false;
  const status = h("p", { class: "note example-status", id: "colimaStatus", role: "status", "aria-live": "polite", "aria-atomic": "true" }, "Choose the Colima DEM, then open the example in Setup.");
  const file = h("input", { type: "file", accept: ".tif,.tiff,.geotiff", id: "colimaFile", "aria-describedby": "colimaStatus" });
  const model = h("select", { id: "colimaModel" }, h("option", { value: "coulomb" }, "Coulomb"), h("option", { value: "voellmy" }, "Voellmy–Salm"));
  const open = h("button", { type: "button", class: "btn primary" }, "Upload DEM and open in Setup");
  open.addEventListener("click", async () => {
    const selected = file.files?.[0];
    if (!selected) { status.dataset.state = "error"; file.setAttribute("aria-invalid", "true"); status.textContent = "Select the downloaded colimafinemini GeoTIFF first."; file.focus(); return; }
    const voellmy = model.value === "voellmy";
    status.dataset.state = "loading";
    file.removeAttribute("aria-invalid");
    open.disabled = true;
    file.disabled = true;
    model.disabled = true;
    open.textContent = "Preparing example…";
    try {
      status.textContent = "Uploading Colima terrain…";
      let dem = await api.uploadDem([selected], "Colima · Titan2D example", (loaded, total) => {
        if (!disposed) status.textContent = `Uploading Colima terrain… ${Math.round(100 * loaded / total)} %`;
      });
      while (!disposed && dem.status === "processing") {
        status.textContent = "Preparing Colima terrain…";
        await new Promise((resolve) => setTimeout(resolve, 1000));
        if (!disposed) dem = await api.getDem(dem.id);
      }
      if (disposed) return;
      if (dem.status !== "ready") throw new Error(dem.error || "DEM preparation failed. Check the GeoTIFF and retry.");
      // Guard against an unrelated upload being assigned the Colima release.
      const b = dem.info?.bounds_lonlat;
      if (!b || b[0] > -103.618576 || b[2] < -103.618576 || b[1] > 19.511147 || b[3] < 19.511147)
        throw new Error("This DEM does not cover the Colima release. Download the linked upstream GeoTIFF and retry.");
      store.scenario = colima(dem.id, voellmy);
      store.selected = 0;
      store.saveDraft();
      location.hash = "#/setup";
    } catch (error) {
      if (!disposed) { status.dataset.state = "error"; status.textContent = `Could not load the example: ${(error as Error).message}`; }
    } finally {
      if (!disposed) { open.disabled = false; file.disabled = false; model.disabled = false; open.textContent = "Upload DEM and open in Setup"; }
    }
  });
  file.addEventListener("change", () => {
    file.removeAttribute("aria-invalid");
    delete status.dataset.state;
    status.textContent = file.files?.length ? "Terrain selected. Choose a material model, then open in Setup." : "Choose the Colima DEM, then open the example in Setup.";
  });
  const link = (text: string, href: string) => h("a", { href, target: "_blank", rel: "noopener" }, text);
  const rows = [
    ["Terrain", "colimafinemini · 900 × 900 cells · 5 m pixels"],
    ["Coordinates", "WGS 84 / UTM zone 13N (EPSG:32613)"],
    ["Release centre", "644 956 m E, 2 157 970 m N"],
    ["Upstream release", "Cylinder · 30 m high · 55 m radius · initially at rest"],
    ["Coulomb friction", "Basal 27° · internal 37°"],
    ["Voellmy–Salm", "μ = 0.35 · ξ = 120 m/s²"],
    ["Titan3D grid / time", "10 m · 300 s · output every 1 s"],
  ];
  root.replaceChildren(
    h("div", { class: "sys-head" }, h("div", {}, h("h1", {}, "Examples"), h("p", { class: "text-muted" }, "Explore a published Titan2D setup using real terrain and traceable parameters."))),
    h("article", { class: "colima-example" },
      h("header", { class: "example-intro" }, h("h2", {}, "Colima volcano"),
      h("p", {}, "Start with the Colima fine mini dataset from the Titan2D repository. Download its terrain, choose a material model, and review the adapted scenario before running."),
      ),
      h("section", { class: "example-load", "aria-labelledby": "colimaLoadHeading" }, h("h3", { id: "colimaLoadHeading" }, "Load the example"),
        h("p", { class: "note" }, "Save the linked GeoTIFF locally, then select it below."),
        h("a", { class: "btn example-download", href: DEM, target: "_blank", rel: "noopener" }, "Download upstream GeoTIFF"),
        h("div", { class: "field" }, h("label", { for: "colimaFile" }, "Colima GeoTIFF"), file),
        h("div", { class: "field" }, h("label", { for: "colimaModel" }, "Material model"), model),
        h("p", { class: "example-consequence" }, "This creates a new terrain entry and replaces your current Setup draft. No simulation starts automatically."), open, status),
      h("div", { class: "example-reference" },
      h("section", { class: "section" }, h("h3", {}, "Terrain and parameters"),
        h("dl", { class: "example-parameters" }, rows.map(([label, value]) => h("div", {}, h("dt", {}, label), h("dd", {}, value))))),
      h("section", { class: "section" }, h("h3", {}, "How this example is adapted"),
        h("p", {}, "Titan3D uses a paraboloid pile. A 60 m peak and 55 m radius preserve the upstream cylinder’s volume (about 285 100 m³), but change its thickness profile. The release centre is converted from UTM to longitude and latitude."),
        h("p", {}, "The 4.4 × 4.4 km domain stays inside the DEM. Titan3D uses a fixed 10 m grid and its second-order solver; upstream uses adaptive mesh refinement and first-order numerics. The 300 s duration is a Titan3D choice: upstream stops at an iteration limit. Voellmy’s upstream output interval is 100 s; this adaptation uses 1 s. Curvature and Savage–Hutter pressure follow Titan3D settings. Results are an adaptation, not a numerical reproduction or an official hazard map.")),
      h("section", { class: "section example-sources" }, h("h3", {}, "Upstream sources"),
        h("div", {}, link("Titan2D on GitHub", "https://github.com/TITAN2D/titan2d/"), link("View Coulomb input.py", `${ROOT}/colimafinemini/Coulomb_GeoTIFF/input.py`), link("View Voellmy input.py", `${ROOT}/colimafinemini/Voellmy_Salm/input.py`)),
        h("p", { class: "note" }, `Source: TITAN2D/titan2d, revision ${REV.slice(0, 12)}. Terrain remains a local dataset.`)))),
  );
  return () => { disposed = true; };
}
