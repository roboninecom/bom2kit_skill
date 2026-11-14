# Four-hour volumetric nesting audit

**The objective is not achieved.** The nominal volume limits are 19.423040 L for
SO-ARM101 and 20.063360 L for SO-ARM102, with no loss of practical usability.
The selected geometric drafts are 28.852296 L and 36.126552 L. Neither is released
for shipment. See [measured results](volumetric-nesting-results.md).

The window started on 2026-11-13 at 20:28:41 UTC. New experiments stop at
23:58:41 UTC; final reporting ends at 2026-11-14 00:28:41 UTC. No verified downtime
extension is included. PR #3 is the base; work remains in draft PR #4, unmerged.

| Requirement | Evidence / outcome |
| --- | --- |
| Freeze matching inputs and baseline | `session.json` and final audit verify 143 input/baseline/CAD file hashes. |
| Evaluate psacking and sparrow-3d | Setup attempted and logged; neither completed a real-part benchmark. CPU SciPy correlation is a separate fallback. |
| Search cavities, complementary forms and stacks | Original-source 3D occupancy correlation, independent stable poses and source-triangle replay implemented. Search is bounded, not general continuous 6-DOF optimization. |
| Start with 2–6 parts; retain individual sources | Source-bound clusters and exact quantity accounting implemented; optional extension reaches twelve members. |
| Demonstrate actual use in a complete kit | The 101 three-carton alternative contains an eleven-part combination with one stacked pair and nine floor-supported parts. It is not eleven mutually nested parts. |
| Use cavity insertion in the selected full kits | Not achieved. Local 102 cavity examples pass source replay, but selected full kits do not use them. The displayed actual 101 pair is a separated stack. |
| Validate placement sequence, support and access | Original-source clearance, modeled static/intermediate support and vertical two-finger insertion replay pass for delivered drafts. General tilted/rotated insertion and physical grip remain unverified. |
| Consider OMPL + FCL | General SE(3) planner not implemented. One native FCL continuous-collision configuration failed a thin-wall probe; the unchanged distance-bounded replay remains authoritative. |
| Jointly choose groups and carton dimensions | Motif-aware partitions, common-height alternatives, CP-SAT carton selection and complete-block repacking implemented. Local savings still fail to translate reliably into whole-kit improvements. |
| Preserve the complete BOM and protection | Matching 79/108-unit source manifests, 106 mm clamp frame, 1.5 mm inner walls and six-face foam retained; no inter-carton spacers. Purchased envelopes remain declared assumptions. |
| Validate a changed BOM | Only one servo quantity changes from six to seven; unchanged source geometry. Regenerated 109-unit / 38.342952 L result and independent replay retained. |
| Shared skill, commands and tests | Codex/Claude skill copies match; reproducible commands documented; 289 tests pass with installed solver backends. |
| R3 guides and concise visual comparison | Two ten-page CAD guides and a four-page comparison rendered and visually checked; actual used pair shown separately from local controls. |
| Operational comparison | Carton/type counts, source/material placement events, type mixing/fragments, empty-space bounds and free-travel diagnostics recorded. Labor, procurement cost and Alan's physical retention are not measured. |
| No worse than Alan | Failed on nominal volume; equivalent source/protection replay and physical practical superiority are also unproven. |

## Specific unresolved algorithmic limits

1. `cluster_correlation.py` keeps one initial seed per SKU multiset and caps the
   initial frontier. That can discard a different useful arrangement of the same
   parts before full-kit evaluation. The next experiment should retain a bounded
   Pareto set of pose-distinct seeds by footprint, height, support and access,
   rather than increasing member count alone.
2. Cluster growth ranks partners by volume/void opportunity; it does not receive
   the marginal cost of the current full carton layout. Test carton-conditioned
   destroy-and-repair: remove a semantic neighborhood, generate several nested
   replacements at its candidate height/footprint, retile and replay the full kit.
3. The new final Pareto filter preserves organization tradeoffs, but cannot recover
   useful layouts discarded during proposal generation. Apply the same type and
   fragmentation objectives before the limited replay queue, then measure both
   whole-kit volume and kitting organization on the frozen inputs.
4. Vertical fingertip replay rejects or times out on some dense proposals. A
   bounded OMPL SE(3) insertion attempt with FCL discrete checks and certified
   segment bounds is an unimplemented next candidate, not an established fix.
5. Geometric nesting does not supply retention. Any further design must explicitly
   resolve free travel with adjusted carton dimensions and counted, specified
   protective packaging; it must not silently infer restraint from a closed box.

Private evidence and generated PDFs remain under
`packaging-results/volume-round5/final/`; original source material remains ignored.
The final artifact audit records hashes, selections, tests and unmet conditions.
