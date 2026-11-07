# Transport packaging: algorithm and implementation design

**Superseded constraint:** the user subsequently prohibited spacers between
inner cartons. References to residual spacers below are historical proposals,
not current requirements. The transport implementation instead enlarges inner
cartons to tile a complete block and jointly adjusts its dimensions. Six-face
outer protective foam remains required. See `logistics_design.py` and
`carton_tiling.py`; their geometric checks do not certify transit performance.

7 November 2026. Baseline: `c4114f0`. This is a concrete design for the next
implementation, supported by source inspection and two executable research
probes. It is not a claim that the proposed pipeline already packs 101/102.
The [earlier audit](transport-packaging-research.md) records operational gaps;
this document specifies algorithms, interfaces and their limits.

## 1. Current algorithm, not just current features

The independent runner currently implements this chain:

```text
individual meshes
  -> discover_pairs / extend_groups: geometric nesting candidates
  -> group_configurations: greedy savings order + leave-one-out/anchor variants
  -> design_grouped_library: consume available counts in that order
  -> design_mesh_envelopes: oriented bounds + uniform padding
  -> design_layers: candidate footprints + greedy floor strips / height sequences
  -> improve_layer_membership: random moves/swaps between equal-footprint layers
  -> original-mesh + insertion replay
  -> minimum external volume
```

Specific mechanisms explain the observed behavior:

- `group_portfolio.py::group_configurations` orders groups by
  `group_box_volume_mm3 - separate_box_volume_mm3`. The second sorting inside
  its selection loop can undo the intended ordering of an anchor pool. It does
  not solve an exact-cover or compatibility-constrained selection problem.
- `mesh_groups.py` proposes pairs using unused bounding-box volume and type
  diversity. `cavity_groups.py` uses voxel occupancy, dilation and 3D prefix sums
  to find empty regions, then checks original geometry. Neither expresses a
  supplier's packing unit or a requirement to keep printed and heavy metal parts
  separate. These mechanisms should remain optional local geometry tools.
- `strip_packing.py::pack_strip` maintains maximal free rectangles, splits every
  intersecting free rectangle after insertion, and removes contained rectangles.
  It tries a finite set of orientations and scores such as bottom-left,
  short-side fit or height-fill. Every placed envelope sits on that strip's floor.
- `layered_design.py::design_layers` samples footprint sizes around a cube-root
  volume estimate, tests one/two columns and height bands, then refines dimensions.
  Heights become arbitrary manufacturing increments, not supplier carton SKUs.
- `layer_neighborhood.py` changes membership while keeping or reducing combined
  layer height. It only handles stacks sharing footprint and XY origin. It
  cannot create an Alan-like row of several independently chosen module cartons
  as part of that repair step.
- Volume-only rejection exists in `design_layers`, `design_mesh_envelopes`,
  `layer_improvement` and the runner's `min(choices)`. Replacing only the final
  score would still discard operationally better candidates upstream.
- `carton_design.py` rejects extra item/policy fields. `normalize` builds units
  containing only identity, dimensions and orientations; mesh conversion filters
  metadata too. Adding `family` or `mass` to input JSON alone changes nothing.
- `mesh_motion.py` concatenates grouped parts into one moving body. The source
  transformations are verified, but there is no physical carrier holding that
  group together. `mesh_validation.py` rejects surface contact; it must not be
  reused unchanged for touching foam, carton walls and retention pads.

Keep the geometry kernels and source hashes. Introduce a new orchestration path
rather than gradually adding logistical fields to the volume-only runner.

## 2. Selected architecture and alternatives

**Implement bounded pattern generation + CP-SAT set partitioning + a small
guillotine/slicing floorplan search for closed cartons.** Keep Trimesh/FCL as the
independent original-part checker. Use one shared catalogue across both kits.

| Decision | Chosen method | Why not the alternative first? |
| --- | --- | --- |
| Form logical groups | Must-link contraction + conflict graph + bounded compatible subsets | Material-only sorting misses functional groups; unconstrained clustering can mix incompatible parts |
| Pack a candidate module | Existing MaxRects-style strips, approved rotations, optional checked local nesting | Full continuous 3D optimization is costly and does not encode procurement or handling |
| Choose modules and shared box types | CP-SAT exact-cover constraints with SKU activation | Greedy volume savings cannot account for shared purchasing costs |
| Arrange a few closed cartons | Subset dynamic programming over slicing layouts with explicit spacers | Unrestricted 3D packing makes support and manufacturable gap filling harder |
| Generate outer foam | Analytic six-panel solids with an explicit butt-joint convention | Drawing a translucent bounding box supplies neither cut sizes nor material quantities |
| Improve a result | Policy-constrained large-neighborhood search (LNS) over modules/SKUs | Arbitrary part swaps break grouping and retain bespoke heights |

