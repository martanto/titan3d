---
version: 1
slug: "frontend-index-html"
primary_target: "frontend/index.html"
related_targets: []
---

# Surface brief: titan3d app (frontend/index.html)

Scope: the whole single-page app with three views (Setup, Running, Results) plus run history and presenter mode. Visitor mode: **Operate**.

Audience and job: PVMBG hazard analysts, researchers and outreach viewers (PRODUCT.md). They set up a granular-flow scenario on a DEM, start a run that may take minutes to hours, follow its progress, then read, brief on and export the result.

Confirmed answers (owner, 2026-10-06):
- Stack: Vite + TypeScript.
- Setup is a full scenario form; the user clicks the terrain to place piles and vents.
- Results opens on the briefing plan view (max-inundation envelope with map furniture); 3D playback is one click away.
- Flow depth is shown true by default; boost is optional and always badged when active.
- Simple presenter mode now.
- Visual direction is pinned by the owner: "as close to scientific as possible".
- Owner request (later): add a terrain surface like crater.id/volcanoes/semeru/summit, a natural-colour relief. Built as a DEM-derived synthetic surface (not imagery, disclosed in captions). Default on terrain-only views (Setup, Running). Under data layers (Results) the default is the hillshade, so colour stays reserved for data; Natural stays available there, desaturated.

Constraints:
- Must work offline on internal servers: bundle every asset and self-host the font.
- Long runs; users leave and return.
- Light and dark themes.
- WCAG 2.2 AA; reduced motion respected.

## Direction contract
THESIS: The figure is the interface. Every stage view is a publication-ready scientific figure: graticule, scale bar, north arrow, colourbar with units and scale type, a stated vertical exaggeration, and an auto-written figure caption with provenance. It refuses the category default of a dark game-like 3D canvas with floating chrome and decorative gradients.
OWN-WORLD: Neutral figure paper (cool off-white ground, white panels) and near-black ink, with hairline rules at ≥3:1 for controls. One functional blue accent, used only for actions and selection. Under data, terrain is a greyscale hillshade with labelled index contours, so colour is reserved for data; on terrain-only views a DEM-derived natural-colour relief (owner request) is the default. Data colour maps: Crameri batlow (depth), imola (speed), lajolla reversed (max-depth envelope, release footprint masked and outlined). One workhorse sans (Source Sans 3, self-hosted) with tabular numerals and sentence-case labels; no tracked mono costume. SI units on every number.
STORY: The analyst sees the DEM as a map, places sources, and sees grid size, memory and runtime class before committing. They watch honest, specific progress with live runout and speed curves. They land on the inundation envelope figure and can export it, cite it and play it back.
FIRST VIEWPORT: Top bar (product name, DEM in use, view tabs Setup · Runs · Results, theme). The left ~70 % is the stage: plan-view hillshade map with graticule labels on the edges, scale bar lower left with the north arrow above it (cartographic convention, amended after review), colourbar lower right and a caption strip along the bottom. The right 360–400 px is the context panel: Setup form with a sticky "Run simulation" primary button, the Running progress card, or Results readouts and downloads.
FORM: Scientific figure / instrument panel (owner-pinned brief; no concept-seed roll). Signature move: the auto figure caption plus map furniture that turns any stage view into a citable figure (copy caption, export PNG). Seed key: n/a (pinned direction).
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
