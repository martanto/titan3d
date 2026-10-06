// titan3d frontend entry: hash router over Setup, Runs and Run (progress → results).
import "./styles/app.css";
import { api } from "./api/client";
import { store } from "./app/store";
import { h } from "./ui/dom";
import { mountResults } from "./ui/results";
import { mountRunning } from "./ui/running";
import { mountRuns } from "./ui/runs";
import { mountSetup } from "./ui/setup";
import { Stage } from "./ui/stage";

const panel = document.getElementById("panel") as HTMLElement;
const tabRun = document.getElementById("tabRun") as HTMLAnchorElement;

// ------------------------------------------------------------------ theme
const THEMES = ["system", "light", "dark"] as const;
type Theme = (typeof THEMES)[number];
function applyTheme(t: Theme): void {
  if (t === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = t;
  localStorage.setItem("titan3d.theme", t);
  const btn = document.getElementById("themeBtn")!;
  btn.title = `Colour theme: ${t}`;
  btn.setAttribute("aria-label", `Colour theme: ${t}. Switch theme`);
}
applyTheme((localStorage.getItem("titan3d.theme") as Theme) || "system");
document.getElementById("themeBtn")!.addEventListener("click", () => {
  const cur = (localStorage.getItem("titan3d.theme") as Theme) || "system";
  applyTheme(THEMES[(THEMES.indexOf(cur) + 1) % THEMES.length]);
});

// ------------------------------------------------------------------ stage
let stage: Stage;
try {
  stage = new Stage();
} catch (e) {
  document.getElementById("stageMessage")!.hidden = false;
  document.getElementById("stageMessage")!.replaceChildren(
    h(
      "div",
      { class: "box", role: "alert" },
      h("h2", {}, "3D graphics are unavailable"),
      h("p", { class: "text-muted" }, `This browser could not start WebGL 2 (${(e as Error).message}). Results can still be downloaded from the Runs list.`),
    ),
  );
  throw e;
}

// ----------------------------------------------------------------- router
let cleanup: (() => void) | null = null;

function setTabs(route: string): void {
  for (const a of document.querySelectorAll<HTMLAnchorElement>(".tabs a")) {
    const active = a.dataset.tab === route;
    if (active) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
  const last = store.lastRun;
  tabRun.href = last ? `#/run/${last}` : "#/run";
  tabRun.setAttribute("aria-disabled", String(!last));
}

async function mountRun(id: string): Promise<() => void> {
  let inner: (() => void) | null = null;
  let disposed = false;
  try {
    const job = await api.getSimulation(id);
    if (disposed) return () => undefined;
    store.lastRun = id;
    setTabs("run");
    const show = (j: typeof job) => {
      inner?.();
      if (j.status === "completed") inner = mountResults(stage, panel, j);
      else if (j.status === "running" || j.status === "queued") inner = mountRunning(stage, panel, j, show);
      else inner = mountEnded(j);
    };
    show(job);
  } catch (e) {
    panel.replaceChildren(
      h("div", { class: "panel-head" }, h("h1", {}, "Run not found")),
      h("div", { class: "panel-body" }, h("p", { class: "note" }, (e as Error).message), h("a", { class: "btn", href: "#/runs" }, "All runs")),
    );
  }
  return () => {
    disposed = true;
    inner?.();
  };
}

function mountEnded(j: Awaited<ReturnType<typeof api.getSimulation>>): () => void {
  const why: Record<string, string> = {
    failed: "The run stopped with an error.",
    cancelled: "The run was cancelled.",
    interrupted: "The server stopped while this run was in progress.",
  };
  panel.replaceChildren(
    h("div", { class: "panel-head" }, h("h1", {}, j.name), h("span", { class: "sub" }, h("span", { class: `status ${j.status}` }, j.status), ` ${why[j.status] ?? ""}`)),
    h(
      "div",
      { class: "panel-body" },
      h(
        "section",
        { class: "section" },
        j.error ? h("div", { class: "alert", role: "alert" }, h("strong", {}, "Error: "), j.error) : null,
        h("p", { class: "note" }, `Simulated ${j.progress.sim_t.toFixed(1)} of ${j.progress.t_end} s before stopping.`),
        h(
          "div",
          { class: "flex flex-wrap gap-2" },
          h(
            "button",
            {
              type: "button",
              class: "btn",
              onclick: async () => {
                const d = await api.duplicate(j.id);
                location.hash = `#/run/${d.id}`;
              },
            },
            "Run again",
          ),
          h(
            "button",
            {
              type: "button",
              class: "btn",
              onclick: () => {
                store.scenario = structuredClone(j.scenario);
                store.saveDraft();
                location.hash = "#/setup";
              },
            },
            "Edit as new",
          ),
          j.artifacts?.includes("run.log") ? h("a", { class: "btn", href: api.fileUrl(j.id, "run.log") }, "Solver log") : null,
        ),
      ),
    ),
  );
  stage.setBadges([{ text: j.status, warn: true }]);
  stage.setColourbar(null);
  return () => undefined;
}

async function route(): Promise<void> {
  cleanup?.();
  cleanup = null;
  panel.scrollTop = 0;
  stage.hideMessage();
  const hash = location.hash.replace(/^#\/?/, "");
  const [name, id] = hash.split("/");
  if (name === "runs") {
    setTabs("runs");
    cleanup = mountRuns(stage, panel);
  } else if (name === "run" && id) {
    setTabs("run");
    cleanup = await mountRun(id);
  } else if (name === "run" && store.lastRun) {
    location.hash = `#/run/${store.lastRun}`;
  } else {
    setTabs("setup");
    cleanup = mountSetup(stage, panel);
  }
}

store.on(() => {
  setTabs(document.querySelector(".tabs a[aria-current]")?.getAttribute("data-tab") ?? "setup");
});
addEventListener("hashchange", route);
route();
