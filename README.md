# BOM to Kit

A local Python engine and shared Codex / Claude Code skill for reproducible packing plans. The engine searches rigid rectangular packing envelopes, independently checks layouts, and renders instructions from their coordinates. Optional STEP inspection supplies geometry evidence.

This is a bounded packing tool, not a general concave CAD nesting optimizer. Envelope validation does not establish the contents of a grouped box, foam performance, or transport qualification. Keep these evidence levels explicit when comparing with an engineer.

## Install

Python 3.11 or later:

```powershell
python -m pip install -e ".[test]"
# Optional STEP import:
python -m pip install -e ".[cad]"
```

Box packing and HTML reports use the standard library; CAD is loaded only when requested.

## Run

```powershell
python -m bom2kit solve packaging-inputs/job.json --output packaging-results/job --time-limit 5 --seed 0
python -m bom2kit validate packaging-inputs/job.json packaging-results/job/layout.json
python -m bom2kit report packaging-inputs/job.json packaging-results/job/layout.json --output packaging-results/job
python -m bom2kit inspect packaging-inputs/part.step --output packaging-results/geometry.json
python -m bom2kit inspect packaging-inputs/print-project.3mf --output packaging-results/mesh-inventory.json
python -m bom2kit reconcile packaging-inputs/bom.json packaging-inputs/job.json --output packaging-results/coverage.json
python -m bom2kit optimize packaging-inputs/job.json --output packaging-results/optimized --time-limit 5
python -m pytest -q
```

`solve` writes `input.json`, `layout.json`, and `validation.json`. Exit codes: `0` validated output, `1` invalid or incomplete layout, `2` input/dependency error. A failed bounded search is not proof that the kit cannot fit.

`reconcile` checks declared SKU counts and revisions independently of geometry; see
[the BOM mapping contract](docs/bom-reconciliation.md). It cannot infer a packet's contents.

For a fully assembled mesh manifest, run
`python -m bom2kit assess BOM.json input.json layout.json --output assessment.json`.
The input must specify `reference.external_mm` and the container's explicit
`wall_mm` offset from its stated inner dimensions to the shipping exterior.
Acceptance requires independently valid geometry, complete declared BOM counts,
and external volume no larger than the reference. Estimated packet envelopes stay
visible. Physical qualification and insertion paths remain separate checks;
the supplied BOM must itself represent the complete intended kit.

`optimize` compares the original carton and explicit `container_candidates`, retaining
wall/foam protection and top reservation. Its `input.json` contains the selected actual
carton; `request.json` preserves the original request. Search is deterministic and
the compatibility `--seed` option does not change it.

3MF inspection uses no CAD dependencies. It resolves nested component and build transforms, preserves local/object/printer frames, and flags Bambu support/modifier meshes separately. Printed part candidates still require BOM/revision mapping. Printer plate positions are not packing coordinates. Mesh inventory does not validate watertightness or shape nesting.

## Supplied mesh layouts

Install `python -m pip install -e ".[mesh]"` to use `bom2kit.mesh_validation.validate_mesh_layout(problem, layout)`. This separate API validates explicit triangle placements; it does not search them. It checks source SHA256, counts, rigid transforms, watertight positive-volume meshes, cavity bounds, FCL collisions, enclosed solids, and requested pair clearance. It rejects surface contact conservatively. Floating-point mesh checks do not certify self-intersection-free CAD, packing sequence, support, protection, or transport performance.

The mesh manifest uses `units: "mm"`, `container.inner_mm`, optional `container.protection_mm` and `clearance_mm`, and `items` with `id`, `quantity`, and `mesh: {"path": "...", "sha256": "..."}`. JSON mesh files contain `units: "mm"`, `vertices_mm`, and triangle indices in `triangles`. A `.3mf` source additionally requires `mesh.instance_id` from its inventory; `mesh.frame` defaults to `object`.

