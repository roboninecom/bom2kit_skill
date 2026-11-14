# Volumetric nesting study

**Status: the complete-kit no-worse-than-Alan objective is not achieved.**
These are computational results on frozen source inputs. Physical shipping
retention, cushion strength, manufacturing tolerances and manual labor remain
unqualified. The primary guides retain grouping rather than selecting by volume alone.
They are geometric drafts, not packaging released for shipment.

## Complete-kit results

| Kit / option | Shipping volume, L | Inner cartons / sizes | Contact sheets | Decision |
| --- | ---: | ---: | ---: | --- |
| 101 frozen baseline | 28.974770 | 4 / 4 | 0 | Comparison control |
| 101 selected grouped candidate | 28.852296 | 4 / 4 | 0 | Primary guide; grouping proxies unchanged |
| 101 lower-volume four-carton alternative | 28.099062 | 4 / 4 | 0 | More scattered and mixed types |
| 101 fewer-carton alternative | 29.144258 | 3 / 3 | 1 | Uses an actual eleven-part nesting combination |
| 101 smaller-volume alternative | 27.654264 | 7 / 7 | 2 | More cartons and handling |
| 101 Alan reference | 19.423040 | 7 / not audited | Not counted | Nominal target |
| 102 retained baseline | 36.126552 | 4 / 4 | 0 | New candidates have not improved it |
| 102 Alan reference | 20.063360 | 7 / not audited | Not counted | Nominal target |

The selected four-carton 101 candidate reduces volume by 0.42% against the frozen
baseline, but remains 48.55% above Alan's nominal volume. Retained 102 remains
80.06% above its nominal target. Alan's matching source poses, BOM and protection
are not fully replayable; nominal volume is not a verified equivalence claim.

The same source-derived type labels give these organization proxies:

| 101 option | Type-cohabitation pairs | Additional spatial fragments | Split type groups |
| --- | ---: | ---: | ---: |
| Baseline / selected grouped | 49 | 4 | 0 |
| 28.099 L four-carton alternative | 72 | 11 | 2 |
| 29.144 L three-carton alternative | 89 | 11 | 0 |
| 27.654 L seven-carton alternative | 34 | 8 | 2 |

Fragments use a declared 10 mm bounds-adjacency rule. These are organization
proxies, not measured kitting labor or retention. The new practical Pareto
filter preserves these tradeoffs instead of letting lower volume dominate a
better-grouped layout; missing measurements are not treated as perfect grouping.

Inputs retain 79 packing units for 101 and 108 for 102, including packet contents.
The comparison preserves the 106 mm clamp frame, 1.5 mm inner walls, 7 mm outer
wall, 15 mm foam on six faces, 1 mm source padding and 0.2 mm additional gap.
There are no inter-carton spacers. The engine uses original individual parts,
not fictitious rigid compound objects. Purchased envelopes remain estimates.

## What changed

- Full 3D occupancy correlation proposes independent source orientations and
  translations; original triangles, containment and clearance decide acceptance.
- Actual internal support faces allow protected nesting below the contact plane.
  Source-bound combinations default to six separately handled parts; an optional
  twelve-part ceiling has produced independently replayed eleven-part subsets.
- Common-height motif selection, motif-aware partitioning and finite CP-SAT
  carton selection connect local combinations with the complete kit.
- PackingSolver rectangle can translate motif envelopes while retaining their
  individual source poses, directional access lanes and contact sheets.
- Final repacking now compares the original motif and a floor alternative at
  complete-block scope. A lower floor layout no longer silently replaces a
  narrower nesting pattern merely because it fits an expanded carton.
- Required accessory sets remain together. A smaller 28.210944 L proposal was
  rejected because it split the ArUco set; it is not a deliverable result.
- R3 guides show close-ups extracted from motifs actually used in the frozen
  result. Catalog examples are labeled separately as subset experiments.
- An eleven-part combination is actually used in the complete 29.144258 L
  three-carton alternative: one supported pair plus nine floor-supported parts,
  not eleven mutually nested parts. Its separately replayed subset control is
  11.799882 L versus 10.737408 L (-9.00%). A fourteen-part extension gave
  29.608704 L for the full kit, so increasing group size was not a reliable gain.

## Local gains and negative controls

These controls retain the same complete source subset and protection. Their
floor search is bounded, not proven optimal; they are not complete-kit gains.

| Source subset | Replayed floor control, L | Nested, L | Change |
| --- | ---: | ---: | ---: |
| 101: six original printed parts | 8.309265 | 7.290456 | -12.26% |
| 102: SO102.02.040 + SO102 Trigger | 2.220680 | 1.992144 | -10.29% |
| 102: two SO102.02.080-01 parts | 3.860325 | 4.024272 | +4.25% |
| Two original declared clamp proxies | 3.037968 | 3.122080 | +2.77% |

All listed subsets passed original-source, support and modeled finger-access
replay. Clamp cavities are assumptions in the retained source proxy, not measured
manufactured CAD. Their pair is floor-supported; no envelope is reclassified as
a load-bearing carton. A smaller local bounding envelope can still produce a
larger protected shipping box, as the negative controls demonstrate.

## Remaining causes of the gap

