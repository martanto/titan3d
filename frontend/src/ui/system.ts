// System view: server resources, services and storage. Not realtime: the server
// reuses one reading for 5 minutes and only "Re-measure" forces a new one.
import type { components } from "../api/schema";
import { h, kids, svg, toast } from "./dom";
import { num } from "./format";

type SystemOut = components["schemas"]["SystemOut"];
type Resource = components["schemas"]["ResourceOut"];
type Service = components["schemas"]["ServiceOut"];
type Health = SystemOut["condition"];

const REFRESH_ICON =
  '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M13.5 8a5.5 5.5 0 1 1-1.6-3.9"/><path d="M13.5 2.5v3h-3"/></svg>';
const CLEAR_ICON =
  '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 9h5.8l.6-9"/></svg>';

const LABEL: Record<Health, string> = { normal: "Normal", warning: "Warning", critical: "Critical" };

function pill(s: Health): HTMLElement {
  return h("span", { class: `status health-${s}` }, LABEL[s]);
}

function ago(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 45) return "just now";
  if (s < 90) return "1 min ago";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  return `${Math.round(s / 3600)} h ago`;
}

function uptime(s: number): string {
  const d = Math.floor(s / 86400);
  const hh = Math.floor((s % 86400) / 3600);
  const mm = Math.floor((s % 3600) / 60);
  return d ? `${d} d ${hh} h` : hh ? `${hh} h ${mm} min` : `${mm} min`;
}

function bar(r: Resource): HTMLElement {
  const pct = Math.min(Math.max(r.fraction, 0), 1) * 100;
  return h(
    "div",
    {
      class: `usage usage-${r.status}`,
      role: "meter",
      "aria-label": `${r.label} usage`,
      "aria-valuemin": 0,
      "aria-valuemax": 100,
      "aria-valuenow": Math.round(pct),
      "aria-valuetext": `${num(pct, 1)} % used, ${LABEL[r.status].toLowerCase()}`,
    },
    h("span", { class: "usage-fill", style: `--p:${pct / 100}` }),
    h("span", { class: "usage-mark warn", style: `left:${r.thresholds.warning * 100}%`, title: `Warning from ${num(r.thresholds.warning * 100)} %` }),
    h("span", { class: "usage-mark crit", style: `left:${r.thresholds.critical * 100}%`, title: `Critical from ${num(r.thresholds.critical * 100)} %` }),
  );
}

/** "924.4 GB" → value with a muted, smaller unit (the readout Unit Rule). */
function unitized(text: string): HTMLElement {
  const m = /^(-?[\d.,]+)\s+(.+)$/.exec(text);
  return m ? h("span", {}, m[1], h("span", { class: "unit" }, m[2])) : h("span", {}, text);
}

function cell(label: string, value: string | Node, title?: string): HTMLElement {
  return h("div", { class: "sys-cell" }, h("dt", {}, label), h("dd", { title }, value));
}

function serviceDetails(sv: Service): HTMLElement {
  return h(
    "dl",
    { class: "sys-details" },
    (sv.details ?? []).map((d) => h("div", {}, h("dt", {}, d.label), h("dd", {}, d.value))),
  );
}