The layout uses `units: "mm"` and `placements` containing `item_id`, `unit_id` (for example `servo#1`), and `transform`: a 4-by-4 column-vector homogeneous matrix. Translation is in the last column in millimetres. Scaling and reflections fail validation. This matrix convention differs from the raw row-vector 3MF transforms; the extraction API handles those separately.

```powershell
python -m bom2kit mesh-pair packaging-inputs/pair.json --output packaging-results/pair --time-limit 30 --pitch-mm 2
python -m bom2kit mesh-validate packaging-results/pair/input.json packaging-results/pair/layout.json
python -m bom2kit mesh-report packaging-results/pair/input.json packaging-results/pair/layout.json --output packaging-results/pair
```

Pair search uses a fixed first-part orientation and 24 rotations of the second.
Voxel proposals are checked against actual triangles before acceptance. Its budget
is a soft search bound; geometry preparation and final validation can add time.
It does not solve a complete mixed kit or check an insertion path.

For a mixed group, `mesh-solve` retains alternative placements in a bounded beam:

```powershell
python -m bom2kit mesh-solve packaging-inputs/group.json --output packaging-results/group --time-limit 300 --beam-width 8 --pitch-mm 2
# Recheck and reuse an unchanged recipe, or complete a partial seed:
python -m bom2kit mesh-solve packaging-inputs/group.json --output packaging-results/replay --seed-layout packaging-results/group/layout.json
```

This experimental search uses JSON triangle sources and optional proper rotation
`orientation_hint` matrices per item. Complete recipes are independently checked
before replay. Changed parts, quantities or cavities require fresh validation.
Incomplete searches return exit code 1 and a checkpoint; they do not prove
infeasibility. Coarse voxels can miss close-fitting arrangements, so vary grouping,
orientation hints or grid pitch when necessary. Search time is a soft limit.

`mesh-report` additionally needs `[report]`. It renders the actual checked triangles
in four views, with no scaling to fit a suggested envelope. The view is a static
geometry review, not a packing-order certificate.

`bom2kit.mesh_motion.check_vertical_sequence(problem, layout, groups=...)`
separately checks an upward removal order and returns the reverse downward packing
order. Named groups move together. It binds the result to input, layout and source
hashes and does not certify internal group assembly, support, hands or tools.

`bom2kit.mesh_packing.solve_mesh_pair(problem, time_limit=30, pitch_mm=2)` searches exactly two manifested units. It proposes translations through voxel correlation and 24 proper rotations of the second part, then checks promising placements with triangle collisions and returns an independent validation certificate. The first part's orientation stays fixed. The time budget is soft: preprocessing, a proposal operation, and final validation may exceed it. This restricted search is neither a complete-kit mesh solver nor a proof of optimality. Report two-part envelope savings separately from complete shipping volume.

## Input contract

All dimensions are millimetres. Minimal example:

```json
{
  "units": "mm",
  "container": {"inner_mm": [200, 160, 100], "wall_mm": 3, "protection_mm": 5},
  "gap_mm": 2,
  "items": [
    {"id": "servo-box", "quantity": 2, "dimensions_mm": [80, 60, 40], "allowed_rotations": "upright"}
  ]
}
```

`inner_mm` describes the inner container before the `protection_mm` margin on each face. `wall_mm` is the per-face offset between inner and external dimensions. Each can be a three-number vector; wall and protection can also be scalar. If the source specifies the final usable foam cavity, use that as `inner_mm`, zero protection, and the complete cavity-to-exterior offset as `wall_mm`; do not double-count foam.

`container.reserved_top_mm` reserves additional height below the top protection,
for example a measured booklet thickness. It does not increase the carton size.

`allowed_rotations` accepts `fixed`, `upright` (swap X/Y only), or explicit dimension permutations such as `[[0,1,2],[2,1,0]]`. `gap_mm` is lateral spacing between envelopes with overlapping heights. Items may touch vertically for support. Quantities must be positive integers and item IDs unique. Use measured packed-state envelopes, including protection already attached to an item. Store provenance and unresolved assumptions alongside the job; geometrical fit alone does not validate those assumptions.

