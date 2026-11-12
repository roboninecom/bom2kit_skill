# Transport packaging: implementation audit and recommended redesign

**Subsequent requirement:** no spacers between inner cartons. The spacer
recommendation below is superseded by adjusting carton dimensions to form a
complete block; the external six-face protective foam is still required.

Research date: 7 November 2026. Audited code: `ffb2a5e`.
Scope: code inspection, frozen 101/102 artifacts and primary-source research.
No new packing search, supplier quotation or physical test was performed.

Follow-up: [algorithm and implementation design](transport-packaging-algorithms.md)
provides concrete data contracts, optimization constraints, floorplan/foam
algorithms and executed research probes. This audit remains the problem analysis.

## Decision

Keep the existing CAD, BOM and motion validators. Replace volume-first grouping
with a packaging policy and a small, reusable family of purchasable cartons.
Generate protected, identifiable kitting modules, arrange their closed cartons
inside an explicitly modeled foam enclosure, and optimize cost/handling as well
as volume. Changing the geometric solver alone will not fix the current problem.

This recommendation supersedes the volume-first ranking in
[the earlier implementation review](from-scratch-design-review.md).
It does not replace the requirement for independent design or justify copying
Alan's grouping, dimensions or placements into search inputs.

## What the current artifacts actually contain

Source: `packaging-results/independent/{101,102}/hour-membership/result.json`.
All dimensions below are nominal external carton dimensions in millimetres.

| Property | 101 | 102 |
| --- | --- | --- |
| Outer carton | 253 x 253 x 305 | 252 x 264 x 330 |
| Inner carton count | 3 | 5 |
| Inner carton dimensions | 209 x 209 x 145 / 70 / 45 | 208 x 220 x 95 / 39 / 45 / 48 / 58 |
| Slots per inner carton | 28, 16, 22 | 24, 12, 14, 26, 24 |
| Declared outer protection | 15 mm on every face | 15 mm on every face |
| Generated inner carton sizes | 3 distinct sizes | 5 distinct sizes |

There are eight distinct inner-carton dimension triples across the two kits,
not dozens of physical inner boxes. Many small rendered cuboids are supplied
component models or packed-component envelopes, not purchasable cartons.
Dimension triples alone are not complete procurement SKUs.

The selected cartons already form full-footprint, vertically adjacent stacks.
In 101, their height sum is 260 mm, inside a 291 mm outer cavity: 30 mm is
reserved for bottom/top protection and 1 mm remains, including the 0.8 mm booklet
reservation. In 102, the corresponding values are 285 mm and 316 mm. Horizontal
protection occupies 30 mm of each outer cavity dimension. Therefore adding the
same 15 mm foam geometry must not add another 30 mm to the shipping dimensions.

The important distinction is **tight outer modules versus retained contents**.
Closed inner cartons nominally cannot exchange contents, but loose parts inside
each carton can still move. Every current inner carton contains both purchased
hardware and printed-part sources. Source IDs provide evidence of mixing, not
a reliable material taxonomy: several printed sources use other ID prefixes.

Alan's supplied documents show named modules, quantities, bag labels, separation
instructions and an outer EPE arrangement. These are useful operational criteria;
they are not evidence of measured packing time, quoted cost or passed transit
tests. The 102 printing guide also describes bags: a reference picture alone
must not be interpreted as a complete shipping-material specification.

## Root causes in the implementation

| Code | Current behavior | Required change |
| --- | --- | --- |
| `models.py::normalize` | Protection reduces usable bounds; units retain geometry and rotations | Preserve typed handling, compatibility and evidence metadata |
| `mesh_envelope_design.py::design_mesh_envelopes` | Uniform padding; unrestricted rotations required; narrow metadata allowlist | Per-item approved packing states, rotation rules and protection options |
| `group_design.py`, `group_portfolio.py` | Rank clusters by envelope-volume savings; concatenate source meshes | Restrict candidates by kitting compatibility and physical retention recipe |
| `layered_design.py::design_layers` | Generates arbitrary millimetre carton heights; accepts smaller volume | Select carton SKUs or bounded custom families; retain cost/complexity trade-offs |
| `layer_neighborhood.py`, `layer_repair.py` | Moves membership and repairs dimensions for volume | Enforce the same policy after every move, not just initial grouping |
| `validation.py`, `validate_layered` | Coverage, bounds, clearance, rectangular base support, top insertion | Separate retention, tolerance, mass/load and procurement checks |
| `mesh_motion.py` | Treats a declared group as moving together | Require a bag/tray/fixture or an actual supported assembly method |
| `assessment.py` | Computational acceptance combines BOM, static geometry and nominal volume | Separate geometry, logistics policy, procurement, kitting and physical qualification |
| `solid_views.py`, report scripts | Show source geometry and cutaway inner walls | Also show outer carton, foam, closures, dividers and material IDs |

