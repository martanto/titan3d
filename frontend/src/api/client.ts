// Typed client for the titan3d API. Types come from the generated
// `schema.d.ts` (`npm run gen:api` reads backend/openapi.json).
import type { components } from "./schema";

type S = components["schemas"];
export type Dem = S["DemOut"];
export type Scenario = S["ScenarioRequest"];
export type Pile = S["PileIn"];
export type Material = S["MaterialIn"];
export type FluxSource = S["FluxSourceIn"];
export type Simulation = S["SimulationOut"];
export type SimulationCreated = S["SimulationCreated"];
export type FrameStats = S["FrameStatsOut"];
export type Estimate = S["ScenarioEstimate"];
export type ImportResult = S["ScenarioImportOut"];
export type JobStatus = Simulation["status"];
export type Artifact =
  | "max_depth.tif"
  | "max_speed.tif"
  | "inundation.geojson"
  | "inundation.kml"
  | "scenario.yaml"
  | "summary.json"
  | "run.log";

const BASE = "/api";

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((d: { loc?: unknown[]; msg?: string }) =>
          `${(d.loc ?? []).filter((p) => p !== "body").join(".")}: ${d.msg ?? ""}`,
        )
        .join("; ");
    }
  } catch {
    /* not JSON */
  }
  return `${res.status} ${res.statusText}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, init);
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res));
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  health: () => request<{ status: string; version: string; commit: string }>("/health"),

  listDems: () => request<Dem[]>("/dems"),
  getDem: (id: string) => request<Dem>(`/dems/${encodeURIComponent(id)}`),
  deleteDem: (id: string) =>
    request<void>(`/dems/${encodeURIComponent(id)}`, { method: "DELETE" }),
  demPreviewUrl: (id: string, maxCells = 512) =>
    `${BASE}/dems/${encodeURIComponent(id)}/preview?max_cells=${maxCells}`,

  /** Multi-file upload with byte-level progress (fetch has no upload progress). */
  uploadDem(
    files: File[],
    name: string,
    onProgress: (loaded: number, total: number) => void,
  ): Promise<Dem> {
    return new Promise((resolve, reject) => {
      const form = new FormData();
      for (const f of files) form.append("files", f, f.name);
      form.append("name", name);
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${BASE}/dems`);
      xhr.responseType = "json";
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded, e.total);
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response as Dem);
        else {
          const detail = (xhr.response as { detail?: string } | null)?.detail;
          reject(new ApiError(xhr.status, detail ?? `Upload failed (${xhr.status})`));
        }
      };
      xhr.onerror = () => reject(new ApiError(0, "Network error during upload"));
      xhr.send(form);
    });
  },

  defaultScenario: () => request<Scenario>("/scenarios/default"),
  presets: () => request<Record<string, number>>("/scenarios/presets"),
  estimate: (s: Scenario) => request<Estimate>("/scenarios/estimate", json(s)),
  async exportYaml(s: Scenario): Promise<Blob> {
    const res = await fetch(`${BASE}/scenarios/export`, json(s));
    if (!res.ok) throw new ApiError(res.status, await errorMessage(res));
    return res.blob();
  },
  importYaml(file: File): Promise<ImportResult> {
    const form = new FormData();
    form.append("file", file, file.name);
    return request<ImportResult>("/scenarios/import", { method: "POST", body: form });
  },

  createSimulation: (s: Scenario) => request<SimulationCreated>("/simulations", json(s)),
  listSimulations: () => request<Simulation[]>("/simulations"),
  getSimulation: (id: string) => request<Simulation>(`/simulations/${id}`),
  frames: (id: string) => request<FrameStats[]>(`/simulations/${id}/frames`),
  cancel: (id: string) => request<Simulation>(`/simulations/${id}/cancel`, { method: "POST" }),
  duplicate: (id: string) =>
    request<SimulationCreated>(`/simulations/${id}/duplicate`, { method: "POST" }),
  deleteSimulation: (id: string) =>
    request<void>(`/simulations/${id}`, { method: "DELETE" }),
  resultUrl: (id: string, maxCells = 640) => `${BASE}/simulations/${id}/result?max_cells=${maxCells}`,
  fileUrl: (id: string, name: Artifact) => `${BASE}/simulations/${id}/files/${name}`,
};
