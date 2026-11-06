---
name: bom-to-kit
description: Convert a BOM with measured packing envelopes or CAD into traceable packing layouts and illustrated kitting instructions, and compare them with an engineer's reference using the local bom2kit engine.
---

# BOM to Kit

Use the repository's shared Python engine for coordinates, quantities, validation, and diagrams. Read `README.md` for installation and commands; inspect the input schema before preparing a new job. Run from the repository root with `python -m bom2kit` after installation.

## Establish comparable inputs

- Discover the BOM, quantity/revision information, actual packed-state envelopes, protection requirements, and source documents. Keep private inputs under `packaging-inputs/` and generated artifacts under `packaging-results/`.
- Preserve variant and assembly identity. A CAD solid is not necessarily one BOM item. Cable coils, fastener bags, and sealed factory boxes need measured packed envelopes.
- Record missing geometry and contradictory source instructions. Never invent dimensions or silently replace deprecated geometry with production evidence.
- Keep usable cavity dimensions separate from external shipping dimensions. Compare complete matching kits with the same protective materials and packed states.

## Search and validate

1. Normalize verified dimensions and constraints into the engine's JSON input. Use `reconcile BOM.json job.json` to check declared SKU quantities and revisions; do not treat grouped packet counts as an expanded hardware BOM. Use `inspect` for STEP evidence when available; CAD import is optional for measured envelopes.
2. Run `solve` with a bounded time budget and write the layout and validation to an ignored output directory.
3. Run `validate` independently on the resulting input/layout pair. Correct input errors or reject invalid candidates before generating operating instructions.
4. Use `optimize` with explicit `container_candidates` to compare permitted cartons. The rectangular search is deterministic: changing `seed` does not diversify it. Change permitted grouping/orientations only when supported by the input rules. Preserve all required items and protection. A timeout means incomplete search, not impossibility or optimality.
5. Render diagrams and packing sequence from the canonical layout. State exactly which checks passed and which remain unimplemented or unverified.

## Compare and deliver

Report external volume, complete-kit coverage, implemented constraint checks, and measured runtime. Label engineer-template replay separately from search from scratch. A solution matching an engineer's outer box is not proof that all its contents fit.

Distinguish rectangular-envelope validation, actual CAD collision validation, and physical packing/transport trials. Report unresolved evidence as a limitation; never call a preliminary result production-approved. If the requested no-worse result cannot be demonstrated, deliver the working tool and explicit evidence gap without claiming the objective was met.

## Irregular parts and local benchmarks

Install the optional `[mesh]` dependencies to check triangle geometry. Use
`mesh-validate input.json layout.json` for supplied rigid transforms. Use
`mesh-pair input.json --output packaging-results/pair --time-limit 30` for a
bounded two-part nesting search; this is not a complete-kit optimizer.
Reject scaling, changed source hashes and missing instances. Voxel arrangements
and printer-plate positions are proposals, never packing certificates. Reusing
a recipe requires matching part revisions and quantities; unchanged labels alone
are insufficient.

Run `python scripts/run_benchmarks.py` when the private 101/102 evidence manifests
are available. This compares seven closed boxes per kit and intentionally leaves
full-kit acceptance false. With `[report]` installed, run
`python scripts/build_comparison_pdf.py` to generate the concise visual comparison.
Do not infer the reported 50 L failure from these inputs: its original layout
has not been supplied, so it is not a reproducible baseline.

The authoritative skill is `skills/bom-to-kit/SKILL.md`. After editing it, run `python skills/bom-to-kit/scripts/sync_skill.py` to update the Codex and Claude Code copies.
