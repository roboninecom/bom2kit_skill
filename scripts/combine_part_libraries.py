"""Combine neutral source libraries without accepting duplicate SKU identities."""
import argparse
from hashlib import sha256
import json
from pathlib import Path


def combine(paths):
    items, provenance, seen = [], [], set()
    for path in paths:
        path = Path(path).resolve()
        raw = path.read_bytes()
        library = json.loads(raw)
        if library.get("units") != "mm" or not library.get("all_meshes_valid_volumes"):
            raise ValueError(f"Unverified source library: {path}")
        for item in library["items"]:
            if item["id"] in seen:
                raise ValueError(f"Duplicate identity: {item['id']}")
            seen.add(item["id"])
            items.append(item)
        provenance.append({"path": str(path), "sha256": sha256(raw).hexdigest(), "scope": library.get("scope")})
    if not items:
        raise ValueError("Empty library")
    return {"units": "mm", "items": items, "part_count": sum(i["quantity"] for i in items),
            "all_meshes_valid_volumes": True, "sources": provenance,
            "scope": "Merged declared source libraries; complete shipping BOM coverage requires separate reconciliation"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = combine(args.sources)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf8")
    print(json.dumps({"part_count": result["part_count"], "part_types": len(result["items"])}))
