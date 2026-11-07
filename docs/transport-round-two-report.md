# Second transport packaging window

**Improved, but the no-worse target remains unmet.** Both complete kits have
checked layouts; neither matches Alan's nominal volume. Physical restraint
and shipping performance remain unqualified.

## Measured result

Before means the previous transport session. Source quantities, CAD revisions
and protective allowances match between before and after.

| Kit | Before, L | After, L | Alan, L | After vs Alan | Cartons / sizes, before -> after |
| --- | ---: | ---: | ---: | ---: | --- |
| 101 | 20.800 | 20.407 | 19.423 | +5.1% | 3 / 3 -> 3 / 3 |
| 102 | 23.593 | 22.926 | 20.063 | +14.3% | 5 / 5 -> 3 / 3 |

Selected exteriors: **314 x 261 x 249 mm** and **217 x 284 x 372 mm**.
Each kit uses three compatible groups: printed parts, mechanics/fastener
packets, and protected electronics/servos. Closed cartons fill a nominally
complete block without spacers. Six faces retain 15 mm foam; outer walls are
7 mm and inner walls 1.5 mm.

Fresh design and verification took **752.2 s / 772.2 s**, including failed
trials, versus 340.9 s / 403.9 s previously. Compactness currently costs roughly
twice the search time. Source preparation is excluded; concurrent workloads
and budgets differ. These are best observed runs, not quality or runtime
guarantees. Both selected runs kept code unchanged. The earlier 101 baseline
was an exploratory changed-code run, independently replayed afterward.

A separate default CLI run with a 45-second proposal budget, no nesting and no
external solvers finished in **54.6 s / 59.1 s**, but occupied **23.443 L /
27.228 L**. Fast generation works; fast generation at Alan's compactness is
not demonstrated.

## Implementation

- Parallel CAD nesting and translation refinement; integer selection preserves
  quantities across repeated nested groups.
- Supported order/orientation improvement, shared carton footprints and local
  refinement of the best grouping generated within each run. An anytime complete
  layout replaces the poor timeout fallback.
- Optional PackingSolver and isolated CP-SAT proposals, independently checked.
  Experimental columns are opt-in and do not replace default floor proposals.
- Numbered CAD views, exact carton layer sections, recorded runtimes and
  hash-bound comparisons that reject reduced protective allowances.

The selected 101 layout uses supported placement and local improvement, without
external solvers. The 102 layout uses local improvement and shared footprints;
CP-SAT was enabled, but its causal contribution is not established. Whole-family
heightfields, six identical cartons and aspect-biased pair ranking did not
improve the selected results. This remains a bounded heuristic.

## Evidence

The inputs contain **64 SKU / 79 packing units** for 101 and **71 / 108** for
102; packets retain component quantities. The clamp remains 106 mm. Revisions
and purchased-envelope estimates are unchanged; see
[source assumptions](benchmark-assumptions.md).

**204 tests passed**, including real isolated CP-SAT integration. Final report
generation rechecks original CAD, complete BOM, assembly, compatibility, carton
partition and foam. All selected CAD views were inspected. Codex/Claude skill
copies match.

Private evidence is in `packaging-results/logistics-round2/`:

- `final-report/report.html`: before/after/Alan and all inner CAD views.
- `final-report/{101,102}/transport-review.html`: contents and assembly.
- `selection.json`: frozen hashes, parameters and engine commits.
- `run-inventory.json`, `environment.json`, `tests-final.txt`: measured alternatives,
  environment and test output.

Selected engine commits: `92248ed` (101), `6ae7107` (102). See the
[transport workflow](transport-packaging.md) for commands. Frozen layouts are in
`selected/{101,102}/result.json`; no poses were manually edited.

## Remaining obstacle

Even ideal cubic proportions at the selected block volumes require at least
**20.266 L / 22.560 L** outside with unchanged walls/foam, ignoring top reserve.
Those blocks must shrink by approximately **4.9% / 13.0%** to reach Alan's volume;
rearranging the existing cartons alone cannot close the gap. This bound does
not cover every possible packing of the parts.

Envelope occupancy is 73-82% / 71-80%; it does not prove actual contact support
or stability. Better coordinated CAD nesting and measured packing states are
still needed, followed by restraint, material and tolerance checks.

Alan's dimensions are independent benchmarks, never solver inputs. His complete
placements were not replayed; the 102 illustration shows one inner carton.
No supplier-cost, shipping-qualification or no-worse equivalence is claimed.
