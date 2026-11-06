# Independent design implementation status

The original objective remains open. No new complete-kit comparison has passed.
This document records executable progress, not acceptance of the finished product.

## Bound geometric assembly plans

`scripts/build_assembly_plan.py RESULT BOM --output PLAN.json` now freshly checks
the BOM, original insertion sequence, closed-carton hierarchy, external wall
dimensions and actual part containment in each assigned carton. Internal group
templates are replayed on the workbench and every final copy must be a common
rigid transform of that template. Unexplained multi-part groups, cross-carton
sequences and altered memberships fail. Output includes per-copy unit mapping,
workbench-to-final transforms and the outer carton insertion order, bound by
canonical result and expected-BOM fingerprints.

Both retained height-fill candidates pass this new check. Their plans are saved
at `packaging-results/independent/{101,102}/height-fill-review/assembly-plan.json`.
Fresh replay took 12.77 s for 101 and 21.86 s for 102 in this run (not cold design
times). These are machine-readable geometric instructions; illustrated operator
steps, handling/stability and transport qualification remain unfinished.
Full suite: 129 tests passed in 18.67 seconds, including rejection of altered
carton assignments, incorrect exterior dimensions and missing group templates.

`carton.placement_score: "portfolio"` additionally compares bottom-left and
height-fill alternatives inside the same layer sequence search. Three 102
grouping experiments produced 22.880880, 24.504480 and 22.927600 L envelopes;
all were rejected against the 22.087296 L verified incumbent. Broader search
does not automatically improve a fixed wall-time budget. Evidence is under
`102/mixed-layer-group-search/`; the equivalent 101 experiment is separate.
Its first 101 configuration passed complete declared BOM, source geometry and
assembly at **212 x 253 x 383 mm = 20.542588 L**, a further 0.016172 L reduction.
This remains above the reference. The selected evidence is
`101/mixed-layer-group-search/0/result.json`; the remaining configurations are
not implied successful by this result.

## Height-oriented placement improves 102

`carton.placement_score: "height_fill"` prefers taller permitted orientations
within each candidate height band, reducing the floor area consumed by a unit.
It changes neither dimensions nor allowed rotations. This differs from sorting
units by volume, which did not improve these benchmarks.

With the independently discovered groups, unchanged protection and a 90-second
carton budget, 102 improved to **252 x 264 x 332 mm = 22.087296 L**. Original
geometry, group assembly, outer insertion and complete declared BOM pass. It is
still **10.09% above** the 20.063360 L reference; the objective remains open.
The selected artifact is `102/height-fill-design/result.json`; `height-fill-review/`
freshly checks and renders all 108 units in five inner cartons. Reused group
discovery means this experiment is not an end-to-end cold timing measurement.

The shared skill documents this mode alongside other tested heuristics. Full
regression suite: 127 tests passed in 15.55 seconds.

The same height-oriented placement experiment on 101 also improved its verified
candidate to **213 x 254 x 380 mm = 20.558760 L**, preserving all 79 packing
units and complete declared BOM coverage. Geometry and assembly checks pass;
it remains about **5.85% above** the reference. Evidence is under
`101/height-fill-design/`, with exact-coordinate review under `height-fill-review/`.

## Orientation coverage under short search budgets

The expanded 102 search revealed that several expensive pairs explored only
1–6 of 24 orientations before their search budget expired. Pair search now
allocates the first half of its soft budget to collecting voxel proposals across
orientations, then sorts the combined proposals by envelope volume before exact
triangle/distance/containment checks. Adjacent non-overlapping bounds skip only
the logically unnecessary containment query; collision, clearance and final
independent validation remain required.

Search metadata distinguishes orientation proposals from exact candidates and
records proposal time. The small cavity regression explores all 24 rotations
and preserves nested assembly checks. Full suite: 125 tests passed in 15.85 s.
Whole-kit performance remains an empirical question; synthetic success does not
establish a smaller 101/102 carton.

The 102 orientation-first trial explored 17–24 rotations per attempted pair in
121.69 seconds. Accepted pair envelope volumes matched the earlier alternatives;
the complete carton remained 22.340736 L and was rejected as non-improving.
Evidence: `102/orientation-first-pairs/` and `102/orientation-first-design/`.

