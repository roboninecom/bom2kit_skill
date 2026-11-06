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