`packaging_bom` in the selected layered candidates lists only the closed inner
cartons. It does not supply purchasable foam panels, outer carton, bags, tape,
labels or dividers. Thickness alone is not a board-strength specification.
The existing `optimization.py` catalogue utility is not an immediate replacement:
it filters candidates against a supplied reference volume and remains volume-only.

The validators are valuable but certify specific abstractions. Full support of
a rectangular envelope does not prove stable support of its irregular contents.
A collision-free group transform does not make loose pieces a rigid assembly.

## Approaches evaluated

| Approach | Benefit | Decision |
| --- | --- | --- |
| More unrestricted CAD nesting | May reduce nominal volume | Defer; can worsen mixing and handling |
| Catalogue cartons + protected functional modules | Limits purchasing complexity and makes contents repeatable | Recommended first implementation |
| A few custom modular carton sizes shared across kits | Can reduce empty space while preserving purchasing scale | Compare with catalogue options using real batch quantities |
| Trays/dividers/pouches inside shared cartons | Separates parts without one carton per item | Enumerate as protection options; include material and assembly cost |
| Die-cut foam nests for every component | Can provide repeatable restraint | Optional for vulnerable parts; do not assume tooling and picking costs are justified |
| CP-SAT selection of feasible module patterns | Expresses exact coverage, compatibility, SKU activation and budgets | Recommended bounded discrete stage |
| PackingSolver or SCIP branch-and-price | Alternative rectangular backend or larger pattern catalogue | Benchmark later if the discrete stage is the bottleneck |
| Full contact/dynamic simulation | Can investigate specific mechanical failures | Not the first fix; needs material/contact data and still requires validation |

