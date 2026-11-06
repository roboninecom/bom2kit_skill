# Packaging acceptance evidence

## Reference and scope

The acceptance target is the complete kit, including its protection and packing instructions. Matching the outer carton alone does not satisfy it.

| Reference | Nominal outer carton (mm) | Calculated volume |
|---|---|---|
| Alan, SO-ARM101 | 364 x 290 x 184 | 19.42304 L |
| Alan, SO-ARM102 | 376 x 290 x 184 | 20.06336 L |

Sources: Redmine [#9415](https://redmine.fosterflow.com/issues/9415), [#9391](https://redmine.fosterflow.com/issues/9391), attachment **2555**, and the supplied box-size documents. These are nominal design dimensions, not new physical measurements. Earlier 101 designs at 17.247 L and 27.3 L are superseded.

The user selected **Visual Layout R3** for 101: electronics in BOX4, ArUco unassembled, **43 printed pieces**. The user identified the SO-ARM-102 repository as the current BOM source; the benchmark pins its fetched main commit **4b9d7eb8d6d8e4860b6ba238b665120fdc48644e**. Its 44 robot printed pieces reconcile with the packing PDF; the PDF adds 17 educational pieces, giving **61 printed pieces**. The older April costing workbook is not authoritative.

## Evidence available

- The user confirmed BOX1-7 dimensions are **external**, with **1.5 mm walls**. Subtract 3 mm per dimension for their nominal interiors; 102 BOX1 is 243 x 113 x 72 mm. This does not change the outer-envelope comparison.

- Source dimensions reconstruct the seven nominal inner-box envelopes in two layers.
- The 101 foam drawing establishes a 320 x 246 x 140 mm protected cavity with 15 mm EPE. Applying the same material thickness to 102 implies 332 x 246 x 140 mm; that is a derived assumption.
- Current CAD/print sources provide robot geometry. Figure geometry is available in the supplied 101 print source set.
- Packing PDFs illustrate Alan's inner arrangements. Printing-project 3MF transforms describe printer placement, not packing poses.

## Evidence still required for full-kit acceptance

Part-level progress: BOX7 now has independent static triangle certificates for
**17/17 pieces in 101** and **31/31 in 102**, inside the confirmed **193 x 75 x 61 mm**
interior at 0.1 mm pair clearance. The 102 solution nests the two wrist holders;
101 reuses the same figure placements. Both select the current `-2.3mf` ArUco
alternative permitted by the packing PDF. This does not establish the remaining
boxes, protective bags, stability or the complete kit.

1. Collision-validated poses and containment for every printed part and purchased packet, with complete quantities and the chosen revision.
2. Verified packed envelopes for purchased parts, especially the different servo variants and PSUs. The 101 source's 5V4A PSU and current 102 BOM's 5V2A PSU cannot silently share geometry.
3. Explicit accounting for factory-included cables, horns and screws, plus packing additions such as regional cords and booklet.
4. Manufacturing tolerance, booklet thickness and protection validation. The nominal two-layer stack is 139 mm inside a 140 mm cavity.

No recovered original Alan packed-assembly transform file has been established. An earlier local 101 nesting implementation is a separate 19.98 L design with 10 mm foam and assumed purchased envelopes; it is a search aid, not the reference or acceptance evidence.

## Source fingerprints

SHA-256 identifies the exact supplied artifacts; raw files remain ignored.

| Source | SHA-256 |
|---|---|
| Redmine attachment 2555 | `acca6a274e1dd0887dc376c490df82fc25c6a3c4eaefc1cf97361a2d40c019d5` |
| 101 Visual_Layout_R3.pdf | `922bd4ce58a7ca906364e319f5dea29a6796e2f829f1f3595e1e33865f024a5f` |
| 101 Box_sizes.pdf | `8219ef32e6c5c1c733dad3de22da1039ae38c7c47617f333c19bfb2dc45240a5` |
| SO102_Printing_and_Packing.pdf | `170af12b417277664281e1f9791c65285bc20d61f139adc8fdd30d40dae3f20c` |
