# Independent design implementation status

The original objective remains open. No new complete-kit comparison has passed.
This document records executable progress, not acceptance of the finished product.

## Implemented foundation

`python -m bom2kit design-envelopes request.json --output OUTPUT --time-limit 5`
generates outer carton dimensions from protected rectangular units. The request
contains no container, reference, grouping or initial poses. Unknown fields are
rejected. Candidate shelves and a dimension lattice come from item geometry;
the existing supported rectangular solver improves candidates. Every retained
result is independently validated. Walls, protection, top allowance and external
manufacturing increments are preserved.

Example request:

```json
{
  "units": "mm",
  "items": [
    {"id": "protected-part", "quantity": 4, "dimensions_mm": [10, 10, 10], "allowed_rotations": "fixed"}
  ],
  "policy": {
    "wall_mm": 1.5,
    "protection_mm": 2,
    "reserved_top_mm": 1,
    "gap_mm": 0.5,
    "dimension_increment_mm": 5
  }
}
```

Optional `max_external_mm` is a manufacturing constraint; it must not be copied
from a comparison reference. Preparation/search/validation timings and all
candidate outcomes are saved in `design.json`. Deadlines are currently soft;
optimality is not established. This stage consumes already protected envelopes:
it does not yet design groups, nest irregular meshes or select protection.

## Clean source preparation

The generic `scripts/prepare_printing_library.py` adapter maps three-column
Markdown part-number/name/quantity tables to exact STL filenames. Ambiguous
matches fail. It records source hashes and quantities, removes only source
translation, and checks mesh volume topology without changing dimensions.
STL units are explicitly assumed to be millimetres.

```powershell
python scripts/prepare_printing_library.py packaging-inputs/so-arm-102/repository-main/docs/printing.md packaging-inputs/so-arm-102/repository-main/models/stl --step-models packaging-inputs/so-arm-102/repository-main/models/step --output packaging-inputs/independent/102/printed
```

The current run imports 25 types / 44 robot printed parts in approximately 16 s
including STEP fallback. It does not include figures or purchased hardware.
It reads no old results. All meshes now pass positive watertight-volume checks:
exactly zero-area triangle removal resolves wrist holder and trigger; the bottom
servo holder is retessellated from its valid STEP after face unification, using
0.05 mm linear tolerance. Its mesh volume differs from STEP by approximately
0.017%. Every operation and source hash is recorded. No holes are filled and no
parts are scaled. Bounds/volume screening is not a surface-distance certificate;
downstream clearance policy must account for mesh approximation.

## Independent mesh baseline

`design-mesh-baseline` computes oriented bounds directly from each part's vertices,
generates outer-carton dimensions with `design-envelopes`, maps source triangles
back into proper rigid poses and checks whole-manifest geometry and vertical
insertion. Explicit unrestricted rotations are required in this first version.
No packing positions, group names or reference dimensions enter the algorithm.

```powershell
python -m bom2kit design-mesh-baseline packaging-inputs/independent/102/printed/library.json --policy packaging-inputs/independent/102/printed-baseline-policy.json --output packaging-results/independent/102/printed-baseline --time-limit 10
```

The recorded policy uses 7 mm external wall offset, 15 mm outer protection,
0.8 mm top reservation, 1 mm dimension increments, 0.2 mm envelope gap, 1 mm
per-face item padding, and 0.2 mm triangle clearance. Padding here is a geometric
allowance, not a manufactured sleeve or a claim of transport equivalence.

First measured run: **306 x 334 x 207 mm = 21.156228 L**, containing only the
44 robot printed pieces. Preparation/orientation: 4.89 s; carton search: 3.74 s;
triangle and motion checks: 16.43 s; total: 25.06 s (excluding source conversion).
Both geometry and vertical insertion pass. This partial-kit volume is not an
acceptance result or a like-for-like comparison with Alan's complete kit.
It establishes a reproducible conservative starting layout for cluster search.
The time limit currently covers carton search, not the entire command.

## Next work

### Adaptive heights and larger groups

Layer search now adds height bands weighted by the volume and quantities of
the remaining units. It retains the original sampled heights as alternatives.
This avoids overlooking a useful height merely because it falls between the
ten globally sampled bands. On the complete 102 library and unchanged grouping
and protection, it produced **312 x 222 x 351 mm = 24.311664 L**. Declared BOM,
original triangles and group insertion pass. Evidence:
`packaging-results/independent/102/adaptive-height-design/result.json`.
The result remains above the independent engineer comparison threshold.

