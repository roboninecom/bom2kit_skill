"""Reconcile declared SKU quantities independently of packing geometry."""

from collections import Counter


def _identifier(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _count(value, label):
    if type(value) is not int or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _rows(document, key):
    if not isinstance(document, dict) or not isinstance(document.get(key), list):
        raise ValueError(f"{key} must be an array")
    if not document[key]:
        raise ValueError(f"{key} must not be empty")
    seen = set()
    for row in document[key]:
        if not isinstance(row, dict):
            raise ValueError(f"Each {key} entry must be an object")
        identifier = _identifier(row.get("id"), f"{key} id")
        if identifier in seen:
            raise ValueError(f"Duplicate {key} id: {identifier}")
        seen.add(identifier)
        _count(row.get("quantity"), f"{identifier} quantity")
        if "revision" in row:
            _identifier(row["revision"], f"{identifier} revision")
    return document[key]


def reconcile_bom(bom, problem):
    """Compare exact, case-sensitive SKU declarations; never infer packet contents.

    Each item declares its quantity and either a per-item ``contents`` SKU-count
    map or its direct SKU ``id``. For revisioned BOM entries, direct items use
    ``revision``; packets use ``contents_revisions``. Missing revisions fail the
    revision check. Malformed declarations raise ValueError. A successful result
    proves declared counts only, not placement, physical contents or feasibility.
    """
    components = _rows(bom, "components")
    items = _rows(problem, "items")
    expected = {row["id"]: row["quantity"] for row in components}
    revisions = {row["id"]: row["revision"] for row in components if "revision" in row}
    actual = Counter()
    contributions = []
    mismatches = []
    for item in sorted(items, key=lambda row: row["id"]):
        identifier = item["id"]
        if "contents" in item:
            contents = item["contents"]
            if not isinstance(contents, dict) or not contents:
                raise ValueError(f"{identifier} contents must be a nonempty object")
            supplied_revisions = item.get("contents_revisions", {})
            if not isinstance(supplied_revisions, dict):
                raise ValueError(f"{identifier} contents_revisions must be an object")
            for sku, revision in supplied_revisions.items():
                _identifier(sku, "contents revision SKU")
                _identifier(revision, f"{sku} revision")
                if sku not in contents:
                    raise ValueError(f"Revision for undeclared contents: {sku}")
        else:
            if "contents_revisions" in item:
                raise ValueError("contents_revisions requires contents")
            contents = {identifier: 1}
            supplied_revisions = {identifier: item.get("revision")}
        for sku, per_item in contents.items():
            _identifier(sku, "contents SKU")
            _count(per_item, f"{sku} contents quantity")
        for sku, per_item in sorted(contents.items()):
            quantity = item["quantity"] * per_item
            actual[sku] += quantity
            contributions.append({"item_id": identifier, "sku": sku, "quantity": quantity})
            if sku in revisions and supplied_revisions.get(sku) != revisions[sku]:
                mismatches.append({"item_id": identifier, "sku": sku,
                                   "expected": revisions[sku],
                                   "declared": supplied_revisions.get(sku)})
    missing = {sku: quantity - actual[sku] for sku, quantity in sorted(expected.items())
               if quantity > actual[sku]}
    extra = {sku: quantity - expected.get(sku, 0) for sku, quantity in sorted(actual.items())
             if quantity > expected.get(sku, 0)}
    return {
        "scope": "declared_sku_coverage_only",
        "complete": not missing and not extra and not mismatches,
        "expected": dict(sorted(expected.items())),
        "declared": dict(sorted(actual.items())),
        "missing": missing,
        "extra": extra,
        "revision_mismatches": mismatches,
        "contributions": contributions,
        "geometry_validated": False,
    }
