# Visual packing guide

The skill's primary transport deliverable is an A4 PDF inspired by the supplied
Visual Layout R3 document. It presents the generated packing as an operator guide,
with the technical HTML comparison retained separately.

```powershell
python scripts/build_visual_packing_guide.py RESULT.json EXPECTED.json --kit SO-ARM101 --revision "Draft 1" --output packaging-results/my-kit/visual-guide
```

Install the existing `[mesh,report]` extras. The command needs a validated transport
result and its independent expected BOM; it does not run a new packing search.

## Document structure

1. **Where each box goes:** exploded outer carton, actual six-face foam geometry,
   visible CAD inside numbered cartons, and packing order derived from the plan.
2. **Each box:** isometric, numbered top and side views; insertion order; a
   thumbnail inventory with source IDs, packing-unit quantities and slot numbers.
3. **Nested groups:** original workbench poses and numbered internal assembly
   sequences, linked to the relevant box and slot.
4. **Checklist before taping:** manual verification fields, exterior illustration
   and source/result hashes. The checklist is not marked as completed automatically.

Long inventories continue onto additional pages with repeated box/table headers.
Page count follows the actual BOM, not the nine-page reference document.

## Geometry and evidence

The generator rechecks transport geometry, complete BOM and geometric assembly.
It hashes source meshes again before rendering. All original CAD triangles and
part-to-carton membership are retained. One rigid display translation per carton
creates the explosion; it is never written back into the packing result.

Carton walls are shortened and lids omitted in the display to reveal contents.
These are closed cartons in the actual packing. Purchased components without
detailed CAD remain declared envelopes; thumbnails do not imply detailed geometry.
The reference's carton sizes, quantities, poses and branding are not imported.

Outputs are `packing-guide.pdf`, `assembly-plan.json`, `guide-manifest.json` and
an `illustrations/` directory. The manifest binds the PDF and images to the raw
result/BOM hashes, records carton numbering, source-unit coverage and display
offsets. Keep all generated artifacts in ignored `packaging-results/`.

The document remains a geometric draft until actual restraint, cushioning,
manufacturing tolerances and shipping performance have separate evidence.
Inspect every rendered PDF page for clipping, unreadable labels and pagination
before sharing it. English is used throughout the repository and generated guide.
