---
target: visual-guideline model page
total_score: 28
max_score: 36
na_heuristics: 9
p0_count: 0
p1_count: 0
target_identity: "file:D:\\Projects\\titan3d\\frontend\\src\\ui\\visual-guideline.ts"
target_fingerprint: "sha256:feb92962bc49d31f9b639c473e530db46cc480f3aee74bde5ed006e8bfea1a08"
target_path: "D:\\Projects\\titan3d\\frontend\\src\\ui\\visual-guideline.ts"
timestamp: 2026-10-09T02-53-13Z
slug: frontend-src-ui-visual-guideline-ts
---
Method: dual-agent (A: /root/design_review; B: /root/technical_review).

Target: frontend/src/ui/visual-guideline.ts. Read mode. Review scored the page before the final follow-up fixes; no full-page rerating was performed.

Design specificity: authored for titan3d's scientific-figure identity. Units, data dependencies, terrain geometry and physical assumptions make this product-specific.

| Heuristic | Score | Finding before fixes |
| --- | --- | --- |
| Visibility of status | 3 | Mobile detail could remain outside the viewport. |
| Match to real world | 3 | Numerical vocabulary assumed experience. |
| Control and freedom | 4 | Free selection, section jumps and angle reset. |
| Consistency | 3 | Eight pipeline steps versus six modelling stages needed explanation. |
| Error prevention | 3 | Bounded controls and illustrative scope labels. |
| Recognition over recall | 3 | Some formula terms lacked local definitions. |
| Flexibility and efficiency | 3 | Long mobile travel to selected detail. |
| Aesthetic/minimalist design | 3 | Cohesive, though duplicated selectors add length. |
| Error recovery | n/a | Explanatory surface has no submitted data or recovery workflow. |
| Help/documentation | 3 | Useful worked example and interpretation checks. |
| Total | 28/36 | Baseline score; not a post-fix score. |

Strengths: pipeline first gives orientation; terrain/release and the two clocks explain common misconceptions; friction assumptions and omitted physics are explicit.

Priority issues (both resolved):
1. P2 navigation feedback/accessibility: mobile detail was out of view and section jumps left keyboard focus behind. Mobile selection now scrolls/focuses detail; section jumps focus the requested heading. Browser checks passed.
2. P2 local comprehension: flux/CFL/SSP-RK2, k/r/g_eff and spreading/convergence needed definitions. Added local definitions without adding sections. Also explained the eight-versus-six stage counts.

Cognitive load: five section links, eight pipeline steps and six walkthrough choices are grouped but make a long page. Keep the expandable example; further beginner sections would add duplication.

Personas: first-time readers faced a numerical-vocabulary valley; mobile and keyboard readers faced disconnected detail updates. These findings are resolved. Analysts benefit from units, provenance and conditional-result language.

Minor observations: the mobile diagram scrolls sideways with an explicit hint and duplicate readable selectors. Native live regions can be verbose. Overlay findings in the hidden viewer shell are outside this guide's scope.

Assessment B: CLI detector returned [] (0 findings). Desktop/mobile light/dark had no document overflow or clipped nodes. All eight selections synchronized, Enter activated rows, and ArrowRight changed the basal-angle slider. Mutable browser detector injection succeeded. Four shadow findings were existing viewer-shell controls; gray-on-color and cramped-padding were stylistic signals without a demonstrated guide defect. Preview /api/health returned 502 without a backend; no guide JavaScript exception was found.

Fix verification: Assessment A checked its four individual findings and reported all resolved with no material regression in those changes. This was a fix-list verification, not a whole-page rescore.

Questions skipped: two priority issues; both addressed under the already authorized polish scope.
