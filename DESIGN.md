---
name: titan3d
description: Titan2D-style granular-flow simulation, monitoring and analysis, drawn as a citable scientific figure.
colors:
  accent: "#1b56c9"
  accent-weak: "#e7eefc"
  on-accent: "#ffffff"
  paper-ground: "#f1f3f5"
  panel: "#ffffff"
  panel-2: "#f6f7f8"
  ink: "#15181c"
  muted-ink: "#535b64"
  hairline: "#dfe2e6"
  control-stroke: "#858d97"
  ok: "#1a7f37"
  warn: "#8a5a00"
  err: "#b42318"
  err-weak: "#fdecea"
  scene: "#e9ecef"
  terrain-low: "#a9afb5"
  terrain-mid: "#d0d4d8"
  terrain-high: "#f5f6f7"
  contour: "#353b42"
  grid-line: "rgba(21, 24, 28, 0.38)"
  pile: "#15181c"
  vent: "#c2410c"
  accent-dark: "#7aa6ff"
  accent-weak-dark: "#1c2a44"
  on-accent-dark: "#0b1220"
  paper-ground-dark: "#0f1215"
  panel-dark: "#171b1f"
  panel-2-dark: "#1d2227"
  ink-dark: "#e7eaed"
  muted-ink-dark: "#a3abb4"
  hairline-dark: "#2b3238"
  control-stroke-dark: "#6f7882"
  ok-dark: "#56c271"
  warn-dark: "#e0b04f"
  err-dark: "#ff7b6e"
  err-weak-dark: "#3a1d1a"
  scene-dark: "#121519"
  terrain-low-dark: "#5a626b"
  terrain-mid-dark: "#7d868f"
  terrain-high-dark: "#c3c9cf"
  contour-dark: "#07090b"
  grid-line-dark: "rgba(231, 234, 237, 0.34)"
  pile-dark: "#e7eaed"
  vent-dark: "#ff8a4c"
typography:
  display:
    fontFamily: "Source Sans 3 Variable, Source Sans 3, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.2
    fontFeature: "tnum"
  headline:
    fontFamily: "Source Sans 3 Variable, Source Sans 3, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
    lineHeight: 1.2
  readout:
    fontFamily: "Source Sans 3 Variable, Source Sans 3, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "1.375rem"
    fontWeight: 600
    lineHeight: 1.2
    fontFeature: "tnum"
  title:
    fontFamily: "Source Sans 3 Variable, Source Sans 3, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: 1.2
  body:
    fontFamily: "Source Sans 3 Variable, Source Sans 3, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.45
    fontFeature: "tnum"
  label:
    fontFamily: "Source Sans 3 Variable, Source Sans 3, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 600
    lineHeight: 1.45
    letterSpacing: "normal"
  caption:
    fontFamily: "Source Sans 3 Variable, Source Sans 3, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.45
    fontFeature: "tnum"
rounded:
  sm: "4px"
  pill: "999px"
spacing:
  s1: "4px"
  s2: "8px"
  s3: "12px"
  s4: "16px"
  s5: "20px"
  s6: "24px"
  s8: "32px"
components:
  button:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "0 16px"
    height: "36px"
  button-hover:
    backgroundColor: "{colors.panel-2}"
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "0 16px"
    height: "44px"
  button-small:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "32px"
  button-transport-play:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.panel}"
    rounded: "{rounded.sm}"
    size: "44px"
  input:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "4px 8px"
    height: "36px"
  segmented-option:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    padding: "0 8px"
    height: "36px"
  segmented-option-selected:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
  toolgroup-button:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "36px"
  toolgroup-button-pressed:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
  tab:
    textColor: "{colors.muted-ink}"
    typography: "{typography.body}"
    padding: "0 12px"
    height: "48px"
  tab-active:
    textColor: "{colors.ink}"
  option-card-selected:
    backgroundColor: "{colors.accent-weak}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
  estimate:
    backgroundColor: "{colors.panel-2}"
    rounded: "{rounded.sm}"
    padding: "12px"
  badge:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    typography: "{typography.caption}"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
  status-pill:
    textColor: "{colors.ok}"
    typography: "{typography.caption}"
    rounded: "{rounded.pill}"
    padding: "1px 8px"
  colourbar:
    backgroundColor: "{colors.panel}"
    typography: "{typography.caption}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
    width: "260px"
  caption-strip:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    padding: "8px 16px"
  toast:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.panel}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
