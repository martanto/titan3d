---
target: viewer/template.html
total_score: 20
max_score: 40
na_heuristics: 
p0_count: 1
p1_count: 3
target_identity: "file:D:\\Projects\\titan3d\\viewer\\template.html"
target_fingerprint: "sha256:abd1f84d1ab38d2cb9ad2744ff0cb58d9472adb19d05026c1b130a21eff802a7"
target_path: "D:\\Projects\\titan3d\\viewer\\template.html"
timestamp: 2026-10-06T14-08-01Z
slug: viewer-template-html
---
# Critique — viewer/template.html (2026-10-06)

Method: dual-agent (A: design review sub-agent with browser · B: detector + browser evidence sub-agent)

## Design Health Score (Nielsen) — 20/40, Acceptable (bottom of band)
| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 2 | Loader never paints during sync decode; hangs forever on failure; play shows "Pause" when nothing loaded |
| 2 | Match system / real world | 2 | windows-1252 mojibake in every unit; no scale bar / north arrow; probe E/N relative km |
| 3 | User control & freedom | 2 | No reset view; top-down orbit = empty stage; silent auto-restart |
| 4 | Consistency & standards | 3 | Max-depth envelope vs per-time stats; Granflow vs titan3d naming |
| 5 | Error prevention | 2 | 4× thin-flow exaggeration default unmarked in scene; hard-coded run-agnostic copy |
| 6 | Recognition rather than recall | 3 | Shortcuts undocumented; probe has no in-scene marker |
| 7 | Flexibility & efficiency | 2 | No 1× rate, camera presets, export |
| 8 | Aesthetic & minimalist design | 2 | Stage is a dark silhouette; clock loudest element |
| 9 | Error recovery | 0 | CDN failure → dead page, no message |
| 10 | Help & documentation | 2 | "hover to probe" impossible on touch; stale model notes |

## Design Specificity Verdict
Authored, not interchangeable: survey-sheet identity (Archivo expanded, Plex Mono tabular numerals, basalt-oxide accent) and domain content (H/L vs tan φ_bed, conservation check, inundation threshold). Character lives only in the panel; the 3D stage is generic and broken (no map furniture, source marker, front cue, energy line).
Detector: exit 2, 16 warnings — undersized-ui-text ×7 (real), low-contrast ×8 (CLI false positives; browser found real 4.46:1 muted-on-stage), all-caps-body ×1 (borderline), em-dash-overuse (false positive: mojibake of ×). Overlay injected light + dark.

## Priority Issues
- [P0] Terrain/flow inside-out (winding a,c,b/b,c,d with Z=−y → downward faces culled, normals down → near-black). Fix: CCW-from-above winding. — /impeccable harden
- [P1] No doctype/charset/viewport/lang → mojibake, quirks mode, 8 px margin, mobile breakpoint never fires. — /impeccable harden
- [P1] Hard-coded run-agnostic copy; no provenance, downloads, or model-output disclaimer. — /impeccable clarify
- [P1] No loading/error/offline states; CDN dependencies. — /impeccable harden
- [P2] Max-depth mode mixes time bases; legend lacks backing; no scale bar/north arrow/crosshair; 4× depth default; playback starts at 40 s and loops after 2.5 s. — /impeccable layout, /impeccable colorize

## Persona Red Flags
- Analyst: deposit shown 2.5 s; no plan view w/ UTM, scale bar, north arrow; no export; no reset view; mojibake on projector; no disclaimer.
- Researcher: no in-domain/outflow split; no provenance; sparklines without axes; sqrt depth legend unlabelled; no comparison.
- Public: dark blob; jargon; no 1× rate; no landmarks; touch probe impossible; canvas traps scroll.

## Minor Observations
Clock width jumps; scrub announces tenths; sparkline seek mouse-only; navy speed low end vanishes on dark; 0.05 m discard vs 0.1 m inundation; stale probe; mobile camera crops cone; Space/arrows hijacked on buttons; fixed 50 m contours.

## Questions to Consider
- Open Results on the briefing artifact (plan-view max inundation with graticule, scale bar, source), 3D playback as "explain it"?
- Defend a 4× thickened flow in a briefing?
- Draw the H/L energy line in-scene?
