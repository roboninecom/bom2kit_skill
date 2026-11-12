# Concept-first packing goal

Implement a practical BOM/CAD packaging planner on the existing PR #3 branch.
The active-work window starts at 2026-11-12 20:16:08 UTC and ends at
2026-11-13 00:16:08 UTC. Check real 101/102 cases before 22:16:08 UTC;
stop new search experiments at 23:46:08 UTC. Compensate only verified downtime.

## Required behavior

Derive evidenced part properties, semantic groups and executable packing motifs
before searching complete-kit concepts. Keep several volume/organization/handling
tradeoffs. Start with constrained parts, revise groups when geometry fails, and
reuse unchanged subsolutions. Preserve complete current BOM, accepted geometry,
the 106 mm purchased clamp, 1.5 mm inner walls, existing part protection and
six-face outer foam. Use no inter-carton spacers or reference-derived recipes.

Patterns include repeated rows, supported stacks, alternating protrusions,
nested pairs and protected groups where applicable. Every pattern must specify
geometry, materials and operator actions. A bag alone cannot certify protection,
restraint or rigid handling. Facts and assumptions remain distinguishable.

## Evidence and acceptance

Compare previous and new results using identical inputs. Measure carton sizes,
external volume, packaging types, semantic mixing, repeated-SKU separation,
operations, orientations, space use, support/access/restraint and elapsed stages.
Use Alan only after freezing results: nominal limits are 19.42304 L for 101 and
20.06336 L for 102, subject to contents/protection comparability. Include a
modified-BOM case; do not hardcode either kit's placement solution.

Deliver tested code, synchronized Codex/Claude skill, reproduction commands,
two rendered and inspected R3-style guides, and a concise before/after/reference
comparison. Keep private inputs and generated outputs ignored. Commit and update
PR #3 in English using Conventional Commits; do not merge.

The full objective requires no-worse volume and practical organization for both
kits with corresponding evidence. Computational checks alone do not establish
shipping qualification. At the deadline deliver the best checked result and
specific measured shortcomings; do not mark an unmet goal complete.
