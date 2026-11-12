# Concept-first practical packing

The new experimental planner starts with part properties and meaningful groups,
then generates arrangements and reconciles carton dimensions. It does not load
Alan's grouping, coordinates, carton sizes or target volume. The acceptance target
in [the goal](concept-packing-goal.md) remains open; an executable architecture is
not evidence of a better shipping kit.

## Data and decisions

`part_properties.py` builds evidence-tagged cards for type, assembly, material,
fragility, repetition, packing state, protection and stable orientations. Textual
classification and visual annotations are assumptions, not permission to reduce
protection or use a part as a structural support. Unknown materials remain unknown.
The optional annotation JSON maps item IDs to `part_type`, `assembly`, `material`
or `fragility`, each with `value`, `status` and `source`.

Grouping modes are `assembly`, `type`, `sku`, `shape` and `adaptive`. Shape cohorts
use Trimesh's rigid-invariant descriptor only to suggest neighbors; every original
mesh and identity remains in the final replay. Adaptive grouping splits whole SKUs
when height/footprint estimates justify the added group, and permits later reunion.

## Search and geometry

1. `concept_patterns.py` generates equal-orientation rows, actual flat-interface
   stacks with enumerated contact sheets, alternating floor pairs and supported
   nesting. `hybrid` preserves competing row/stack/pair patterns per carton.
   Zones are search envelopes, **not extra boxes or rigid handling assemblies**.
2. `concept_planner.py` uses a bounded beam, placing the largest constraining
   groups first. It compares compact, balanced and organized scoring profiles;
   incompatible families never share a carton. Multiple carton counts survive.
   Cohabitation is normalized by compatible group-pair count so finer labels do
   not overwhelm volume. Bounded whole-group moves/swaps reconsider early choices.
3. The cohesive strip heuristic penalizes growth of a group's occupied region
   without assigning it an inflexible rectangular compartment. Same-SKU orientation
   reuse and group-aware pair/support selection reduce arbitrary interleaving.
4. `carton_tiling.py` chooses and expands carton dimensions into a complete slicing
   block. Six-face foam, cardboard walls and the no-interbox-spacer rule are retained.
   Joint refinement feeds only footprints generated during this invocation back
   into the same source groups.
5. Optional source-surface refinement tries smaller footprints and real 3D support
   surfaces within each semantic group. It preserves the unrefined geometric
   proposal when no smaller complete arrangement is found. Independent replay can
   still reject either proposal.
6. Validation failures identify affected cartons. Local repair keeps unaffected
   patterns and first reserves access around blocked units. A whole-carton margin
   is the fallback. Both repairs retile and replay; neither lowers finger, support,
   clearance or protection thresholds. Row compaction preserves required clearance
   even when neighboring X intervals are disjoint but closer than the required gap.

Pair motifs cache source-relative transforms keyed by both source hashes, frames
and protection. Reuse creates fresh unit identities. Cached proposal success never
substitutes for original-mesh clearance or insertion replay. Timed failure is not
cached as infeasibility. Stable-pose preparation is also reusable and separately timed.

`--preserve-contact-faces` retains different stable support faces with equal
bounding dimensions, including opposite orientations. Floor pairs may reuse the
opposite face while keeping each original source independently supported; the 3D
surface proposer also considers these alternatives. Bounding-box equality alone
does not establish interchangeable nesting geometry. Source-only concept search
skips unused projected-contour preparation; contour solvers retain full projections.

## Run and reproduce

```powershell
python scripts/design_concept_packaging.py LIBRARY.json POLICY.json EXPECTED.json --output packaging-results/concepts --cache packaging-results/pose-cache --grouping type --motifs hybrid --placement-style cohesive --time-limit 180 --wall-limit 900 --max-replays 4 --refinement-budget 45 --surface-budget 60 --repair-budget 90
python -m pytest -q tests/test_concept_packing.py tests/test_practical_packing.py
```

The time limit is a soft proposal budget; the wall limit includes preparation and
replay and terminates the owned subprocess tree. `run.json` records all stage times,
input/engine hashes, failed trials and verified Pareto alternatives. Compare warm
and cold timings explicitly. Concurrent runs are not controlled speed benchmarks.
`proposal-*.json` files are diagnostic proposals, not accepted operator instructions.
Keep the best fully replayed incumbent across experiments rather than replacing it
with a worse result merely because it uses the new planner.

## Evaluation and limits

Report external volume, cartons and carton sizes separately from factory cartons,
packets, floor liners and contact sheets. Count source placements, sheet placements,
SKU orientation changes and splits. Real procurement prices and operator times are
unknown until measured. Existing packets retain their source contents and protection;
the planner does not assume that a newly drawn bag makes loose parts rigid.

Organization metrics use the **same cards for before and after**. Group cohabitation
pairs measure shared cartons, not proven physical intermixing. Connected components
use a declared 10 mm AABB-distance proxy. Type grouping is the primary measurement;
assembly grouping is recorded separately. Visual inspection remains necessary.

`retention_screen.py` can prove an empty rigid-translation path through conservative
source bounding boxes. It reports movement over a diagnostic 5 mm threshold, not a
transport standard. Overlapping bounds are indeterminate; blocked bounds do not
prove restraint. Friction, rotation, bag compliance, cushion performance and drop/
vibration tests remain outside this screen. Geometric acceptance must never be
presented as shipping qualification.

Render only independently passing results with `build_visual_packing_guide.py`.
Preserve full current BOMs, the confirmed 106 mm clamp, 1.5 mm inner walls and the
accepted protection. A changed-BOM test and measured comparison against Alan are
required independently of unit-test success.
