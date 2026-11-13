# Volumetric nesting study

**Status: the complete-kit no-worse-than-Alan objective is not achieved.**
These are computational results on frozen source inputs. Physical shipping
retention, cushion strength, manufacturing tolerances and manual labor remain
unqualified. Final selection is pending the remaining bounded experiments.

## Complete-kit results

| Kit / option | Shipping volume, L | Inner cartons / sizes | Contact sheets | Decision |
| --- | ---: | ---: | ---: | --- |
| 101 frozen baseline | 28.974770 | 4 / 4 | 0 | Comparison control |
| 101 current practical candidate | 28.099062 | 4 / 4 | 0 | Provisional guide selection |
| 101 smaller-volume alternative | 27.654264 | 7 / 7 | 2 | More cartons and handling |
| 101 Alan reference | 19.423040 | 7 / not audited | Not counted | Nominal target |
| 102 retained baseline | 36.126552 | 4 / 4 | 0 | New candidates have not improved it |
| 102 Alan reference | 20.063360 | 7 / not audited | Not counted | Nominal target |

The current four-carton 101 candidate reduces volume by 3.02% against the frozen
baseline, but remains 44.67% above Alan's nominal volume. Retained 102 remains
80.06% above its nominal target. Alan's matching source poses, BOM and protection
are not fully replayable; nominal volume is not a verified equivalence claim.

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

## Verification and rejected shortcuts

The latest full suite passed **287 tests**, including installed CP-SAT and
PackingSolver backends (`full-tests-v10.log`). A changed 102 BOM with one additional
servo produced a verified 109-unit layout; this demonstrates quantity-aware
regeneration, not reference-volume achievement.

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
