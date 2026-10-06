// Decoding of the quantised, zlib-compressed bundles produced by
// backend/src/titan3d/core/export.py (viewer_bundle / terrain_preview).

export interface SourceMeta {
  kind: "pile" | "flux";
  x: number;
  y: number;
  lon: number;
  lat: number;
  radius: number;
  height?: number;
  influx?: number;
  start?: number;
  duration?: number;
}

export interface FrameStat {
  t: number;
  steps: number;
  vol: number;
  vol_out: number;
  released_m3: number;
  hmax: number;
  umax: number;
  area: number;
  runout: number;
}

export interface GridMeta {
  nx: number;
  ny: number;
  dx: number;
  x0: number;
  y0: number;
  crs: string | null;
  zmin: number;
  zmax: number;
}

export interface ResultMeta extends GridMeta {
  title: string;
  dem: string;
  rheology: string;
  phi_bed: number;
  phi_int: number;
  mu: number;
  xi: number;
  pressure: string;
  curvature: boolean;
  every: number;
  t_end: number;
  volume_m3: number;
  sources: SourceMeta[];
  ref: { x: number; y: number };
  grid_dx: number;
  grid_shape: [number, number];
  steps: number;
  wall_time_s: number;
  stride: number;
  nframes: number;
  hmax: number;
  vmax: number;
  provenance: Record<string, unknown>;
}

export interface PreviewMeta extends GridMeta {
  dem_id: string;
  name: string;
  bounds_lonlat: [number, number, number, number] | null;
  grid_bounds_lonlat: [number, number, number, number];
  res_m: number | null;
  summit: { lon: number; lat: number; z: number; x: number; y: number } | null;
}

/** Terrain heights in metres, row-major [j][i], j = 0 is the south edge. */
export interface Terrain {
  meta: GridMeta;
  bed: Float32Array;
}

export interface Preview extends Terrain {
  meta: PreviewMeta;
  valid: Uint8Array; // 1 where the DEM has data
}

export interface Result extends Terrain {
  meta: ResultMeta;
  stats: FrameStat[];
  depthQ: Uint8Array; // nframes × N, sqrt-quantised depth
  speedQ: Uint8Array; // nframes × N, linear speed
  hmaxQ: Uint8Array; // N, sqrt-quantised max depth over every step
}

function b64(s: string): Uint8Array {
  const bin = atob(s);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/** zlib (RFC 1950) inflate with the browser's native DecompressionStream. */
async function inflate(s: string): Promise<Uint8Array> {
  const stream = new Blob([b64(s) as BlobPart]).stream().pipeThrough(new DecompressionStream("deflate"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

async function decodeTerrain(s: string, meta: GridMeta): Promise<Float32Array> {
  const raw = await inflate(s);
  const q = new Uint16Array(raw.buffer, raw.byteOffset, raw.byteLength / 2);
  const bed = new Float32Array(q.length);
  const span = meta.zmax - meta.zmin;
  for (let k = 0; k < q.length; k++) bed[k] = meta.zmin + (q[k] / 65535) * span;
  return bed;
}

export async function fetchJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url, { signal });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

interface RawPreview {
  meta: PreviewMeta;
  terrain: string;
  valid: string;
}

export async function loadPreview(url: string, signal?: AbortSignal): Promise<Preview> {
  const raw = await fetchJson<RawPreview>(url, signal);
  const bed = await decodeTerrain(raw.terrain, raw.meta);
  const bits = await inflate(raw.valid);
  const n = raw.meta.nx * raw.meta.ny;
  const valid = new Uint8Array(n);
  for (let k = 0; k < n; k++) valid[k] = (bits[k >> 3] >> (7 - (k & 7))) & 1;
  return { meta: raw.meta, bed, valid };
}

interface RawResult {
  meta: ResultMeta;
  stats: FrameStat[];
  terrain: string;
  depth: string;
  speed: string;
  hmaxField: string;
}

export async function loadResult(url: string, signal?: AbortSignal): Promise<Result> {
  const raw = await fetchJson<RawResult>(url, signal);
  const [bed, depthQ, speedQ, hmaxQ] = await Promise.all([
    decodeTerrain(raw.terrain, raw.meta),
    inflate(raw.depth),
    inflate(raw.speed),
    inflate(raw.hmaxField),
  ]);
  return { meta: raw.meta, stats: raw.stats, bed, depthQ, speedQ, hmaxQ };
}

/** Lookup tables from quantised bytes to physical values. */
export function depthTable(hmax: number): Float32Array {
  const t = new Float32Array(256);
  for (let q = 0; q < 256; q++) t[q] = (q / 255) ** 2 * hmax;
  return t;
}

export function speedTable(vmax: number): Float32Array {
  const t = new Float32Array(256);
  for (let q = 0; q < 256; q++) t[q] = (q / 255) * vmax;
  return t;
}