---

# Design System: titan3d

## Overview

**Creative North Star: "The Figure Is the Interface"**

Every stage view is a publication-ready scientific figure. Plan views carry a UTM graticule with edge labels, a scale bar and north arrow in the lower left, labelled index contours, and a colourbar that states units, scale type and colour-map citation. Perspective views state their vertical exaggeration. Every view has an auto-written figure caption with provenance (code version, DEM hash, run id) and the disclaimer "Model output, not an official hazard map". The chrome around the figure works like an instrument panel: neutral paper, near-black ink, hairline rules and one functional blue.

The density is that of a lab instrument. A fixed 392 px context panel on the right holds forms, progress or readouts in a 4 px rhythm. The stage on the left gets all remaining width and stays plain. Colour belongs to the data: Crameri scientific colour maps for flow fields, and greyscale hillshade under data so no terrain hue competes with them. On terrain-only views (Setup, Running) the default is a natural-colour relief synthesised from the DEM, which the caption says is not imagery. The system rejects the category default of a dark, game-like 3D canvas with floating chrome and decorative gradients.

Light (figure paper) and dark themes are both first-class. Dark follows `prefers-color-scheme` unless the user picks a theme with the top-bar toggle, which sets `data-theme`.

**Key Characteristics:**
- Neutral cool paper with white panels; near-black ink; hairlines for separation, a stronger control stroke (at least 3:1) for anything interactive.
- One blue accent, used only for actions, selection and progress.
- Colour inside the figure comes only from Crameri batlow, imola and lajolla (reversed), or the DEM-derived natural relief.
- One sans (Source Sans 3, self-hosted) with tabular numerals everywhere, sentence-case labels, and an SI unit on every number.
- Map furniture drawn on a canvas so exported figures composite it pixel-exact.
- Flat at rest; a soft shadow only on elements floating over the stage.

## Colors

Ink on cool paper, with one functional blue and a data palette that the chrome never borrows.

### Primary
- **Survey Blue** (accent; dark theme `accent-dark`): the only chrome colour. Used for the primary "Run simulation" button, pressed segmented and toolgroup options, the active tab underline, focus rings, links, progress fills, chart series lines, the current phase dot, running/queued status, and selected option or source cards (outlined in blue on `accent-weak`). It stays at 6.2:1 on panel in light mode.

### Neutral
- **Figure Paper** (paper-ground): app ground behind the panels.
- **Sheet White** (panel): top bar, context panel, caption strip, floating stage furniture, inputs and buttons.
- **Tint Sheet** (panel-2): hover fill, estimate block, dropzone, progress and minibar tracks.
- **Plate Ink** (ink): text, chart axes, colourbar ticks, the transport play button, toast.
- **Annotation Grey** (muted-ink): secondary text, units, hints, chart tick labels, inactive tabs (7.0:1 on panel).
- **Hairline** (hairline): decorative separators between sections, panel edges, inside segmented controls and toolgroups. Never the only boundary of a control.
- **Control Stroke** (control-stroke): borders of inputs, buttons, segmented controls, toolgroups, badges and the colourbar swatch (3.3:1 on panel).

### Semantic
- **ok / warn / err** with **err-weak**: run status pills, completed phase dots, the "flow depth exaggerated" warning badge, validation borders and text, alert blocks.

### Stage
- **scene**: the canvas ground around the DEM.
- **terrain-low / mid / high**: the three-stop greyscale ramp the hillshade surface is lit through.
- **contour**: contour line colour, mixed in at 18% (minor) and 42% (index, every fifth interval).
- **grid-line**: the dashed (2/4) graticule.
- **pile** (ink, solid ring) and **vent** (burnt orange, dashed ring): source markers on the map and as swatches on source cards.

