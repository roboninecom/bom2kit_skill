# Practical packing redesign

This work addresses handling complexity, not only shipping volume. The previous
selected layouts used 14 / 17 compound templates and 61 / 85 carton placements
for 101 / 102. These counts exclude the internal assembly of the compounds.
Factory packaging and declared component envelopes were visually conflated;
101 explicitly assumed twelve unmeasured factory servo cartons.

## Architecture

1. `packing_states.py` distinguishes source parts, factory cartons, packets and
   declared envelopes. Unmeasured alternative states are research-only. Component
   counts must remain unchanged.
2. `practical_geometry.py` derives source-hashed stable poses and full triangle
   projections. Uniform-density center-of-mass and planar support checks screen
   poses; they do not certify real load capacity or restraint.
3. `regular_patterns.py` generates floor patterns in repeated SKU poses and uses
   height-cost dynamic programming or repeated-copy splits for family subdivision.
   A directional access lane reserves finger space along one axis instead of
   expanding every inter-item gap in both axes; original grip replay still gates it.
   No unsecured multipart compound is handled as a rigid assembly. The existing
   bottom protection allowance becomes an explicitly specified EPE floor liner,
   included in the packaging BOM, without increasing or removing that allowance.
4. `irregular_floor.py` optionally proposes 2D contour layouts with PackingSolver.
   Conservative simplified silhouettes generate proposals; original CAD, full
   padded projections, quantities and allowed rotations remain independently
   checked. Mirroring is forbidden.
5. `practical_master.py` optionally calls isolated OR-Tools CP-SAT to select
   generated carton candidates with exact component coverage. Its finite-pool
   objective is a surrogate, not a proof of globally optimal packing. The carton
   tiler verifies the resulting actual type count and complete no-spacer block.
6. `practical_validation.py` replays actual source floor contact and vertical
   clearance for a declared pair of cylindrical fingertips. Stored pass flags
   never substitute for replay when producing assembly instructions.
7. `regular_stacks.py` permits bounded stacks only on actual flat source faces.
   Each interface specifies a protective sheet inside the existing two facing
   padding allowances. Sheet geometry/BOM, all source contacts and the complete
   upper load line are replayed. Actual density, sheet strength and manual sheet
   handling remain unverified. Count sheet placements and distinct cut sizes.
8. `regular_floor_pairs.py` proposes adjacent individually floor-supported parts.
   Bounding rectangles may overlap; original source clearance and proper rigid
   transforms must independently pass `source_floor_validation.py`. These are
   adjacent placements, not rigid multipart handling groups.
9. `practical_refinement.py` repacks against generated carton footprints and
   reruns the carton tiler to shrink the outer block when possible. No reference
   footprint is imported. This is bounded local improvement, not global search.
10. `common_floor.py` searches source-derived shared footprints, allocates partial
    floors with a coverage-diversified beam, crops underfilled cartons and rejoins
    them. A one-dimensional dynamic program rounds heights upward to limit sizes.
    Equal-footprint stacks compete with sliced layouts; neither is assumed best.
11. `regular_cavity_pairs.py` optionally seats an individual part on an actual
    horizontal internal face of another part. It checks full source clearance,
    a real protective sheet and support; final replay checks individual insertion
    and fingertip paths. Pairs are never carried as rigid preassemblies.
12. `source_surfaces.py` tries bounded 3D extreme-point placement on the floor or
    actual horizontal CAD faces. Several individually placed parts can share a
    lower part. A single-parent support tree checks complete loads; the removal
    sequence also checks every intermediate load state. Center-of-mass balance
    of only the final arrangement is insufficient. Bridging multiple parents,
    friction contacts and compliant deformation are outside this model.
    Source-hashed faces are cached, quarter-turn faces reuse the original polygons,
    and expensive contact intersections are deferred until a candidate survives
    broad-phase ranking. Free floor extremes are retained ahead of overlapping
    proposals. Height/occupied-volume objectives and failed-unit reorder probes
    are search heuristics, not additional acceptance evidence.
