// Running view: honest, specific progress for long simulations.
// Phases are inferred from the job record: queued → domain → kernels → solving → outputs.
import { api, type FrameStats, type Simulation } from "../api/client";
import { store } from "../app/store";
import { TimeChart } from "./chart";
import { h } from "./dom";
import { dateTime, duration, num, sci } from "./format";
import type { Stage } from "./stage";
import { domainBox, ensurePreview, showScenario, terrainCaption, terrainProbe } from "./terrain";

type Phase = "queued" | "domain" | "kernels" | "solving" | "outputs";

const PHASES: [Phase, string][] = [
  ["queued", "Waiting in the queue"],
  ["domain", "Cutting and reprojecting the domain"],
  ["kernels", "Compiling solver kernels"],
  ["solving", "Solving the flow equations"],
  ["outputs", "Writing GeoTIFFs, outlines and playback"],
];

function phaseOf(j: Simulation): Phase {
  if (j.status === "queued") return "queued";
  if (!j.grid) return "domain";
  if (j.progress.steps === 0) return "kernels";
  if (j.progress.sim_t >= j.progress.t_end - 1e-6) return "outputs";
  return "solving";
}

export function mountRunning(stage: Stage, panel: HTMLElement, first: Simulation, onFinished: (j: Simulation) => void): () => void {
  let disposed = false;
  let job = first;
  let frames: FrameStats[] = [];
  let lastFramesAt = 0;
  const runout = new TimeChart({ title: "Runout", unit: "m" });
  const speed = new TimeChart({ title: "Maximum speed", unit: "m/s", digits: 1 });
  const body = h("div", { class: "panel-body" });

  const cancel = h(
    "button",
    {
      type: "button",
      class: "btn danger",
      onclick: async () => {
        cancel.setAttribute("disabled", "");
        cancel.textContent = "Stopping…";
        job = await api.cancel(job.id);
        render();
      },
    },
    "Cancel run",
  );

  function render(): void {
    const p = job.progress;
    const ph = phaseOf(job);
    const pi = PHASES.findIndex(([k]) => k === ph);
    const active = job.status === "running";
    const indeterminate = ph === "queued" || ph === "domain" || ph === "kernels" || ph === "outputs";
    const pct = Math.round(p.fraction * 100);
    const r = (k: string, v: string, n?: string) =>
      h("div", { class: "readout" }, h("span", { class: "k" }, k), h("span", { class: "v" }, v), n ? h("span", { class: "n" }, n) : null);
    body.replaceChildren(
      h(
        "section",
        { class: "section", "aria-labelledby": "prog-h" },
        h("h2", { id: "prog-h", class: "sr-only" }, "Progress"),
        h(
          "div",
          { class: "progress" },
          h(
            "div",
            { class: "progress-clock" },
            `t = ${num(p.sim_t, 1)}`,
            h("span", { class: "unit" }, `of ${num(p.t_end)} s`),
          ),
          h(
            "div",
            {
              class: `progress-track${active ? " active" : ""}${active && indeterminate ? " indeterminate" : ""}`,
              role: "progressbar",
              "aria-label": "Simulated time",
              "aria-valuemin": 0,
              "aria-valuemax": 100,
              "aria-valuenow": pct,
              "aria-valuetext": `${num(p.sim_t, 1)} of ${num(p.t_end)} seconds simulated`,
            },
            h("div", { class: "progress-fill", style: `--p:${pct / 100}` }),
          ),
          h(
            "div",
            { class: "readouts", style: "grid-template-columns: repeat(3, 1fr)" },
            r("Complete", `${pct} %`),
            r("Elapsed", duration(p.elapsed_s)),
            r("Remaining", job.status === "running" && ph === "solving" ? `≈ ${duration(p.eta_s)}` : "—", "estimate"),
          ),
        ),
        h(
          "ol",
          { class: "phases", "aria-label": "Run phases" },
          PHASES.map(([k, label], i) =>
            h(
              "li",
              { class: i < pi ? "done" : i === pi && active ? "current" : i === pi ? "done" : "", "aria-current": i === pi ? "step" : null },
              label,
              k === "solving" && p.steps ? h("span", { class: "muted" }, ` · ${num(p.steps)} steps`) : null,
            ),
          ),
        ),
      ),
      h(
        "section",
        { class: "section" },
        h("h2", {}, "Flow so far"),
        h(
          "div",
          { class: "readouts" },
          r("Runout", p.runout != null ? `${num(p.runout)} m` : "—"),
          r("Maximum speed", p.umax != null ? `${num(p.umax, 1)} m/s` : "—"),
          r("Maximum depth", p.hmax != null ? `${num(p.hmax, 1)} m` : "—"),
          r("Inundated area", p.area != null ? `${num(p.area, 2)} km²` : "—", "h > 0.1 m"),
          r("Mass in domain", p.vol_in_domain != null ? `${num(p.vol_in_domain * 100, 2)} %` : "—", p.vol_out ? `${num(p.vol_out * 100, 2)} % left the domain` : "of released volume"),
          r("Released", p.released_m3 != null ? `${sci(p.released_m3)} m³` : "—"),
        ),
        runout.root,
        speed.root,
      ),
      h(
        "section",
        { class: "section" },
        h("h2", {}, "Run"),
        h(
          "dl",
          { class: "params" },
          h("dt", {}, "Submitted"),
          h("dd", {}, dateTime(job.created_at)),
          h("dt", {}, "Grid"),
          h("dd", {}, job.grid ? `${num(job.grid.nx)} × ${num(job.grid.ny)} @ ${num(job.grid.dx)} m (${job.grid.crs})` : "being prepared"),
          h("dt", {}, "Run id"),
          h("dd", {}, job.id),
        ),
        h("p", { class: "note" }, "You can close this page or start another setup: the run continues on the server and appears under Runs."),
        job.status === "running" || job.status === "queued" ? cancel : null,
      ),
    );
    const t = frames.map((f) => f.t);
    runout.setData(t, frames.map((f) => f.runout), p.t_end);
    speed.setData(t, frames.map((f) => f.umax), p.t_end);
  }

  panel.replaceChildren(
    h(
      "div",
      { class: "panel-head" },
      h("h1", {}, first.name),
      h("span", { class: "sub" }, h("span", { class: `status ${first.status}` }, first.status === "queued" ? "queued" : "running"), " Simulation in progress"),
    ),
    body,
  );
  render();

  // stage: terrain with the scenario's release and domain
  stage.setView("plan");
  stage.setColourbar(null);
  stage.setBadges([{ text: "Simulation running" }]);
  stage.onPick(undefined);
  ensurePreview(stage, first.dem_id)
    .then((p) => {
      if (disposed) return;
      showScenario(stage, first.scenario, p);
      stage.scene.focus(domainBox(first.scenario, p.meta.crs ?? "EPSG:32749"));
      stage.setProbe(terrainProbe(p));
      stage.setTerrainLabel(`Terrain: ${p.meta.name}`);
      stage.setCaption(`${terrainCaption(p, stage.scene.surface)} Release and computational domain of run ${first.id}; results appear here when the run completes.`, "Running.");
    })
    .catch(() => undefined);

  const poll = async () => {
    if (disposed) return;
    try {
      job = await api.getSimulation(job.id);
      if (Date.now() - lastFramesAt > 3000 || job.status !== "running") {
        frames = await api.frames(job.id);
        lastFramesAt = Date.now();
      }
      if (disposed) return;
      if (job.status !== "running" && job.status !== "queued") {
        store.emit();
        onFinished(job);
        return;
      }
      render();
    } catch {
      /* transient network error: keep polling */
    }
    setTimeout(poll, 1500);
  };
  setTimeout(poll, 800);

  return () => {
    disposed = true;
    stage.setProbe(undefined);
  };
}
