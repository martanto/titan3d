# Frontend

`frontend/` is a Vite 8 + TypeScript 6 app with no UI framework. It uses three.js for WebGL 2, proj4 for UTM, and **Tailwind CSS v4** on top of the project's design tokens. In production the FastAPI server (or nginx) serves the build from `frontend/dist`.

```bash
cd frontend
npm ci
npm run dev        # http://localhost:5173 (proxies /api to :8000; run the backend too)
npm run build      # tsc + vite build → dist/
npm run gen:api    # regenerate src/api/schema.d.ts from backend/openapi.json
```

TypeScript is pinned to 6.0 because `openapi-typescript` needs the TS JS API, which TypeScript 7 (native) does not ship. `.npmrc` sets `legacy-peer-deps=true` for its peer range.

## Source map

```
src/
  main.ts              hash router (#/setup, #/runs, #/run/<id>), theme toggle, WebGL fallback
  api/client.ts        typed client (generated types in schema.d.ts); XHR upload with progress
  app/store.ts         shared state: DEMs, preview, draft scenario (localStorage), last run
  data/bundle.ts       decode terrain previews and playback bundles (native DecompressionStream)
  geo/utm.ts           lon/lat ↔ UTM (proj4), zone choice matching the backend
  scene/engine.ts      FlowScene: terrain + flow meshes, shaders, plan/3D cameras, picking, overlays
  scene/furniture.ts   graticule, scale bar, north arrow, labelled index contours (2D canvas)
  scene/ramps.ts       colour-map textures and CSS gradients; cmaps.ts = Crameri data (generated)
  ui/stage.ts          stage controller: furniture, colourbar, caption, probe, messages, PNG export
  ui/setup.ts          Setup view
  ui/running.ts        Running view (progress, phases, live charts)
  ui/results.ts        Results view (envelope masking, playback, readouts, downloads, presenter)
  ui/runs.ts           Runs list
  ui/system.ts         System health page
  ui/terrain.ts        DEM preview loading, scenario overlays, terrain captions
  ui/chart.ts          time-series charts with axes
  ui/dom.ts, format.ts DOM helper h(), icons, toasts; number and unit formatting
  styles/tokens.css    design tokens (light/dark)
  styles/app.css       Tailwind import, @theme mapping, base and component layers
```

## Views

| View | Route | Highlights |
|---|---|---|
| Setup | `#/setup` | DEM list and multi-file upload; click-to-place piles and vents; pile volume entry; domain, material, resolution presets; live estimate; YAML load/download; Run |
| Running | `#/run/<id>` (queued or running) | Phases inferred from the job record; hatched and indeterminate progress (with reduced-motion variants); ETA; live readouts and charts; cancel |
| Results | `#/run/<id>` (completed) | Max-depth envelope (release masked and outlined) in plan view; depth/speed playback; H/L; charts; downloads; Export figure / Copy caption; display controls; presenter mode |
| Runs | `#/runs` | History with live progress; open, run again, delete with confirm; terrain on the stage |
| System | `#/system` | Full-width health page (the map workspace is hidden and 3D rendering paused): summary strip, Server table with usage bars and limit marks, Services table, Storage with Clear caches (two-step confirm). Not realtime: it loads the cached reading, and Re-measure forces a new one. |

The router mounts one view at a time. Each view returns a cleanup function that stops polling, ticks and handlers.

## 3D engine (`scene/engine.ts`)

- **Geometry:** one grid mesh per layer, with vertices at cell centres and counter-clockwise winding seen from above. Heights are computed in the vertex shader from an R32F bed texture, so vertical exaggeration is just a uniform.
- **Terrain shader:**
  - *Hillshade:* a greyscale hypsometric ramp lit from the north-west.
  - *Natural:* colour synthesised from elevation (treeline at 78 % of relief), slope (bare above about 40°), two-scale curvature (dark gullies, light ridges) and value noise. It is muted under data layers.
  - Contours are drawn with `fwidth` (index every fifth line); fog is applied in 3D only.
