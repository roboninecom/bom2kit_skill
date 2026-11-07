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
python scripts/design_transport_packaging.py LIBRARY.json POLICY.json EXPECTED.json --output packaging-results/transport --portfolio --time-limit 240 --nesting-budget 140
python scripts/render_transport_review.py packaging-results/transport/result.json EXPECTED.json --output packaging-results/transport/review
```

The classifier records description-based inferences. Review them before use.
Unknown purchased descriptions fail explicitly. `--combine-printed` allows
structural printed parts and learning objects in one printed-only family;
electronics, servos and mechanical parts remain separate. Classification is
not a material-compatibility test.
`--combine-protected-electronics` additionally groups protected servos with
protected electronics and cables, requiring explicit protective/factory packing
evidence in the input. Bare mechanical parts remain separate from printed parts.

The policy specifies wall and foam thickness, part padding, permitted rotations,
clearance, dimension increment and carton/type caps. Its family map must cover
every source SKU. These manufacturing requirements are independent inputs,
not parameters copied from Alan's solution.

## Implemented search

1. Verify source hashes and positive watertight geometry; calculate intrinsic
   envelopes without using printer-plate or reference packing positions.
2. Optionally discover nested pairs and extensions within compatible families.
   Voxels (4 mm by default) and translation refinement generate proposals only.
   Disjoint ranked streams can run in parallel. Original triangles, clearance
   and internal assembly must pass before a proposal becomes a compound unit.
   Integer set packing resolves competing group quantities; greedy and nearby
   groupings remain competitors because envelope savings are not shipping volume.
3. Generate module patterns using maximal free rectangles, several part-order
   heuristics, supported surfaces and columns. Bounded order/orientation evolution
   improves supported placements. Preserve height bands for the outer search.
4. Use subset dynamic programming over slicing trees. Join along X, Y or Z and
   enlarge carton cross-sections until the leaves partition the complete block.
   Count a horizontal quarter-turn as the same carton size. A complete beam-search
   incumbent survives subset-search timeouts. A uniform carton grid also competes;
   fewer sizes do not guarantee lower volume. No spacers are made.
5. Repack modules against footprints found in the current run, then repeat the
   carton search. Apply the outer wall, four side panels, bottom, lid and top
   reserve exactly once.
6. Replay BOM, original CAD, nested-group assembly, insertion, carton hierarchy,
   compatibility, type/count caps and the nonoverlapping foam shell.

`--largest-family-cartons 2` or `3` tests subdivision of the largest family by
geometry and cumulative volume, within policy caps. It is a candidate strategy,
not an automatic improvement. Keep the smaller fully checked result when
comparing runs. Neither this heuristic nor the slicing search proves optimality.

For a single-strategy run, `--partition-strategy packing` instead proposes
membership using actual partial floor layouts. `--balanced-cartons N` allocates
the carton budget across families by envelope volume. These options do not
accept predefined SKU groupings or reference cartons. Compare them against the
unsplit result: premature partitioning can make the complete block much larger.

For automatic selection, use `--portfolio --time-limit 240 --nesting-budget 140`.
The runner compares a fresh baseline, several compatible nesting configurations
and a subdivision trial, retaining the smallest fully verified result. It reuses
only alternatives discovered within that invocation, bound to source and policy
fingerprints. Rejected trials do not replace the incumbent. The total reported
runtime includes every trial, not just the selected one. A `not_improved` trial
cannot beat the current invocation's checked incumbent and skips expensive
original-mesh replay; it is not a certified alternative.

Optional search controls:

| Option | Effect |
| --- | --- |
| `--nesting-workers 4` | Separate processes explore disjoint pair proposals; 1-8 workers. |
| `--nesting-pitch 2` | Finer proposal grid; higher preparation/search cost, unchanged exact clearance. |
| `--shared-footprint-budget 40` | Co-design family carton footprints and heights; portfolio limits this to half each trial's budget. |
| `--polish-budget 180` | Additional supported order/orientation search on the winning grouping from this invocation; retains the checked incumbent. |
| `--nesting-objective balanced` | Experimental aspect-sensitive CAD pair ranking; shipping volume still determines the winner. |
| `--heightfield-budget 180` | Experimental whole-family CAD insertion using heightfields and inaccessible-space scoring. Requires the portfolio. |

Heightfield proposals still require original geometry and assembly checks. This
strategy has not improved the measured complete 101/102 results; it is not a
recommended substitute for the checked incumbent.

The optional `--packing-solver PATH` uses the
[PackingSolver box CLI](https://fontanf.github.io/packingsolver/box.html).
Integer dimensions are conservatively rounded; exact source dimensions are
restored and independently validated. Missing units, invalid orientations,
unsupported envelopes and malformed certificates are rejected. Validly decoded
box proposals may also seed a fresh support-constrained reconstruction, which
must independently pass all envelope checks. The executable
is supplied explicitly; the engine never downloads one. PackingSolver's open-height
proposals are not a substitute for the no-spacer carton partition.

`--rectangle-solver PATH` separately uses the
[PackingSolver rectangle CLI](https://fontanf.github.io/packingsolver/rectangle.html)
to improve generated floor layouts. Each seed fixes a vertical axis and permits
only authorized horizontal turns. All parts remain on the carton floor. The
adapter verifies quantities, exact dimensions, orientations, clearance and support;
it never treats the external solver's success as a certificate.

### Optional CP-SAT proposals

`--cp-sat-python PATH` runs OR-Tools in a separate interpreter. Install it explicitly,
without replacing the engine's geometry dependencies:

```powershell
python -m venv packaging-results/tools/cpsat
packaging-results/tools/cpsat/Scripts/python.exe -m pip install ortools==9.15.6755
```

Pass that interpreter to the transport CLI. The adapter searches vertical axes
and floor positions using optional rectangles and `NoOverlap2D`. A second model
jointly selects bounded supported columns (up to four envelopes per column) and
their positions, with exactly one occurrence of every source unit. Both use
conservatively rounded dimensions and independently replay exact envelopes;
the enclosing pipeline still checks original CAD, quantities and assembly.
The backend can time out or return no useful improvement. An optimal status
only concerns its restricted envelope model, not the complete CAD problem.
No solver is downloaded automatically. Source-derived candidates and existing
in-run layouts provide hints; engineer layouts are never supplied.

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
Optional `before_review` points to a previous transport review whose result hash
must match `before_result`. The comparison embeds its outer view and all current
inner-carton CAD views. Images use separate display scales; compare dimensions.
Use `reference_caption` to distinguish an inner-carton illustration from a
complete outer layout when only partial reference illustrations are available.
Before/after source quantities, mesh hashes and protection must agree.
Reference data never enters the design command.

## Qualification limits

An exact carton block reduces nominal movement between closed cartons. It does
not prove restraint of their contents. Envelope support does not prove contact
or stability of irregular CAD surfaces. Padding is a geometric allowance, not
a manufactured protective sleeve. Foam grade, compression, tolerances, hand
access, carton strength, purchase prices and transit tests remain unqualified.
The report must retain those distinctions even when a volume target is met.
