# Concept-first packing: measured outcome

**The no-worse-than-Alan objective is not achieved.** The planner and shared
Codex/Claude skill run, but neither selected kit meets the nominal volume target
or has qualified transport restraint. This is a computational prototype.

## Same-input comparison

| Kit / result | Exterior, mm | Volume, L | Cartons / sizes | Decision |
| --- | --- | ---: | ---: | --- |
| 101 before | 565 x 291 x 181 | 29.759115 | 3 / 3 | Retain as procurement alternative |
| 101 new | 290 x 341 x 293 | 28.974770 | 4 / 4 | Selected for the new guide |
| 101 Alan | 364 x 290 x 184 | 19.423040 | 7 / not audited | Nominal reference |
| 102 before | 346 x 452 x 231 | 36.126552 | 4 / 4 | Retained for the guide |
| 102 new candidate | 451 x 375 x 222 | 37.545750 | 4 / 4 | Not selected: larger |
| 102 Alan | 376 x 290 x 184 | 20.063360 | 7 / not audited | Nominal reference |

101 improves external volume by **2.64%**, with one extra carton/size. Its gap
to Alan is **49.18%**. The retained 102 gap is **80.06%**. The lowest-volume new
102 candidate is **3.93% larger** than its incumbent, despite better grouping.
No global optimum or impossibility claim follows from these bounded searches.

Using identical semantic cards for both layouts, type cohabitation pairs / spatial
fragments change from **89 / 11 to 49 / 4** for 101 and **173 / 18 to 112 / 6**
for the new 102 candidate. Cohabitation measures shared cartons; fragments use a
10 mm bounding-box adjacency proxy. Neither directly measures physical mixing.
No selected layout splits a source SKU or the declared complete accessory sets.

101 retains 79 individual placements, 12 factory cartons, nine packets and no
contact sheets; liners increase from three to four. 102 retains 108 placements,
ten packets and four liners. The purple purchased-item envelopes are **not extra
cartons**. Manual seconds, supplier prices and strength are unmeasured.

## Why the gap remains

1. **Grouping improved; internal space use did not.** For 101, space outside
   protected source bounds increases from 6.566 to 6.955 L, or 40.06% to 41.25%
   of cavity volume. The volume gain comes from a more efficient exterior shape:
   space outside inner cavities falls from 13.368 to 12.114 L. For the new 102
   candidate, cavity space outside protected bounds increases from 47.47% to
   50.16%. These are lower bounds on empty space, not additional usable capacity.
2. **The best selected concepts remain predominantly floor arrangements.**
   Working stack, interlocking and cavity motifs did not translate into a better
   complete-kit layout. Contact, protection and individual access restrict usable
   combinations; turning off those checks would not solve the shipping task.
3. **Carton reconciliation can enlarge a poorly filled module.** In selected 101,
   a 160 x 281 x 45 mm mechanics pattern becomes a 246 x 297 x 45 mm carton to
   tile the block without spacers. Local assignment repair cannot guarantee the
   best coupled grouping, orientation and carton partition.
4. **Geometric restraint still fails as a shipping argument.** The conservative
   screen finds potential travel above 5 mm for all 79 selected 101 units and
   106 of 108 retained 102 units. That threshold is a diagnostic, not a transport
   standard. Blocked bounds also would not prove restraint. No drop/vibration,
   cushion, friction or manual kitting tests were performed.

## Implemented changes and rejected shortcuts

Evidence-tagged properties, hard material compatibility, semantic adjacency,
rows/stacks/alternating/supported nesting, beam concepts, actual-volume assignment
repair, diverse carton-count scheduling, source-derived contact faces, local
access repair, contour proposals and FFT-ranked floor-pair translations now work
together. Relative quarter-turns allow a nested child to use a rectangular recess.
Original triangles, BOM, support and insertion are independently replayed.

Visual review rejected an apparently smaller layout that put six marker faces
in a separate 10 mm carton. Complete accessory-set membership is now an independent
gate. Sub-10 mm contact-sheet cuts are rejected under an explicit manual-handling
assumption. Existing packets retain their contents; no new bag is treated as a
rigid assembly or automatic restraint. The CLI/skill start with typed rows and
compare expensive motifs separately, preserving earlier checked alternatives.

## Evidence, scope and reproduction

Before/after sources and protection match exactly: complete 101/102 BOM, current
102 source revision `43252799d077e7f9971d7c695fd59f31413aa9b6`, custom 106 mm clamp,
1.5 mm inner walls, 7 mm outer wall, 15 mm foam on six faces and unchanged item
protection. Purchased dimensions remain labelled estimates where applicable.
Alan's complete matching source poses/BOM/protection cannot be replayed from the
supplied illustrations; his dimensions are used only after search.

The synthetic changed-BOM case increases `hardware-line-52` from six to seven:
109 packing units are reconciled and replayed, yielding 38.153808 L in 185.6 s.
This is a regression case, not the actual 102 BOM. The selected 101 run took
282.4 s including preparation/search/replay; the illustrated new 102 run took
375.0 s. Timings use prepared source meshes,
warm caches and concurrent execution; source import and manual preparation were
not timed. Selected-run times exclude the other unsuccessful experiments.

The shared skill and [design document](concept-packing-design.md) contain the CLI
workflow. Frozen runs retain parameters, source/engine hashes, proposal history,
rejected trials and assembly fingerprints under ignored
`packaging-results/concept-round4/`. Selected 101 is
`101/cohesive-type-rows/frontier-01/result.json`; retained 102 is
`packaging-results/practical-round3/selected/102/result.json`. The comparison
also shows `102/typed-hybrid-surfaces/frontier-01/result.json` as the unselected
new candidate. Results may vary under bounded wall-clock search.

Local deliverables are `final/101/guide/packing-guide.pdf`,
`final/102/guide/packing-guide.pdf` and `final/comparison/comparison.pdf` below
the round directory. The comparison JSON preserves fresh replay and metric
evidence. Raw CAD and generated artifacts stay ignored.

Validation: **264 tests pass**, including enabled real PackingSolver and OR-Tools
integrations, source geometry/support regressions, relative cavity rotation,
accessory-set cohesion and budgeted concept diversity. The shared skill passes
its validator and both agent copies match. This evidence validates implemented
behavior; it does not establish the no-worse shipping objective.

Next work must improve the **coupled pattern/partition search and physical packing
states**, not merely add more independent random trials: persist verified local
motifs keyed by source/protection hashes; select compatible motifs and carton
partitions together; feed underfilled expanded cartons back into group assignment.
Any tighter flexible packaging requires an evidenced protection/retention design
and prototype. These are remaining work, not delivered capabilities.
