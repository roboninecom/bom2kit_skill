# Benchmark assumptions

The requested deliverable is a working tool that packs the complete BOM compactly
into organized groups. The user permits necessary BOM-based assumptions; uncertain
minor packaging details must not stop the search.

## Accepted inputs

- Use Visual Layout R3 for 101: electronics in BOX4 and disassembled ArUco.
- Use the pinned current SO-ARM-102 repository BOM for 102.
  The 12 November 2026 check supersedes the earlier source pin with
  `43252799d077e7f9971d7c695fd59f31413aa9b6`. BOM tables are unchanged, but
  the printed clamp, gear rack and nail meshes changed. The rack bounds changed
  from approximately 4.5 x 9.35 x 61 to 4.4 x 13 x 61 mm. The purchased custom
  106 mm clamp is unaffected. Current runs pin these three source mesh digests
  in the independent expected BOM; old results require fresh matching-source replay.
  On 7 November 2026, upstream HEAD was checked at
  `77e2469737f30ee30cac6da9c3ecb82e7ff2539d`. The BOM is unchanged from
  `4b9d7eb8d6d8e4860b6ba238b665120fdc48644e`; the Board cap
  `SO102.02.101-01` CAD was updated to the fixed-ear version. Its outer bounds
  remain unchanged, but its triangles and volume differ. Current comparisons
  must identify this revision and replay geometry rather than assuming a fit.
- Alan's BOX1–BOX7 dimensions are external. Cardboard walls are 1.5 mm;
  subtract 3 mm from each dimension to obtain the nominal cavity.
- Bearings may be removed from factory cartons and packed in a protective bag.
  Model 6812 bearings using the BOM dimensions: 60 mm bore, 78 mm outside diameter,
  and 10 mm thickness. Record bag allowance separately when provided.
- Other purchased-part envelopes may be estimated from the BOM or supplied CAD.
  Label each estimate and its source; do not present it as a measurement.
- The user confirmed the clamps were custom manufactured with a **106 mm frame**.
  The catalogue drawing showing an 80 mm frame does not describe the supplied
  clamps. Any layout using that smaller proxy is superseded and cannot support
  acceptance. Preserve the existing custom-frame geometry; identify other
  unmeasured dimensions separately.
- Group membership and internal box dimensions may be optimized. Preserve the
  complete contents and compare the resulting external shipping volume with Alan.

## Computational acceptance

Count every required item, preserve rigid CAD geometry, and independently check
containment and interference. Show group contents and an actionable placement
sequence. Report estimated purchased envelopes alongside validated CAD placements.

The nominal complete-kit target is at most **19.42304 L for 101** and
**20.06336 L for 102**. Equal volume is acceptable. A partial layout or a solution
that fits only the seven empty inner boxes does not meet this target.

Physical transport testing, manufacturing tolerances and hand access are separate
qualification steps. They do not prevent delivery of a complete computational
packing solution under these explicit assumptions. The report must distinguish
that solution from a physically tested shipping design.