### Data colour maps (not tokens; 256-sample tables in the scene code)
- **Depth: batlow** (square-root scale).
- **Speed: imola**.
- **Maximum-depth envelope: lajolla reversed**, pale yellow through red to dark brown (square-root scale). The release footprint is masked, outlined, and left out of the scale.
- Each quantity has its own map family, so modes cannot be confused. The flow edge gets a crisp 1 px ink line at the threshold (0.05 m live depth, 0.1 m envelope). The colourbar is sampled from the same table as the texture and always cites "Crameri (2018), doi:10.5281/zenodo.1243862".

### Named Rules
**The Data Owns Colour Rule.** Hue inside the figure belongs to the data. Under a flow layer the terrain is greyscale hillshade by default. If the user picks Natural there, it is desaturated (mute 0.6) so no vegetation green collides with a colour map.

**The One Blue Rule.** The accent marks actions, selection and progress only. It never decorates, never fills a panel, and never appears in the data colour maps.

**The Two-Weight Stroke Rule.** Hairline separates; control stroke encloses. Any boundary the user acts on uses control stroke.

## Typography

**Display Font:** Source Sans 3 Variable (self-hosted via @fontsource-variable, fallback system-ui, -apple-system, Segoe UI, sans-serif)
**Body Font:** the same family
**Label/Mono Font:** none. There is no monospace face; numbers use tabular figures in the sans.

**Character:** One workhorse humanist sans, set like a figure legend. Weight (400 / 600, 700 only for the wordmark) and size carry the hierarchy. No tracking or case tricks.

### Hierarchy
The scale uses fixed rem steps with a ratio of about 1.15.
- **Display** (600, 1.5rem): the elapsed clock on the Running card and the large time readout in the presenter bar.
- **Readout** (600, 1.375rem): key result numbers (runout, H/L, peak depth, peak speed, area, mass), with the unit at 0.72em in muted ink.
- **Headline** (600, 1.25rem, 1.2): panel heading (scenario name, "New simulation").
- **Title** (600, 1rem, 1.2): h2; estimate values; the wordmark at 700.
- **Body** (400, 0.875rem, 1.45): default text, buttons (600), inputs, tabs (600), section legends (600).
- **Label** (600, 0.8125rem): field labels, segmented and toolgroup options, small buttons, colourbar title. The caption strip and hints use this size at 400.
- **Caption** (400, 0.75rem): help text, units inside inputs, card meta, colourbar ticks and notes, badges and status pills (600), probe readouts.

### Named Rules
**The Tabular Rule.** `font-variant-numeric: tabular-nums` is set on body and inputs, so every number aligns in columns. Numeric inputs are right-aligned, have no spinners, and show their unit inside the field.

**The Unit Rule.** No bare numbers. Every value carries an SI unit (m, m/s, km², m³, °, %, s). Units are muted and smaller than the value. Coordinates group thousands with a space ("9 105 000").

**The Sentence-Case Rule.** Labels, buttons, tabs and headings are sentence case at normal letter-spacing. No uppercase tracking, and no small labels above headings.

## Layout

