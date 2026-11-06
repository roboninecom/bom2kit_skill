# Benchmark assumptions

The requested deliverable is a working tool that packs the complete BOM compactly
into organized groups. The user permits necessary BOM-based assumptions; uncertain
minor packaging details must not stop the search.

## Accepted inputs

- Use Visual Layout R3 for 101: electronics in BOX4 and disassembled ArUco.
- Use the pinned current SO-ARM-102 repository BOM for 102.
- Alan's BOX1–BOX7 dimensions are external. Cardboard walls are 1.5 mm;
  subtract 3 mm from each dimension to obtain the nominal cavity.
- Bearings may be removed from factory cartons and packed in a protective bag.
  Model 6812 bearings using the BOM dimensions: 60 mm bore, 78 mm outside diameter,
  and 10 mm thickness. Record bag allowance separately when provided.
- Other purchased-part envelopes may be estimated from the BOM or supplied CAD.
  Label each estimate and its source; do not present it as a measurement.
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
