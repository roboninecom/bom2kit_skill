# SO-ARM101 validated layout

The complete declared Visual Layout R3 kit fits Alan's **364 × 290 × 184 mm**
external carton: **19.42304 L**, a **0% volume change**. Independent checks cover
69 logical packing units, including all 43 printed pieces. The original R3
contents ledger reconciles without missing or extra items.

## Packing groups

| Group | Contents | Internal cavity, mm |
|---|---|---|
| Merged lower carton | 26 robot printed pieces, two adapter packets, servo cables | 265 × 243 × 72.2 |
| BOX3, lower side | Two sleeved PSUs; two USB subbags | 243 × 72.2 × 49 |
| BOX5, upper side | Twelve original servo boxes, original variant mix | 243 × 121 × 61 |
| BOX6, upper front | Four custom 106 mm clamps and two AC cord packets | 193 × 165 × 61 |
| BOX7, upper rear | Seventeen educational pieces, camera, fasteners/tools packet | 193 × 75 × 61 |

Prepare the five nested printed clusters using their numbered cards. Assemble
the clamp group on the work surface in order **4, 3, 2, 1**, approaching along
the documented negative Y direction, then lower it into BOX6. Stack the two
AC cord packets beside it with the declared 0.1 mm separator. Pack both lower
cartons first, followed by BOX6, BOX5 and BOX7. The outer carton layout has
independently checked support and top insertion.

## Explicit assumptions

- The user confirmed custom **106 mm clamp frames**. The unchanged historical
  assembled proxy is 140 × 40 × 52 mm; its remaining dimensions are estimates.
  The smaller 80 mm catalogue model is excluded.
- Each USB subbag contains one cable and one adapter. Two 110 × 30 × 20 mm
  envelopes preserve the former packet's total estimated volume and contents.
- Purchased packet dimensions, folded leads and sleeves are declared estimates.
  Cardboard is 1.5 mm, external foam 15 mm, carton offset 7 mm and booklet
  allowance 0.8 mm. These checks do not constitute a physical shipping trial.

## Reproduce and inspect

With the private input/source artifacts present, run from the repository root:

```powershell
python scripts/repack_101_custom_clamps.py
python scripts/assemble_101_kit.py
python -m bom2kit mesh-report packaging-results/so-arm-101/complete-kit/input.json packaging-results/so-arm-101/complete-kit/layout.json --output packaging-results/so-arm-101/complete-kit
```

The output directory contains the exact poses, source hashes, independent BOM,
assessment, outer-carton certificate and actual mesh views. Independent audit
and group-motion certificates are linked in `independent-readiness.md` there.
The full geometry/BOM/volume recheck took **4.67 seconds** on the development
machine; this is recipe validation time, not the original arrangement search.
