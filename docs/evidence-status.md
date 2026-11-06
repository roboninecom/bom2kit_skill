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

## Complete-kit results

Independent static checks and source-BOM reconciliation pass for both kits:

| Kit | Packing units | Printed pieces | External volume | Change from Alan |
|---|---:|---:|---:|---:|
| 101 | 69 logical units | 43 | 19.42304 L | 0% |
| 102 | 93 logical units / 335 declared components | 61 | 20.06336 L | 0% |

The final manifests live under `packaging-results/so-arm-*/complete-kit/`.
They retain source hashes, proper rigid poses and explicit purchased-envelope
assumptions. The authoritative BOM ledgers are independent of the layouts.
See [101 details](101-validated-layout.md) and [102 details](102-validated-layout.md).

The internal subgroup and outer group assembly checks pass for both kits.
The final 102 BOX7 recipe places both wrists independently; all 31 pieces have
checked individual vertical insertion paths. The former statically nested wrist
pair is superseded and is not used in the delivered instruction. Motion evidence
is recorded separately from static fit and bound to the final input/layout hashes.

The 102 upper groups use declared thin film instead of the original rigid inner
cartons. Ten upper servos use estimated 1 mm EPE sleeves; two lower servos retain
2 mm sleeves. External 15 mm foam remains. These are explicit packing changes,
not proof of equal transport protection. Purchased dimensions, folded cables,
booklet thickness, manufacturing tolerance and physical transport performance
remain qualified as described in [benchmark assumptions](benchmark-assumptions.md).

Experimental 6812 bearing annuli use the current BOM's 60 x 78 x 10 mm dimensions. The user permits bagged bearings and confirms factory cartons are not required. The annulus bounds the bare bearing; a flexible bag is assumed, with thickness and placement still outside the triangle certificate. This is an authorized packing-state assumption, not measured bag geometry.

No recovered original Alan packed-assembly transform file has been established. An earlier local 101 nesting implementation is a separate 19.98 L design with 10 mm foam and assumed purchased envelopes; it is a search aid, not the reference or acceptance evidence.

## Source fingerprints

SHA-256 identifies the exact supplied artifacts; raw files remain ignored.

| Source | SHA-256 |
|---|---|
| Redmine attachment 2555 | `acca6a274e1dd0887dc376c490df82fc25c6a3c4eaefc1cf97361a2d40c019d5` |
| 101 Visual_Layout_R3.pdf | `922bd4ce58a7ca906364e319f5dea29a6796e2f829f1f3595e1e33865f024a5f` |
| 101 Box_sizes.pdf | `8219ef32e6c5c1c733dad3de22da1039ae38c7c47617f333c19bfb2dc45240a5` |
| SO102_Printing_and_Packing.pdf | `170af12b417277664281e1f9791c65285bc20d61f139adc8fdd30d40dae3f20c` |

## Custom clamp correction

The user confirms that the actual clamp is custom-made with a **106 mm frame**. The current supplier listing's 80 mm frame is inapplicable. Its geometric certificates remain experimental artifacts and cannot support complete-kit acceptance. The restored historical 106 mm proxy retains the other legacy geometry assumptions without shrinking the knob, pad or shaft to match the unrelated listing. Replacement layouts require independent validation and updated source hashes.
