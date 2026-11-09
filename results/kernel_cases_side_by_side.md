# SolidCraft kernel cases: OCCT replay vs SolidCraft's published results

OCCT 7.9.3 through FreeCAD 1.1.3's Part module, an independent replay of each case's recipe (`harness/kernelcases/replay.py`), graded against the case's own `expected.json` (`harness/kernelcases/run_cases.py`). One process per case, 120 s timeout.

SolidCraft columns: **docs** is `docs/kernel-cases.md` (generated; stale, it covers only 128 of these 334 cases); **gate** is the area's `KNOWN_FAILING` list (a case not listed passes the kernel-rig gate at the list's baseline). Gate failures marked `fail(continuity)` fail only the continuity check, which this replay does not grade.

Checks graded: body_count, volume, area, faces, shells, bbox, center_of_mass, validity, refusal (by any OCCT exception; the message is not compared). Not graded: continuity, surface_types, splines, watertight, edges/vertices, inspect results.

## Counts

| Area | Cases | OCCT pass | fail | error | invalid | crash | timeout | unsupported | uncertain (of the non-pass) | SolidCraft gate pass | SolidCraft docs pass / listed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| booleans | 72 | 72 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 72 | 47 / 55 |
| continuity | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 0 / 0 |
| crashes | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 2 / 2 |
| fillets | 204 | 116 | 10 | 31 | 6 | 1 | 0 | 40 | 4 | 194 | 28 / 35 |
| shell | 17 | 7 | 7 | 1 | 2 | 0 | 0 | 0 | 0 | 17 | 5 / 7 |
| solids | 3 | 2 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 3 | 0 / 0 |
| sweeps | 20 | 19 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 20 | 15 / 17 |
| tessellation | 9 | 9 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 9 | 9 / 9 |
| threads | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 2 / 3 |
| all | 334 | 234 | 17 | 32 | 8 | 1 | 0 | 42 | 4 | 324 | 108 / 128 |

## Every case