The 101 extension search retained seven original-source-checked three-part
groups. Their combined greedy carton was 21.213568 L, worse than the verified
20.612862 L incumbent, so original whole-carton pose certification was skipped.
Evidence: `101/expanded-nested-search/` and `101/expanded-nested-design/`.

## Latest retained 101 candidate

The expanded independently discovered portfolio was evaluated in three
configurations with unchanged BOM and protection. The first two envelopes
(20.674907 and 21.225945 L) did not improve the incumbent. Configuration 2
passed original-source geometry, internal group assembly, external insertion
and declared BOM reconciliation at **213 x 254 x 381 mm = 20.612862 L**.
It uses six discovered group types and six inner cartons, covering all 79
packing units. This is still **6.13% above** the 19.423040 L reference.

Evidence: `packaging-results/independent/101/expanded-portfolio-design/2/`.
`expanded-portfolio-review/` reruns geometry/BOM/carton checks and renders these
exact coordinates. This experiment reused independent group discovery and is
not a fresh complete source-to-carton timing measurement.

The optional `carton.unequal_columns: true` now also generates two adjacent
stacks with different widths from the total geometry-derived footprint. Each
stack has closed cartons with the original wall thickness, full base support
and independently checked containment. No reference dimensions are used. A
synthetic mixed-size kit exercises actual unequal-width output and rejects a
carton moved into its neighbor. Full suite: 125 tests passed in 15.30 seconds.
The first 102 trial matched the existing 22.340736 L envelope exactly, so it
was not accepted as an improvement.
The corresponding 101 trial reused its older single-group portfolio and matched
20.671200 L; it also provided no improvement. Both trials are under each kit's
`unequal-column-design/`. The latest 101 incumbent remains 20.612862 L.

## Height-utilization experiment

The retained 101 layers occupy 86–98% of their floor area but 71–91% of their
volume; 102 layers occupy 90–97% of floor area and 71–90% of volume. These are
protected-envelope occupancies, not solid-material density. This motivates
height-aware grouping rather than only improving two-dimensional floor packing.

An optional `carton.item_order: "volume"` prioritizes bulky units; the default
remains `"area"`. With unchanged independently discovered groups and protection,
90-second carton budgets produced 20.898000 L for 101 and 22.889412 L for 102.
Both passed original geometry, assembly and complete declared BOM checks, but
both were worse than the retained incumbents. These runs are carton-search
experiments with cached independent groups, not fresh end-to-end design.
Evidence: `packaging-results/independent/{101,102}/volume-order-design/`.
Full regression suite: 124 tests passed in 16.27 seconds.

A broader 102 pair search (`expanded-pair-search/`) used a 240-second soft
budget, five seconds per pair and at most 40 proposals. It checked 29 proposals
in 241.23 seconds and retained 15 assembly-checked alternatives, including new
mixed printed/purchased groups. A whole-kit evaluation with these alternatives
plus the existing independently generated groups is required before claiming
any volume improvement. Pair savings alone do not satisfy the objective.

The combined expanded portfolio produced a 269 x 220 x 381 mm envelope
(22.547580 L), which was rejected before original-pose certification because it
exceeded the verified incumbent. Group configuration generation now explores
leave-one-out neighbors before isolated anchors, allowing a locally compact
group to be removed when it makes the complete carton worse. Quantity-aware
selection and equivalent-layout deduplication remain in force.

The runner now saves exact library/policy/BOM file hashes, search parameters
and per-stage wall times. A fresh two-cuboid smoke run exercised this output
and selected a verified baseline in 4.21 seconds from prepared meshes. Each
stage includes its own checks; these timings do not yet provide a disjoint
aggregate preparation/search/validation breakdown or include source import.

Four 102 leave-one-out configurations under `group-neighbors/` generated
24.285184, 23.323300, 22.401288 and 22.432068 L envelopes with 90-second
carton budgets. All were correctly rejected as non-improving; they do not carry
original-pose acceptance certificates. The verified 22.340736 L incumbent is
unchanged. A matching broader 101 discovery checked 28 proposals in 242.86 s
and retained 20 assembly-checked pairs (`101/expanded-pair-search/`). Full-kit
evaluation is separate from those local pair certificates.

## Current search and review improvements