`nested_groups.extend_groups` can now search group/part and group/group
combinations. Previously discovered groups become temporary rigid source meshes;
proposals exceeding any original SKU quantity are excluded before search. Every
retained candidate is expanded back to original source poses and receives a new
whole-group assembly certificate. It is not accepted on a compound bounding box
or an earlier pair certificate alone. Synthetic tests cover a three-part group,
source identity expansion and preventing reuse of an unavailable ring.

The clean runner exposes `--nesting-rounds 1` (default 0). Each round receives
the declared pair budget; this is additional work, not free acceleration. It
reads groups found during that same command. Reference geometry, reference
cartons and prepared engineer placements are never inputs. Whole-kit selection
remains bounded and greedy; larger local groups do not guarantee a smaller
shipping carton.

### Diverse pairs and adjacent carton stacks

Pair proposal ranking now discounts repeatedly explored part types. A limited
budget therefore explores different shapes instead of only the three largest
arm combinations. Ranking remains a heuristic; original-source collision,
clearance and workbench assembly checks still gate every retained pair.

The full 102 experiment in `diverse-pairs/pairs.json` tested 12 proposals in
142.66 s and retained seven alternatives, including base/base and arm/clamp.
Using all alternatives greedily produced **223 x 310 x 390 mm = 26.9607 L**,
with complete declared BOM and valid original geometry/insertion. This is worse
than the incumbent and is not adopted. Evidence is under
`packaging-results/independent/102/diverse-column-design/`.

The carton constructor now also tries two adjacent stacks of closed inner
cartons, allowing different total stack heights with independent support.
On the previously discovered mixed-arm grouping, the expanded search retained
**224 x 268 x 433 mm = 25.993856 L**. The new run includes packaging dimension
specifications and passes BOM, hierarchy, triangle and insertion checks; it does
not establish transport qualification or production dielines. Evidence:
`packaging-results/independent/102/column-design/result.json`.

The pair experiment exposed a timing defect: voxel preparation consumed the
entire eight-second budget for some parts, so those attempts checked zero
rotations. Pair search now starts its soft search deadline after preparation and
records preparation, search and final verification separately. The overall pair
portfolio deadline remains soft and may overrun during preparation/verification.
No complete-kit acceptance claim follows from these changes.

With corrected timing, the first five diverse proposals completed in 81.61 s.
All five produced assembly-checked savings. The 106 mm-frame clamp pair now
checks all 24 rotations (10.77 s preparation, 1.88 s search, 0.08 s final static
verification) and has envelope ratio 0.90384 to separate boxes. The formerly
unsearched `SO102.02.060` pair also becomes feasible with ratio 0.94961.
Evidence: `packaging-results/independent/102/diverse-pairs-timed/pairs.json`.
These are pair-level savings, not yet whole-carton improvement.

Extending the independently found incumbent grouping with new alternatives
whose part identities do not conflict reduces the complete 102 result to
**265 x 222 x 433 mm = 25.47339 L**, about 2.0% below 25.993856 L. The extension
rule uses only source membership, never Alan's grouping or poses. Its saved
portfolio and result are in
`packaging-results/independent/102/extended-column-design/`. All 108 packing
units remain present; declared BOM, original mesh, assembly/insertion and an
independently rerun carton hierarchy check pass. The envelope-design substage
took 39.42 s (6.14 s geometry preparation, 14.60 s carton design, 18.68 s triangle
and motion validation); this excludes pair discovery and group composition.
The complete-kit volume remains above the separate 20.06336 L reference for
102. The objective is still open, including independent 101 completion,
transport-equivalent protection, manufacturing and final illustrated reports.

### Supported multilayer cartons

Optional `policy.carton.inner_wall_mm` now enables geometry-derived closed inner
cartons. The constructor searches footprint/height bands, chooses per-part
orientations, fills each layer and stacks the cartons. A second policy anchors
each layer on a large remaining part before placing smaller parts around it.
Both alternatives compete with the unchanged single-floor incumbent.

The independent hierarchical validator checks exact source-unit coverage, every
inner cavity, material thickness, outer containment, full carton base support
and top insertion. Original triangle validation and internal/group motion checks
remain separate. Inner and outer carton dimensions respect manufacturing
increments. The engine emits an inner-carton dimension BOM; production dielines
and carton strength are not certified by these geometry checks.

