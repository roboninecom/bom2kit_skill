# Declared BOM coverage

`reconcile_bom` checks SKU quantities independently of geometry. IDs are case-sensitive; variants are never substituted. A box must explicitly declare its contents. Quantities are positive integers, and duplicate item or component IDs are rejected.

```python
from bom2kit.bom import reconcile_bom

bom = {"components": [{"id": "STS3215-C018", "quantity": 6}]}
problem = {"items": [{
    "id": "BOX5", "quantity": 1,
    "contents": {"STS3215-C018": 6},
}]}
coverage = reconcile_bom(bom, problem)
assert coverage["complete"]
assert not coverage["geometry_validated"]
```

`contents` describes **one** item; its counts are multiplied by the item's quantity. Without `contents`, the item ID is treated as a direct SKU. An opaque box does not automatically cover its intended components. Packaging that is itself part of the BOM must appear explicitly in its own contents map or as a separate item.

Optional BOM `revision` values require matching item `revision` for direct SKUs, or `contents_revisions: {"SKU": "revision"}` for packets. Missing or different revisions fail coverage. Malformed declarations raise `ValueError`; valid but incomplete declarations return `missing`, `extra` and `revision_mismatches`.

`complete` means only that declared SKU counts and required revisions match. It does not verify actual packet contents, placement, collision, protection or full-kit acceptance. The caller must independently validate the corresponding packing result. If a ledger groups screws into a packet, it certifies that packet count, not its individual screw quantities.
