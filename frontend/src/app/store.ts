// Application state shared between views (draft scenario persists locally).
import type { Dem, Scenario } from "../api/client";
import type { Preview } from "../data/bundle";

const DRAFT_KEY = "titan3d.scenario.v1";
const LAST_RUN_KEY = "titan3d.lastRun";

type Listener = () => void;

class Store {
  dems: Dem[] = [];
  preview: Preview | null = null;
  previewFor: string | null = null;
  scenario: Scenario | null = null;
  selected = 0; // index into [...piles, ...flux_sources]
  private listeners = new Set<Listener>();

  loadDraft(fallback: Scenario): Scenario {
    try {
      const raw = localStorage.getItem(DRAFT_KEY);
      if (raw) return JSON.parse(raw) as Scenario;
    } catch {
      /* corrupted draft: start over */
    }
    return fallback;
  }

  saveDraft(): void {
    if (this.scenario) localStorage.setItem(DRAFT_KEY, JSON.stringify(this.scenario));
  }

  get lastRun(): string | null {
    return localStorage.getItem(LAST_RUN_KEY);
  }

  set lastRun(id: string | null) {
    if (id) localStorage.setItem(LAST_RUN_KEY, id);
    else localStorage.removeItem(LAST_RUN_KEY);
    this.emit();
  }

  on(f: Listener): () => void {
    this.listeners.add(f);
    return () => this.listeners.delete(f);
  }

  emit(): void {
    for (const f of this.listeners) f();
  }
}

export const store = new Store();