Google's [bin-packing example](https://developers.google.com/optimization/pack/bin_packing)
illustrates assignment and bin-use variables, but scalar capacity does not prove
3D fit. [CP-SAT](https://or-tools.github.io/docs/pdoc/ortools/sat/python/cp_model.html)
can select discrete patterns; each pattern must carry its own checked geometry.
[SCIP's example](https://www.scipopt.org/doc/html/BINPACKING_MAIN.php) demonstrates
branch-and-price for bin packing, not a ready-made transit-packaging system.
[PackingSolver](https://github.com/fontanf/packingsolver) is an alternative geometry
backend to evaluate, not a source of this project's missing handling policy.
None was benchmarked for the proposed policy during this research.

## Recommended pipeline

1. **Enrich the BOM.** Store functional/kitting family, material, measured mass,
   fragile surfaces, ESD requirements, approved rotations, packed dimensions and
   uncertainty. Separate SKU identity from packing-unit identity. Unknown fields
   remain unknown; an agent's inferred class needs recorded evidence/confidence.
2. **Define compatibility.** Hard rules express forbidden unprotected contact,
   required barriers, maximum mass and must-stay-together sets. Prefer functional
   grouping as well as material grouping: neither all-metal nor all-plastic is
   automatically the right module. A protected mixed module can be allowed
   explicitly. These rules come from BOM/process requirements, not Alan's poses.
3. **Load purchasing options.** Each carton option has supplier ID, internal and
   external toleranced dimensions, construction, board/load specification,
   availability, MOQ, price tier and setup cost. Include common bags/dividers.
   Optimize the shared carton family for 101 and 102, then solve each kit's layout.
4. **Generate feasible module patterns.** Pack only compatible protected units;
   keep several shapes and carton options. Irregular nesting is allowed only
   when wrapping, restraint and assembly remain realizable. Cache by geometry,
   policy, packaging SKU and tolerance hashes, not geometry alone.
5. **Select modules and tile the outer cavity.** Choose a small set of patterns
   covering each BOM unit exactly once. A binary SKU-activation variable counts
   distinct packaging types across both kits. Arrange closed modules in supported
   rows/layers; fill remaining functional gaps with specified removable spacers.
   Catalogue dimensions need not tile perfectly, so an adjacency graph alone is
   insufficient: record allowed travel and each restraining face or insert.
6. **Construct physical protection.** Produce bottom, four side and top foam
   pieces, including their joint convention, cut sizes, material grade and
   assembly order. Model bags, dividers and closure allowances. Existing foam
   reservation is consumed exactly once. Render an exploded outer assembly and
   a closed section showing continuous protection and module restraint.
7. **Independently recheck and issue instructions.** Validate source geometry,
   quantities, policy, material coverage, retention assumptions and procurement
   entries. Instructions list named modules, part pictures, quantities, bag IDs,
   label locations and closure steps. Retain original CAD and evidence hashes.

FEFCO codes provide a shared language for carton construction; they do not supply
stock availability, prices or guaranteed dimensions. Use supplier data alongside
the [FEFCO construction reference](https://www.fefco.org/technical-information/fefco-code).

Foam thickness cannot be selected from geometry alone. Cushion response depends
on material, thickness, loading and impact conditions; manufacturer cushion curves
and prototype testing are needed. Keep 15 mm as the current dimensional assumption,
not as a certified protection level. See
[Pregis on cushion curves](https://www.pregis.com/knowledge-hub/how-cushion-curves-enable-smarter-packaging-decisions/).
Separation, cushioning and movement control are also explicit in
[UPS packaging guidance](https://www.ups.com/us/en/support/shipping-support/packaging-tips?os=wtmbzegmu5hw).

## Objective and speed

Safety/compatibility, complete contents, manufacturability and required protection
are hard gates. Do not trade them for millilitres. Among feasible plans, retain
a small Pareto set over shipping volume, distinct packaging SKUs, material cost
and assembly operations. Use policy caps and real commercial data to choose.

When prices and timed operations exist, compare total cost per kit:
packaging + allocated setup/MOQ inventory + labor + carrier charge.
Do not invent an expected damage cost or carrier saving without measurements.
Until then, report SKU count and operation count as proxies, not measured money
or labor time. Fewer boxes alone can produce an awkward, heavy mixed carton.

Initial experiments should vary maximum inner-carton count and distinct-SKU caps
instead of prescribing Alan's exact number. A useful proposed sweep is 2/3/4
distinct inner-carton SKUs per kit, with shared-family alternatives across kits;
these are experimental knobs, not proven feasible requirements.

Bound the candidate pool, cache checked patterns, apply cheap bounds first and
run full triangle/motion checks on finalists. Preserve a valid incumbent and a
single end-to-end deadline including verification. Proposed initial target:
first valid candidate within 3 minutes and final checked report within 10 minutes
from prepared inputs on a declared machine. This is unmeasured; the previous
fresh runs took 16.04/17.97 minutes and did not reproduce the best cached volumes.
Report source preparation and warm-cache acceleration separately.

## Implementation order and acceptance

| Priority | Deliverable | Gate |
| --- | --- | --- |
| P0 | Versioned policy schema, lossless metadata propagation, status changes | Unknown required fields cannot silently become logistics approval |
| P1 | Explicit foam/outer assembly and complete packaging BOM | Missing side/top/bottom protection fails; no double-counted foam volume |
| P2 | Compatible module generation and retention recipes | No forbidden mixing; nested loose groups cannot pass as rigid packets |
| P3 | Shared carton catalogue, SKU caps, pattern selection | Every chosen material maps to a purchasable or clearly provisional specification |
| P4 | Unified scorer and policy-aware repair | Larger but operationally preferable candidates survive; every repair revalidates policy |
| P5 | Kitting report and repeated benchmark | Clear module identities, procurement list, full outer cutaway and reproducible timings |

Add negative tests for removed foam, conflicting categories, excess SKU counts,
policy-changing repairs, missing restraint, underestimated package dimensions and
unsupported orientations. Keep existing original-geometry and BOM tests.

Run 101/102 cold from prepared inputs with three recorded seeds, plus an unseen
kit. Compare against the present volume-only baseline and a separately frozen
Alan reference. Report contents, volumes, material assumptions, packaging SKU
counts, operations, uncertainties and runtime. An infeasible budget or timeout
must not trigger silent mixing or protection reduction. The original no-worse
volume target remains open; a logistics improvement does not automatically meet it.

Finally, pack a prototype and measure assembly/checking/unpacking time, closure,
access, restraint on reorientation and damage after the relevant test sequence.
These checks are distinct from computational certificates. The public
[ISTA 3A overview](https://ista.org/docs/3Aoverview.pdf) describes parcel-delivery
testing for packaged products up to 70 kg, including shock and vibration. It is
an overview of the 2018 procedure, not the complete current laboratory protocol;
select the applicable procedure with the test provider and actual shipping route.
No transit-test success is established for either design by the supplied evidence.

## Inputs still needed for a production decision

- Supplier carton/foam options, tolerances, MOQ, price tiers and intended batch size.
- Actual packed dimensions and mass of uncertain purchased parts; ESD/contact rules.
- Approved material grades, closure method, protection and allowable movement limits.
- Measured Alan packing time/cost and comparable shipping configuration.

The software can explore clearly labeled assumptions before these arrive. It
cannot honestly certify procurement economy or shipping performance without them.