With 1.5 mm inner walls, the full 102 singleton run reached 27.55 L. Combining
generated layers with the independently discovered mixed-arm pair reached
**224 x 268 x 433 mm = 25.993856 L**, using seven inner cartons. All 108 packing
units, declared BOM counts, original-source triangles and assembly/insertion
checks pass. Evidence:
`packaging-results/independent/102/complete-layered-grouped/1/result.json`.
This remains worse than the required engineer comparison; the goal is open.
The next compaction step is broader geometry-driven groups and improved layer
selection, with unchanged protection requirements.

### Complete 102 hardware input and first full search

`prepare_hardware_library.py` reads the extracted source rows and an explicit
geometry specification. Every nonalternative row must be represented exactly
once. Small monotype hardware is automatically assigned a conservative regular
cell grid and a bag envelope; source quantities become packet `contents`, not
discarded counts. Packet contents and variant identities now survive final mesh
layout composition. `design_grouped_meshes.py --bom EXPECTED.json` checks expected
counts before search and again on the selected output.

The 102 specification is under
`packaging-inputs/independent/102/hardware-specification.json`. It includes the
confirmed 106 mm clamp frame with retained intrinsic proxy primitives, 2 mm servo
sleeves, BOM-sized bearings/rods, and explicitly estimated protected electronics,
power supplies, cables and tools. STS3235/3250 envelope equivalence to the archived
servo model remains an estimate. No former clamp packing poses are copied.

```powershell
python scripts/prepare_hardware_library.py packaging-inputs/independent/102/hardware-source-rows.json packaging-inputs/independent/102/hardware-specification.json --output packaging-inputs/independent/102/hardware
python scripts/combine_part_libraries.py packaging-inputs/independent/102/all-printed.json packaging-inputs/independent/102/hardware/library.json --output packaging-inputs/independent/102/complete-library.json
python scripts/design_grouped_meshes.py packaging-inputs/independent/102/complete-library.json packaging-inputs/independent/102/printed-baseline-policy.json --bom packaging-inputs/independent/102/expected-complete-bom.json --output packaging-results/independent/102/complete-design --max-pairs 3
```

The input represents **108 packing units**, covering **335 individually enumerated
components plus one factory-accessory packet**. Factory screws are counted in the
BOM fastener rows and are excluded from that extra packet; unlisted horns and
supplied leads remain retained in its estimated envelope. The expected count
ledger and full output pass declared BOM reconciliation.

The first full search, before the latest carton-validation scheduling improvement,
took **302.24 s** and selected **373 x 577 x 207 mm = 44.550747 L**. Original-source
geometry, internal assembly and external insertion checks pass, but the volume
is unacceptable. Evidence: `packaging-results/independent/102/complete-first-run/`.
The full kit replaces the earlier partial-kit experiment; no 19.6144 L complete-kit
claim is made.

Protected singleton boxes total approximately 10.947 L before carton voids and
outer protection. The current single-floor constructive layouts waste substantial
space. The next optimization priority is supported multilayer construction and
larger geometry-driven clusters, without lowering declared protection. A carton
experiment that avoids validating non-improving proposals reduced the same
singleton-envelope design to 36.059814 L; it is only an envelope-stage result,
not a freshly certified full mesh layout.

### Complete printed-source inventory

The new `prepare_3mf_library.py` source adapter splits manufacturing objects into
physical-part candidates. Explicit nonpart roles are excluded and unknown roles
fail. Optional contact-shell joining preserves touching color/material islands
with their printed panel; it must be enabled only after reviewing source semantics.
Printer build positions are not packing positions. Individual source hashes,
object/instance identifiers and component membership are preserved.

For the current 102 sources, `colored_figures.3mf` yields 10 colored objects;
`aruco_cube.3mf` yields the core and six separate marker panels. The marker islands
remain attached to their panels, giving 17 physical figure parts rather than 35
material shells. All extracted meshes pass positive watertight-volume checks.
Combining these with the 44 robot parts gives **61 printed parts**.

```powershell
python scripts/prepare_3mf_library.py packaging-inputs/so-arm-102/repository-main/models/3mf/colored_figures.3mf packaging-inputs/so-arm-102/repository-main/models/3mf/aruco_cube.3mf --join-contacting-shells --output packaging-inputs/independent/102/figures
python scripts/combine_part_libraries.py packaging-inputs/independent/102/printed/library.json packaging-inputs/independent/102/figures/library.json --output packaging-inputs/independent/102/all-printed.json
python scripts/extract_bom_tables.py packaging-inputs/so-arm-102/repository-main/docs/bom.md --output packaging-inputs/independent/102/hardware-source-rows.json
```

