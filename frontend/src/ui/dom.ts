// Minimal DOM helpers (no framework).

type Attrs = Record<string, string | number | boolean | null | undefined | EventListener>;
type Child = Node | string | number | null | undefined | false;

export function h<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: Attrs = {},
  ...children: (Child | Child[])[]
): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") {
      el.addEventListener(k.slice(2).toLowerCase(), v as EventListener);
    } else if (k === "class") {
      el.className = String(v);
    } else if (v === true) {
      el.setAttribute(k, "");
    } else {
      el.setAttribute(k, String(v));
    }
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

/** Inline SVG from markup (icons are authored, stroke 1.6–1.7). */
export function svg(markup: string): SVGSVGElement {
  const t = document.createElement("template");
  t.innerHTML = markup.trim();
  return t.content.firstElementChild as SVGSVGElement;
}

export const ICON = {
  play: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 2.5v11l9-5.5z"/></svg>',
  pause: '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="3.5" y="2.5" width="3" height="11"/><rect x="9.5" y="2.5" width="3" height="11"/></svg>',
  back: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M12 3v10L5 8z"/><rect x="3" y="3" width="1.8" height="10"/></svg>',
  fwd: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 3v10l7-5z"/><rect x="11.2" y="3" width="1.8" height="10"/></svg>',
  download:
    '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2.5v8M4.5 7.5 8 11l3.5-3.5M2.5 13.5h11"/></svg>',
  upload: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 11V3M4.5 6.5 8 3l3.5 3.5M2.5 13.5h11"/></svg>',
  plus: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 3v10M3 8h10"/></svg>',
  trash:
    '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 9h5.8l.6-9"/></svg>',
  target:
    '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="5"/><path d="M8 1.5v3M8 11.5v3M1.5 8h3M11.5 8h3"/></svg>',
  copy: '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="5.5" y="5.5" width="8" height="8" rx="1"/><path d="M10.5 5.5V3a.5.5 0 0 0-.5-.5H3a.5.5 0 0 0-.5.5v7a.5.5 0 0 0 .5.5h2.5"/></svg>',
  image:
    '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="2.5" y="3" width="11" height="10" rx="1"/><path d="M2.5 11l3.5-3.5 3 3 2-2 2.5 2.5"/></svg>',
};

export function icon(name: keyof typeof ICON): SVGSVGElement {
  return svg(ICON[name]);
}

export function toast(message: string, ms = 2600): void {
  const t = h("div", { class: "toast", role: "status" }, message);
  document.body.append(t);
  setTimeout(() => t.remove(), ms);
}

export function download(blob: Blob, filename: string): void {
  const a = h("a", { href: URL.createObjectURL(blob), download: filename });
  document.body.append(a);
  a.click();
  setTimeout(() => {
    URL.revokeObjectURL(a.href);
    a.remove();
  }, 0);
}

export function debounce<T extends unknown[]>(f: (...a: T) => void, ms: number): (...a: T) => void {
  let id = 0;
  return (...a: T) => {
    clearTimeout(id);
    id = window.setTimeout(() => f(...a), ms);
  };
}

/** Drop empty children so conditional nodes can be passed to replaceChildren. */
export function kids(...c: (Node | string | null | undefined | false)[]): (Node | string)[] {
  return c.filter((x): x is Node | string => x !== null && x !== undefined && x !== false);
}
