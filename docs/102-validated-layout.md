# SO-ARM-102 validated layout

The current computational result contains **93 packing units covering all 335 declared components across 59 BOM entries**. Independent mesh validation and canonical BOM reconciliation pass. The external carton is **376 × 290 × 184 mm, 20.06336 L**, equal to Alan's reference volume. Physical handling and protection equivalence have not been demonstrated.

## Arrangement

Dimensions below are group envelopes in millimetres, rounded for display. The saved JSON retains full precision. The lower carton supports four upper groups.

| Group | Envelope | Contents |
| --- | --- | --- |
| LOWER | 332 × 246 × 75 | 26 printed parts, two large bearings, two PSUs, camera, two servos, adapters, cables, small hardware, rods, USB cables and fasteners/tools |
| UPPER_ARMS | 203.2435 × 143.6007 × 56.1 | Four current upper-arm meshes |
| CLAMPS_SERVOS_EXTRAS | 123.3 × 238.3 × 64.2 | Four custom 106 mm clamps, ten servos and all factory accessory packets |
| BOX7 | 191.7400 × 74.82 × 63.82 | Fourteen printed robot components and seventeen figures; wrists packed separately |
| AC_CORDS | 200.2 × 27.1 × 60.1 | Two regional AC cords |

The outer 15 mm EPE liner and 7 mm carton walls remain. The lower carton retains 1.5 mm walls. Upper rigid inner cartons are replaced by an assumed **0.05 mm film per face**. Ten upper servos use estimated 1 mm EPE sleeves; the two lower servos retain 2 mm sleeves. The booklet reserve is an assumed 0.8 mm.

Clamp proxies preserve the unchanged historical 140 × 40 × 52 mm geometry and the user-confirmed 106 mm frame. Other purchased dimensions, flexible folds and packet interiors remain explicit assumptions. Each AC-cord envelope is 100 × 27 × 60 mm: the previous 162 cm³ volume is preserved, with primary plug dimensions supporting the thin orientation. No CAD solid is scaled.

## Reproduce and inspect

Run from the repository root with the optional mesh dependencies installed. Downloaded sources and saved search seeds must remain in the ignored input/result directories; the scripts do not download private material.

```powershell
python scripts/write_102_arm_recipe.py
python scripts/experiment_102_clamps_servos.py
python scripts/experiment_box7.py --seconds 120 --aruco-3mf --bag-height 64.1 --output packaging-results/so-arm-102/box7-independent-wrists
python scripts/assemble_102_complete.py
python scripts/experiment_102_lower_internal_motion.py
python scripts/verify_complete_102.py --recheck-motion
```

The assembler consumes the validated lower seed `packaging-results/so-arm-102/lower-usb-fasteners/`, current arm meshes, the existing BOX7 certificate, canonical BOM mapping and purchased-item catalogues. It writes `packaging-results/so-arm-102/complete-kit/`, including input, layout, independent BOM, assessment, outer layout and validation certificates.

The lower seed was built by `complete_102_lower.py`, `add_102_psus.py` and bounded calls to `experiment_102_lower_hardware.py`, with two servo sleeves added before the small-packet search. Saved manifest/pose files preserve those intermediate choices. This is a reproducible validated recipe, not a claim that an unconstrained search always finds it.

Final mesh validation, a second fresh mesh check during BOM assessment, and outer-group validation took **17.56 seconds** in the recorded run. Earlier searches are separate: small packets took 57.13 seconds; USB/fastener placement took 31.15 seconds. The final independent-wrist BOX7 arrangement took **0.87 seconds**, one envelope-packing attempt; all 31 individual vertical assembly paths passed in 1.49 seconds. These timings exclude source acquisition and the exploratory engineering work. Internal assembly/motion certificates are separate from static fit and from physical qualification.

The additional bag height matters: a 33.6 mm wrist envelope and a 30 mm figure can stack with clearance below 64.1 mm. That replaces the earlier compact but unresolved nested-wrist arrangement. The final result uses no nested wrist subassembly and does not require its unsuccessful motion searches.

## Lower-group assembly

The two cyclic lower subgroups have independently checked continuous assembly paths on an open work surface. Original final-layout coordinates define the directions:

- Assemble the seven-part cluster along **−Y**: `bottom#4`, base #1, base #2, `bottom#3`, `servo#1`, adapter packet #2, `servo#2`. Here `servo` denotes the printed servo holder, not an electric motor.
- Assemble printed gripper clamp #2, then wrist roll #1, along **−X**.

The respective successful checks took 10.33 and 1.09 seconds. Certificates under `complete-kit/internal-motion/` bind the final input/layout, source meshes, coordinate rotation and original unit identities. These checks establish collision-free translations; hands, tools, film handling and support during assembly are not modeled.