The shared Codex/Claude skill now launches independent group discovery and
carton design. Compatible anchored group portfolios replace redundant individual
evaluations. A candidate whose envelope volume cannot improve an already
verified incumbent is marked `not_improved`; its original poses are deliberately
not certified and it cannot become the selected result.

Pair proposals now include clearance-expanded voxels, with original-grid fallback
and unchanged exact triangle checks. Equal-volume ties prefer separated part
centres, allowing successive parts to occupy a cavity. Synthetic ring tests
verify insertion of two cylinders without changing their source geometry.
An additional alternating proposal queue nominates dense small parts inside
hollow bounds. Occupancy and bounds nominate candidates only; exact fit and
assembly still require validation. This heuristic is not a measured kit-volume
improvement until a complete candidate passes.

Alternative short-side rectangle scoring was tested with unchanged inputs and
protection: 101 produced 21.902400 L and 102 produced 23.771088 L. Both were
worse than retained candidates (20.671200 and 22.644144 L respectively).
These unsuccessful experiments remain under each kit's `short-side-design/`.

`scripts/render_design_review.py RESULT BOM --output OUTPUT` freshly checks BOM,
source triangles, carton hierarchy, original-part containment in assigned inner
cartons and exact diagram membership. It creates top-view PNGs and an HTML
review bound to source/result hashes. The five-carton reviews cover all 79 and
108 packing units for 101 and 102. They are geometric reviews, not assembly
instructions or shipping qualification. Final instructions, comparison and the
no-worse gate remain unfinished.

Validation after these changes: 123 tests passed in 15.28 seconds. A fresh 102
run under `clean-portfolio-run/` was launched before the new cavity-priority
queue; its result must not be attributed to that later change.

That fresh run finished in **699.62 seconds** from the prepared source library
(source import time is excluded). It independently generated eight group
alternatives and evaluated six configurations. The selected `packing-0/result.json`
is **258 x 264 x 328 mm = 22.340736 L**, with complete declared BOM coverage
and passing original-source geometry and motion checks. Five other configurations
were rejected as non-improving. This improves the prior 22.644144 L incumbent
by 0.303408 L, but is still **11.35% larger** than the 20.063360 L reference.
The 101 incumbent remains 20.671200 L versus 19.423040 L. Neither kit passes
the requested comparison gate. Separate aggregate preparation/search/validation
timing and faster end-to-end execution remain necessary.

The first cavity-priority experiment (`cavity-diverse-pairs/`) finished in
84.71 seconds. All five added dense/hollow nominations failed to save envelope
volume; the five accepted alternatives were familiar same-part pairs. Therefore
this queue is experimental and opt-in (`--cavity-proposals`), preserving the
broader default proposal portfolio. Outer bounds alone do not describe useful
interior voids; cavity size/shape screening needs improvement before allocating
half of a short search budget to this strategy.

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

### Alternative layer sequences and footprint refinement

The layered constructor now retains multiple remaining-part states instead of
always selecting the densest next layer. Equal remaining inventories discard
taller prefixes. Only complete stacks are returned, and the existing independent
hierarchy validator checks each accepted result. A synthetic regression case
shrinks a 33 mm stack to 26 mm without losing a part or reducing walls.

The broad sequence mode (`policy.carton.refine_footprints: false`) explores
more of the generated coarse footprints. The default refinement mode spends
part of the budget exploring nearby manufacturing-grid sizes around its own
incumbent. It never receives an engineer footprint or volume target. These are
different bounded searches; neither dominates the other on every kit.

The initial broad-mode experiments produced **300 x 216 x 319 mm = 20.6712 L**
for 101 and **308 x 221 x 341 mm = 23.211188 L** for 102. Evidence is in each
kit's `layer-sequence-design/result.json`. Refinement improved 102 further to
**276 x 258 x 318 mm = 22.644144 L**, but gave 21.1302 L for 101, so the better
101 incumbent is retained. Refinement evidence is in each kit's
`refined-sequence-design/result.json`. Source BOM and original mesh/motion checks
pass. All volumes remain above their separate engineer references.

