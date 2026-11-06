"""Extract quantity-bearing Markdown BOM rows, preserving variants and evidence.

This is source ingestion only. Narrative additions and optional alternatives
require reconciliation; the result is not a certified complete shipping BOM.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re


def extract(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    rows, headers, section = [], None, ""
    for line_number, line in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
        if line.startswith("#"):
            section = line.lstrip("#").strip()
            headers = None
        if not line.strip().startswith("|"):
            headers = None
            continue
        values = [v.strip() for v in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
        qty = [i for i,v in enumerate(values) if v.casefold() in ("qty", "quantity")]
        if qty:
            if len(qty) != 1:
                raise ValueError(f"Ambiguous quantity column at line {line_number}")
            headers = (values, qty[0])
            continue
        if headers is None:
            continue
        names, quantity_index = headers
        if len(values) != len(names):
            raise ValueError(f"Malformed BOM row at line {line_number}")
        value = values[quantity_index]
        if not value or re.fullmatch(r"[:\-]+", value):
            continue
        if not value.isdigit() or int(value) <= 0:
            raise ValueError(f"Non-integer BOM quantity at line {line_number}: {value}")
        rows.append({"source_line": line_number, "section": section,
                     "item": values[0], "quantity": int(value),
                     "columns": [{"name": k, "value": v} for k,v in zip(names,values)],
                     "optional_alternative": any("alternative" in v.casefold() for v in values),
                     "source_row": line})
    if not rows:
        raise ValueError("No quantity-bearing BOM table rows found")
    return {"source": str(path), "source_sha256": sha256(raw).hexdigest(), "rows": rows,
            "nonalternative_table_quantity": sum(r["quantity"] for r in rows if not r["optional_alternative"]),
            "scope": "BOM table rows only; narrative additions, included accessories and shipping contents require review"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = extract(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf8")
    print(json.dumps({"rows": len(result["rows"]), "nonalternative_table_quantity": result["nonalternative_table_quantity"]}))
