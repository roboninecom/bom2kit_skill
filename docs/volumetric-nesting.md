# Volumetric source-part nesting

This mode proposes cavity use, complementary shapes and protected stacks from
original CAD. It does not consume engineer carton dimensions or packing poses.
It is an experimental portfolio member: preserve the better verified incumbent.
The full SO-ARM101/102 no-worse-than-Alan objective remains open.

## Reproduce

Run from the repository root with the existing `[mesh]` dependencies:

```powershell
python scripts/build_volumetric_catalog.py LIBRARY.json POLICY.json --output packaging-results/volume/catalog.json --cache packaging-results/volume/cache --pose-cache packaging-results/pose-cache --max-pairs 24 --pair-seconds 12 --cluster-seconds 30
python scripts/design_concept_packaging.py LIBRARY.json POLICY.json EXPECTED.json --output packaging-results/volume/concepts --cache packaging-results/pose-cache --motifs volumetric --volumetric-catalog packaging-results/volume/catalog.json --grouping type --placement-style cohesive --time-limit 150 --wall-limit 900
```

Also compare the family-partition planner by passing the same
`--volumetric-catalog` to `scripts/design_practical_packaging.py`. Both planners
retain ordinary floor candidates. Search budgets are soft; the design runners'
`--wall-limit` includes preparation and replay. Catalog preparation currently
has no process supervisor: account for it separately within the task deadline.

To preserve row-generated carton architectures while trying nesting inside them,
use `--motifs rows --volumetric-catalog CATALOG.json
--volumetric-refinement-budget 60`. This avoids changing the initial partition
estimates when a catalog's locally compact motifs rank whole-kit concepts poorly.
Both the refined proposal and its fallback still require independent replay.

The practical planner also compares motif-aware content partitions. A compact
combination stays together during height-based partition estimates, preventing
the ordinary SKU split from separating its members before placement search.
These temporary estimate objects are expanded back into exact original unit
IDs. They neither introduce cartons nor require carrying several loose parts
as one object. Ordinary partitions remain competing alternatives.
The practical runner accepts `--annotations FILE.json` for evidence-tagged
semantic labels and saves `part-properties.json`. Before layout generation it
reunites any split accessory set in the least-cost generated partition. Final
replay independently rejects split sets. A smaller geometric layout that
separates an ArUco core from its faces is not an accepted kitting improvement.
Initial carton-count alternatives are visited round-robin. `--types 4 7` can
compare a lower procurement cap with individually sized cartons; defaults still
prefer fewer types. Joint refinement also tests motifs at footprints generated
by the current run. If later floor repacking lowers the required height, the
outer block is retiled and independently replayed rather than keeping stale
larger exterior dimensions.
The final floor-repair pass keeps the original motif as a competing pattern.
A repair fitting an expanded carton can have a lower height but a wider floor;
it no longer replaces nesting before comparing both complete shipping blocks.
If retiling cannot improve the block, the original source poses are preserved.

Inspect local combinations, optionally rendering actual CAD with `[report]`:

```powershell
python scripts/replay_volumetric_motifs.py LIBRARY.json POLICY.json packaging-results/volume/catalog.json --output packaging-results/volume/motifs --maximum 5 --render --control-floor
```

These subset experiments do not prove that a motif is selected in the full kit.
Use the accepted result's individual poses and motif records for final guides.
`--control-floor` generates and independently replays a separate floor-layout
control with the same source quantities and protection, and reports external
shipping volume for both. A smaller local pair envelope can still lose after
carton walls and six-face foam. Keep negative results; this bounded control
portfolio is not an optimality certificate.
`--extend-catalog EXISTING.json` reuses pair proposals and searches larger
combinations without repeating pair discovery. New BOM quantities are checked
when selecting motifs; new or changed geometry needs new discovery.

`--merge-catalog EARLIER.json` adds source-bound pair alternatives before
extension. `--source-kinds factory_carton` can supplement printed-part search
with retained factory cartons. `--cluster-correlation-seconds 120` additionally
searches fresh translations against a complete multi-part obstacle, instead of
only chaining previously discovered pair alignments. The temporary combined
mesh is a search obstacle, never a BOM item or a rigid handling instruction.
Depth-first extension is the default: two promising partners per seed and a
3 mm proposal grid let the bounded search reach four to six source parts before
exhausting its budget on pairs. `--cluster-order breadth --cluster-partners 6
--cluster-pitch 2` restores the broader, finer proposal experiment. Neither
configuration changes original-source clearance or support acceptance.

