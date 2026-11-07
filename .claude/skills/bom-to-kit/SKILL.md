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
the flag alone certifies nothing. Supply an independent expected BOM with a
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

For local 101/102 cases, read `docs/benchmark-assumptions.md`: preserve accepted
content revisions and the user-confirmed 106 mm custom clamp frame. Old
`assemble_*` scripts and complete-kit comparison recipes do not establish
from-scratch design. The reported 50 L example has no supplied reproducible
layout; do not invent a measured baseline.

Edit this authoritative file, then run
`python skills/bom-to-kit/scripts/sync_skill.py` to synchronize both agent copies.
