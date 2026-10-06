// Runs view: history of simulations with live progress, open / run again / delete.
import { api, type Simulation } from "../api/client";
import { store } from "../app/store";
import { h, kids } from "./dom";
import { dateTime, duration, num } from "./format";
import type { Stage } from "./stage";
import { ensurePreview, terrainCaption, terrainProbe } from "./terrain";

export function mountRuns(stage: Stage, panel: HTMLElement): () => void {
  let disposed = false;
  let runs: Simulation[] = [];
  let error: string | null = null;
  const confirming = new Set<string>();
  const list = h("ul", { class: "runs", "aria-live": "polite" });

  function item(j: Simulation): HTMLElement {
    const active = j.status === "running" || j.status === "queued";
    const del = h(
      "button",
      {
        type: "button",
        class: "btn small danger",
        onclick: async () => {
          if (!confirming.has(j.id)) {
            confirming.add(j.id);
            render();
            return;
          }
          await api.deleteSimulation(j.id);
          if (store.lastRun === j.id) store.lastRun = null;
          confirming.delete(j.id);
          await refresh();
        },
      },
      confirming.has(j.id) ? "Confirm delete" : "Delete",
    );
    const grid = j.grid ? `${num(j.grid.nx)} × ${num(j.grid.ny)} @ ${num(j.grid.dx)} m` : `Δx ${num(j.scenario.numerics?.dx ?? 20)} m`;
    return h(
      "li",
      { class: "run" },
      h(
        "div",
        { class: "run-top" },
        h("a", { href: `#/run/${j.id}` }, j.name),
        h("span", { class: `status ${j.status}` }, j.status),
      ),
      active
        ? h(
            "div",
            {
              class: "minibar",
              role: "progressbar",
              "aria-label": `${j.name} progress`,
              "aria-valuenow": Math.round(j.progress.fraction * 100),
              "aria-valuemin": 0,
              "aria-valuemax": 100,
            },
            h("span", { style: `width:${Math.round(j.progress.fraction * 100)}%` }),
          )
        : null,
      h(
        "span",
        { class: "meta" },
        `${dateTime(j.created_at)} · ${j.dem_id} · ${grid} · ${num(j.scenario.t_end ?? 0)} s`,
        j.status === "completed" ? ` · ${duration(j.progress.elapsed_s)} solver time` : "",
        active ? ` · t = ${num(j.progress.sim_t, 1)} s` : "",
      ),
      j.error ? h("span", { class: "meta text-err" }, j.error) : null,
      h(
        "div",
        { class: "flex flex-wrap gap-2" },
        h("a", { class: "btn small", href: `#/run/${j.id}` }, j.status === "completed" ? "Open results" : active ? "Follow progress" : "Details"),
        h(
          "button",
          {
            type: "button",
            class: "btn small",
            onclick: async () => {
              const d = await api.duplicate(j.id);
              store.lastRun = d.id;
              location.hash = `#/run/${d.id}`;
            },
          },
          "Run again",
        ),
        del,
      ),
    );
  }

  function render(): void {
    list.replaceChildren(...runs.map(item));
    const body = panel.querySelector(".panel-body");
    if (!body) return;
    body.replaceChildren(...kids(
      error ? h("div", { class: "alert", role: "alert" }, h("strong", {}, "Cannot load runs: "), error) : null,
      runs.length
        ? list
        : h(
            "div",
            { class: "empty" },
            h("p", {}, "No simulations yet."),
            h("p", { class: "note" }, "Set up a release on the map and press Run simulation; every run is kept here with its configuration and outputs."),
            h("a", { class: "btn", href: "#/setup" }, "Go to setup"),
          ),
    ));
  }

  async function refresh(): Promise<void> {
    try {
      runs = await api.listSimulations();
      error = null;
    } catch (e) {
      error = (e as Error).message;
    }
    if (!disposed) render();
  }

  panel.replaceChildren(
    h("div", { class: "panel-head" }, h("h1", {}, "Runs"), h("span", { class: "sub" }, "Queued, running and finished simulations on this server.")),
    h("div", { class: "panel-body" }),
  );
  stage.setBadges([]);
  stage.setColourbar(null);
  stage.onPick(undefined);
  stage.setCaption("Select a run to see its progress or results.", "Runs.");
  // the stage always carries a figure: show the current terrain on direct load
  (async () => {
    try {
      if (!store.dems.length) store.dems = await api.listDems();
      const dem =
        store.dems.find((d) => d.id === store.scenario?.dem_id && d.status === "ready") ??
        store.dems.find((d) => d.status === "ready");
      if (!dem || disposed) return;
      const p = await ensurePreview(stage, dem.id);
      if (disposed) return;
      stage.scene.setMarkers([]);
      stage.setProbe(terrainProbe(p));
      stage.setTerrainLabel(`Terrain: ${dem.name}`);
      stage.setCaption(`${terrainCaption(p, stage.scene.surface)} Select a run to see its progress or results.`, "Runs.");
    } catch {
      /* terrain is context only; the list still works */
    }
  })();
  refresh();
  const timer = setInterval(() => {
    if (runs.some((j) => j.status === "running" || j.status === "queued")) refresh();
  }, 2500);
  return () => {
    disposed = true;
    clearInterval(timer);
    stage.setProbe(undefined);
  };
}