The current code reproduces the 101 broad result in
`broad-sequence-design/result.json`, using
`packaging-inputs/independent/101/broad-sequence-policy.json`. Fresh hierarchy
and declared-BOM checks pass for that result and the 102 refined result. The
complete suite passes **118 tests**. No final no-worse comparison, manufactured
packaging qualification or final illustrated delivery is claimed.

Pair proposals now reuse immutable voxel grids keyed by verified source hash,
3MF instance/frame and pitch. The original mesh hash is checked even on a cache
hit, and every retained placement still receives independent triangle checks.
Containment queries reuse local-mesh acceleration structures by transforming
sample points with the rigid inverse. Tests exercise cache reuse and rejection
of a changed source. A fresh nested 102 experiment retained the known four-arm
group but found no improved group; no whole-kit speedup is claimed from that run.

### Independent 101 input reconciliation

`scripts/extract_xlsx_bom.py SOURCE.xlsx --output ROWS.json` reads a single
worksheet BOM without modifying it. It records worksheet/cell addresses and
the source hash, preserves variants, and rejects fractional, zero or unevaluated
formula quantities. The 101 source contains 25 rows with mixed units: individual
hardware, printed sets, booklet and packaging. Its sum of 200 is not a physical
component count.

The explicitly confirmed R3 content revision overrides C001/C046 quantities
from 1/3 to 2/2 and supersedes the older named PSU selections with 12V5A and
5V4A supplies. Only content identities/counts are used; reference box assignments,
dimensions and poses are excluded. Raw cell evidence is retained beside each
override in `packaging-inputs/independent/101/hardware-source-rows.json`.

The source printing-order document requests one follower set (including its
camera wrist mount), one leader set, ten colored figures, disassembled ArUco
and both nameplate colors. These expand to 43 verified source meshes. Camera
mount is not counted again. Nineteen purchased rows expand to 194 components;
two regional cords and two USB adapters from R3 add four more. The resulting
neutral library contains **79 packing units covering 241 product components**.
Booklet reserve, generated outer carton and its label are tracked separately;
their full packaging acceptance remains open.

Factory servo cartons are retained as explicitly estimated 65 x 45 x 35 mm
envelopes. Purchased electronics, cable folds, fastener cells and other
unmeasured dimensions are listed in `hardware-specification.json`. They are
assumptions, not source measurements. The custom clamp keeps its confirmed
106 mm frame. Source reconciliation and preparation are stored under
`packaging-inputs/independent/101/`; the clean search reads no historical layouts.

The first complete-product singleton baseline is **260 x 303 x 274 mm =
21.58572 L**, with source geometry and insertion checks passing. It is above
the engineer comparison and is not acceptance. Evidence:
`packaging-results/independent/101/complete-first-run/baseline.json`.

The clean 101 run then discovered five valid pair alternatives and evaluated
three group configurations. In **259.85 s** including the initial baseline,
pair discovery and full geometry checks, it selected **258 x 300 x 273 mm =
21.1302 L**. All 79 source packing units and 241 declared product components are
preserved. Original triangles, assembly/insertion and an independently rerun
carton hierarchy check pass. `complete-first-run/run.json` selects
`packing-2/result.json`; `coverage.json` records the count reconciliation. This
still exceeds the separate 19.42304 L reference and does not close the objective.

The second 102 nesting round mostly rediscovered the four-arm group. Proposal
diversity now uses original source identities inside compounds, so renaming the
same shapes as different groups does not hide repeated exploration. A fresh
141.52 s experiment explored other combinations but produced no additional
verified savings. The 23.557248 L incumbent remains unchanged. The full suite
passes 115 tests, including source-cell extraction and compound-overlap ranking.

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

The first full-library extension experiment completed in 153.15 s and retained
one four-arm group with an original-envelope ratio of 0.80409. Every original
part has a fresh assembly certificate; the group is not a copied engineer
arrangement. Adding it to the independently discovered alternatives reduced
the complete 102 candidate to **264 x 264 x 338 mm = 23.557248 L**. All 108
packing units, the declared BOM, original triangle/insertion checks and a fresh
hierarchical carton check pass. Evidence:
`packaging-results/independent/102/nested-discovery/groups.json` and
`packaging-results/independent/102/nested-carton-design/result.json`.
The full test suite passes 110 tests. This is measured progress, not completion:
the 102 volume is still above 20.06336 L and the remaining delivery gates stay open.

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
