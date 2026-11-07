# One-hour packaging progress report

Session: 7 November 2026, starting 12:52 UTC. New searches stopped at 13:42 UTC;
the remaining time was reserved for checks, artifacts and commits.

## Result

**The no-worse objective is not achieved.** Complete declared contents, source
geometry and protection were preserved throughout the accepted comparison.

| Kit | Before (L) | Best after (L) | Alan (L) | Above Alan |
| --- | ---: | ---: | ---: | ---: |
| 101 | 19.842790 | 19.522745 | 19.423040 | 0.51% |
| 102 | 22.087296 | 21.954240 | 20.063360 | 9.42% |

101 uses 253 x 253 x 305 mm and three closed inner cartons. 102 uses
252 x 264 x 330 mm and five. Both pass fresh declared-BOM, original-mesh,
carton-wall/support, internal assembly and external insertion checks.
Purchased envelopes retain their documented estimates; this is not a transport test.

## What changed

- Added automatic moves/swaps between generated layers and footprint repair.
  Original meshes are transferred rigidly and independently checked again.
- Fixed a policy error that allowed a wall-free shelf to replace required inner
  cartons. Existing selected benchmark layouts already had checked inner walls.
- Added a necessary floor-area bound to skip impossible fits. Basic deterministic
  ordering runs first; broader ordering is a separate second pass.
- Added a portable HTML comparison with Alan's PDF images, actual CAD views,
  numbered contents, group assembly diagrams and insertion steps.

The current code matched the 101 volume from the same independently generated
incumbent in 45 seconds, with different poses. Fresh original-mesh and assembly
replay passed in 58.86 seconds. This is **not** a cold design run.

Final verification: **145 tests passed in 17.07 seconds**. The HTML contains
25 checked embedded images and needs no external image files.

## Fresh searches

Both fresh processes used prepared individual libraries and expected BOMs, with
no prior groups, carton sizes or poses. Code: `27b6aa3`. They ran concurrently.

| Kit | Fresh result (L) | Runtime | Declared BOM |
| --- | ---: | ---: | --- |
| 101 | 19.828116 | 16.04 min | Complete |
| 102 | 22.619520 | 17.97 min | Complete |

These runs did not reproduce the smaller cached incumbents. Source import is
excluded from timing; stage times include checks. End-to-end speed and reliable
reproduction of the best layouts remain unresolved.

Recorded invocation (replace `KIT` with `101` or `102`; use a new output directory):

```powershell
python scripts/design_grouped_meshes.py packaging-inputs/independent/KIT/complete-library.json packaging-inputs/independent/KIT/hour-policy.json --bom packaging-inputs/independent/KIT/expected-complete-bom.json --output packaging-results/independent/KIT/new-run --pair-budget 120 --pair-seconds 8 --max-pairs 12 --nesting-rounds 1 --cavity-budget 90 --carton-budget 80 --group-configurations 3 --improvement-budget 120
```

## Evidence and next step

Local ignored artifacts: `packaging-results/hour-report/report.html`,
`comparison-checks.json`, and `independent/{101,102}/hour-membership/` and
`hour-cold-run/`. The HTML embeds its images and can be opened offline.

Wider footprints, alternate ordering, weaker-group removal and median carton
splitting did not improve the selected results. An isolated OR-Tools 9.15.6755
experiment also found no improvement within its limits; it was not promoted into
the engine. Its model used optional rectangles from the
[official CP-SAT API](https://or-tools.github.io/docs/pdoc/ortools/sat/python/cp_model.html),
then restored original dimensions and independently checked proposals.

At the current memberships and footprints, a one-millimetre height reduction in
every layer is excluded by an individual-part or minimum-area bound. The next
useful search must change memberships, group shapes or carton footprints jointly.
This restricted bound does not establish global optimality or impossibility.
