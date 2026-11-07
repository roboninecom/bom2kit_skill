# Two-hour transport packaging result

**The requested no-worse result is not achieved.** Both selected designs exceed
Alan's nominal exterior volume. Physical transport qualification is also open.
This session delivers an experimental working search and checked instructions,
not a production-approved packaging design.

## Measured comparison

Exterior dimensions include the outer wall and six foam panels. Before/after
use matching source quantities, geometry and protection allowances.

| Kit / design | Exterior, mm | Litres | Inner cartons / sizes |
| --- | --- | ---: | ---: |
| 101 before | 253 x 253 x 305 | 19.523 | 3 / 3 |
| 101 best observed | 196 x 379 x 280 | 20.800 | 3 / 3 |
| 101 Alan | 364 x 290 x 184 | 19.423 | 7 / unverified |
| 102 before, current CAD replay | 252 x 264 x 330 | 21.954 | 5 / 5 |
| 102 best observed | 233 x 394 x 257 | 23.593 | 5 / 5 |
| 102 Alan | 376 x 290 x 184 | 20.063 | unverified |

The best observed results are approximately **7.1% and 17.6% larger than Alan**.
They are also larger than the previous computational layouts; compatibility,
the complete carton block and explicit foam are not free volume improvements.

The 101 best result took 340.9 seconds, but files changed during that run:
it is an exploratory result, independently replayed afterward. A subsequent
unchanged-code run produced 20.964 L, three cartons/sizes, in 390.1 seconds.
The selected 102 run kept engine files unchanged and took 403.9 seconds.
A three-carton/three-size 102 alternative took 399.3 seconds and occupied
24.093 L. Timings include design and verification from prepared libraries,
not downloading or converting source CAD. Time-bounded searches can vary.

## What changed

- Compatible-family grouping keeps bare mechanics separate from printed parts.
  Protected servos can share electronics cartons when the input records their
  protective packing state (101 factory cartons; 102 declared EPE allowances).
- CAD nesting proposes compatible pairs and extensions. Original triangles,
  quantities, clearance and assembly are replayed before accepting them.
- Rectangle, column and supported-envelope heuristics generate inner layouts.
  Slicing-tree dynamic programming joins and enlarges cartons into a complete
  block. Nearby footprints are repacked; no spacers are generated.
- Four side foam panels, bottom and lid are modeled without overlaps or double
  allowances. Reports show original CAD, numbered contents and insertion steps.
- PackingSolver was tested for both inner and outer proposals. It is optional;
  none of the selected best results depends on it. The adapter rejects invalid
  coverage, rotations, support and insertion certificates.

## Evidence and reproducibility

The complete libraries contain 64 SKU records / 79 packing units for 101 and
71 / 108 for 102. Packets retain their component quantities. The custom clamp
frame remains 106 mm. The 102 Board cap uses upstream commit
`77e2469737f30ee30cac6da9c3ecb82e7ff2539d`; its BOM is unchanged.
The old 102 layout was replayed on that CAD revision without moving its parts.
See [source assumptions](benchmark-assumptions.md).

Run commands and policy preparation are documented in the
[transport workflow](transport-packaging.md). Shared Codex and Claude skill
copies are synchronized. The test suite passed **168 tests**. Final report
generation independently rechecks the selected original geometry, BOM,
assembly, compatible groups, carton block and foam.

Private evidence remains ignored:

- `packaging-results/logistics-session/selection.json`: selected paths/hashes.
- `packaging-results/logistics-session/selected/{101,102}/result.json`: frozen layouts.
- `packaging-results/logistics-session/final-comparison-config.json`: evaluator inputs.
- `packaging-results/logistics-session/final-report/report.html`: visual comparison.
- `packaging-results/logistics-session/final-report/{101,102}/transport-review.html`:
  carton contents, CAD views, assembly and foam.
- `packaging-results/logistics-session/{101,102}/skyline-portfolio/result.json`:
  unchanged-code operational alternatives.

```powershell
python scripts/compare_transport_designs.py packaging-results/logistics-session/final-comparison-config.json --output packaging-results/logistics-session/final-report
```

## Why the goal remains open

The bounded nesting and slicing search has not found a sufficiently compact
compatible layout. It does not prove that a better one is impossible. Five
different carton sizes in the smaller 102 candidate still impose procurement
overhead; the three-size alternative costs another 0.50 L.

The block prevents nominal inter-carton gaps, but contents are not physically
restrained merely because meshes fit. Real contact support, protective bags,
foam grade/compression, carton strength, handling clearance and manufacturing
tolerances still need specified materials and prototype checks. Purchased
envelopes include declared estimates. Full original placement geometry for
Alan was not replayed; his supplied illustrations and dimensions are reference
evidence only. No shipping-test or supplier-cost equivalence is claimed.
