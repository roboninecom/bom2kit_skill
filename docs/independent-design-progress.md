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
python scripts/prepare_printing_library.py packaging-inputs/so-arm-102/repository-main/docs/printing.md packaging-inputs/so-arm-102/repository-main/models/stl --output packaging-inputs/independent/102/printed
```

The current run imports 25 types / 44 robot printed parts in approximately 3 s
after dependency import. It does not include figures or purchased hardware.
It reads no old results. Three source STL types fail the positive watertight
volume gate: bottom servo holder, wrist holder and trigger. Compare their STEP
sources before admitting them to collision validation; do not silently repair
shape or accept invalid meshes to obtain a fit.

## Next work

1. Resolve the three source meshes and prepare complete neutral 101/102 input
   libraries, including figures, purchased items, BOM mapping and protection.
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