export function mountSystem(page: HTMLElement): () => void {
  let disposed = false;
  let data: SystemOut | null = null;
  let error: string | null = null;
  let busy = false;
  let confirmClear = false;

  async function load(refresh: boolean): Promise<void> {
    busy = true;
    render();
    try {
      const res = await fetch(`/api/system${refresh ? "?refresh=true" : ""}`);
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      data = (await res.json()) as SystemOut;
      error = null;
    } catch (e) {
      error = (e as Error).message;
    }
    busy = false;
    if (!disposed) render();
  }

  async function clearCaches(): Promise<void> {
    if (!confirmClear) {
      confirmClear = true;
      render();
      return;
    }
    confirmClear = false;
    try {
      const res = await fetch("/api/system/caches/clear", { method: "POST" });
      const out = (await res.json()) as components["schemas"]["CacheClearOut"];
      toast(`Cleared ${out.files} cached file${out.files === 1 ? "" : "s"} (${out.size}).`);
      await load(true);
    } catch (e) {
      toast(`Could not clear caches: ${(e as Error).message}`);
    }
  }

  function render(): void {
    if (disposed) return;
    const head = h(
      "header",
      { class: "sys-head" },
      h(
        "div",
        { class: "grid gap-1" },
        h("h1", {}, "System"),
        h(
          "p",
          { class: "text-muted" },
          "Server and application health. A reading is reused for 5 minutes; Re\u2011measure reads now.",
        ),
      ),
      h(
        "button",
        { type: "button", class: "btn", disabled: busy, onclick: () => load(true) },
        svg(REFRESH_ICON),
        busy ? "Measuring…" : "Re-measure",
      ),
    );
    if (!data) {
      page.replaceChildren(
        head,
        h(
          "div",
          { class: "sys-card p-6", role: error ? "alert" : "status" },
          error ? h("p", {}, h("strong", { class: "text-err" }, "Could not read system health: "), error) : h("p", { class: "text-muted" }, "Measuring disk, memory, CPU and services…"),
        ),
      );
      return;
    }
    const d = data;
    const summary = h(
      "dl",
      { class: "sys-summary" },
      cell("Condition", pill(d.condition)),
      cell("Measured", ago(d.measured_at), new Date(d.measured_at).toLocaleString("en-GB")),
      cell("Host", d.host),
      cell("Operating system", d.os),
      cell("Environment", d.environment),
      cell("Python · titan3d", h("span", {}, `${d.python} · ${d.titan3d} `, h("span", { class: "unit" }, d.commit))),
      cell("App uptime", uptime(d.app_uptime_s)),
      cell("Server uptime", uptime(d.server_uptime_s)),
    );

    const resources = h(
      "section",
      { class: "sys-card", "aria-labelledby": "sys-server" },
      h(
        "div",
        { class: "sys-card-head" },
        h("h2", { id: "sys-server" }, "Server"),
        h(
          "ul",
          { class: "sys-legend", "aria-label": "Usage bar legend" },
          h("li", {}, h("span", { class: "swatch-used" }), "Used"),
          h("li", {}, h("span", { class: "swatch-mark warn" }), "Warning limit"),
          h("li", {}, h("span", { class: "swatch-mark crit" }), "Critical limit"),
        ),
      ),
      h(
        "table",
        { class: "sys-table" },
        h(
          "thead",
          {},
          h(
            "tr",
            {},
            h("th", { scope: "col" }, "Resource"),
            h("th", { scope: "col", class: "w-[38%]" }, "Usage"),
            h("th", { scope: "col", class: "num" }, "Used"),
            h("th", { scope: "col", class: "num" }, "Capacity"),
            h("th", { scope: "col", class: "num" }, "Free"),
            h("th", { scope: "col" }, "Status"),
          ),
        ),
        h(
          "tbody",
          {},
          d.resources.map((r) =>
            h(
              "tr",
              {},
              h("th", { scope: "row" }, h("span", { class: "sys-name" }, r.label), h("span", { class: "sys-sub" }, r.detail)),
              h(
                "td",
                { "data-label": "Usage" },
                h("div", { class: "usage-row" }, bar(r), h("span", { class: "usage-pct" }, num(r.fraction * 100, 1), h("span", { class: "unit" }, "%"))),
              ),
              h("td", { class: "num", "data-label": "Used" }, unitized(r.used)),
              h("td", { class: "num", "data-label": "Capacity" }, unitized(r.capacity)),
              h("td", { class: "num", "data-label": "Free" }, unitized(r.free)),
              h("td", { "data-label": "Status" }, pill(r.status)),
            ),
          ),
        ),
      ),
      h("p", { class: "sys-foot" }, d.notes[0] ?? ""),
    );

    const services = h(
      "section",
      { class: "sys-card", "aria-labelledby": "sys-services" },
      h("div", { class: "sys-card-head" }, h("h2", { id: "sys-services" }, "Services")),
      h(
        "table",
        { class: "sys-table services" },
        h(
          "thead",
          {},
          h(
            "tr",
            {},
            h("th", { scope: "col", class: "c-service" }, "Service"),
            h("th", { scope: "col", class: "c-status" }, "Status"),
            h("th", { scope: "col", class: "num c-response" }, "Response"),
            h("th", { scope: "col" }, "Details"),
          ),
        ),
        h(
          "tbody",
          {},
          d.services.map((sv) =>
            h(
              "tr",
              {},
              h(
                "th",
                { scope: "row" },
                h("span", { class: "sys-name" }, sv.name),
                sv.version ? h("span", { class: "sys-sub" }, sv.version) : null,
                sv.note ? h("span", { class: "sys-sub text-warn" }, sv.note) : null,
              ),
              h("td", { "data-label": "Status" }, pill(sv.status)),
              h("td", { class: "num", "data-label": "Response" }, sv.response_ms != null ? unitized(`${num(sv.response_ms, 1)} ms`) : "—"),
              h("td", { "data-label": "Details" }, serviceDetails(sv)),
            ),
          ),
        ),
      ),
      h("p", { class: "sys-foot" }, d.notes[1] ?? ""),
    );

    const caches = d.storage.find((s) => s.key === "caches");
    const storage = h(
      "section",
      { class: "sys-card flex flex-col", "aria-labelledby": "sys-storage" },
      h(
        "div",
        { class: "sys-card-head" },
        h("h2", { id: "sys-storage" }, "Storage"),
        h("span", { class: "text-muted text-sm" }, `Data folder · ${d.data_dir}`),
      ),
      h(
        "ul",
        { class: "sys-storage" },
        d.storage.map((s) =>
          h(
            "li",
            {},
            h(
              "div",
              { class: "min-w-0" },
              h("span", { class: "sys-name" }, s.label),
              h("span", { class: "sys-sub" }, `${s.description} · ${num(s.files)} file${s.files === 1 ? "" : "s"}`),
            ),
            h("span", { class: "sys-size" }, unitized(s.size)),
          ),
        ),
      ),
      h(
        "div",
        { class: "sys-card-foot mt-auto" },
        h(
          "p",
          { class: "text-muted text-sm" },
          "Clearing removes terrain previews and playback bundles only; runs, DEMs and downloads are kept and the caches are rebuilt when next opened.",
        ),
        h(
          "button",
          {
            type: "button",
            class: confirmClear ? "btn danger" : "btn",
            disabled: !caches || caches.files === 0,
            onclick: () => clearCaches(),
            onblur: () => {
              if (confirmClear) {
                confirmClear = false;
                render();
              }
            },
          },
          svg(CLEAR_ICON),
          confirmClear ? `Confirm: clear ${caches?.size ?? ""}` : `Clear caches${caches ? ` (${caches.size})` : ""}`,
        ),
      ),
    );

    page.replaceChildren(
      ...kids(
        head,
        error ? h("div", { class: "alert", role: "alert" }, h("strong", {}, "Last re-measure failed: "), error) : null,
        summary,
        resources,
        h("div", { class: "sys-columns" }, services, storage),
      ),
    );
  }

  load(false);
  return () => {
    disposed = true;
  };
}
