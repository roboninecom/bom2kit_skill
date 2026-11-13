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

Grouping modes are `assembly`, `type`, `sku`, `shape`, `adaptive`, `adaptive_type`
and `replicated`. Shape cohorts
use Trimesh's rigid-invariant descriptor only to suggest neighbors; every original
mesh and identity remains in the final replay. Adaptive grouping splits whole SKUs
when height/footprint estimates justify the added group, and permits later reunion.
Declared small accessory sets (fiducial object, learning objects and identification)
remain atomic for carton assignment even when shipped disassembled. Height or copy
splitting must not isolate marker faces from their core or create a thin label
carton merely to improve volume. This is a kitting rule applied to evidenced
semantic labels, not a reference recipe or rigid-handling assumption. Independent
whole-set membership replay gates concept acceptance and operator guides.
`adaptive_type` applies that split to type groups. `replicated` also proposes two
balanced repetitions when a group contains repeated units; original unit IDs are
preserved and later concepts may reunite them. Packets are never opened by this split.

## Search and geometry

1. `concept_patterns.py` generates equal-orientation rows, actual flat-interface
   stacks with enumerated contact sheets, alternating floor pairs and supported
   nesting. `hybrid` includes all four motif families per carton; adding a
   family can change bounded search ranking and is not a monotonic improvement.
   Zones are search envelopes, **not extra boxes or rigid handling assemblies**.
2. `concept_planner.py` uses a bounded beam, placing the largest constraining
   groups first. It compares compact, balanced and organized scoring profiles;
   incompatible families never share a carton. Multiple carton counts survive.
   Cohabitation is normalized by compatible group-pair count so finer labels do
   not overwhelm volume. Bounded whole-group moves/swaps reconsider early choices.
   Expensive geometry trials cover distinct carton counts before nearby beam
   variants, reducing starvation of simple architectures under a time limit.
3. The cohesive strip heuristic penalizes growth of a group's occupied region
   without assigning it an inflexible rectangular compartment. Same-SKU orientation
   reuse and group-aware pair/support selection reduce arbitrary interleaving.
4. `carton_tiling.py` chooses and expands carton dimensions into a complete slicing
   block. Six-face foam, cardboard walls and the no-interbox-spacer rule are retained.
   Joint refinement feeds only footprints generated during this invocation back
   into the same source groups.
   Intact source-based carton patterns retain a horizontal quarter-turn option;
   source poses, contact sheets and geometric zone metadata rotate together.
   This preserves gravity support and avoids relying on an independently
   regenerated floor pattern to rediscover the opposite carton footprint.
5. Optional source-surface refinement tries smaller footprints and real 3D support
   surfaces within each compatible carton, with soft type/assembly affinity. It preserves the unrefined geometric
   proposal when no smaller complete arrangement is found. Independent replay can
   still reject either proposal.
6. Validation failures identify affected cartons. Local repair keeps unaffected
   patterns and first reserves access around blocked units. A whole-carton margin
   is the fallback. Both repairs retile and replay; neither lowers finger, support,
   clearance or protection thresholds. Row compaction preserves required clearance
   even when neighboring X intervals are disjoint but closer than the required gap.
7. Optional `--assignment-budget 90` revisits whole-group assignments using the
   regenerated carton/block volume. It moves, exchanges or splits semantic groups,
   regenerates only affected cartons and retiles the complete package. This differs
   from the beam's preliminary height/area estimate. The bounded proposals still
   need full source, material, support and access replay; the original in-run
   proposal remains a fallback. Pareto filtering counts SKU and semantic splits.

Pair motifs cache source-relative transforms keyed by both source hashes, frames
and protection. Reuse creates fresh unit identities. Cached proposal success never
substitutes for original-mesh clearance or insertion replay. Timed failure is not
cached as infeasibility. Stable-pose preparation is also reusable and separately timed.
Already explored bounded pair probes can be deferred until a larger budget is
available; other partners remain eligible. Source-hash equality allows repeated
geometry at different paths to share a proposal, never an identity. Vertex-plane
offsets complement coarse pair sampling; FCL still checks original triangle clearance.
Floor-pair proposals also correlate dilated 3 mm voxel occupancy along shared Z
columns with SciPy FFTs. This ranks XY translations for stable, independently
supported parts; it does not turn the pair into a rigid assembly. Coarse raster
emptiness never certifies clearance. Original triangles, full source containment
and individual insertion still gate acceptance. Cold voxel preparation is charged
to elapsed time; a short bounded narrow phase may exceed the soft pair budget.
The second member can use its minimum-height or minimum-footprint stable pose,
not just a same-height opposite face. Pairs rank their resulting 3D envelope;
the original source transform, identity and independent support are preserved.