The selected architecture is an engineering recommendation, not a demonstrated
speed/quality winner. Two-dimensional hierarchical packing research supports
decomposing inner blocks from outer arrangement with feedback; its experiments
do not establish performance on these kits or transport safety.
[Grus et al., hierarchical rectangle packing](https://arxiv.org/html/2512.20239v2).

PackingSolver's `box-stacks` uses common-footprint stacks and a stackability ID,
with load and maximum-weight-above constraints. That is useful as an alternative
outer-carton backend, but its unloading groups are not our incompatibility or
ESD rules. Its sequential stack/rectangle decomposition is relevant; it still
does not generate foam, supplier costs or kitting patterns.
[Model](https://fontanf.github.io/packingsolver/boxstacks.html),
[algorithms](https://fontanf.github.io/packingsolver/internals/boxstacks.html).

## 3. Data contracts

Use a versioned logistics document alongside the immutable geometry manifest.
Do not infer material from filename prefixes in the production algorithm.

```text
PartSpec:
  sku, revision, quantity, mesh_hash, source_evidence
  kitting_family, material_class, mass_g, protected_surfaces, esd_requirement
  allowed_packing_states[]             # each has explicit proper rigid transforms
  must_link_id?, forbidden_contact_classes[], uncertainty_mm[3]

PackagingOption:
  supplier_sku, kind, revision, price_tiers, MOQ, order_multiple, setup_cost
  inner_min_mm[3], inner_max_mm[3], outer_max_mm[3]
  material_grade, closure, max_mass_g, max_supported_load_g
  allowed_orientations, seam/fold_allowances, evidence_status

ModulePattern:
  id, kit_id, coverage{sku: count}, carton_sku, protection_recipe_id
  original_part_poses[], packed_units[], internal_sequence[]
  outer_max_mm[3], mass_g, operation_counts{}, material_requirements{}
  geometry_certificate, retention_status, policy_hash, provenance_hash

PackingPlan:
  selected_patterns[], module_poses[], outer_carton_sku
  foam_parts[], dividers[], spacers[], packaging_BOM[], kitting_steps[]
  score_vector, timing, separate_validation_statuses
```

A compatibility decision has three states: prohibited, allowed with named
barrier/retention recipe, or unrestricted. Unknown required mass/protection does
not become zero or unrestricted. It produces a provisional pattern that cannot
enter a production-approved pool.

## 4. Module generation: constraints before geometry

1. Expand units or use count vectors for identical parts. Contract explicit
   must-link sets with union-find. An internal conflict makes that set invalid;
   never repair it by silently splitting it.
2. Build a conflict graph over these atoms. Add an edge for a forbidden
   co-location under the proposed protection recipe. Functional separation
   preferences remain soft costs; hazardous/unprotected combinations are hard.
3. Seed groups from compatible functional families and repeated-part sets.
   Enumerate a bounded beam of compatible additions/splits, ordered by handling
   operations and available carton dimensions. Do not enumerate all graph
   independent sets. Pairwise compatibility is only an early filter: recheck
   group mass, access and all higher-order rules before accepting a pattern.
4. For each group and catalogue carton, reject impossible dimensions, mass and
   floor-area bounds. Bounds use protected dimensions, not bare part volume.
5. Run the existing strip packer inside `inner_min_mm`, initially allowing one
   accessible floor layer. Additional layers need physical trays/separators and
   their assembly steps. Try the existing orientation/ordering portfolio.
6. For approved nested subsets, call the existing mesh pair/cavity search, then
   original-triangle and assembly checks. Nesting requires a rigid carrier,
   approved retained bundle or an in-carton sequence with support at each step.
7. Store several nondominated patterns for the *same coverage*. Preserve carton
   identity: a locally more costly SKU may be cheaper globally because another
   kit uses it. Do not Pareto-prune across SKUs using only volume/material cost.

Current frame selection also needs modification: allowed orientations refer to
physical parts/packing states. Applying `packing_bounds()` and then allowing all
six permutations must not bypass an upright or protected-face requirement.

MaxRects is appropriate for rapid pattern generation, not a feasibility proof
when it fails. See the original implementation and survey in
[RectangleBinPack](https://github.com/juj/RectangleBinPack).

## 5. Discrete selection: exact model over a finite pattern pool

Let `a[k,p,i]` be the number of SKU `i` in pattern `p` for kit `k`, and `q[k,i]`
the required count. Each pattern is one complete closed inner carton.
Use bounded nonnegative integer `x[k,p]` for selected pattern copies, and Boolean
`y[s]` for whether packaging SKU `s` is used across either kit.

```text
For every kit k and item i:
    sum_p a[k,p,i] * x[k,p] = q[k,i]              # exact cover, not >=

For every pattern p using carton/protection SKU s:
    x[k,p] <= U[k,p] * y[s]
For every SKU s:
    y[s] <= sum_{k,p using s} x[k,p]             # no unused activated SKU

For each kit k:
    sum_p x[k,p] <= max_inner_cartons[k]
For the shared catalogue:
    sum_{s of kind inner_carton} y[s] <= max_shared_carton_SKUs
```

Do not merge bag/foam counts with carton-SKU counts; report them separately.
Incompatible patterns never enter the pool. Additional policy checks are still
run independently on expanded original membership after selection.

For a purchasing horizon with `N[k]` kits, material demand is
`d[s] = sum_k N[k] * sum_p material_qty[p,s] * x[k,p]`.
Order variables must satisfy demand, MOQ and order multiples. Model tier prices
with tier-selection binaries and bounded quantity variables; do not multiply a
Boolean by an unconstrained variable without a proper linearization.
Cost includes ordered materials, tooling/setup, measured assembly seconds times
labor rate, and freight from the resulting outer dimensions. Inventory left over
from MOQ is reported, not automatically charged as waste.

Without quotes/timed operations, use SKU and operation caps and enumerate a small
Pareto frontier. Do not fabricate monetary weights. Freight/outer volume belong
to the outer-layout stage, so the cheapest selected modules are not automatically
the best shipping plan. Keep several module selections and feed outer costs back.

CP-SAT operates on integers: scale monetary values to cents and dimensions
conservatively. `OPTIMAL` means optimal for the supplied finite model, not for
all possible meshes, groups or catalogues.
[OR-Tools solver and statuses](https://developers.google.com/optimization/cp/cp_solver).

## 6. Outer arrangement: slicing-floorplan dynamic programming

After module selection there should be only a few closed cartons. Represent each
copy as a leaf with external toleranced dimensions, mass and approved rotations.
For a set `S` of leaves, keep a bounded frontier `F[S]` of feasible rectangular
blocks, including layout tree, dimensions, material requirements and load data.

For each unordered split `S=A union B`, combine candidates along X, Y or Z:

```text
X: (wA + seam + wB, max(dA,dB), max(hA,hB))
Y: (max(wA,wB), dA + seam + dB, max(hA,hB))
Z: (max(wA,wB), max(dA,dB), hA + separator + hB)
```

`seam` is zero for approved touching outer faces or the specified physical
divider thickness. A maximum in these equations creates residual rectangular
regions: recursively partition and fill them with specified pads/spacers, or
reject the combination. They are not free imaginary support. Reject fillers
that violate minimum manufacturable size, material limits or operation/SKU caps.
Z combinations require verified support through equal footprints or a specified
load-rated full-area separator; generic soft foam must not be assumed load-bearing.

At the root, compare the resulting block with each supplier outer cavity after
foam. Partition any remaining gap into nonoverlapping spacer slabs. Count every
piece and closure operation in the score. The lower-bound dimensions alone are
not the final shipping dimensions; these come from the selected outer carton.

Subset DP has approximately `3^n` partition work before shape-frontier factors.
Start with an experimental frontier cap of 24 states per subset and at most
8 inner cartons; measure rather than promise runtime. Preserve different useful
aspect ratios, supported-load classes and SKU/material alternatives. A bounded
frontier and slicing-only layouts make this a heuristic; non-slicing packings
may be missed. Exceeding these limits requires a declared fallback, not an
optimality claim. This layout restriction is intentional: it makes simple cut
spacers and organized rows/layers easier to manufacture and assemble.

Alternative benchmark: use CP-SAT `NoOverlap2D` for selected carton footprints
on physical tray layers, with layer heights chosen from catalogue sizes and
explicit top pads. `NoOverlap2D` is two-dimensional; it supplies neither vertical
support nor retention. PackingSolver `box`/`box-stacks` can be a third backend.
All backends consume the same protected modules and return to the same validator.

## 7. Feedback and improvement without invalid infeasibility claims

Use a bounded master/subproblem loop: select modules, arrange cartons, validate,
retain nondominated complete plans, then generate useful new module alternatives.
If a module causes height or width waste, request alternative carton/pattern
dimensions for its coverage. This avoids freezing a locally smallest group.

Geometric failure handling matters:

- A certified incompatible set can generate a no-good constraint.
- `INFEASIBLE` from an integer grid model excludes that model's grid domain only.
- A MaxRects miss, bounded slicing search failure or timeout is **UNKNOWN**,
  not a valid global geometric cut. Keep it eligible for another backend/budget.
- Excluding an already visited exact selection to enumerate other candidates is
  search bookkeeping, not proof that the selection is impossible.

The distinction follows the master/feasibility-subproblem approach in
[Cote, Haouari and Iori](https://www.cirrelt.ca/documentstravail/cirrelt-2019-41.pdf).
Their method concerns 2D rectangles; no exactness is transferred to our bounded
3D/module heuristic merely by calling it Benders decomposition.

LNS operators should remove/rebuild whole modules, switch a catalogue size,
merge/split compatible families, change a divider recipe or retile two adjacent
blocks. Lock the unaffected modules and re-solve that neighborhood. Do not reuse
the current unrestricted unit-swap operator unchanged. Compare complete score
vectors, including material and operations; remove volume-only early rejection
from every new logistics-mode stage.

## 8. Foam and restraint algorithms

For outer internal dimensions `(X,Y,Z)` and equal nominal foam thickness `t`,
use this six-panel butt-joint construction in outer-cavity coordinates:

| Piece | Origin | Size |
| --- | --- | --- |
| Bottom | (0,0,0) | (X,Y,t) |
| Top | (0,0,Z-t) | (X,Y,t) |
| Front | (0,0,t) | (X,t,Z-2t) |
| Back | (0,Y-t,t) | (X,t,Z-2t) |
| Left | (0,t,t) | (t,Y-2t,Z-2t) |
| Right | (X-t,t,t) | (t,Y-2t,Z-2t) |

The panels have disjoint interiors and cover the shell around the central cavity.
Verify bounds, no positive-volume overlap, no intrusion into that cavity, and
total volume `XYZ - (X-2t)(Y-2t)(Z-2t)`. For this axis-aligned shell these conditions
establish nominal coverage up to boundaries. Deleting one panel must fail.
Generate a cut list grouped by material and identical dimensions, then reuse
2D rectangle packing for sheet utilization; cutting kerf and allowed rotations
are manufacturing inputs. Geometry does not establish cushion performance.

Model contacts separately from product collisions:

```text
product/product: clearance and prohibited-contact rules
product/divider: allowed only on declared protected/contact faces
carton/foam and foam/foam: intended face contact allowed
positive solid overlap: reject, except a separately quantified compression model
```

Use analytic boxes for foam/carton solids where possible. FCL distances and
source triangles remain for products. The existing universal contact rejection
cannot certify these mixed-material scenes. Nominal contact is not permission
for unlimited foam compression.

**Fit and rattle use opposite tolerance extremes.** Fit must use largest packed
unit and smallest cavity; maximum travel must use smallest unit and largest cavity.
Include foam min/max thickness, carton tolerance, seams and divider positions.
Rounding up objects and down cavities gives a conservative lattice feasibility
test; rejection on that lattice is not continuous-space impossibility.

For the first release, certify only predefined retention constructions: rigid
closed cells with bounded six-direction travel, approved padded trays, or an
approved retained bundle with a measured packed envelope. A sealed loose bag
prevents loss/mixing but is not a rigid pose-preserving fixture. If a design relies
on exact relative poses, the carrier must maintain them. Otherwise validate the
range of possible movement or disallow that nesting pattern.

Six ray distances or an adjacency graph alone do not establish six-degree-of-
freedom restraint for an irregular part. For upright retained rectangular packets
inside closed cells, interval gaps can bound axial travel; arbitrary rotation,
deformation and impact require a qualified retention recipe or physical test.
Missing evidence stays `retention_unverified`.

## 9. Executed research probes

The reproducible probe is
[`scripts/research_transport_models.py`](../scripts/research_transport_models.py).
It deliberately does not call the production designer or change a packing result.

1. **Real frozen 101/102 nominal shell construction:** generated six 15 mm panels
   per outer cavity; checked disjoint interiors, complete shell volume and
   containment of the existing inner cartons. Both passed; removing one side
   failed. The shipping dimensions stayed unchanged. This proves the reserved
   space can be represented by that nominal panel construction, not that 15 mm
   is adequate cushioning or that manufacturing tolerances fit.
2. **Synthetic CP-SAT master:** two synthetic kits, each with a printed and metal
   module, have dedicated or shared carton SKUs. Unit-only minimization selects
   four SKUs; a synthetic setup cost selects two shared SKUs, still four cartons.
   Exhaustive enumeration independently confirmed both finite-pool optima.
   A one-SKU cap is infeasible; two artificially cheap mixed patterns are excluded
   by the hard compatibility rule. These are invented costs and patterns, not
   measured 101/102 savings or verified real module geometry.

Run with OR-Tools available (the existing isolated research environment was used):

```powershell
python scripts/research_transport_models.py --result packaging-results/independent/101/hour-membership/result.json --result packaging-results/independent/102/hour-membership/result.json --output packaging-results/transport-research/model-probes.json
```

These probes establish two mechanisms, not the superiority of the complete
proposed solver. A real catalogue/compatibility benchmark remains to be run.

## 10. Implementation map and benchmark

Proposed modules, all with explicit input/output contracts from section 3:

| Module | Responsibility |
| --- | --- |
| `logistics_policy.py` | Versioned metadata, must-link/conflict graph, independent policy check |
| `packaging_catalogue.py` | Supplier options, tolerances, price/MOQ variables and SKU identity |
| `module_patterns.py` | Compatible subset beam, protected local packing and original-pose certificates |
| `module_selection.py` | CP-SAT exact cover and shared-SKU activation |
| `carton_floorplan.py` | Slicing DP, load/support checks, explicit residual spacers |
| `protection_geometry.py` | Foam panels, divider/cell geometry and cutting list |
| `transport_validation.py` | Separate product clearance, material contacts, tolerance and retention checks |
| `transport_design.py` | Deadline, candidate frontier, feedback and module-level LNS |

Preserve legacy search as the volume-only baseline. Add a logistics CLI and schema
version instead of silently changing old certificate meaning. Update the shared
skill only when these commands work, then synchronize Codex/Claude copies.

Benchmark in stages with identical inputs, hardware and fixed seeds:

```text
A: existing volume-first runner
B: compatibility + protected units + catalogue, greedy selection
C: B + CP-SAT pattern selection + shared SKU activation
D: C + slicing outer floorplans + feedback/LNS
```

Run each kit separately and together for catalogue selection. Use three cold
seeds and separate warm-cache runs. Record actual runtime, valid-solution rate,
external volume, inner-carton count, distinct SKUs, material demand, operations
and every unverified assumption. Compare A only on metrics it actually models;
it must not win by silently omitting required protection or compatibility.

Use a single wall-clock budget with reserved final validation time, shared
monotonic deadline and checkpointed fully valid incumbents. Cache complete
pattern certificates by geometry+policy+catalogue+algorithm version. No claimed
ten-minute guarantee until this benchmark passes.

Required adversarial cases: contradictory must-link/conflict rules; tiny cheap
mixed carton; cheaper shared versus smaller dedicated SKU; foam side removed;
double-counted foam margin; fit passes but worst-case travel fails; a nominal
bundle without a carrier; LNS breaking compatibility; timeout misreported as
infeasible; and a slightly larger but cheaper complete candidate incorrectly
pruned by a volume-only check.

The release gate is a complete independently checked logistics plan plus an
honest physical-qualification status. The original no-worse Alan volume target
remains a separate requirement. Neither the synthetic probe nor the algorithm
choice proves it will be met.
