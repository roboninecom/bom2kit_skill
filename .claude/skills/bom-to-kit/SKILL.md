---
name: bom-to-kit
description: Design grouped packaging from a BOM and individual CAD or declared envelopes using the local bom2kit engine, validate geometry and quantities, and compare a frozen result with an engineer reference.
---

# BOM to Kit

Use this repository's shared Python engine from its root. The same instructions
apply to Codex and Claude Code. Install `python -m pip install -e ".[mesh,cad,test]"`
as needed; `[report]` enables mesh visualization. Read
`docs/independent-design-progress.md` for capabilities and remaining gaps.
The complete no-worse 101/102 objective is still open.
For shipping kits and manual kitting, start with **Concept-first packing** below
and compare the **Practical manual packing** baseline when an incumbent exists.
The older compound engines are research/baseline tools: their
collision-free groups do not establish a practical way to carry loose parts.

Retain the better independently verified practical
incumbent: the new architecture alone is not evidence of improved packaging.

## Prepare independent inputs

Keep private sources in `packaging-inputs/` and results in `packaging-results/`.
Preserve original files and record hashes, units, quantities, revisions, packing
state and dimension evidence. Prefer measured envelopes for factory cartons,
cables and bags. Explicitly authorized estimates remain estimates; do not
silently change them to hit a comparison target.

Use the source adapters' `--help`:

- `scripts/extract_bom_tables.py`: Markdown quantity tables.
- `scripts/extract_xlsx_bom.py`: one XLSX worksheet with cell evidence.
- `scripts/prepare_printing_library.py`: part-number tables and STL/STEP.
- `scripts/prepare_3mf_library.py`: physical parts in object coordinates.
- `scripts/prepare_hardware_library.py`: purchased shapes and count-preserving packets.
- `scripts/combine_part_libraries.py`: verified, uniquely identified libraries.

Expand printed sets, retain attached color shells, exclude printer modifiers,
and avoid counting included parts twice. Packet `contents` must preserve
individual quantities. Document revision overrides and shipping additions.
Track the booklet and generated packaging separately. A table sum is not
necessarily a physical component count.

A neutral library has `units: "mm"`, `all_meshes_valid_volumes: true`, and
items with `id`, `quantity`, and `mesh: {path, sha256}`. Mesh JSON contains
`units`, `vertices_mm` and `triangles`. The engine rechecks source geometry;
the flag alone certifies nothing. Research-only alternative packing states are
excluded from the primary practical comparison. Supply an independent expected BOM with a
`components` list of SKU quantities and required revisions.

## Design from scratch

Search consumes individual geometry, quantities and protection/manufacturing
policy. Do not import an engineer's carton sizes, grouping, poses, target volume,
printer-plate positions or prepared packing recipes. No manual coordinate tuning
or SKU-specific placement scripts. Reference data belongs only to a separate
evaluator after freezing a result.

The policy requires `carton`, `item_padding_mm`, `clearance_mm` and
`allow_all_rotations: true`. Carton fields include `wall_mm`,
`protection_mm`, `inner_wall_mm`, `reserved_top_mm`, `gap_mm` and
`dimension_increment_mm`. Choose values from actual requirements.
`refine_footprints` switches local size refinement versus broader sequence
search. `placement_score` accepts `bottom_left`, `short_side`, `area` or
`height_fill` (prefer taller allowed orientations within a layer).
`portfolio` compares both bottom-left and height-oriented choices per layer.
No heuristic dominates every kit; preserve protection while comparing them.
`item_order` accepts `area` or `volume`; `unequal_columns: true` also searches
adjacent stacks of different widths. Keep the best fully verified result across
experiments. These settings do not relax walls, padding or part geometry.

The following command is the older compound-search research path. Use the
practical pipeline for a new operator-facing shipping design.

```powershell
python scripts/design_grouped_meshes.py LIBRARY.json POLICY.json --bom EXPECTED.json --output packaging-results/design --pair-budget 120 --pair-seconds 8 --max-pairs 10 --nesting-rounds 1 --carton-budget 90 --group-configurations 6 --improvement-budget 120
```