## Agent integration

The authoritative skill is `skills/bom-to-kit/SKILL.md`. Repository copies under `.agents/skills/bom-to-kit/` and `.claude/skills/bom-to-kit/` expose the same workflow to Codex and Claude Code. Refresh them after editing:

```powershell
python skills/bom-to-kit/scripts/sync_skill.py
```

Invoke the skill with a BOM, measured envelopes or CAD, packing rules, and a reference to compare. Keep engineer-template replay separate from an independent search. Missing dimensions and conflicting BOM revisions must remain visible.

## Local 101 / 102 benchmarks

The private evidence manifests and downloads must exist under `packaging-inputs/`.
They are intentionally absent from Git. See [evidence status](docs/evidence-status.md)
for exact sources and remaining gaps.

```powershell
python scripts/run_benchmarks.py
python -m pip install -e ".[report]"
python scripts/build_comparison_pdf.py
```

Outputs are in `packaging-results/benchmarks/`: two HTML instructions, independently
checked layouts, source fingerprints and `packing-comparison.pdf`. The nominal
seven-box arrangement equals Alan's 19.42304 L for 101 and 20.06336 L for 102.
Those nominal outputs are **not complete-kit certificates**. The original reported
50 L layout is unavailable and is not used as a reproducible before/after baseline.

## Complete-kit recipes and comparison

The corrected 101 recipe and its explicit assumptions are documented in
[the validated 101 layout](docs/101-validated-layout.md). Its 69 logical packing
units include all 43 printed pieces; one USB packet is represented by two subbags.
Replay validates the supplied recipe; it is not a new packing search.
The [102 layout](docs/102-validated-layout.md) contains 93 packing units covering
335 declared components, including 61 printed pieces. Both static comparisons
match Alan's external volume. Read the separate motion-readiness certificates
before treating a pose diagram as a complete assembly sequence.

With private sources and generated subgroup manifests present:

```powershell
python scripts/repack_101_custom_clamps.py
python scripts/assemble_101_kit.py
python scripts/write_102_arm_recipe.py
python scripts/experiment_102_clamps_servos.py
python scripts/experiment_box7.py --seconds 120 --aruco-3mf --bag-height 64.1 --output packaging-results/so-arm-102/box7-independent-wrists
python scripts/assemble_102_complete.py
python scripts/experiment_102_lower_internal_motion.py
python scripts/verify_complete_102.py --recheck-motion
python -m bom2kit assess packaging-results/so-arm-101/complete-kit/bom.json packaging-results/so-arm-101/complete-kit/input.json packaging-results/so-arm-101/complete-kit/layout.json --output packaging-results/so-arm-101/complete-kit/fresh-assessment.json
python scripts/build_complete_comparison_pdf.py --draft-101
# Final comparison requires both corrected complete kits to pass fresh assessment:
python scripts/build_complete_comparison_pdf.py
```

The final PDF generator rejects missing or invalid kits, stale renderings, and
the superseded 80 mm clamp model. The user confirmed custom 106 mm clamp frames.
Keep actual CAD, declared purchased envelopes, checked assembly paths, and physical
shipping qualification distinct. Standalone 101 group cards are generated with
`python scripts/write_101_group_recipe.py` followed by
`python scripts/render_101_group_cards.py`; these explain the nested printed
groups and BOX7, while the complete-kit report also includes purchased groups.
Generate the 102 numbered geometry cards with `python scripts/render_102_group_cards.py`.

## Repository

- `src/bom2kit/`: solver, independent validator, geometry inspection, report, and CLI.
- `tests/`: synthetic regression and adversarial validation cases.
- `skills/bom-to-kit/`: shared agent instructions and synchronization helper.
- `docs/`: architecture, implementation plan, and evidence notes.
- `packaging-inputs/`, `packaging-results/`: ignored private sources and generated artifacts.

Documentation and commits are in English; use Conventional Commits. Include the input scope, relevant tests, and evidence limitations when changing packing behavior.
