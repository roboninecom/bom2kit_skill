# Practical packing: measured progress

**The no-worse objective is not met.** The new pipeline checks individual
handling and real geometric support, but its compact verified layouts remain
larger than Alan's reference. Physical shipping qualification is still absent.

The four-hour window began on 12 November 2026 at 14:13:22 UTC. The user requested
continuation and compensation for the recorded 4,526-second pause. The revised
report deadline is 19:28:48 UTC; new searches stop at 19:08:48 UTC.

## Current measured results

These are frozen selections after the bounded experiments completed.
Generated CAD, PDFs and detailed certificates stay in the ignored result folder.

| Kit / case | Exterior, mm | Volume, L | Cartons / sizes | Source + compound placements |
|---|---|---:|---:|---:|
| 101 before | 314 x 261 x 249 | 20.406546 | 3 / 3 | 93 |
| 101 practical | 565 x 291 x 181 | 29.759115 | 3 / 3 | 79 |
| 101 Alan | 364 x 290 x 184 | 19.423040 | 7 / not audited | Not counted |
| 102 before, current CAD | 294 x 240 x 354 | 24.978240 | 3 / 3 | 128 |
| 102 practical | 346 x 452 x 231 | 36.126552 | 4 / 4 | 108 |
| 102 Alan | 376 x 290 x 184 | 20.063360 | 7 / not audited | Not counted |

Practical rows have no rigid compound preassemblies or contact sheets. Add one
specified floor liner per carton, carton forming/closure, outer insertion and
six-face foam handling to the operation count. Old layouts did not specify those
liner operations. These are model counts, not measured labor or supplier prices.
The final 102 pose-aware partition improves on the previous four-carton 38.974080 L
and six-carton 37.847544 L variants. Simpler three-carton alternatives remain in
the recorded frontier; they use more shipping volume.
For 101, the smallest verified alternative is 29.697876 L with four carton sizes.
The selected three-carton layout costs only 0.21% more volume and avoids an extra
carton and size. Selected search/replay invocations took 389.5 s and 538.5 s,
respectively; these are warm-cache, potentially concurrent runs.

## What changed and what was actually tested

- Separate source CAD, factory cartons, protective packets and declared envelopes.
  The twelve 101 servo cartons remain explicit, unmeasured input assumptions.
- Generate repeated stable floors, height-diverse patterns, flat-contact stacks,
  adjacent floor pairs and source-derived common footprints. Repack and retile
  closed cartons into a complete block without spacers.
- Test PackingSolver rectangle/irregular and finite-pool OR-Tools exact coverage.
  Neither backend is a global concave 3D packing or physical-support certificate.
- Add internal-face pairs and branching actual-surface support proposals. Synthetic
  cavity and shared-base examples pass. Full-kit surface-search attempts so far
  have not displaced the regular-floor incumbent; they remain experimental.
- Replay original geometry, BOM, protection, source contact, complete load lines,
  individual fingertip sweeps and intermediate load states. Count protective
  sheets explicitly. The final full suite passed 238 tests with real backends.

## Why the volume gap remains

The old solution optimized dense compound envelopes without establishing how
loose members were supported or carried. Only 11/79 and 21/108 source units
already pass the new carton-floor check. Another support mechanism may exist;
these counts do not prove impossibility. In addition, 27/79 and 30/108 original
orientations are not stable on an isolated flat plane.

The replacement still loses space through floor-only placement, broad low boxes,
limited stable-pose/contact proposals and early greedy choices. Support-aware 3D
search is expensive and incomplete. Changing libraries alone does not fix that
model. Dense layouts involving multiple-parent bridges, side contacts or soft
retaining bags need explicit contact/retention models and executable operations.

In the selected floor layouts, padded part bounding boxes occupy about **60%**
of 101's inner cavity volume and **52%** of 102's. This is proxy accounting,
not a global lower bound: access clearances and shape voids are not all reclaimable.
For example, 102's mechanical-parts cavity is 54 mm high while its area-weighted
mean protected envelope height is only 29.6 mm. The detailed audit is
`selected/space-audit.json`.

The historical 22.925616 L 102 layout is invalid on current CAD: the updated rack
instances collide. The matching-input before row is a fresh old-engine run,
not that historical result. Alan's 102 illustration shows BOX1 contents; complete
reference assembly transforms are unavailable, so protection/handling equivalence
cannot be inferred from nominal volume alone.
The 102 reference also specifies bags around its printed-part groups. A retained
bagged group is a different handling model from this engine's individually
supported loose parts; verified carryable bag groups have not been implemented.
The tight outer carton block does not establish restraint of uneven-height loose
contents inside each carton. These layouts are not shipping-ready recommendations.

The next implementation priority is an explicit retained-group state: derive
candidate groups from the BOM and CAD, specify a real bag/closure or protective
wrap, validate the enclosed envelope and insertion path, and count its handling
operations. Do not turn an arbitrary nested collision-free set into a rigid unit.
For loose parts, extend support search to multiple contacts and evaluate motion
under transport loads; the current single-parent static support tree cannot
certify that behavior. These are outstanding requirements, not delivered features.

## Reproduce and inspect

Use [the practical workflow](practical-packing-design.md) and the shared
`skills/bom-to-kit/SKILL.md`. Each run records source hashes, engine hashes,
parameters, rejected trials and elapsed time. Prepared mesh inputs and warm pose
caches are disclosed; concurrent-run timings are not a controlled speed benchmark.

Local evidence root: `packaging-results/practical-round3/`. The comparison is
`comparison/comparison.pdf` and `comparison/report.html`; kit guides are
`101/guide/packing-guide.pdf` and `102/guide/packing-guide.pdf`. Final selections,
hashes and exact reproduction commands are recorded alongside those artifacts.