Motifs prefer shared type **or** assembly labels within the hard compatibility
family. Compact 3D proposals retain separately ranked empty-floor fallbacks so a
bounded queue of colliding cavity candidates cannot hide all free positions.
The `--minimum-sheet-side 10` default rejects generated contact sheets with width
or depth below 10 mm. This is an explicit manual cutting/handling assumption,
not a strength or cushioning standard; source packets remain unchanged.
The check acts while selecting individual interfaces so one tiny contact does
not discard every otherwise valid stack in a carton. Final replay and the guide
recompute the material screen from the actual sheet dimensions.

Source-surface refinement includes a footprint-first alternative, with a height
cap derived from the minimum-footprint stable source orientations. A low existing
carton must not accidentally forbid those taller poses. This remains a proposal;
actual contact, complete intermediate load states and individual access decide acceptance.
Supported nesting also probes connected horizontal support patches, rather than
only the parent part's overall center. Every proposed interface still needs
source clearance, a sufficiently large contact sheet and independent load replay.

`--irregular-solver PATH --irregular-budget 150` optionally invokes the installed
PackingSolver Irregular binary on full projected source outlines. Projections are
prepared lazily for selected stable frames and cached within the invocation.
The solver preserves compatible-carton membership; it does not promise type
adjacency. Report measured organization and retain the simpler in-run fallback
if original geometry, access, or subsequent repair rejects an apparent improvement.
Contour proposals retain actual part padding but omit the heuristic row-access
lane. The unchanged two-finger trajectory check, local repair and fallback decide
whether their tighter arrangement is usable; a zero proposal lane is not a lower
finger-clearance threshold.

`--preserve-contact-faces` retains different stable support faces with equal
bounding dimensions, including opposite orientations. Floor pairs may reuse the
opposite face while keeping each original source independently supported; the 3D
surface proposer also considers these alternatives. Bounding-box equality alone
does not establish interchangeable nesting geometry. Source-only concept search
skips unused projected-contour preparation; contour solvers retain full projections.

## Run and reproduce

```powershell
python scripts/design_concept_packaging.py LIBRARY.json POLICY.json EXPECTED.json --output packaging-results/concepts --cache packaging-results/pose-cache --grouping type --motifs rows --placement-style cohesive --time-limit 150 --wall-limit 900 --max-replays 4 --assignment-budget 60 --refinement-budget 15 --repair-budget 90
python -m pytest -q tests/test_concept_packing.py tests/test_practical_packing.py
```

Typed rows are the CLI starting point because the real-case portfolio did not
show a consistent benefit from more expensive motifs. Compare a separate
`--motifs hybrid --grouping adaptive_type` run without replacing the incumbent
automatically. Relative quarter-turns of a nested child preserve its stable face
and original transform; independent support, protection and grip replay still apply.

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

The concept Pareto filter uses source/contact-sheet placements, carton count,
carton-size count, SKU orientation changes and organization/split metrics as
separate dimensions. The comparison report additionally counts liner, carton
forming/closing/insertion and foam events under declared assumptions. This
expanded inventory is report-only: it is not a calibrated labor objective in
the beam score or Pareto filter. Preparation, labeling and rework remain excluded.

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

`space_use.py` measures the exact union of protected source AABBs and declared
liners/contact sheets inside each cavity. Space outside that union is a lower
bound on unoccupied volume, not usable extra capacity; concave source shapes can
have additional internal voids. Report it separately from wall/outer-foam overhead.

Render only independently passing results with `build_visual_packing_guide.py`.
Preserve full current BOMs, the confirmed 106 mm clamp, 1.5 mm inner walls and the
accepted protection. A changed-BOM test and measured comparison against Alan are
required independently of unit-test success.
