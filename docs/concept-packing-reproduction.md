# Reproduce concept packing

Run from the repository root with the dependencies in the README. The private
prepared inputs and frozen artifacts below must already exist; they are ignored
and are not distributed with a fresh clone. Search does not consume Alan's data.
Wall limits include replay. Bounded search can return different Pareto layouts
with different CPU availability; the frozen files preserve the measured outcome.

## Design complete kits from prepared BOM/CAD

```powershell
python scripts/design_concept_packaging.py packaging-inputs/independent/101/complete-library.json packaging-inputs/independent/101/transport-policy-protected-electronics.json packaging-inputs/independent/101/expected-complete-bom.json --annotations packaging-results/concept-round4/101-semantic-annotations.json --output packaging-results/reproduced/101 --cache packaging-results/practical-round3/pose-cache --grouping type --motifs rows --placement-style cohesive --time-limit 150 --wall-limit 900 --max-replays 4 --assignment-budget 60 --refinement-budget 15 --repair-budget 90 --preserve-contact-faces
python scripts/design_concept_packaging.py packaging-inputs/practical-round3/102/complete-library.json packaging-inputs/independent/102/transport-policy-protected-electronics.json packaging-inputs/practical-round3/102/expected-bom.json --output packaging-results/reproduced/102 --cache packaging-results/practical-round3/pose-cache --grouping type --motifs rows --placement-style cohesive --time-limit 150 --wall-limit 900 --max-replays 4 --assignment-budget 60 --refinement-budget 15 --repair-budget 90 --preserve-contact-faces
```

Inspect `run.json`, rejected trials and each verified `frontier-*/result.json`.
Do not automatically choose a smaller result if it adds undesirable carton sizes,
splits groups or increases handling. Compare a separate `--motifs hybrid` run only
within the available budget. Keep earlier checked alternatives.

## Replay the delivered selection and visual comparison

These commands use frozen results, not a new search. The 102 guide intentionally
retains the previous incumbent; the comparison shows the unselected new candidate.

```powershell
python scripts/build_visual_packing_guide.py packaging-results/concept-round4/final/101/result.json packaging-inputs/independent/101/expected-complete-bom.json --kit SO-ARM101 --properties packaging-results/concept-round4/final/101/part-properties.json --output packaging-results/reproduced/101-guide
python scripts/build_visual_packing_guide.py packaging-results/concept-round4/final/102/result.json packaging-inputs/practical-round3/102/expected-bom.json --kit SO-ARM102 --output packaging-results/reproduced/102-guide
python scripts/build_practical_comparison.py packaging-results/concept-round4/final-comparison-config.json --output packaging-results/reproduced/comparison
```

Render and inspect every PDF page before delivery. Hash-bound geometry and BOM
replay must pass; a stored `valid` flag alone is insufficient. See
[the outcome](concept-packing-outcome.md) for the unmet acceptance criteria.

## Changed-BOM regression and tests

The synthetic case adds one servo while retaining geometry/protection. It must
reconcile 109 packing units; it is not the actual 102 kit specification.

```powershell
python scripts/design_concept_packaging.py packaging-inputs/concept-round4/102-plus-servo/library.json packaging-inputs/independent/102/transport-policy-protected-electronics.json packaging-inputs/concept-round4/102-plus-servo/bom.json --output packaging-results/reproduced/102-plus-servo --cache packaging-results/practical-round3/pose-cache --time-limit 90 --wall-limit 600 --max-replays 2 --assignment-budget 30 --refinement-budget 15 --repair-budget 60 --preserve-contact-faces
python -m pytest -q
python skills/bom-to-kit/scripts/sync_skill.py
```

To enable the real optional solver integrations in tests, set
`BOM2KIT_IRREGULAR_SOLVER`, `BOM2KIT_RECTANGLE_SOLVER` and
`BOM2KIT_CPSAT_PYTHON` to the installed PackingSolver executables and an interpreter
containing OR-Tools. Without those configured dependencies, optional cases skip.