1. **Local savings do not automatically survive carton selection.** A compact
   combination can raise the common height, split another useful combination,
   or force larger neighboring cartons. Preserving alternatives fixes one
   selection error but does not make the joint heuristic globally optimal.
   In the actual 101 three-carton option, inner-carton exterior volumes total
   17.081 L versus 17.950 L for the selected four-carton design (-0.869 L).
   But volume outside those cartons rises from 10.902 to 12.063 L (+1.161 L)
   with the longer 563 x 286 x 181 mm outer shape. Net shipping volume is
   0.292 L worse. Printed-carton volume itself rises by 0.170 L because all
   43 printed units share a 78 mm-high carton. This is measured carton
   arithmetic, not a claim that the entire overhead is wasted space.
2. **Large unused regions remain inside boxes.** The frozen 102 baseline has
   at least 10.158 L outside protected source bounds inside its cavities. Another
   14.726 L lies outside inner cavities, including walls and the protection shell.
   These are geometric decompositions, not claims that all empty space is usable.
3. **Handling can erase geometric gains.** Dense candidates sometimes exhaust
   the unchanged 90-second vertical finger-path check. Repairs can enlarge the
   carton substantially. A timeout is not proof that a human cannot pack it.
4. **The physical model is limited.** Purchased-part envelopes hide usable shape
   detail; general tilted insertion, compliant wrapping, frictional bracing and
   multi-parent support are not validated. Those omissions cannot be replaced
   with an unsupported claim of transport feasibility.
5. **Loose-part retention is still a known problem.** The selected layouts have
   demonstrated free translations above the diagnostic 5 mm threshold for
   78 of 79 units in 101 and 106 of 108 in 102. The 101 maximum rises from
   137.1 to 201.1 mm despite its small volume reduction. The screen ignores
   friction/compliance and is not a shipping test, but a closed, tightly tiled
   carton block alone does not restrain the parts inside it.

## Verification and rejected shortcuts

The latest full suite passed **289 tests**, including installed CP-SAT and
PackingSolver backends (`full-tests-final.log`). A changed 102 BOM with one additional
servo produced a verified 109-unit layout; this demonstrates quantity-aware
regeneration, not reference-volume achievement. Its 38.342952 L, four-carton
result was independently replayed again in 34.63 seconds on the final geometry
checker; replay time is not design time.

Native psacking and sparrow-3d did not complete real-part benchmarks because their
required build environments were unavailable. The SciPy CPU implementation is
separate. General OMPL SE(3) motion planning remains unimplemented.

A native continuous-collision probe using installed `python-fcl 0.7.0.11`, BVH
meshes, translational motion and conservative advancement missed a thin-wall
collision with free endpoints. That configuration was rejected, and the existing
distance-bounded sweep remains authoritative. This is evidence about the tested
configuration, not a claim that every FCL CCD configuration fails. See the
[binding API](https://github.com/BerkeleyAutomation/python-fcl) and
[request parameters](https://github.com/BerkeleyAutomation/python-fcl/blob/master/src/fcl/collision_data.py).
Caching fingertip candidates alone produced no material speed improvement in
the measured controls and was not merged into the engine.
Caching immutable original-source FCL geometry within one replay reduced one
102 baseline check from 21.81 to 17.56 seconds. The moving geometry and complete
distance-bounded sweeps remain unchanged. A hard candidate still exhausted its
budget; neither this observation nor the concurrent timings establish a general
speedup. Per-grip time/step caps did not validate the hard candidate and were not
integrated.

## Runtime and selection

Recorded complete search invocations, including their own checks: selected 101
grouped candidate 305.73 s; four-carton 28.099 L alternative 368.6 s; eleven-part
three-carton alternative 621.0 s; seven-carton alternative 489.1 s. A new 102
four-carton search reproduced 36.126552 L in 484.96 s; the retained baseline's
original invocation was 537.72 s. These exclude preceding catalog generation
and use prepared inputs/pose caches. They are not end-to-end cold timings.

For the selected concept run, recorded preparation is 5.51 s, search 48.57 s and
replay 250.32 s. The changed-BOM run records 6.16 s preparation, 36.31 s search and
207.13 s replay (250.05 s total). Detailed refinement/assignment counters overlap
these phases and must not be added again. Practical-planner runs do not expose
the same disjoint search/replay breakdown.

A final search reproduction on committed engine revision `bbf4ce2` completed in
340.80 s (5.04 s preparation, 47.68 s search, 286.82 s replay). It reproduced
the selected 101 result's exact original-source poses, carton dimensions and
foam geometry at 28.852296 L. Engine files remained unchanged during that run;
its other frontier options are recorded rather than assumed deterministic.

The fresh 101 eleven-part extension took 182.54 s, and the fresh 102 extension
took 182.13 s. Source extraction occurred before this four-hour study, so its
time is not measured here. Failed backend setup, unsuccessful candidates and
verification probes remain part of the four-hour work, not hidden setup cost.

## Evidence and reproduction

Private evidence is under `packaging-results/volume-round5/`; frozen inputs are
under `packaging-inputs/volume-round5/`. `session.json` records source hashes,
the base revision and the deadline. Individual `run.json` files record parameters,
code provenance and replay outcomes. A `wall-limit.json` is a terminated search,
not a verified frontier. Partial trials require independent replay.

Use [the reproducible workflow](volumetric-nesting.md). Preparation, catalog
discovery, failed trials, search, repair and replay must be counted separately.
Prepared-mesh and voxel-cache runs are not cold-start speed measurements, and
concurrent bounded runs are not controlled performance comparisons.

Final PDF guides, comparison and their source/result bindings are assembled in
`packaging-results/volume-round5/final/`. Source CAD and generated artifacts stay
ignored. The draft PR is not a claim of goal completion.
The [requirement audit](volumetric-nesting-goal-audit.md) lists unmet conditions
and concrete, unimplemented next experiments.