The runner discovers pairs, optionally extends groups, compares greedy,
leave-one-out and anchored groupings, and generates cartons. It retains a verified incumbent. `run.json`
identifies the selected result. `not_improved` candidates lack original-pose
certification and are not accepted plans. Budgets are soft and per stage.
Report total runtime separately from preparation, search and validation;
certificate replay is not cold design.
The runner reuses only its own verified in-run footprints across grouping
evaluations, with source-library and hierarchy checks. It generates new poses.
Layered search also tries local repacking of its generated single-column layer
memberships and nearby manufacturing dimensions; complete proposals require
independent hierarchy validation. This is a heuristic, not an optimality proof.
`--improvement-budget` optionally moves and swaps units between generated layers,
then repairs nearby footprints. It requires `--bom`. The runner uses only the
winner from its current run, transfers unchanged original meshes rigidly, and
replays geometry, BOM and assembly before retaining any improvement. Existing
in-run poses may be preserved during local repair; external recipes remain
forbidden. Search and final replay times are reported separately for this stage.
When `inner_wall_mm` is specified, a wall-free shelf cannot replace the required
closed-carton hierarchy. The whole carton budget is used for hierarchical search.
`run.json` records input-file hashes, parameters and per-stage wall times.
Stage times include their checks and exclude source import; they are not a
disjoint preparation/search/validation breakdown.

Optional `--cavity-budget 120` adds actual voxel-void discovery for dense parts
inside hollow parts, followed by a cavity-extension round in discovered groups.
The budget applies to each of these two stages. Original source quantities,
triangle clearance and internal assembly are rechecked after flattening groups.
Voxel emptiness alone never certifies a fit. This differs from the older
`--cavity-proposals` bounds/occupancy ranking experiment.

## Validate, illustrate and compare

### Concept-first packing

Read `docs/concept-packing-design.md`. Build evidence-tagged property cards, form
semantic groups, generate executable motifs, compare bounded kit concepts, refine
geometry and independently replay. Name inference, shape similarity and visual
annotations guide grouping only; they never authorize reduced protection or loads.

```powershell
python scripts/design_concept_packaging.py LIBRARY.json POLICY.json EXPECTED.json --output packaging-results/concepts-rows --cache packaging-results/pose-cache --grouping type --motifs rows --placement-style cohesive --time-limit 150 --wall-limit 900 --max-replays 4 --assignment-budget 60 --refinement-budget 15 --repair-budget 90
```

Start with the bounded typed-row incumbent. Then, within the user's remaining
budget, compare a separate run with `--motifs hybrid --grouping adaptive_type`
and a different output directory. Hybrid includes rows, stacks, alternating
floor pairs and supported nesting; it can lose under a fixed search budget.
Preserve the row result unless independent replay and the measured tradeoffs
justify replacing it. Never overwrite an earlier result during this comparison.

Compare `assembly`, `type`, `shape`, `adaptive_type` and `replicated` grouping when names are incomplete
or height differences waste space. Keep original identities even for geometrically
similar parts. An annotation file may supply evidence-tagged type/assembly/material/
fragility labels; it cannot replace geometry. Same-SKU rows, explicit protected
stacks, alternating floor pairs and supported nesting remain individually handled.
Existing protective packets retain their source contents; a newly proposed bag
does not certify a rigid group, protection or restraint.
`replicated` proposes balanced repetitions of groups with repeated units and permits
later reunion, preserving original unit IDs. Pair/stack neighbors may share a type
or assembly; hard material-family restrictions still apply. The default
`--minimum-sheet-side 10` rejects contact cuts too small for the declared manual
handling assumption. Report that assumption; it is not transport qualification.
Keep complete small accessory sets together: disassembled fiducial faces and core,
learning-object sets and identification pieces must not be scattered across cartons
by a height split. The planner and renderer replay this kitting rule from semantic
cards; it does not make the contents a rigid assembly or establish restraint.
Optional `--irregular-solver PATH --irregular-budget 150` tests full concave source
outlines inside the generated compatible cartons. It may alter same-type adjacency;
compare organization and handling after original-source replay. Keep the earlier
in-run proposal if contour placement or its repair is worse. A backend certificate
alone is never an accepted packaging instruction.
Use `--assignment-budget 90` to revisit whole-group assignments against actual
regenerated carton/block volume. This can trade an extra carton for lower volume;
retain and report the earlier fewer-carton alternative instead of hiding that cost.

