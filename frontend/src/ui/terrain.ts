// Shows a DEM preview with a scenario's sources and domain on the stage.
import { api, type Scenario } from "../api/client";
import { store } from "../app/store";
import { loadPreview, type Preview } from "../data/bundle";
import { toLonLat, toUtm, utmCrsFor } from "../geo/utm";
import type { DomainBox, Marker, PickInfo, SurfaceKind } from "../scene/engine";
import { lonLat, num } from "./format";
import type { ProbeRows, Stage } from "./stage";

export async function ensurePreview(stage: Stage, demId: string, signal?: AbortSignal): Promise<Preview> {
  if (store.preview && store.previewFor === demId) {
    if (stage.scene.gridMeta !== store.preview.meta) stage.scene.setTerrain(store.preview, store.preview.valid);
    return store.preview;
  }
  stage.showMessage("loading", "Loading terrain…", "Reprojecting the DEM preview to its local UTM zone.");
  const p = await loadPreview(api.demPreviewUrl(demId, 1024), signal);
  store.preview = p;
  store.previewFor = demId;
  stage.scene.setTerrain(p, p.valid);
  stage.hideMessage();
  return p;
}

export function anchorOf(s: Scenario): [number, number] {
  const d: Partial<NonNullable<Scenario["domain"]>> = s.domain ?? {};
  if (d.center_lon != null && d.center_lat != null) return [d.center_lon, d.center_lat];
  const src = s.piles?.[0] ?? s.flux_sources?.[0];
  return src ? [src.lon ?? 0, src.lat ?? 0] : [0, 0];
}

/** Domain rectangle in the preview CRS (the run uses the anchor's UTM zone). */
export function domainBox(s: Scenario, crs: string): DomainBox {
  const [lon, lat] = anchorOf(s);
  const runCrs = utmCrsFor(lon, lat);
  const d: Partial<NonNullable<Scenario["domain"]>> = s.domain ?? {};
  const [x, y] = toUtm(runCrs, lon, lat);
  const corners = [
    [x - (d.west_km ?? 6) * 1000, y - (d.south_km ?? 14) * 1000],
    [x + (d.east_km ?? 16) * 1000, y + (d.north_km ?? 6) * 1000],
  ];
  if (runCrs === crs) return { west: corners[0][0], south: corners[0][1], east: corners[1][0], north: corners[1][1] };
  const [sw, ne] = corners.map(([cx, cy]) => toUtm(crs, ...toLonLat(runCrs, cx, cy)));
  return { west: sw[0], south: sw[1], east: ne[0], north: ne[1] };
}

export function markersOf(s: Scenario, crs: string, selected: number): Marker[] {
  const out: Marker[] = [];
  (s.piles ?? []).forEach((p, i) => {
    const [x, y] = toUtm(crs, p.lon ?? 0, p.lat ?? 0);
    out.push({ kind: "pile", x, y, radius: p.radius ?? 300, selected: i === selected });
  });
  const np = s.piles?.length ?? 0;
  (s.flux_sources ?? []).forEach((f, i) => {
    const [x, y] = toUtm(crs, f.lon ?? 0, f.lat ?? 0);
    out.push({ kind: "flux", x, y, radius: f.radius ?? 100, selected: np + i === selected });
  });
  return out;
}

export function showScenario(stage: Stage, s: Scenario, preview: Preview, selected = -1): void {
  const crs = preview.meta.crs ?? "EPSG:32749";
  stage.scene.setMarkers(markersOf(s, crs, selected), domainBox(s, crs));
}

export function terrainProbe(preview: Preview): (p: PickInfo) => ProbeRows | null {
  return (p) => {
    const crs = preview.meta.crs;
    if (!crs || !preview.valid[p.k]) return null;
    const [lon, lat] = toLonLat(crs, p.x, p.y);
    return [
      ["Easting", `${num(p.x)} m`],
      ["Northing", `${num(p.y)} m`],
      ["Position", lonLat(lon, lat)],
      ["Elevation", `${num(p.z)} m a.s.l.`],
    ];
  };
}

export function surfaceNote(kind: SurfaceKind): string {
  return kind === "natural"
    ? "natural-colour relief synthesised from the DEM (elevation, slope and curvature; not imagery), lit from the north-west"
    : "greyscale hillshade lit from the north-west";
}

export function terrainCaption(preview: Preview, kind: SurfaceKind): string {
  const m = preview.meta;
  const res = m.res_m ? `${num(m.res_m, 1)} m source resolution, ` : "";
  return `Terrain: ${m.name} (${m.crs}), ${res}preview at ${num(m.dx)} m. Elevation ${num(m.zmin)}–${num(m.zmax)} m a.s.l.; ${surfaceNote(kind)}, with contours.`;
}
