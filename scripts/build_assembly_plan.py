"""Build a fresh, result-bound geometric assembly plan for generated cartons."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from bom2kit.assembly_plan import build_assembly_plan

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("bom", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = build_assembly_plan(json.loads(args.result.read_text()), json.loads(args.bom.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2), encoding="utf8")
    print(json.dumps({"status": plan["status"], "output": str(args.output.resolve()),
                      "cartons": len(plan["cartons_in_outer_insertion_order"]),
                      "group_templates": len(plan["templates"]), "seconds": plan["elapsed_seconds"]}))