The independent hardware-table extractor finds 25 rows and **267 components**
excluding optional alternative rows. It preserves distinct servo variants,
source lines, every column and the source fingerprint. This is not a complete
shipping reconciliation: two additional long cables, tools, regional power cords
and included factory accessories still need explicit handling. Hardware geometry
and protection are not inferred from a quantity table.

The clean 61-piece run (fresh pair discovery, baseline and four complete group
configurations) finished in **272.16 s**. Its selected printed-only carton is
**230 x 533 x 160 mm = 19.6144 L**, with all original mesh placements and group
assembly/insertion checks passing. Output:
`packaging-results/independent/102/all-printed-design/run.json`, selecting
`packing-2/result.json`. This includes the figures, unlike the earlier 44-piece
16.9104 L experiment. Purchased parts are still absent; this is not a successful
complete-kit comparison and does not close the objective.

The same adapter also reads the independent 101 manufacturing files: follower,
leader, colored figures and ArUco produce 41 parts; the two separate logo/nameplate
files produce two additional parts. These **43 source candidates** are stored
under `packaging-inputs/independent/101/`, with separate nameplate identities.
Their source meshes pass volume checks, but variant/quantity reconciliation
against the 101 BOM remains a required gate before complete-kit acceptance.

### Pair discovery experiment

`scripts/design_grouped_meshes.py LIBRARY POLICY --output OUTPUT` now runs
geometry-ranked pair discovery, workbench assembly checks along six cardinal
directions, quantity-aware group selection and original-part expansion into a
new outer layout. The runner retains the smaller verified result between the
singleton baseline and grouped candidate. Full source geometry and internal
assembly certificates are checked again before composition. Bounds, orientations
and pair membership come from source geometry, not Alan's arrangement.

The first 102 printed-only experiment produced three assembly-checked arm pair
alternatives. Their envelope-volume ratios to separate part boxes were roughly
0.853, 0.890 and 0.882. Greedy selection chose two disjoint same-type pairs.
However, the resulting whole carton was **144 x 749 x 299 mm = 32.248944 L**,
worse than the 21.156228 L singleton baseline. All 44 original parts and group
insertion paths passed geometry checks. This is evidence that local savings
alone are the wrong selection objective; it is not packing improvement.

The subsequent carton update adds maximal-free-rectangle strip construction:
each part can choose its own orientation within a geometry-derived height band,
and smaller parts fill remaining floor rectangles. It needs no floating parts
or unmodeled support material. Existing independent validation still checks every
retained candidate.

On the same 44-piece inputs and unchanged protection policy, this reduced the
singleton baseline to **320 x 389 x 160 mm = 19.9168 L**, and the two-pair
candidate to **298 x 362 x 175 mm = 18.8783 L**. Both original-source geometry
and insertion checks pass. These are partial-kit measurements, not acceptance
against a full engineer kit.

The runner now evaluates all proposed alternatives together and individual
alternatives separately (`--group-configurations`, default 4). It selects by
validated whole-carton volume, retaining the baseline if no grouping improves it.
This is a bounded joint comparison, not an exhaustive partition search. Genuine
multilayer construction, larger clusters, the full shipping BOM, manufactured
packaging and the final comparison remain open.

The three individually evaluated alternatives produced 18.5952, **16.9104**, and
18.62656 L respectively. The best uses the automatically discovered mixed
left/right arm pair twice, and a **271 x 390 x 160 mm** outer box. All 44 original
part poses, internal pair assembly and external group insertion pass. Compared
with the earlier 21.156228 L independent singleton baseline, this is about 20.1%
less volume for the same printed-only scope. It is not a full-kit comparison.
Reproducible evidence is under `packaging-results/independent/102/strip-comparison/`;
the best evaluated candidate is `alternative-1/result.json`. Pair proposals were
reused from the independent `pairs-axes` search, never from Alan's reference.

1. Prepare complete neutral 101/102 input libraries, including figures, purchased
   items, BOM mapping and protection. Robot 102 source topology is resolved.
2. Generate orientations and small group candidates from geometry; verify their
   internal assembly paths. Add protection alternatives under fixed policy.
3. Connect groups to the outer-carton generator, then implement bounded joint
   improvement, manufacturing specifications and canonical instructions.
4. Run isolated, recipe-free searches; freeze outputs before reference evaluation.
   Compare complete contents and comparable protection, then render the report.
5. Update and synchronize the shared skill once the new end-to-end command works.

The existing prepared recipes remain historical evidence only. They must not be
inputs to these stages. See [the audit](from-scratch-design-review.md) for the
complete architecture and acceptance gates.