- **Flow shader:**
  - Depth and speed for the frames around the current time arrive as two RG8 textures and are interpolated on the GPU.
  - The max-depth envelope uses an R8 texture with the release footprint masked out.
  - Colour comes from a 256-entry ramp texture. In plan view a threshold line (paper colour) outlines the flow; edges get soft alpha.
- **Cameras:** plan view is orthographic and north-up, with pan, wheel/pinch zoom and `focus()` on the domain. 3D uses a perspective camera with OrbitControls.
- **Picking:** the camera ray is marched over the CPU bed (heights live on the GPU) and refined by bisection.
- **Overlays:** draped `Line2` rings for piles and vents, and a dashed domain box.

## Figure furniture and export

- `furniture.ts` draws on a 2D canvas over the WebGL canvas:
  - a UTM graticule with edge labels that avoid the toolbar;
  - an alternating scale bar with the north arrow above it;
  - labelled index contours that avoid flow cells and other labels;
  - a projection, grid and contour note; in 3D, "perspective, not to scale, vertical exaggeration N×".
- `Stage.exportFigure()` composites the WebGL snapshot, the furniture canvas, a redrawn colourbar and the wrapped caption into a PNG.

## Colour maps

These are Crameri Scientific Colour Maps, exported from `cmcrameri` 1.8 into `scene/cmaps.ts`:

| Quantity | Map | Scale |
|---|---|---|
| Depth at t | batlow | square root; range = flow maximum outside the release area |
| Speed at t | imola | linear |
| Max-depth envelope | lajolla (reversed) | square root; release footprint masked |

Colourbars state the title with units, ticks, the scale type, the threshold behaviour and the citation.

## Styling: Tailwind v4 + design tokens

- **Tokens:** `styles/tokens.css` holds the light/dark tokens (paper ground, ink, one blue accent, terrain and contour colours). `DESIGN.md` and `.impeccable/design.json` document them.
- **Tailwind setup:** `styles/app.css` imports Tailwind (CSS-first, through the `@tailwindcss/vite` plugin) and maps the tokens in `@theme inline`.
  - The default palette is removed, so only system colours exist as utilities: `text-muted`, `bg-panel`, `border-control`, `text-accent`, `text-err`, …
  - The type scale is mapped to `text-xs … text-2xl`, and spacing follows Tailwind's 4 px scale (same as the tokens).
- **Layers:** preflight < `@layer base` (element rules) < `@layer components` (buttons, segmented controls, stage, colourbar, panels…) < utilities. Utility classes in `src/ui/*.ts` can therefore adjust components. Examples: `grid grid-cols-2 gap-3`, `flex flex-wrap gap-2`, `col-span-full`.
- **Rules:**
  - Use utilities for layout and one-offs, and component classes for repeated controls.
  - Keep data-driven values (progress fraction, gradient, tick position) inline.
  - Never add colours outside the tokens.
- **Responsive:** at ≤ 760 px the panel stacks under the map, the legend becomes a strip below the map, and stage tools wrap.

## Accessibility

- **Structure:** semantic landmarks; labelled controls; `aria-pressed` on toggles; progress bars with `aria-valuetext`.
- **Keyboard:** visible focus rings; Space/←/→ for playback, ignored when a control has focus.
- **Readability:** contrast ≥ 4.5:1 for text and ≥ 3:1 for control borders.
- **Motion:** reduced motion stops the hatch and pulse animations, and playback never autostarts.

## Verifying UI changes

The project rule is that frontend work uses the **impeccable** and **playwright-cli** skills:
1. Build.
2. Run `impeccable detect --json frontend/index.html frontend/src`.
3. Capture desktop (1440×900) and mobile (390×844), light and dark, with `playwright-cli --browser=msedge`.
4. Check the console is error-free.

The direction contract lives in `.impeccable/surfaces/frontend-index-html.md`.