| Case | OCCT | OCCT detail | SolidCraft docs | SolidCraft gate | wall s |
|---|---|---|---|---|---|
| booleans/1107-join-hollow-hub-with-nine-blades | pass |  | pass | pass | 0.7 |
| booleans/114-extrude-join-on-curved-body-coincident-wall | pass |  | pass | pass | 0.2 |
| booleans/1279-cut-with-tool-cylinder-coaxial-with-hole | pass |  | fail: step 4 (solid.cylinder): SMLib boolean: SMLib's check refuses the result: 6 failed tests: SmFace::Test #33 Face has Coin | pass | 0.3 |
| booleans/13-split-body-by-a-plane | pass |  | pass | pass | 0.3 |
| booleans/1647-box-cylinder-general-intersect | pass |  | pass | pass | 0.2 |
| booleans/1649-crossing-cylinders-union-far-from-origin | pass |  | pass | pass | 0.2 |
| booleans/168-rim-touching-coin-along-a-circle-only | pass |  | fail: shells Coin: 2 (want 1); body_count 1 (want 2) | pass | 0.3 |
| booleans/1717-two-overlapping-sphere-cuts | pass |  | pass | pass | 0.3 |
| booleans/1730-cut-short-of-far-face-keeps-skin | pass |  | pass | pass | 0.2 |
| booleans/1865-tube-and-sector-meeting-along-cylinder-walls | pass |  | pass | pass | 0.3 |
| booleans/1910-coaxial-cylinders-intersect | pass |  | pass | pass | 0.2 |
| booleans/1949-extrude-side-drawn-in-collinear-pieces | pass |  | pass | pass | 0.2 |
| booleans/1949-tapered-extrude-side-in-collinear-pieces | pass |  | pass | pass | 0.2 |
| booleans/1984-near-coaxial-pin-overlaps-bore-wall | pass |  | pass | pass | 0.2 |
| booleans/1984-rivet-with-flush-heads-a-hair-off-its-hole | pass |  | pass | pass | 0.3 |
| booleans/2008-coaxial-cylinders-join-one-wall | pass |  | pass | pass | 0.2 |
| booleans/2564-joined-side-run-wrapping-past-loop-start | pass |  | pass | pass | 0.3 |
| booleans/2580-clip-round-small-hole-of-long-plate | pass |  | pass | pass | 0.3 |
| booleans/2583-taper-side-drawn-in-collinear-pieces | pass |  | pass | pass | 0.2 |
| booleans/2601-taper-with-start-offset | pass |  | pass | pass | 0.2 |
| booleans/2754-taper-extrude-line-arc-corner | pass |  | pass | pass | 0.2 |
| booleans/2810-taper-extrude-arcs-meeting-at-corners | pass |  | pass | pass | 0.2 |
| booleans/2826-cut-up-to-face-leaves-no-skin | pass |  | pass | pass | 0.2 |
| booleans/2896-join-arm-end-into-ring-wall | pass |  | pass | pass | 0.2 |
| booleans/2896-join-arm-end-near-ring-wall-gap | pass |  | pass | pass | 0.2 |
| booleans/2928-join-cap-touching-lips-with-offset-walls | pass |  | fail: volume_mm3 1066.022935 (want 769.468975) | pass | 0.3 |
| booleans/3027-pin-seated-line-to-line-in-bore | pass |  | pass | pass | 0.3 |
| booleans/307-tangent-hole-contacts-ring-against-grid | pass |  | fail: measure Plate: the operation failed: not supported yet: tessellation: face 0 (plane): triangulation does not (want measu | pass | 0.3 |
| booleans/308-blind-cut-ending-inside-a-cylinder | pass |  | pass | pass | 0.3 |
| booleans/3092-ring-on-perforated-plate | pass |  | fail: measure Plate: the operation failed: not supported yet: tessellation: face 1 (plane): triangulation does not (want measu | pass | 2.6 |
| booleans/3175-cut-beside-sealed-void | pass |  | pass | pass | 0.2 |
| booleans/3303-inward-cut-of-frustum-top-face | pass |  | pass | pass | 0.2 |
| booleans/3327-cut-ending-flush-with-side-wall | pass |  | pass | pass | 0.2 |
| booleans/3447-split-along-plane-of-a-face | pass |  | pass | pass | 0.3 |
| booleans/3455-join-of-64-separate-pegs | pass |  | hang: no result after 20 s | pass | 13.0 |
| booleans/3456-deep-cut-through-drilled-taper-leaves-base | pass |  | pass | pass | 0.4 |
| booleans/3460-cut-by-lid-with-coincident-walls-and-half-moon-tabs | pass |  | pass | pass | 0.4 |
| booleans/3485-boss-joined-on-rod-top-keeps-side-whole | pass |  | pass | pass | 0.2 |
| booleans/3497-collinear-cylinders-partial-height-intersection | pass |  | pass | pass | 0.2 |
| booleans/3497-pin-overlapping-bore-by-20-microns | pass |  | pass | pass | 0.2 |
| booleans/3526-intersect-keeps-every-lump | pass |  | pass | pass | 0.2 |
| booleans/3665-join-extrude-column-on-floor-and-curved-walls | pass |  | fail: measure Housing: the operation failed: not supported yet: tessellation: face 9 (plane): boundary crosses its (want measu | pass | 0.2 |
| booleans/3671-intersect-tool-in-top-face-beside-rib | pass |  | pass | pass | 0.2 |
| booleans/3702-board-in-cavity-of-filleted-rim-case | pass |  | pass | pass | 0.2 |
| booleans/3703-two-face-extrudes-join-keep-the-step | pass |  | pass | pass | 0.2 |
| booleans/3729-extrude-to-point-on-step-edge | pass |  | pass | pass | 0.2 |
| booleans/3850-cross-cut-touching-round-side | pass |  | pass | pass | 0.4 |
| booleans/3850-hole-through-wall-after-cross-cut | pass |  | pass | pass | 0.5 |
| booleans/3887-ring-standing-on-perforated-plate | pass |  | fail: measure Plate: the operation failed: not supported yet: tessellation: face 1 (plane): triangulation does not (want measu | pass | 2.8 |
| booleans/4008-symmetric-revolve-cut-ends-in-side-face | pass |  | pass | pass | 0.2 |
| booleans/4095-slab-cut-standing-off-a-bore-r10 | pass |  | pass | pass | 0.2 |
| booleans/423-through-all-cut-must-not-reach-behind-sketch-plane | pass |  | pass | pass | 0.3 |
| booleans/4286-split-body-and-join-pieces-back | pass |  | not in docs table | pass | 0.3 |
| booleans/4313-join-3x3-grid-of-overlapping-rings | pass |  | not in docs table | pass | 0.6 |
| booleans/4322-join-rectangle-cornered-on-slanted-edge | pass |  | not in docs table | pass | 0.2 |
| booleans/4347-slab-joined-under-tapered-pyramid-base | pass |  | not in docs table | pass | 0.2 |
| booleans/4468-box-minus-bore-measures-exact | pass |  | not in docs table | pass | 0.2 |
| booleans/451-cut-block-crossing-hollow-sphere-tool | pass |  | pass | pass | 0.3 |
| booleans/451-cut-block-inside-hollow-sphere-tool | pass |  | pass | pass | 0.2 |
| booleans/4654-split-body-by-its-own-face-extended | pass |  | not in docs table | pass | 0.2 |
| booleans/4701-join-disc-on-tapered-ring | pass |  | not in docs table | pass | 0.2 |
| booleans/4829-cut-from-flat-top-bounded-by-fillet-edge | pass |  | not in docs table | pass | 0.2 |
| booleans/4877-pocket-on-tab-joined-to-chamfered-disc | pass |  | not in docs table | pass | 0.2 |
| booleans/4927-slot-cut-through-chamfered-tube-wall | pass |  | not in docs table | pass | 0.2 |
| booleans/500-coaxial-cylinder-cut-from-thin-disc | pass |  | pass | pass | 0.2 |
| booleans/5126-join-menger-sponge-level-3 | pass |  | not in docs table | pass | 64.7 |
| booleans/5197-join-flush-chord-layers | pass |  | not in docs table | pass | 1.0 |
| booleans/5291-join-pin-on-prism-face-beside-blind-bore | pass |  | not in docs table | pass | 0.2 |
| booleans/5295-intersect-bar-with-two-mirrored-outlines | pass |  | not in docs table | pass | 0.3 |
| booleans/5322-cut-with-a-5000-mm-tool | pass |  | not in docs table | pass | 0.2 |
| booleans/5413-join-rib-flush-on-channel-floor | pass |  | not in docs table | pass | 0.4 |
| booleans/5462-press-pull-inner-wall-of-rectangular-opening | pass |  | not in docs table | pass | 0.2 |
| continuity/g0-box-edge-crease | pass |  | not in docs table | pass | 0.2 |
| continuity/g1-built-one-short-chamfer | pass |  | not in docs table | pass | 0.2 |
| continuity/g1-round-meets-planes | pass |  | not in docs table | pass | 0.2 |
| crashes/140-join-pad-hanging-past-the-edge | pass |  | pass | pass | 0.2 |
| crashes/3540-cut-with-coincident-cylinder-face | pass |  | pass | pass | 0.4 |
| crashes/4547-join-revolved-rings-touching-along-a-circle | pass |  | not in docs table | pass | 0.2 |
| fillets/1008-fillet-tray-floor-and-three-of-four-corners | pass |  | pass | pass | 0.3 |
| fillets/1080-chamfer-beside-openings-fits | pass |  | pass | pass | 0.2 |
| fillets/1080-chamfer-runs-into-openings-cut-by-them | error | raised at step 5: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | not in docs table | pass | 0.2 |
| fillets/1080-fillet-notched-block-top-outline-r7 | fail | volume 10672.905668 (want 10584.365507, rel 0.001) — silently wrong: valid solid, 88 mm3 too much material (same fillet without the notch is exact) | not in docs table | pass | 0.3 |
| fillets/1080-fillet-notched-block-top-outline-r8 | invalid | invalid bodies ['Body1']; volume 10154.883168 (want 10198.718039, rel 0.001) | not in docs table | pass | 0.2 |
| fillets/1113-chamfer-arc-top-edge-full-wall-height | error | raised at step 6: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | not in docs table | pass | 0.3 |
| fillets/1191-fillet-both-rims-of-a-tube-top | pass |  | pass | pass | 0.2 |
| fillets/1207-fillet-bar-top-edge-after-boss-arc-round-partial-chain | unsupported | replay: tangent_chain: false where the chain continues (OCCT's fillet always propagates along tangent edges) | not in docs table | pass | 0.3 |
| fillets/1207-fillet-bar-top-edge-after-boss-arc-round-r0-5 | pass |  | not in docs table | pass | 0.4 |
| fillets/1207-fillet-bar-top-edge-after-boss-arc-round | pass |  | not in docs table | pass | 0.5 |
| fillets/1207-fillet-bar-top-edge-and-boss-arc-together-curvature-corners | unsupported | replay: fillet corner g2 | not in docs table | pass | 0.2 |
| fillets/1207-fillet-bar-top-edge-and-boss-arc-together-reduce-fit | unsupported | replay: solid.fillet params ['fit'] | not in docs table | pass | 0.2 |
| fillets/1207-fillet-bar-top-edge-and-boss-arc-together-taper-fit | unsupported | replay: solid.fillet params ['fit'] | not in docs table | pass | 0.2 |
| fillets/1207-fillet-bar-top-edge-and-boss-arc-together | pass |  | not in docs table | pass | 0.3 |
| fillets/1207-fillet-box-end-edge-into-unblended-round-partial-chain | unsupported | replay: tangent_chain: false where the chain continues (OCCT's fillet always propagates along tangent edges) | not in docs table | pass | 0.3 |
| fillets/1207-fillet-box-end-edge-into-unblended-round | pass |  | not in docs table | pass | 0.2 |
| fillets/1207-fillet-concave-arc-at-boss | pass |  | unsupported: not supported yet: step 3 (solid.fillet): not supported yet: the fillet is larger than the faces beside its edges allow | pass | 0.3 |
| fillets/1207-fillet-straight-edge-ending-on-boss | pass |  | pass | pass | 0.3 |
| fillets/1262-fillet-boss-bottom-arc | pass |  | fail: step 3 (solid.fillet): SMLib fillet: operation: SMLib failed (status 1001) | pass | 0.4 |
| fillets/1390-chamfer-hole-rim-touching-bottom | pass | OCCT raised where a refusal is right (message not compared: OCCError: 21Standard_ProgramError TopOpeBRepDS_DataStructure::Point) | pass | pass | 0.3 |
| fillets/1557-fillet-vertical-corners-after-bottom-rounds | error | raised at step 6: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | fail: faces 14 (want 18) | pass | 0.3 |
| fillets/1667-fillet-rim-line-beside-quarter-turns | pass |  | fail: volume_mm3 1779142.942702 (want 1776536.244667) | pass | 0.2 |
| fillets/1668-fillet-both-sides-of-thin-wall-r7 | invalid | invalid bodies ['Case']; volume -36840.687320 (want 39509.938040, rel 1e-06) | not in docs table | pass | 0.2 |
| fillets/1668-fillet-both-sides-of-thin-wall | invalid | invalid bodies ['Case']; volume -37623.153395 (want 39530.539816, rel 0.001) | pass | pass | 0.2 |
| fillets/1668-fillet-outer-top-edge-of-thin-wall-r7-past-inside-corner | invalid | should refuse; made an invalid result (bodies ['Case']) | not in docs table | pass | 0.2 |
| fillets/190-fillet-disc-rim-past-its-2mm-wall | error | raised at step 2: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | not in docs table | pass | 0.2 |
| fillets/190-fillet-rim-as-tall-as-wall | error | raised at step 2: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | pass | pass | 0.2 |
| fillets/1986-chamfer-arc-edge-of-joined-sectors | pass |  | pass | pass | 0.2 |
| fillets/199-fillet-uses-up-end-face | error | raised at step 2: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | pass | pass | 0.2 |
| fillets/237-fillet-concave-edge-between-two-cylinders | pass |  | pass | pass | 0.2 |
| fillets/2708-fillet-curvature-continuous-angled-ends | unsupported | replay: solid.fillet params ['type'] | pass | pass | 0.2 |
| fillets/2719-chamfer-as-wide-as-corner-round | error | raised at step 3: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | pass | pass | 0.2 |
| fillets/2752-fillet-rim-of-flat-cut-on-sphere | pass |  | fail: step 3 (solid.fillet): SMLib fillet: operation: SMLib failed (status 1001) | pass | 0.2 |
| fillets/2797-chamfer-two-distances-circular-rim | pass |  | pass | pass | 0.2 |
| fillets/2811-fillet-rib-roots | unsupported | replay: solid.extrude params ['side', 'thickness', 'thin'] | pass | pass | 0.3 |
| fillets/2852-fillet-outer-round-concentric-with-inner | pass |  | pass | pass | 0.2 |
| fillets/2852-fillet-outer-round-r30-past-inner-round-refused | pass | OCCT raised where a refusal is right (message not compared: OCCError: 15StdFail_NotDone BRep_API: command not done) | not in docs table | pass | 0.3 |
| fillets/2893-chamfer-distance-and-angle-past-the-wall-refused | unsupported | replay: solid.chamfer params ['angle'] | not in docs table | pass | 0.2 |
| fillets/2893-chamfer-two-distances-across-the-whole-top-refused | fail | should refuse (larger than); OCCT built a valid result: V=5654.87, bodies=1 — OCCT builds a valid solid for a 10 mm setback on an r10 rim (the cone would end in a point) | not in docs table | pass | 0.2 |
| fillets/2893-chamfer-two-distances-elliptical-rim | pass |  | not in docs table | pass | 0.3 |
| fillets/2893-chamfer-two-distances-past-the-bottom | error | raised at step 2: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | not in docs table | pass | 0.2 |
| fillets/2893-chamfer-two-distances-past-the-top-refused | invalid | should refuse; made an invalid result (bodies ['Body1']) | not in docs table | pass | 0.2 |
| fillets/2907-chamfer-two-end-outlines-rounded-top | pass |  | pass | pass | 0.3 |
| fillets/318-fillet-plate-top-outline-as-tall-as-wall | error | raised at step 2: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | not in docs table | pass | 0.2 |
| fillets/324-fillet-over-hole-cut-by-overlong-cylinder | pass |  | not in docs table | pass | 0.3 |
| fillets/324-fillet-over-hole-overlap | pass |  | unsupported: not supported yet: step 6 (solid.fillet): not supported yet: the fillet is larger than the faces beside its edges allow | pass | 0.3 |
| fillets/3276-chamfer-edge-of-1mm-protrusion-on-joined-l | pass |  | pass | pass | 0.2 |
| fillets/334-fillet-top-outline-after-concave-rounds | pass |  | pass | pass | 0.5 |
| fillets/3369-fillet-edge-ends-on-tangent-seam | pass |  | pass | pass | 0.2 |
| fillets/3435-fillet-larger-than-top-ring | pass | OCCT raised where a refusal is right (message not compared: OCCError: 15StdFail_NotDone BRep_API: command not done) | pass | pass | 0.2 |
| fillets/3655-chamfer-edge-order-box | fail | faces 26 (want 18) — volume right; OCCT adds a corner facet at each of the 8 corners where SolidCraft's three chamfer planes meet in a point | pass | pass | 0.3 |
| fillets/3868-chamfer-concave-edge-adds-material | pass |  | pass | pass | 0.2 |
| fillets/4055-chamfer-bar-edge-over-joined-pin | error | raised at step 3: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | unsupported: not supported yet: step 3 (solid.chamfer): not supported yet: the chamfer is larger than the faces beside its edges allo | pass | 0.2 |
| fillets/4101-chamfer-tapered-plug-corners | pass |  | pass | pass | 0.3 |
| fillets/4174-fillet-cylinder-base-arc-ending-at-block-edge | pass |  | not in docs table | pass | 0.3 |
| fillets/4265-chamfers-meeting-on-a-face-as-tall-as-both | error | raised at step 2: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | not in docs table | pass | 0.2 |
| fillets/477-fillet-cube-corner-rounds-as-wide-as-faces-reduce-fit | unsupported | replay: solid.fillet params ['fit'] | not in docs table | pass | 0.1 |
| fillets/477-fillet-cube-corner-rounds-as-wide-as-faces-refused | pass | OCCT raised where a refusal is right (message not compared: OCCError: 15StdFail_NotDone BRep_API: command not done) | not in docs table | pass | 0.2 |
| fillets/4782-fillet-bar-edge-wider-than-both-faces | error | raised at step 2: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | not in docs table | fail(continuity): [fail] continuity_order: got Box: no null seams want >= g1 at every blend seam | 0.2 |
| fillets/4782-fillet-end-top-edge-half-the-wall | pass |  | not in docs table | pass | 0.2 |
| fillets/4782-fillet-full-round-two-end-verticals-reduce-fit | unsupported | replay: solid.fillet params ['fit'] | not in docs table | pass | 0.2 |
| fillets/4782-fillet-full-round-two-end-verticals-taper-fit | unsupported | replay: solid.fillet params ['fit'] | not in docs table | pass | 0.2 |
| fillets/4782-fillet-full-round-two-end-verticals | error | raised at step 2: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | not in docs table | pass | 0.2 |
| fillets/4782-fillet-two-end-verticals-past-a-full-round-reduce-fit | unsupported | replay: solid.fillet params ['fit'] | not in docs table | pass | 0.2 |
| fillets/4782-fillet-two-end-verticals-past-a-full-round | pass | OCCT raised where a refusal is right (message not compared: OCCError: 15StdFail_NotDone BRep_API: command not done) | not in docs table | pass | 0.2 |
| fillets/485-fillet-d-prism-top-outline-arc-and-flat | pass |  | pass | pass | 0.4 |
| fillets/4859-chamfer-inside-corner-of-thin-wall-ring | pass |  | not in docs table | pass | 0.2 |
| fillets/5129-fillet-concave-edge-where-cylinder-meets-block | pass |  | not in docs table | pass | 0.2 |
| fillets/5157-chamfer-bottom-loop-of-box-with-rounded-corners | pass |  | not in docs table | pass | 0.2 |
| fillets/5158-fillet-adjacent-plate-edges-as-thick-as-plate | error | raised at step 10: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | not in docs table | pass | 0.2 |
| fillets/5158-fillet-round-just-past-a-10mm-face | error | raised at step 2: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | not in docs table | pass | 0.2 |
| fillets/5181-two-distance-chamfer-runs-past-tapered-sides | pass |  | not in docs table | pass | 0.2 |
| fillets/5236-fillet-cylinder-end-with-its-own-radius | pass |  | not in docs table | pass | 0.2 |
| fillets/5300-fillet-tube-rim-as-wide-as-its-wall | error | raised at step 6: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | not in docs table | pass | 0.2 |
| fillets/556-fillet-edge-ending-on-curved-boss | pass |  | pass | pass | 0.2 |
| fillets/783-fillet-pick-far-from-any-edge-refused | unsupported | engine-level refusal (no kernel call): no edge at (10.000, -15.000, 10.000) | pass | pass | 0.2 |
| fillets/851-chamfer-arc-and-top-front-2 | pass |  | not in docs table | pass | 0.2 |
| fillets/851-chamfer-arc-top-edge-9-5 | pass |  | not in docs table | pass | 0.2 |
| fillets/851-chamfer-knife-edge-tip-2-box-less-cylinder | error (uncertain) | raised at step 3: OCCError: 15StdFail_NotDone BRep_API: command not done — chamfer of a zero-angle (tangent) knife edge, defined by SolidCraft through ball contacts; OCCT refuses (NotDone) any chamfer of a G1 edge | not in docs table | pass | 0.2 |
| fillets/851-chamfer-knife-edge-tip-5 | fail (uncertain) | volume 9581.494716 (want 9027.684392, rel 0.001) — chamfer of a zero-angle (tangent) knife edge: the expected answer sets the chamfer back where a ball of radius d touches the faces; OCCT measures d along each face, a different definition there (OCCT removed 10 mm3, expe | not in docs table | pass | 0.2 |
| fillets/851-fillet-arc-and-upright | pass |  | not in docs table | pass | 0.2 |
| fillets/851-fillet-arc-then-top-front | pass |  | not in docs table | pass | 0.3 |
| fillets/851-fillet-arc-top-edge-9-5 | pass |  | not in docs table | pass | 0.3 |
| fillets/851-fillet-arc-top-edge-full-wall-height | error | raised at step 6: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | not in docs table | pass | 0.2 |
| fillets/851-fillet-knife-edge-tip-r2 | pass |  | not in docs table | pass | 0.2 |
| fillets/851-fillet-top-front-and-arc | pass |  | not in docs table | pass | 0.3 |
| fillets/851-fillet-top-front-and-front-left-upright | pass |  | not in docs table | pass | 0.2 |
| fillets/851-fillet-top-front-and-upright | pass |  | not in docs table | pass | 0.2 |
| fillets/851-fillet-top-front-then-front-left-upright | pass |  | not in docs table | pass | 0.2 |
| fillets/851-fillet-top-front-then-upright | pass |  | not in docs table | pass | 0.3 |
| fillets/854-fillet-revolved-disc-both-rims-full-round | error | raised at step 5: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | not in docs table | pass | 0.2 |
| fillets/862-fillet-curvature-continuous-box-edge | unsupported | replay: solid.fillet params ['type'] | pass | pass | 0.2 |
| fillets/896-fillet-smooth-seam-refused | pass | OCCT raised where a refusal is right (message not compared: OCCError: 16Standard_Failure There are no suitable edges for chamfer or fillet) | pass | pass | 0.2 |
| fillets/9-fillet-corner-curvature-with-reduce-fit | unsupported | case names a missing capability: solid.fillet builds `corner: g2` with `fit: exact` only | not in docs table | unsupported: [unsupported] solid.fillet builds `corner: g2` with `fit: exact` only | 0.2 |
| fillets/9-fillet-corner-curvature-with-taper-fit | unsupported | case names a missing capability: solid.fillet builds `corner: g2` with `fit: exact` only | not in docs table | unsupported: [unsupported] solid.fillet builds `corner: g2` with `fit: exact` only | 0.2 |
| fillets/9-fillet-corner-r5-curvature-default-setback | unsupported | replay: fillet corner g2 | not in docs table | pass | 0.1 |
| fillets/9-fillet-corner-setback-1-5-not-past-r2-curvature | unsupported | replay: solid.fillet params ['setbacks'] | not in docs table | pass | 0.1 |
| fillets/9-fillet-corner-setback-1-5-not-past-r2-rolling | unsupported | replay: solid.fillet params ['setbacks'] | not in docs table | pass | 0.2 |
| fillets/9-fillet-corner-setback-2-not-past-r2-curvature | unsupported | replay: solid.fillet params ['setbacks'] | not in docs table | pass | 0.1 |
| fillets/9-fillet-corner-setback-2-not-past-r2-rolling | unsupported | replay: solid.fillet params ['setbacks'] | not in docs table | pass | 0.1 |
| fillets/926-chamfer-top-edge-ending-on-boss-wall-above-it | pass |  | not in docs table | pass | 0.2 |
| fillets/926-fillet-top-edge-ending-on-boss-wall-above-it | pass |  | not in docs table | pass | 0.3 |
| fillets/cov-chamfer-concave-edge-through-up-down-joined-squares | crash | process exit 1 — OCCT/FreeCAD process exits (status 1, no exception) inside makeChamfer | not in docs table | pass | 0.2 |
| fillets/cov-fillet-arc-edge-on-an-oblique-cut-of-a-bar | pass |  | not in docs table | pass | 0.3 |
| fillets/cov-fillet-exact-coaxial-cones-r2 | pass |  | not in docs table | pass | 0.2 |
| fillets/cov-fillet-exact-cone-cylinder-sharing-a-ball-r1 | pass |  | not in docs table | pass | 0.3 |
| fillets/cov-fillet-exact-cylinders-touching-at-a-point-r1 | fail | volume 13442.687609 (want 13442.703131, rel 1e-06) — precision only: rel error 1.2e-6 vs the case's 1e-6 (OCCT blend surfaces are approximations) | not in docs table | pass | 0.5 |
| fillets/cov-fillet-exact-oblique-plane-cone-rim-r1-5 | fail | volume 3549.930635 (want 3549.917409, rel 1e-06) — precision only: rel error 3.7e-6 vs the case's 1e-6 | not in docs table | pass | 0.3 |
| fillets/cov-fillet-exact-oblique-plane-cylinder-rim-r2 | fail | volume 6214.510622 (want 6214.410264, rel 1e-06) — precision only: rel error 1.6e-5 vs the case's 1e-6 | not in docs table | pass | 0.3 |
| fillets/cov-fillet-exact-sphere-coaxial-cone-r3 | pass |  | not in docs table | pass | 0.2 |
| fillets/cov-fillet-exact-sphere-plane-rim-r2 | pass |  | not in docs table | pass | 0.2 |
| fillets/cov-fillet-g2-corner-beside-a-cylinder | unsupported | replay: solid.fillet params ['type'] | not in docs table | fail: [fail] step 6 (solid.fillet): the open setback corner is not a closed solid, as on SMLib d01d7b0 | 0.2 |
| fillets/cov-fillet-g2-mixed-corner | unsupported | replay: solid.fillet params ['type'] | not in docs table | unsupported: [unsupported] refused as on SMLib d01d7b0: a G2 corner is set back only where every edge meeting it  | 0.2 |
| fillets/cov-fillet-g2-oblique-three-edge-corner | unsupported | replay: solid.fillet params ['type'] | not in docs table | unsupported: [unsupported] refused on solidcore: its three edges meet at different wedge angles, and one curvatur | 0.2 |
| fillets/cov-fillet-g2-pocket-corner | unsupported | replay: solid.fillet params ['type'] | not in docs table | fail(continuity): [fail] continuity_order: G1 at one seam where the corner patch meets a contact face (g2 wanted), as  | 0.3 |
| fillets/cov-fillet-pocket-floor-round-corners-r3-chain-r1 | pass |  | not in docs table | pass | 0.3 |
| fillets/cov-fillet-section-chamfer-box-edge-3 | pass |  | not in docs table | pass | 0.2 |
| fillets/cov-fillet-section-chamfer-pipe-on-plate-2 | fail (uncertain) | volume 40264.491343 (want 40241.716477, rel 1e-07) — chamfer between a plane and a cylinder at 53 deg: the expected answer sets back by ball contact, OCCT by distance along each face; the 5.7e-4 volume difference is that definition, not a failure | not in docs table | pass | 0.2 |
| fillets/cov-fillet-section-curvature-boss-root-r2 | unsupported | replay: solid.fillet params ['type'] | not in docs table | pass | 0.2 |
| fillets/cov-fillet-section-curvature-box-edge-r3 | unsupported | replay: solid.fillet params ['type'] | not in docs table | pass | 0.1 |
| fillets/cov-fillet-section-curvature-pipe-on-plate-r2 | unsupported | replay: solid.fillet params ['type'] | not in docs table | pass | 0.2 |
| fillets/cov-fillet-section-round-box-edge-r3 | pass |  | not in docs table | pass | 0.2 |
| fillets/cov-fillet-section-round-pipe-on-plate-r2 | pass |  | not in docs table | pass | 0.2 |
| fillets/cov-fillet-tee-pipe-r8-into-pipe-r20-r3 | fail | volume 129830.103856 (want 129829.952906, rel 1e-06) — precision only: rel error 1.2e-6 vs the case's 1e-6 | not in docs table | pass | 0.3 |
| fillets/cov-fillet-turn-mitre-boss-base-r1 | pass |  | not in docs table | pass | 0.4 |
| fillets/cov-fillet-turn-mitre-pocket-floor-corners-r1 | pass |  | not in docs table | pass | 0.2 |
| fillets/cov-fillet-turn-swept-boss-base-r1 | unsupported | replay: solid.fillet params ['turn'] | not in docs table | pass | 0.2 |
| fillets/cov-fillet-turn-swept-pocket-sharp-corner-refused-r1 | unsupported | replay: solid.fillet params ['turn'] | not in docs table | pass | 0.2 |
| fillets/cov-fillet-variable-box-edge-1-to-5-on-its-cone | unsupported | replay: solid.fillet params ['radius2', 'start', 'type'] | not in docs table | pass | 0.2 |
| fillets/cov-junction-boss-tilt-00-root-round | pass |  | not in docs table | pass | 0.2 |
| fillets/cov-junction-boss-tilt-20-root-round | error | raised at step 3: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | not in docs table | fail: [fail] fillet status 1001 on a cylinder tilted 20 degrees into the plate, as on SMLib | 0.3 |
| fillets/cov-junction-boss-tilt-40-root-round | error | raised at step 3: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | not in docs table | pass | 0.3 |
| fillets/cov-junction-tee-equal-round | error | raised at step 3: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | not in docs table | pass | 0.2 |
| fillets/cov-junction-tee-oblique-round | pass |  | not in docs table | pass | 0.3 |
| fillets/cov-junction-tee-oblique-unequal-round | pass |  | not in docs table | pass | 0.6 |
| fillets/cov-junction-tee-offset-round | pass |  | not in docs table | pass | 0.6 |
| fillets/cov-junction-tee-unequal-round | pass |  | not in docs table | pass | 0.3 |
| fillets/cov-junction-wedge-030-chamfer | pass |  | not in docs table | pass | 0.2 |
| fillets/cov-junction-wedge-030-round | pass |  | not in docs table | pass | 0.2 |
| fillets/cov-junction-wedge-045-chamfer | pass |  | not in docs table | pass | 0.2 |
| fillets/cov-junction-wedge-045-round | pass |  | not in docs table | pass | 0.2 |
| fillets/cov-junction-wedge-060-chamfer | pass |  | not in docs table | pass | 0.2 |
| fillets/cov-junction-wedge-060-round | pass |  | not in docs table | pass | 0.2 |
| fillets/cov-junction-wedge-075-chamfer | pass |  | not in docs table | pass | 0.2 |
| fillets/cov-junction-wedge-075-round | pass |  | not in docs table | pass | 0.2 |
| fillets/cov-junction-wedge-090-chamfer | pass |  | not in docs table | pass | 0.2 |
| fillets/cov-junction-wedge-090-round | pass |  | not in docs table | pass | 0.2 |
| fillets/cov-junction-wedge-105-chamfer | pass |  | not in docs table | pass | 0.2 |
| fillets/cov-junction-wedge-105-round | pass |  | not in docs table | pass | 0.2 |
| fillets/cov-junction-wedge-120-chamfer | pass |  | not in docs table | pass | 0.2 |
| fillets/cov-junction-wedge-120-round | pass |  | not in docs table | pass | 0.2 |
| fillets/cov-junction-wedge-135-chamfer | pass |  | not in docs table | pass | 0.2 |
| fillets/cov-junction-wedge-135-round | pass |  | not in docs table | pass | 0.2 |
| fillets/cov-junction-wedge-150-chamfer | pass |  | not in docs table | pass | 0.2 |
| fillets/cov-junction-wedge-150-round | pass |  | not in docs table | pass | 0.2 |
| fillets/cov-junction-y-junction-120-round | pass |  | not in docs table | unsupported: [unsupported] refused as on SMLib: the faces between the three intersection curves narrow to nothing | 0.4 |
| fillets/every-block-cylinder-crease-block-top-edge-r2-curvature | unsupported | replay: solid.fillet params ['type'] | not in docs table | pass | 0.2 |
| fillets/every-block-cylinder-crease-block-top-edge-r2-no-tangent-chain | pass |  | not in docs table | pass | 0.2 |
| fillets/every-block-cylinder-crease-concave-arc-r2 | pass |  | not in docs table | pass | 0.3 |
| fillets/every-block-cylinder-crease-cylinder-top-rim-r2 | pass |  | not in docs table | pass | 0.2 |
| fillets/every-block-cylinder-crease-top-edge-after-arc-round-r1 | error | raised at step 4: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | not in docs table | pass | 0.3 |
| fillets/every-block-cylinder-tangent-block-top-edge-r2-no-tangent-chain | pass | OCCT raised where a refusal is right (message not compared: OCCError: 15StdFail_NotDone BRep_API: command not done) | not in docs table | pass | 0.2 |
| fillets/every-block-cylinder-tangent-concave-arc-r2-no-tangent-chain | invalid (uncertain) | invalid bodies ['Block']; volume 17845.692557 (want 19091.962003, rel 0.001) — SolidCraft's chain stops where the concave arc runs on tangentially into convex edges; OCCT's fillet always propagates along tangent edges, so it attempts a different blend (it does return an invalid solid without raisin | not in docs table | pass | 0.4 |
| fillets/every-block-cylinder-tangent-concave-arc-r2-partial-chain | unsupported | replay: tangent_chain: false where the chain continues (OCCT's fillet always propagates along tangent edges) | not in docs table | pass | 0.2 |
| fillets/every-boss-root-round-r10-as-tall-as-boss | error | raised at step 3: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | not in docs table | pass | 0.2 |
| fillets/every-boss-root-round-r2 | pass |  | not in docs table | pass | 0.2 |
| fillets/every-boss-top-rim-r2 | pass |  | not in docs table | pass | 0.2 |
| fillets/every-box-all-twelve-edges-r2 | pass |  | not in docs table | pass | 0.2 |
| fillets/every-box-corner-three-edges-chamfer-2 | fail | faces 10 (want 9) — OCCT adds a 3.46 mm2 corner facet (volume 23825.33 vs 23826, within tolerance); faces 10 vs 9 | not in docs table | pass | 0.2 |
| fillets/every-box-corner-three-edges-r3-curvature-setback-3-5 | unsupported | replay: solid.fillet params ['setbacks'] | not in docs table | unsupported: [unsupported] refused since solidcore c0d3cc0124 (passed at a445bdaac6); tracked in #13522 | 0.2 |
| fillets/every-box-corner-three-edges-r3-curvature-setback-3-refused | unsupported | replay: solid.fillet params ['setbacks'] | not in docs table | pass | 0.2 |
| fillets/every-box-corner-three-edges-r3-tangent | pass |  | not in docs table | pass | 0.2 |
| fillets/every-box-edge-r3-curvature | unsupported | replay: solid.fillet params ['type'] | not in docs table | pass | 0.2 |
| fillets/every-chamfer-box-edge-2 | pass |  | not in docs table | pass | 0.2 |
| fillets/every-chamfer-box-edge-two-distances-3-1-flipped | pass |  | not in docs table | pass | 0.2 |
| fillets/every-chamfer-box-edge-two-distances-3-1 | pass |  | not in docs table | pass | 0.2 |
| fillets/every-chamfer-pocket-rim-4-9-fits | pass |  | not in docs table | pass | 0.2 |
| fillets/every-chamfer-pocket-rim-5-5-past-the-floor | error | raised at step 3: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | not in docs table | pass | 0.2 |
| fillets/every-chamfer-pocket-rim-5-full-depth | error | raised at step 3: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | not in docs table | pass | 0.2 |
| fillets/every-chamfer-pocket-rim-two-distances-2-1 | pass |  | not in docs table | pass | 0.2 |
| fillets/every-fillet-after-fillet-curvature-front-then-side-r3-partial-chain | unsupported | replay: solid.fillet params ['type'] | not in docs table | pass | 0.2 |
| fillets/every-fillet-after-fillet-curvature-front-then-side-r3 | unsupported | replay: solid.fillet params ['type'] | not in docs table | pass | 0.1 |
| fillets/every-fillet-after-fillet-front-r3-then-vertical-r2 | pass |  | not in docs table | pass | 0.2 |
| fillets/every-fillet-after-fillet-front-then-vertical-r2 | pass |  | not in docs table | pass | 0.2 |
| fillets/every-fillet-after-fillet-vertical-then-front-r2 | pass |  | not in docs table | pass | 0.2 |
| fillets/every-hole-both-rims-chamfer-1 | pass |  | not in docs table | pass | 0.2 |
| fillets/every-hole-both-rims-r1 | pass |  | not in docs table | pass | 0.2 |
| fillets/every-hole-top-rim-chamfer-10-full-depth | error | raised at step 3: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | not in docs table | pass | 0.3 |
| fillets/every-hole-top-rim-chamfer-9-9-fits | pass |  | not in docs table | pass | 0.2 |
| fillets/every-hole-top-rim-r1-curvature | unsupported | replay: solid.fillet params ['type'] | not in docs table | pass | 0.2 |
| fillets/every-hole-top-rim-r1 | pass |  | not in docs table | pass | 0.2 |
| fillets/every-hole-top-rim-r10-as-deep-as-plate | error | raised at step 3: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | not in docs table | pass | 0.2 |
| fillets/every-hole-top-rim-r12-past-plate-bottom | error | raised at step 3: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | not in docs table | pass | 0.2 |
| fillets/every-l-bracket-both-bends-r3-r8-concentric | pass |  | not in docs table | pass | 0.2 |
| fillets/every-l-bracket-front-inner-outline-after-bend-round-r1 | pass |  | not in docs table | pass | 0.3 |
| fillets/every-l-bracket-inside-bend-r3-curvature | unsupported | replay: solid.fillet params ['type'] | not in docs table | pass | 0.2 |
| fillets/every-l-bracket-inside-bend-r3 | pass |  | not in docs table | pass | 0.2 |
| fillets/every-l-bracket-inside-bend-r35-uses-both-faces | error | raised at step 3: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | not in docs table | pass | 0.2 |
| fillets/every-l-bracket-inside-bend-r36-refused | pass | OCCT raised where a refusal is right (message not compared: OCCError: 15StdFail_NotDone BRep_API: command not done) | not in docs table | pass | 0.2 |
| fillets/every-l-bracket-outside-bend-r5 | pass |  | not in docs table | pass | 0.2 |
| fillets/every-pocket-floor-and-rim-edges-r2 | pass |  | not in docs table | pass | 0.2 |
| fillets/every-pocket-floor-edges-r2 | pass |  | not in docs table | pass | 0.2 |
| fillets/every-pocket-rim-edges-r2 | pass |  | not in docs table | pass | 0.2 |
| fillets/every-pocket-rim-edges-r5-as-deep-as-pocket | error | raised at step 3: OCCError: 15StdFail_NotDone BRep_API: command not done — OCCT raised: OCCError: 15StdFail_NotDone BRep_API: command not done | not in docs table | pass | 0.2 |
| shell/1494-shell-box-with-cylinder-on-edge-line | fail | volume 12687.937603 (want [8856.7, 8864.7], rel 0.001) — valid solid, cylinder part not hollowed (12688 vs 8857..8865) | fail: step 3 (solid.shell): SMLib shell: operation: SMLib failed (status 1001) | pass | 0.2 |
| shell/1525-shell-box-with-rounds-chamfer-and-fillet | pass |  | pass | pass | 1.0 |
| shell/1972-shell-one-half-sphere-leaves-the-other | pass |  | pass | pass | 0.2 |
| shell/3103-shell-tapered-cylinder | pass |  | pass | pass | 0.2 |
| shell/316-shell-open-beside-a-bottom-round-r2-4-larger-than-the-wall-steps | fail | volume 11832.246325 (want 4446.399483, rel 0.001) — OCCT's MakeThickSolid (FreeCAD makeThickness) returned the body unchanged without raising. | not in docs table | pass | 0.3 |
| shell/316-shell-open-beside-a-bottom-round-r2-as-large-as-the-wall-steps | fail | volume 11882.890822 (want 4394.890822, rel 0.001) — OCCT's MakeThickSolid (FreeCAD makeThickness) returned the body unchanged without raising. | not in docs table | pass | 0.6 |
| shell/316-shell-open-beside-a-bottom-round-smaller-than-the-wall | fail | volume 11933.694671 (want 4445.694671, rel 0.001) — OCCT's MakeThickSolid (FreeCAD makeThickness) returned the body unchanged without raising. | not in docs table | pass | 0.3 |
| shell/3506-split-body-then-shell-both-halves | pass |  | pass | pass | 0.2 |
| shell/4009-closed-shell-internal-void | pass |  | fail: step 5 (solid.shell): invalid parameters for `solid.shell`: select 1…1000 faces | pass | 0.2 |
| shell/4010-shell-open-at-through-hole-wall | pass |  | pass | pass | 0.2 |
| shell/4377-shell-cone-frustum-open-both-ends | pass |  | not in docs table | pass | 0.2 |
| shell/4711-shell-block-with-hole-clipped-by-notch | fail | should refuse (shell: the 2 mm walls would meet along a line (between a hole and the side, for example), which leaves no solid there; use a thinner or thicker wall, or move the feature); OCCT built a  — OCCT's MakeThickSolid (FreeCAD makeThickness) returned the body unchanged without raising. | not in docs table | pass | 0.2 |
| shell/545-shell-ring-cut-frame-open-at-an-outer-wall | fail | volume -59122.500000 (want 21044.000000, rel 1e-06) — OCCT's thick solid comes out inside-out (volume -59122.5) yet passes isValid | not in docs table | pass | 0.2 |
| shell/616-shell-open-a-rib-side-face-of-a-lid | invalid | invalid bodies ['Lid']; volume 12021.214401 (want [3951.8, 3985.5], rel 0.001) | not in docs table | pass | 0.5 |
| shell/cov-shell-pocket-whose-floor-falls-to-a-drain | error | raised at step 14: OCCError: BRep_API: command not done — OCCT raised: OCCError: BRep_API: command not done | not in docs table | pass | 0.2 |
| shell/cov-shell-trough-whose-floor-falls-to-a-drain | invalid | invalid bodies ['Trough']; volume 249047.303896 (want 37962.272215, rel 1e-05) — OCCT's MakeThickSolid (FreeCAD makeThickness) returned the body unchanged without raising. | not in docs table | pass | 0.3 |
| shell/cov-shell-up-down-joined-squares-open-at-a-side-wall | fail | volume 6000.000000 (want [765.36, 767.24], rel 0.001) — OCCT's MakeThickSolid (FreeCAD makeThickness) returned the body unchanged without raising. | not in docs table | pass | 0.3 |
| solids/cov-cone-frustum-along-x | pass |  | not in docs table | pass | 0.2 |
| solids/cov-cone-full-apex-negative-height | pass |  | not in docs table | pass | 0.2 |
| solids/cov-cone-zero-height-refused | unsupported | engine-level refusal (no kernel call): height must not be zero | not in docs table | pass | 0.1 |
| sweeps/1853-revolve-cut-half-a-slot-about-its-centreline | pass |  | fail: step 8 (solid.revolve): SMLib export: pcurve: pcurve of loop 0 use 0 (Some([-10.0, 1.8369701987210297e-16, 10.0]) to Som | pass | 0.2 |
| sweeps/1866-revolve-half-slot-profile-180 | pass |  | pass | pass | 0.2 |
| sweeps/1866-revolve-half-slot-profile-90 | pass |  | pass | pass | 0.2 |
| sweeps/2183-revolve-profile-crosses-the-axis-refused | pass | OCCT raised where a refusal is right (message not compared: OCCError: BRep_API: command not done) | pass | pass | 0.2 |
| sweeps/2295-revolve-cut-torus-by-an-overlapping-ring | pass |  | pass | pass | 0.2 |
| sweeps/2607-revolve-axis-outside-the-sketch-plane-refused | unsupported | engine-level refusal (no kernel call): the Y axis does not lie in the sketch plane | pass | pass | 0.2 |
| sweeps/2947-revolve-300-degrees-intersected-by-a-plate | pass |  | pass | pass | 0.2 |
| sweeps/3156-revolve-join-end-faces-flush-with-a-face | pass |  | pass | pass | 0.2 |
| sweeps/3191-revolve-cut-leaves-a-cone | pass |  | pass | pass | 0.2 |
| sweeps/3528-revolved-dome-cut-by-a-ball-on-its-seam | pass |  | pass | pass | 0.2 |
| sweeps/4007-revolve-half-disc-horn-torus-270-degrees | pass |  | fail: step 5 (solid.revolve): SMLib revolve: SMLib's check refuses the result: 2 failed tests: SmSurfOfRevolution::Test #2 Par | pass | 0.2 |
| sweeps/4008-symmetric-revolve-cut-end-faces-in-the-side-face | pass |  | pass | pass | 0.2 |
| sweeps/4689-revolve-profile-with-edge-on-axis-keeps-flat-faces-whole | pass |  | not in docs table | pass | 0.2 |
| sweeps/4708-revolve-cut-slot-through-shelled-cup-wall | pass |  | not in docs table | pass | 0.2 |
| sweeps/487-cut-disc-by-revolved-adjacent-profiles | pass |  | pass | pass | 0.2 |
| sweeps/487-revolve-two-adjacent-profiles-on-the-axis | pass |  | pass | pass | 0.2 |
| sweeps/494-extrude-the-flange-face-of-a-fresh-revolve | pass |  | pass | pass | 0.3 |
| sweeps/726-revolve-full-turn-planar-faces-whole | pass |  | pass | pass | 0.2 |
| sweeps/726-revolve-partial-turn-planar-faces-whole | pass |  | pass | pass | 0.2 |
| sweeps/cov-revolve-circle-touching-its-axis-a-quarter-turn | pass |  | not in docs table | pass | 0.2 |
| tessellation/1263-concave-arc-knife-edge-plate | pass |  | pass | pass | 0.3 |
| tessellation/1648-sphere-touches-box-edge-union | pass |  | pass | pass | 0.2 |
| tessellation/1753-bowl-rim-cut-by-cylinder | pass |  | pass | pass | 0.3 |
| tessellation/1813-sphere-lens-thinner-than-tolerance | pass |  | pass | pass | 0.2 |
| tessellation/2528-stadium-joined-with-overlapping-cylinder | pass |  | pass | pass | 0.2 |
| tessellation/311-ramp-cut-cylinder-blank | pass |  | pass | pass | 0.2 |
| tessellation/466-revolved-cone-tip-stays-smooth | pass |  | pass | pass | 0.1 |
| tessellation/784-stl-open-edges-filleted-and-drilled | pass |  | pass | pass | 0.3 |
| tessellation/819-cup-pocket-splits-wall-seam | pass |  | pass | pass | 0.2 |
| threads/3368-faceted-prism-pocket-cut-and-boss-join | pass |  | pass | pass | 10.1 |
| threads/3368-faceted-prism-with-bore-and-cross-hole | pass |  | pass | pass | 10.6 |
| threads/3368-two-faceted-prisms-cut-then-joined | pass |  | hang: no result after 20 s | pass | 34.2 |

Gate baselines: booleans: solidcore pin de85a3e00, tests/kernel-cases run by `cargo xtask kernel-cases`, x86_64 Linux.; continuity: solidcore pin de85a3e00, tests/kernel-cases run by `cargo xtask kernel-cases`, x86_64 Linux.; crashes: solidcore pin de85a3e00, tests/kernel-cases run by `cargo xtask kernel-cases`, x86_64 Linux.; fillets: solidcore pin 8ddce9016, tests/kernel-cases run by `cargo xtask kernel-cases`, x86_64 Linux.; shell: solidcore pin de85a3e00, tests/kernel-cases run by `cargo xtask kernel-cases`, x86_64 Linux.; solids: solidcore pin de85a3e00, tests/kernel-cases run by `cargo xtask kernel-cases`, x86_64 Linux.; sweeps: solidcore pin de85a3e00, tests/kernel-cases run by `cargo xtask kernel-cases`, x86_64 Linux.; tessellation: solidcore pin de85a3e00, tests/kernel-cases run by `cargo xtask kernel-cases`, x86_64 Linux.; threads: solidcore pin de85a3e00, tests/kernel-cases run by `cargo xtask kernel-cases`, x86_64 Linux.