Try `--preserve-contact-faces` when equal-size opposite stable orientations have
different nesting surfaces. It preserves source-derived alternatives; it does not
authorize unstable poses. Account for cold pose preparation separately. Smaller
`--hand-border` or `--access-lane` values only propose tighter geometry: unchanged
finger replay must pass, followed by local repair if necessary.

The planner records alternatives and rejected trials. Joint refinement uses only
its own generated carton footprints; source-surface refinement and local repair
must pass unchanged support, source clearance, BOM and finger checks. Do not use
Alan's dimensions, grouping or target volume as search inputs. Report every stage,
including preparation, failed replay and repair, and distinguish warm caches from
cold runs. A timeout is not an infeasibility result.

Evaluate before/after with the same property cards, reporting type and assembly
grouping separately. Count cartons, factory boxes,
packets, liners and contact sheets separately. Group cohabitation and 10 mm spatial
connectivity are organization proxies; inspect the actual CAD guide. Report the
free-translation retention screen separately: an empty path proves potential
movement, while overlapping/blocked bounding boxes do not prove restraint. Its
5 mm threshold is diagnostic, not a shipping standard. Exercise a modified BOM.
Use the rendering workflow below only for an independently replayed selected result.
For a concept result, pass its bound `part-properties.json` to the guide renderer
with `--properties` to group the contents index without changing checked poses.

### Practical manual packing

For shipping kits, use the practical pipeline described in
`docs/practical-packing-design.md`. Start with individual handling; do not infer
that touching or nested loose parts can be carried as one rigid group.

```powershell
python scripts/design_practical_packaging.py LIBRARY.json TRANSPORT_POLICY.json EXPECTED.json --output packaging-results/practical --cache packaging-results/pose-cache --time-limit 180 --cartons 3 4 5 6 7 --types 2 3 4 --packing-gap 0.2 --access-lane 6.4 --hand-border 7.2 --refinement-budget 30 --max-replays 4 --wall-limit 600
```

The gap/border values above are an experimental access configuration, not measured
requirements. The skill must preserve the actual declared protection. The default
two-cylinder grip has 4 mm radius, up to 8 mm insertion depth and 24 mm length;
its geometric clearance is not proof of real hand access or gripping force.
Report timeouts separately from demonstrated collision/access failures.
Optional `--access-repair-budget 90` repacks cartons rejected by the unchanged
finger model, then retiles and independently replays the complete kit. Include
repair and failed replay time; do not accept a failed smaller layout.
The hard wall limit includes replay. Partial trial files need fresh replay before
delivery. Respect the user's overall deadline, preserving results and reporting
an unmet target when the window ends. Record explicitly authorized extensions.

The engine distinguishes source CAD, factory cartons, protective packets and
declared envelopes. A purple envelope in a guide is not an extra physical box.
Do not invent a smaller alternate packing state: it needs unchanged contents,
dimension evidence and a protection specification. Unmeasured alternatives are
research-only and must not silently replace the accepted benchmark inputs.

Evaluate the following modes separately before combining conclusions:

- Default stable-floor rows with no compound preassemblies.
- `--stack-height-factor 1`: bounded flat-interface stacks inside the tallest
  selected floor height. Actual source faces and the entire upper load line are
  checked. Explicit protective contact sheets occupy the original facing padding
  allowances and must be counted in materials and operations. Their strength and
  manual sheet handling remain unqualified.
- `--floor-pair-budget 60`: adjacent pairs of independently floor-supported parts,
  with original-mesh clearance rather than nonoverlapping bounding rectangles.
  Each source part still requires its own checked insertion operation.
- `--irregular-solver PATH --irregular-budget 40`: full projected contours with
  quarter-turns, no mirroring and independent source/protection replay.
- `--rectangle-solver PATH --rectangle-budget 20`: regular floor proposals from
  PackingSolver rectangle. `--cp-sat-python PATH` selects exact coverage from the
  generated finite carton pool. Neither backend certifies global optimality.
