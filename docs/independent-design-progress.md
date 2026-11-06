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