13. `access_repair.py` uses failed fingertip replay as a local repair signal.
    Repack only rejected cartons with margins derived from the unchanged finger
    radius, retain the other arrangements, retile and replay the complete kit.
    A smaller rejected layout is never promoted by relaxing its grip model.

The search varies family subdivision, carton count and nominal dimensions.
Current-run expanded carton footprints feed back into content placement.
A Pareto set retains operational improvements even when another layout is smaller.
Manual time and supplier price remain unknown until measured.

## Reproduction

```powershell
python scripts/prepare_stable_poses.py LIBRARY.json --output packaging-results/preparation --cache packaging-results/pose-cache
python scripts/design_practical_packaging.py LIBRARY.json POLICY.json EXPECTED.json --output packaging-results/practical --cache packaging-results/pose-cache --time-limit 120 --cartons 3 4 5 6 7 --types 2 3 4
```

Optional `--cp-sat-python PATH` uses the isolated OR-Tools interpreter.
`--irregular-solver PATH --irregular-budget 30` adds contour proposals.
`--rectangle-solver PATH --rectangle-budget 20` adds rectangle proposals.
`--stack-height-factor 1.5` permits bounded individually loaded stacks;
`--floor-pair-budget 60` adds adjacent supported pairs. These alternatives can
compete per carton with retained regular floors; enabling an experimental mode
does not force every family into that mode. Projected-contour experiments are
currently separate from stacks and pair modes.
`--packing-gap 0.2 --access-lane 6.4 --hand-border 9` is an experimental
directional-grip configuration, not a measured ergonomic requirement.
`--refinement-budget 60` adds joint carton/content refinement.
`--common-floor-budget 120 --common-floor-only` isolates footprint-first search.
`--source-surface-budget 120` adds bounded actual-surface 3D proposals.
`--access-repair-budget 90` optionally repairs rejected cartons, charging both
repacking and replay to that soft budget; the hard wall limit remains authoritative.
`--supported-nesting --stack-height-factor 1.5` tests individually inserted
supported pairs, separately from projected-contour and adjacent-floor-pair modes.
Flat-stack proposals also allow at most 25% footprint growth from a centered
overhang; actual contact and complete-load stability still gate acceptance.
These geometric models do not establish cushioning strength or load ratings.
`--wall-limit 900` supervises the entire invocation and stops its owned process
tree at the wall limit. A timeout preserves completed trial files but does not
certify any unfinished result or prove packing infeasibility.
`--packing-gap`, `--hand-border` and `--finger-radius` are declared experimental
parameters, not measured anthropometric requirements. Source preparation and
final independent replay are reported in addition to the proposal budget.
The practical workflow requires a positive `item_padding_mm` floor-liner allowance.

Each trial records support and access checks. Only passing trials enter the
verified frontier. A rejected trial is diagnostic evidence, not an operator plan.
The no-worse volume target remains unmet. See the measured
[four-hour report](practical-packing-four-hour-report.md).

## Current source revision

The 12 November 2026 upstream check found SO-ARM102 HEAD
`43252799d077e7f9971d7c695fd59f31413aa9b6`. Since the prior pinned revision,
the printed clamp, gear rack and nail CAD changed. The rack's source bounds
changed from approximately 4.5 x 9.35 x 61 to 4.4 x 13 x 61 mm. These are
printed components; the user-confirmed 106 mm purchased clamp is unchanged.
New sources and Git LFS digests are preserved separately under
`packaging-inputs/practical-round3/102/`. The new expected BOM pins all three
changed CAD revisions; historical layouts must not be called matching-current
comparisons without replay.
The historical 22.925616 L 102 layout was replayed without moving any part on
the current source library. The two updated rack instances collide, so that
layout is not a valid current-input baseline. A separate old-engine cold search
produced 24.978240 L in 771.881 seconds; this is a different search result.

## Limits

Stable solid geometry, free fingertip paths and closed cartons are necessary
screens, not transport qualification. Purchased envelopes can approximate flexible
or irregular contents. Material deformation, glove/wrist access, actual grasp
forces, shipping loads and manufacturing tolerances require separate evidence.
The previous source-based 101/102 no-worse objective remains open.
