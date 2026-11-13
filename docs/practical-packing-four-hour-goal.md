# Four-hour practical packaging goal

## Outcome

Redesign the shared Codex/Claude BOM-to-Kit skill to generate practical packaging
from individual source geometry and BOM quantities. Replace fragile spatial
puzzles and unsupported envelope columns with repeatable, individually executable
packing operations. Produce complete SO-ARM101 and SO-ARM102 layouts, reproducible
commands, R3-style illustrated PDFs, and a concise before/after/Alan comparison.

This session started at **2026-11-12 14:13:22 UTC**. Stop starting new searches at
**19:08:48 UTC** and finish work with a report by **19:28:48 UTC** (22:28 Moscow).
The user resumed work at 17:04:37 UTC and requested compensation for downtime.
The recorded pause began at 15:49:11 UTC; 4,526 seconds were added to both limits.
The deadline is a stopping condition, not permission to call an unmet goal complete.

## Fixed requirements

- Use the accepted 101 Visual Layout R3 contents, current 102 BOM/CAD, and the
  purchased clamp with its user-confirmed 106 mm frame. Record revision hashes.
- Keep original geometry, quantities, protection allowances and six-face foam.
  Distinguish declared dimensions from measurements. Do not shrink parts or
  discard protective packaging to improve the comparison.
- Keep Alan's dimensions, grouping, coordinates and volume targets outside the
  search input. Evaluate against his reference only after freezing each result.
- Generate a complete block of closed inner cartons without spacers between them.
  Adjust carton dimensions and repack their contents when dimensions change.
- Use general rules, not SKU-specific placement recipes or manual coordinate edits.

## Implementation

1. Separate physical parts, factory cartons, protective packets and declared
   envelopes. Require content preservation and dimension/protection evidence for
   alternative states. Audit the twelve assumed 101 servo cartons explicitly.
2. Generate repeated rows, stable floor arrangements and bounded simple stacks.
   Unsecured parts remain individual placement operations, never a fictional rigid
   compound. Any protective interface material must appear in the packaging BOM
   and assembly steps.
3. Check actual CAD contact surfaces, support margins and permitted load evidence.
   A bounding-box top is not a supporting surface. Replay insertion/removal with
   an explicitly parameterized simplified grip; disclose its limitations.
4. Explore 3-7 inner cartons and caps of 2-4 carton sizes. Select compatible groups,
   orientations and carton dimensions jointly, then recheck the complete BOM.
5. Keep nondominated tradeoffs in volume, carton/type counts, preassemblies,
   placement operations and repeated layout patterns. Do not invent labor times
   or prices. Feasibility and protection are mandatory before ranking.

## Algorithms to evaluate

- Trimesh stable poses and full triangle projections.
- PackingSolver rectangle for regular floor arrangements; irregular for complete
  projected contours, followed by original 3D source checks.
- OR-Tools CP-SAT for exact coverage by generated carton/group alternatives.
- The existing slicing carton tiler for a complete block without fillers.
- Trimesh/FCL for collisions, clearances and bounded motion replay.
- PyBullet only if credible masses/contact models are available; not a required
  dependency or substitute for shipping tests.

Use an existing working proposal algorithm if an integration consumes the budget.
Backend success does not replace independent validation.

## Time allocation

| Elapsed | Required work |
|---|---|
| 0-25 min | Freeze source versions and before metrics; identify actual complexity causes. |
| 25-80 min | Implement regular patterns, individual handling and real support checks. |
| 80-135 min | Joint carton/group/type selection and operational ranking. |
| 135-190 min | Comparable 101/102 experiments; repair observed failures. |
| 190-220 min | Freeze best candidates; independently replay all required checks and tests. |
| 220-240 min | Finish PDFs, concise report, shared skill, English commit and separate PR. |

Compare regular original-state packing, joint selection, and justified alternative
states/simple groups separately. Include failed attempts in elapsed time. Distinguish
an input revision change from an algorithm improvement.

## Acceptance and delivery

Both complete kits must pass original CAD, BOM, protection, compatibility, support,
assembly and no-spacer block checks. Enumerated operations must demonstrate reduced
complexity versus the previous implementation. External shipping volume must not
exceed a comparable Alan reference: **19.42304 L for 101**, **20.06336 L for 102**.
Disclose any differences in contents or protection; an unmatched reference cannot
establish success.

Deliver source code, synchronized Codex/Claude instructions, tests, commands, and
two R3-style PDFs showing actual carton walls, foam, contents and packing steps.
The comparison must show dimensions, volume, carton/type counts, operation counts,
runtime and unresolved limitations. Keep downloaded and generated files ignored.

Without a physical assembly and transit test, label the result a computationally
checked design, not production-qualified packaging. If any acceptance condition
remains unmet at the deadline, preserve the best checked result and report the
measured gap and specific obstacles. Do not mark the goal complete.