For a practical run, optionally pass `--rectangle-solver PATH
--motif-rectangle-budget 40`. PackingSolver translates source-motif envelopes
while retaining each seed's orientation, internal source poses, directional
access lanes and contact sheets. It is a layout proposal, not a rigid assembly.
The complete source and hand replay remains mandatory. `--rectangle-budget`
separately controls ordinary floor proposals. The finite CP-SAT carton master
samples diverse motif and floor patterns rather than only the first floor rows.

## Algorithm and evidence

1. Rank compatible source pairs by geometric void potential, spreading the
   budget across parts. Purchased envelopes retain their declared dimensions;
   their empty bounding space is not treated as a physical cavity.
   Declared factory cartons are eligible for protected flat-interface stacks;
   ordinary purchased-item envelopes are not relabeled as load-bearing cartons.
2. Generate independent stable contact faces and relative quarter-turns.
   `scipy.signal.fftconvolve` correlates **3D occupied voxels**, not projected
   silhouettes. Candidate translations use the floor and original horizontal
   support faces. Internal downward-facing surfaces are also considered: an
   upper U-shaped part can rest on a post while its legs extend below the
   contact plane. Quantization only proposes poses.
3. Recheck original triangle collision and protected clearance with FCL. Check
   enclosed solids with component-wise point containment. Reuse acceleration
   trees across translations. Supported pairs include explicit contact sheets.
   Paired horizontal faces bind both contact planes to original triangles;
   a sheet cannot stand in for a missing support. Replay checks contact area,
   the combined load line, sheet collision and intermediate removal stability.
4. Extend pairs into combinations of up to six individual parts, retaining
   source transforms, quantities and support relationships. Recheck all member
   collisions. Fresh cluster correlation can find third-part translations that
   pair-template chaining misses. Extension failure does not prove that no
   larger nesting exists.
5. Use a bounded exact-coverage beam at shared height bands to select motifs
   and remaining single parts. Compare footprint savings at a common carton
   height; isolated pair volume can wrongly discard useful stacks. Retain
   volume, footprint and height alternatives for carton tiling. Unselected
   copies remain individually placeable rather than occupying one reserved
   rectangle per SKU. Directional access lanes propose tighter floors; the
   unchanged fingertip replay still decides acceptance.
6. Expand every original unit before the existing full-kit BOM, geometry,
   compatibility, foam, support and hand-access replay. A motif is neither a
   new purchased box nor a rigid preassembly.

The cache binds source hashes, pose options, protection, pitch, search parameters
and the pair engine hash. Cached proposal geometry still requires complete-kit
replay. Report cache hits separately from cold search time. The
source-voxel disk cache separately binds mesh hash, pose, pitch and rasterizer
version, and avoids rerasterization after a process restart. Original source
files are still hash-checked. The
`saving_vs_best_separate_fraction` metric compares a pair with the best
side-by-side envelope among its prepared orientations, excluding carton walls.
It is not the complete shipping-volume saving. Larger-cluster selection costs
are heuristic estimates, not measured control layouts.

The R3 guide now includes close-up cards for combinations actually selected in
the frozen result, using source-unit IDs and contact-sheet relationships. A
catalog-only example cannot appear as a used combination. These cards preserve
the checked source poses and individual insertion order. Their explicitly
labeled same-orientation row comparison is geometric envelope arithmetic, not
a separately optimized or assembly-verified control carton.

## Backend trials and limits

The initial native setup trials used
[psacking](https://github.com/Vrroom/psacking/tree/515060015ae7fd1ba437aefe4a33df36d56ba3b9)
and [sparrow-3d](https://github.com/JonasTollenaere/sparrow-3d/tree/bf9babfe7adc953cb41f7b1e4196566139873afe).
The former required an unavailable compiled CUDA extension. The latter needed
the C++/CGAL/MeshCore toolchain; both HTTP and HTTPS WSL dependency setup attempts
failed. Neither native engine completed a real-part benchmark. The implemented
CPU correlation is a separate implementation, not a psacking benchmark result.
Setup logs are retained under ignored `packaging-results/volume-round5/`.

Current motion replay checks straight vertical insertion/removal and a fingertip
model. A failure is not proof against a tilted or rotated insertion path. General
SE(3) motion planning, arbitrary frictional contacts and deformable wrapping are
not implemented. Stable-face search is not exhaustive orientation search.
Static support assumes uniform source-solid density and does not certify EPE
bearing strength, shipping retention or drop-test performance.