- **Shell:** a 48 px top bar (wordmark plus a muted 12 px line with the running version and the credit "v0.1.0 · built by github.com/martanto", the credit a muted link, view tabs Setup / Runs / Results / System, DEM name on the right, theme toggle as a bare 36 px icon button: no frame, panel-2 fill on hover, focus ring), then a two-column workspace: stage `minmax(0, 1fr)` and the context panel at 392 px (340 px at ≤960 px, where the wordmark subtitle is hidden).
- **Stage:** a grid with the map cell and a caption strip below it. On wide screens the legend layer shares the map cell: badges top left (64 px in), colourbar lower right (260 px), tools top right in toolgroups.
- **Map furniture placement (fixed):** north arrow at lower left above the scale bar, scale bar at lower left (alternating ink/paper quarters, about 150 px nice length), projection and grid note along the bottom left ("UTM 49S (WGS 84) · grid 5 000 m · contours 100 m, index 500 m (m a.s.l.)"). Graticule labels sit on the top and left edges on paper chips; labels under the toolbar drop below it. Perspective views drop the graticule and scale bar and state "Perspective view, not to scale · vertical exaggeration N×".
- **Context panel:** a head (title plus muted sub line, hairline below) and a body of sections separated by hairlines with 16 px vertical padding and 12 px internal gaps. A sticky foot holds the primary action ("Run simulation" at 44 px, full width) and secondary buttons.
- **Rhythm:** 4 px grid (4 / 8 / 12 / 16 / 20 / 24 / 32). Field groups use 12 px gaps; label to input is 4 px. Paired numeric fields sit in two columns; domain extents form a 2 × 2 grid so every input keeps the standard width.
- **≤760 px:** the page scrolls. The top bar is sticky and drops the DEM name. Workspace and stage stack. The map is 56svh (min 320 px) with a 28 px right margin kept free for page scrolling. The legend becomes a strip under the map on panel white: badges and a full-width colourbar, unframed and without shadow. The caption wraps at 12 px, actions sit below the text, toolgroup buttons grow to 40 px, and the presenter bar spans the width.
- **System page:** the workspace (stage and panel) is hidden and 3D rendering paused. A single scrolling column (max 1680 px, 24 px padding, rows sized to content) holds the page head (24 px title, muted sub line, Re-measure button right), the summary strip, the Server card, then Services and Storage side by side (1.65fr / 1fr), stacking at ≤1100 px. At ≤760 px the tables become labelled cards (each cell prints its column name).
- **Presenter mode:** the panel is hidden, the stage fills the workspace, and a centred presenter bar floats 16 px above the bottom with large time and mode controls. Escape exits.

## Elevation & Depth

Flat by default. Panels, cards and sections are separated by hairlines and tonal steps (panel to panel-2), not shadows. One soft two-layer ambient shadow lifts only the elements that float over the stage (toolgroups, colourbar, probe, presenter bar, toast). Depth in the figure comes from lit terrain: north-west hillshade, contours, and distance fog into the scene colour in 3D.

### Shadow Vocabulary
- **Float** (`box-shadow: 0 1px 2px rgba(21, 24, 28, 0.08), 0 4px 12px rgba(21, 24, 28, 0.08)`; dark `0 1px 2px rgba(0, 0, 0, 0.4), 0 4px 16px rgba(0, 0, 0, 0.35)`): stage overlays and toast only. Removed when the legend becomes a strip on phones.

### Named Rules
**The Paper Chip Rule.** Furniture text over the map (graticule, contour, scale-bar labels, notes) sits on a paper rectangle at 86% opacity, not a shadow or outline glow, so it stays legible over terrain, flow and overlay lines.

## Shapes

Small, uniform corners: 4 px on every control, card, badge, colourbar, probe and toast. A full pill (999 px) is used only for run and health status and the progress track. Containers are rectangles drawn with 1 px strokes. Segmented controls and toolgroups are single bordered strips with hairline dividers, clipped to the 4 px corner. The source swatch is a 12 px ring: solid ink for piles, dashed orange for vents. Icons are inline 16 px SVG strokes (1.6 to 1.7 px, round caps). The dropzone uses a dashed control stroke.

## Components

### Buttons
- **Shape:** gently squared (4 px), 1 px control stroke, 600 weight, 8 px icon gap, icons 16 px stroked SVG.
- **Default:** panel fill, ink text, 36 px tall, 16 px side padding. Hover moves to panel-2 with an ink border (150 ms, ease-out-expo).
- **Primary:** accent fill and border, on-accent text, 44 px tall; hover brightens 8%. One per view: "Run simulation" in the sticky panel foot.
- **Small:** 32 px, 12 px padding, label size. Used for card actions such as "Placing" and delete.
- **Danger:** default button with err text.
- **Disabled:** 50% opacity, not-allowed cursor.
- **Transport:** 40 px square icon buttons. Play/pause is 44 px with an ink fill and paper glyph, a media-control exception to the blue accent.

### Navigation (top bar tabs)
- 600 body text in muted ink, 12 px padding, full 48 px height. Hover changes to ink. The current tab is ink with a 2 px accent underline sitting on the bar's hairline. An unavailable Results tab is shown at 45% opacity and is not clickable.