- `--common-floor-budget 120 --common-floor-only`: footprint-first partial floors,
  upward height quantization, cropped cartons and fresh no-spacer retiling.
- `--supported-nesting`: individually inserted pairs supported by actual internal
  horizontal faces. Evaluate separately from projected-contour/floor-pair modes.
- `--source-surface-budget 120`: bounded 3D placement on actual surfaces; several
  upper parts can share a lower source. Every intermediate removal/insertion load
  state must remain geometrically stable. Multiple-parent bridges and compliant
  wrapping are not certified by this model.

Joint refinement uses only dimensions generated during this invocation. The
frontier preserves volume/carton/type/handling tradeoffs. Include protective-sheet
placements, floor liners and carton closures when discussing actual labor;
source placements alone are not the full work count. Prices and manual times
remain unknown unless supplied or measured.
For a transparent event-count comparison, list source/compound placements,
contact sheets, liners, inner-carton forming/closing/insertion, foam panels and
outer-carton forming/closing separately. Declaring one event per forming or
closure is a model assumption. Disclose excluded packet preparation, labeling,
rework and individual fold/tape motions; do not call the sum measured labor.
Retain the Pareto alternatives and explain the delivery choice. A slightly
smaller layout with more cartons or protective sheets is not automatically the
better procurement/kitting choice. Label declared hollow proxies as assumptions
even when their original meshes pass geometric floor interlocking checks.

Only independently passing trials may produce an operator guide. A failed trial
or an exhausted budget is diagnostic evidence. Keep the best fully checked result
across experiments and report the complete elapsed time, including failed attempts,
preparation, solver startup and replay. The requested no-worse benchmark remains
open until both complete matching kits actually meet it.

### Transport-compatible carton search

For requests requiring compatible groups, a no-spacer carton block and explicit
foam, use the experimental `scripts/design_transport_packaging.py` pipeline:

```powershell
python scripts/design_transport_packaging.py LIBRARY.json TRANSPORT_POLICY.json EXPECTED.json --output packaging-results/transport --portfolio --time-limit 240 --nesting-budget 140
```

Prepare the explicit SKU-to-family policy with
`scripts/prepare_transport_policy.py --help`; review its description-based
classifications. The transport policy is separate from the older layered policy.
Its carton and protection dimensions are requirements, never reference targets.
Each closed carton contains one compatible family. The search chooses floor
packings and supported envelope columns, optionally discovers CAD pairs and
extensions within families, and joins adjustable
cartons into an exact slicing partition. It enlarges carton dimensions rather
than generating spacers. Joint refinement repacks contents against dimensions
found in the current run. `--split-largest-family` tests two cartons for the
largest family, within the declared carton and type caps; compare separately
with the unsplit run and keep the smaller fully verified result.

The portfolio automatically compares a fresh baseline, several in-run grouping portfolios and subdivision,
retaining the smallest fully checked result. It never imports old packing poses.
The reported duration includes all trials, including rejected ones. This is
still a bounded heuristic; use the separate evaluator for the no-worse target.
Omit `--portfolio` to evaluate a single strategy. The policy generator can
combine printed families and protected electronics explicitly; bare mechanics
must remain separate from unprotected printed parts. Record those assumptions.

The transport portfolio also compares integer-selected group quantities with
greedy alternatives. It skips original-mesh replay for `not_improved` proposals;
those are not certified layouts. `--nesting-workers 4` explores disjoint CAD
pair proposals in separate processes; `--nesting-pitch 2` trades finer proposals
for more work. Exact source clearance never changes with voxel resolution.
`--shared-footprint-budget 40` searches common carton footprints and heights.
`--polish-budget 180` adds supported order/orientation search on the best
grouping generated in this invocation. It cannot replace the checked incumbent
with a worse proposal. `--nesting-objective balanced` is an experimental pair
ranking alternative, not a reduction in protection or a proven improvement.
For explicit non-portfolio trials, `--balanced-cartons N` and
`--partition-strategy packing` alter family subdivisions. Compare complete
results: identical small boxes or more partitions can substantially increase
shipping volume. See `docs/transport-packaging.md` for the experimental controls.

