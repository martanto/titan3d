# Audit — viewer/template.html (2026-10-06)

Evidence: impeccable detector (CLI + in-browser overlay), playwright-cli inspection at 1440×900 and 390×844 (light, dark, reduced motion, CDN failure), source review.

## Audit Health Score — 9/20 (Poor: major overhaul)

| # | Dimension | Score | Key finding |
|---|---|---|---|
| 1 | Accessibility | 2 | Canvas probe mouse-only; Space/arrows hijacked when buttons have focus; scrub/sliders 16 px and checkbox 13 px tall (< 24 px, WCAG 2.5.8); no `lang`; muted text 4.46:1 on the light stage |
| 2 | Performance | 2 | Per-frame CPU loop over every vertex + attribute uploads; synchronous decode and ~12 M-cell front scan at load; three r147 UMD + pako + fonts from CDNs |
| 3 | Responsive | 1 | No viewport meta → 820 px breakpoint never fires on phones; probe hidden on touch; `touch-action: none` on a 62vh canvas traps page scroll |
| 4 | Theming | 3 | Real tokens and a designed dark theme; scene colours hard-coded in JS; hairlines 1.49:1 (light) / 1.35:1 (dark) against the panel |
| 5 | Implementation integrity | 1 | Inside-out mesh winding; no doctype/charset (quirks mode, mojibake); hard-coded, stale copy; eyebrow above H1; unthemed browser defaults (8 px body margin) |

**Implementation Integrity Verdict: fail.** The visual language is coherent and product-specific, but the 3D scene does not render as built, and every unit string is corrupted.

## Findings by severity (P0 ×1, P1 ×4, P2 ×6, P3 ×3)

- **[P0] Inside-out terrain/flow mesh.** Location: `gridGeom` index loop (L256–259). Impact: the primary artifact is invisible or near-black. Fix: counter-clockwise winding from above; compute normals from the bed. → /impeccable harden
- **[P1] Missing doctype, charset, viewport, lang.** Location: L1. Impact: mojibake in units (×, °, ², φ, –); quirks mode; mobile layout never activates. WCAG 3.1.1. → /impeccable harden
- **[P1] Hard-coded run copy, no provenance or downloads.** Location: L1, L127–129, L167, L107. Impact: wrong descriptions for every real run; no hand-off. → /impeccable clarify
- **[P1] No loading, error or offline state.** Location: L172–175 (CDN), init IIFE. Impact: dead page on internal or offline servers. → /impeccable harden
- **[P1] Keyboard hijack.** Location: L395–399. Impact: Space toggles play instead of activating a focused button. WCAG 2.1.1. → /impeccable harden
- **[P2] Touch targets below 24 px** (scrub, ranges, checkbox); play button 38 px. WCAG 2.5.8. → /impeccable adapt
- **[P2] Probe mouse-only; sparkline seek mouse-only and unnamed.** WCAG 2.1.1, 4.1.2. → /impeccable harden
- **[P2] Muted text 4.46:1 on the light stage; 10 px wayfinding labels.** WCAG 1.4.3. → /impeccable typeset
- **[P2] Per-frame CPU geometry rewrite.** It does not scale to 640² bundles. → /impeccable optimize
- **[P2] Max-depth mode keeps per-time stats; default 4× depth exaggeration unmarked.** → /impeccable layout
- **[P2] Hairline and control borders below 3:1** (WCAG 1.4.11). → /impeccable colorize
- **[P3] Scrub `aria-valuetext` missing; favicon 404; fixed 50 m contour interval.**

## Patterns
- Document plumbing was never set up (single-file template), so everything browser-level falls back to defaults.
- Interaction is designed mouse-first; touch and keyboard have gaps in the probe, the seek and the targets.

## Positive findings
- Token system with a designed dark theme; tabular numerals; units as muted suffixes.
- Labelled controls, `aria-pressed` mode group, `:focus-visible` rings in the accent colour, reduced motion starts paused.
- Domain-correct readouts (H/L vs tan φ_bed, conservation check).

## Recommended actions
1. [P0/P1] /impeccable harden — winding, document plumbing, loading/error/offline states, keyboard scoping
2. [P1] /impeccable clarify — copy from run metadata, provenance, downloads, disclaimer
3. [P2] /impeccable adapt — touch targets, touch probe, scroll trap
4. [P2] /impeccable layout — map furniture, max-mode semantics, legend chip, depth-exaggeration default
5. [P2] /impeccable optimize — GPU-side heights and frame streaming (done in the new engine)
6. /impeccable polish — final pass