### Toolgroups (stage tools)
- Bordered strips on panel white with the Float shadow: View (Plan / 3D), Terrain surface (Natural / Hillshade), Zoom (in / out / fit). Buttons are 36 px (40 px on phones), label type, hairline dividers. The pressed state (`aria-pressed`) fills with accent.

### Segmented controls
- Equal-width grid in a control-stroke frame. Each option is 36 px label type, with an optional 12 px muted sub line (for example "Depth / h at t", "Speed / |u| at t"). The selected option fills with accent. Used for display mode, rheology and resolution presets.

### Inputs / Fields
- **Style:** 36 px, 1 px control stroke, 4 px corner, panel fill, 4/8 px padding. Labels are 600 at 13 px above the field; help text is 12 px muted below.
- **With units:** numeric fields are right-aligned with no spinners, and the unit (°E, °N, m³, m, s) sits inside at the right in 12 px muted text.
- **Hover:** border turns ink. **Focus:** 2 px accent outline, 2 px offset (global). **Invalid:** err border plus 12 px err message.
- Checkboxes and ranges use the native control with accent-color (checkbox 18 px, range 28 px track height). The disclosure "More options" summary is 13 px 600 accent text.

### Cards
- **Option card** (DEM choice, list rows): hairline border, 8/12 px padding, radio left, name 600, meta 12 px muted, status pill right. Hover uses the control stroke. Checked: accent border on accent-weak.
- **Source card:** hairline border, 12 px padding. The head has the swatch ring, title and actions; fields sit below. The current source gets an accent border on accent-weak.
- **Run row:** hairline card with name link (600, ellipsis), status pill, 12 px meta and a 4 px accent minibar for progress.
- **Dropzone:** dashed control stroke on panel-2; accent dashed on accent-weak while dragging over.

### Estimate and readouts
- **Estimate:** a panel-2 block (4 px, 12 px padding) laid out as a 2-column grid of readouts (grid size, memory, runtime class) before the user commits.
- **Readout:** 12 px muted key, then the value (16 px 600; 22 px in Results readouts) with the unit muted, then a 12 px muted note (for example "tan φ_bed = 0.45", "h > 0.1 m").
- **Parameter list:** a two-column definition list at 13 px, muted terms and right-aligned values.

### Progress and phases
- Display-size elapsed clock. A 10 px pill track (panel-2, control stroke) with an accent fill scaled by progress (600 ms ease). While active, a moving diagonal hatch of on-accent at 22% runs across the fill; with unknown progress, a 30% sweep.
- Phase list: a 10 px ring per phase. Done is filled ok in ink text. Current is filled accent in 600 weight with a soft pulse. Pending is a muted control-stroke ring.

### Charts
- Inline SVG, 120 px tall. The title row shows the quantity and unit on the left and the peak in muted text on the right. Axes are 1 px ink, gridlines hairline, tick labels muted at 10.5 px. The series is a 1.75 px accent line, and the time cursor a dashed ink line. Clicking a chart seeks playback.

### Colourbar
- Lower right on the map (a full-width strip on phones), panel white at 94%, hairline border, Float shadow, 260 px. It contains: title with unit at 13 px 600; a 12 px gradient bar with a control-stroke frame; ink ticks with 12 px labels (end labels aligned to the bar ends); a muted note giving scale type, map name and citation, threshold outline, and masked release area.

### Badges and status
- **Badge** (on stage): panel white, control stroke, 4 px corner, 12 px 600. It names the current frame or state ("Envelope, 0–120 s"). The warn variant (warn stroke and text) is mandatory whenever thin-flow depth exaggeration is above 1× ("Flow depth ×N (first 10 m)").
- **Status pill:** 12 px 600, full pill, 1 px currentColor border, no fill. Colours: ok (completed/ready), accent (running/queued/processing), err (failed/interrupted), muted (cancelled).
- **Health pill** (System page): the same pill. Normal is ok, Warning is warn, Critical is err on an err-weak fill, the only filled pill, so a critical reading is found at a glance.