`--packing-solver PATH` optionally requests proposals from an explicitly supplied
PackingSolver box executable. Its output must pass independent coverage,
orientation, collision and envelope-support checks. Backend success alone is
not acceptance. No binary is automatically downloaded. The default path does
not depend on that executable.

`--rectangle-solver PATH` optionally improves floor-only layouts with the
PackingSolver rectangle executable. Box proposals can seed a new supported
reconstruction; both adapters require independent envelope validation. Neither
backend permits an unsupported part or an imaginary shelf in an accepted result.

`--cp-sat-python PATH` optionally uses an isolated Python interpreter with
OR-Tools for floor orientation. `--cp-sat-columns` adds experimental supported-column
selection without displacing the floor proposals. See the transport
workflow for installation. Its rounded model and bounded column candidates
only generate proposals; exact envelopes and original CAD still require replay.
Do not interpret solver optimality as global packing optimality.

The result records six nonoverlapping foam panels, an outer carton specification,
inner cartons, compatibility checks and a geometric assembly plan. Nesting and
proposal budgets are separate, soft limits; final validation is additional.
Report total runtime and preserve all source hashes. Carton dimensions are not
supplier-approved dielines. Envelope support, an exact carton block and clear
CAD insertion paths do not establish part restraint, cushion performance or
transport qualification. Those remain explicitly unverified.

Require expected-BOM reconciliation, original triangle validation, internal
group assembly and external insertion checks. For layered envelopes, also run
`bom2kit.layered_design.validate_layered` on the nested envelope candidate's
input/layout. Mesh checks alone do not certify carton walls or support.
An exhausted search is not proof of impossibility.

Freeze source hashes, policy and selected result before evaluation. `assess`
may check a separate copy carrying `reference.external_mm`; do not feed it back
into search. Compare external shipping volume, matching contents and comparable
protection. Continue improving when the requested no-worse criterion fails.
Green tests or a partial kit do not close that objective.

Render the exact validated coordinates. `mesh-report` is a geometric review,
not an assembly instruction. Instructions must show each carton, its contents,
group assembly order/direction and carton insertion order. Bind visuals to the
frozen result. Dimension specifications are not production dielines; geometric
padding is not a manufactured sleeve. Hand access and transport qualification
remain separate from collision-free paths.

`python scripts/build_assembly_plan.py RESULT.json EXPECTED.json --output PLAN.json`
rechecks the BOM, carton hierarchy, original insertion paths, internal templates,
rigid copy mappings and part-to-carton containment. It produces a machine-readable
geometric plan, including workbench poses and carton insertion order. Use this
as the source for illustrated steps; the JSON alone is not the finished operator
instruction. Its fingerprints bind parsed result/BOM objects, not raw file bytes.

### Deliver a visual packing guide

For transport results, make the primary deliverable an English A4 PDF in the
Visual Layout R3 style: exploded outer carton with foam and visible CAD contents,
numbered inner boxes, isometric/top/side views, part thumbnails and quantities,
nested-group assembly cards, and a closing checklist. Keep the technical
comparison HTML as supporting evidence rather than the operator-facing report.

```powershell
python scripts/build_visual_packing_guide.py RESULT.json EXPECTED.json --kit MY-KIT --output packaging-results/my-kit/visual-guide
```

The renderer replays the source/BOM/assembly checks and outputs `packing-guide.pdf`,
`assembly-plan.json` and `guide-manifest.json`. Use the calculated carton count
and placement, not Alan's geometry or page count. Exploded gaps and cutaway walls
are display conventions only; the source poses stay unchanged. Show declared
envelopes honestly when purchased-part CAD is unavailable. Do not synthesize
replacement geometry with image generation. Render and inspect the resulting
PDF pages before delivery. Keep geometric draft/prototype status visible until
the separate shipping qualifications are supported. See `docs/visual-packing-guide.md`.

For local 101/102 cases, read `docs/benchmark-assumptions.md`: preserve accepted
content revisions and the user-confirmed 106 mm custom clamp frame. Old
`assemble_*` scripts and complete-kit comparison recipes do not establish
from-scratch design. The reported 50 L example has no supplied reproducible
layout; do not invent a measured baseline.

Edit this authoritative file, then run
`python skills/bom-to-kit/scripts/sync_skill.py` to synchronize both agent copies.
