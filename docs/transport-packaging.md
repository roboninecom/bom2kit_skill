# Transport packaging workflow

This experimental pipeline designs compatible closed cartons from individual
source geometry, joins them into a complete block without spacers, and adds a
six-face foam shell. It does not use an engineer's cartons or packing poses.
The no-worse SO-ARM101/102 benchmark remains open.

## Inputs and commands

Use a complete millimetre library with original mesh hashes and an independent
expected BOM. Preserve the accepted 106 mm custom clamp frame and source
revisions in [benchmark assumptions](benchmark-assumptions.md). Keep private
inputs and generated artifacts in the ignored directories.

```powershell
python scripts/prepare_transport_policy.py LIBRARY.json --printed-library PRINTED.json --output POLICY.json
python scripts/design_transport_packaging.py LIBRARY.json POLICY.json EXPECTED.json --output packaging-results/transport --time-limit 110 --nesting-budget 140
python scripts/render_transport_review.py packaging-results/transport/result.json EXPECTED.json --output packaging-results/transport/review
```

The classifier records description-based inferences. Review them before use.
Unknown purchased descriptions fail explicitly. `--combine-printed` allows
structural printed parts and learning objects in one printed-only family;
electronics, servos and mechanical parts remain separate. Classification is
not a material-compatibility test.

The policy specifies wall and foam thickness, part padding, permitted rotations,
clearance, dimension increment and carton/type caps. Its family map must cover
every source SKU. These manufacturing requirements are independent inputs,
not parameters copied from Alan's solution.

## Implemented search

1. Verify source hashes and positive watertight geometry; calculate intrinsic
   envelopes without using printer-plate or reference packing positions.
2. Optionally discover nested pairs and extensions within compatible families.
   Coarse 4 mm voxels generate proposals only. Original triangles, clearance and
   internal assembly must pass before a proposal becomes a compound unit.
3. Generate module patterns using maximal free rectangles, several part-order
   heuristics and fully supported envelope columns of repeated units. Preserve
   different height bands for the outer search.
4. Use subset dynamic programming over slicing trees. Join along X, Y or Z and
   enlarge carton cross-sections until the leaves partition the complete block.
   Count a horizontal quarter-turn as the same carton size. No spacers are made.
5. Repack modules against footprints found in the current run, then repeat the
   carton search. Apply the outer wall, four side panels, bottom, lid and top
   reserve exactly once.
6. Replay BOM, original CAD, nested-group assembly, insertion, carton hierarchy,
   compatibility, type/count caps and the nonoverlapping foam shell.

`--largest-family-cartons 2` or `3` tests subdivision of the largest family by
geometry and cumulative volume, within policy caps. It is a candidate strategy,
not an automatic improvement. Keep the smaller fully checked result when
comparing runs. Neither this heuristic nor the slicing search proves optimality.

For automatic selection, add `--portfolio --time-limit 180 --nesting-budget 140`.
The runner compares a fresh baseline, several compatible nesting configurations
and a subdivision trial, retaining the smallest fully verified result. It reuses
only alternatives discovered within that invocation, bound to source and policy
fingerprints. Rejected trials do not replace the incumbent. The total reported
runtime includes every trial, not just the selected one.

The optional `--packing-solver PATH` uses the
[PackingSolver box CLI](https://fontanf.github.io/packingsolver/box.html).
Integer dimensions are conservatively rounded; exact source dimensions are
restored and independently validated. Missing units, invalid orientations,
unsupported envelopes and malformed certificates are rejected. The executable
is supplied explicitly; the engine never downloads one. PackingSolver's open-height
proposals are not a substitute for the no-spacer carton partition.

## Outputs, timing and comparison

`result.json` records original poses, closed-carton geometry, packaging materials,
foam panels, source/policy hashes, algorithm choices and checks.
`assembly-plan.json` binds geometric packing steps to that exact result.
The CLI also hashes the engine files before and after a run; a changed-code run
is exploratory and must not be presented as a frozen-code reproduction.

`--time-limit` covers module and outer search; `--nesting-budget` is additional.
Both are soft budgets. Geometry preparation and final validation can overrun.
Report the measured end-to-end duration, not just the requested search budget.

`scripts/compare_transport_designs.py CONFIG.json --output DIRECTORY` evaluates
frozen designs. Each case supplies `name`, `result`, `before_result`, `bom` and
`reference_external_mm`; optional `reference_image`, `reference_cartons` and
`reference_types` provide independently documented reference evidence.
Before/after source quantities, mesh hashes and protection must agree.
Reference data never enters the design command.

## Qualification limits

An exact carton block reduces nominal movement between closed cartons. It does
not prove restraint of their contents. Envelope support does not prove contact
or stability of irregular CAD surfaces. Padding is a geometric allowance, not
a manufactured protective sleeve. Foam grade, compression, tolerances, hand
access, carton strength, purchase prices and transit tests remain unqualified.
The report must retain those distinctions even when a volume target is met.