### System health
- **Summary strip:** a bordered panel-white grid of cells (auto-fit, min 170 px) divided by hairlines; each cell is a 12 px 600 muted term over an 18 px 600 value. Secondary parts of a value (the commit hash) are set as a muted unit. The first cell is the overall Condition pill.
- **Usage meter:** a 12 px bar in a control-stroke frame with hairline ticks every 10 %. The fill is ink, warn at the warning state and err at the critical state. The warning and critical limits are dashed 1.5 px warn / err verticals overhanging the bar by 4 px. The percentage sits right of the bar (600, 7ch, muted unit). A legend in the card head names Used, Warning limit and Critical limit, and a card foot states the thresholds in words.
- **Resource and service tables:** hairline rows, 12 px muted 600 headers, numeric columns right-aligned with muted units (the Unit Rule). Service details are a small definition list (term over value) in a fixed-width column.
- **Storage list:** label (600), a muted description with the file count, and the size right-aligned. "Clear caches" is a default button that turns into a danger "Confirm: clear …" on first press and acts on the second, then reports with a toast. It deletes only regenerable previews and playback bundles.
- **Not realtime:** no polling or timers. The page loads the cached reading (5 minutes) and states its age ("Measured 4 min ago"); Re-measure forces a new reading.

### Probe
- Hover readout on the map: panel white, control stroke, Float shadow, at least 200 px wide, 12 px definition list with muted terms and right-aligned values with units.

### Caption strip with figure actions (signature)
- A panel-white strip under the map with a hairline above, 13 px text up to 120ch. It opens with a bold lead ("Figure." / "Setup.") and lists DEM and CRS, physics, sources, grid, outcomes, display settings, lighting, a surface disclosure (for example "natural-colour relief synthesised from the DEM … not imagery"), code version, DEM hash and run id. On the right sit "Export figure" (PNG with furniture composited) and "Copy caption".

### Presenter bar
- A centred floating bar (panel white, control stroke, Float shadow, 16 px type) with a 24 px 600 time readout, play and mode segments. It spans the width on phones.

### Toast
- Ink fill with paper text, 13 px, 4 px corner, centred 24 px above the bottom. Used for short confirmations ("Figure caption copied.").

## Do's and Don'ts

### Do:
- **Do** treat every stage view as a figure: graticule with edge labels, scale bar with the north arrow above it at lower left, labelled index contours (every fifth interval), colourbar with unit, scale type and Crameri citation, and an auto-written caption with provenance.
- **Do** state the vertical exaggeration on every perspective view ("not to scale · vertical exaggeration N×").
- **Do** default the terrain to the DEM-derived Natural relief on terrain-only views and to greyscale hillshade under data, and disclose the synthetic surface in the caption.
- **Do** show flow depth true by default, and badge any exaggeration with the warn badge and in the caption.
- **Do** give each quantity its own Crameri map (batlow depth, imola speed, lajolla reversed envelope) and outline the flow edge at the stated threshold.
- **Do** put an SI unit on every number and set numerals tabular. Units go inside numeric inputs.
- **Do** use control stroke (at least 3:1) for every interactive boundary, and a 2 px accent focus outline with 2 px offset.
- **Do** keep motion functional and short (150 ms state transitions, 600 ms progress fill, ease `cubic-bezier(0.22, 1, 0.36, 1)`). Under `prefers-reduced-motion`, collapse transitions to 1 ms, stop the hatch and pulse, and replace the sweep with a static 35% fill. Playback never starts on its own.
- **Do** turn the legend into a strip below the map at ≤760 px, never overlapping the figure.

### Don't:
- **Don't** use a dark, game-like 3D canvas with floating chrome and decorative gradients as the default look.
- **Don't** use the accent for decoration, panel fills or data. Don't use rainbow, jet or other perceptually uneven colour maps.
- **Don't** colour the terrain under a data layer with full-saturation natural relief.
- **Don't** add a monospace face, uppercase tracked labels, or small labels above headings.
- **Don't** use shadows on in-panel cards or sections. The Float shadow is for stage overlays and the toast only.
- **Don't** use glyph or emoji icons. Icons are inline stroked SVG at 16 px.
- **Don't** let any number appear without its unit, or any figure export without its caption and furniture.
