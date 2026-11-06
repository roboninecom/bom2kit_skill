"""Complete the saved 27-unit search with an independently checked final cap."""
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bom2kit.mesh_validation import validate_mesh_layout


def main():
    source = ROOT / "packaging-results/so-arm-102/split-bottom-28"
    problem = json.loads((source / "problem.json").read_text())
    layout = json.loads((source / "checkpoint.json").read_text())
    expected = {f"{item['id']}#{n + 1}" for item in problem["items"] for n in range(item["quantity"])}
    if expected - {pose["unit_id"] for pose in layout["placements"]} != {"cap#2"}:
        raise ValueError("Expected the documented 27-unit checkpoint missing only cap#2")
    layout["placements"].append({"item_id": "cap", "unit_id": "cap#2",
                                  "transform": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 43.9], [0, 0, 0, 1]]})
    layout.pop("complete", None)
    layout["completion_method"] = "Final cap rigid candidate from 6 mm translation grid, independently revalidated"
    started = perf_counter()
    certificate = validate_mesh_layout(problem, layout)
    elapsed = perf_counter() - started
    output = ROOT / "packaging-results/so-arm-102/split-bottom-28-manual"
    output.mkdir(parents=True, exist_ok=True)
    for name, value in (("input", problem), ("layout", layout), ("validation", certificate)):
        (output / f"{name}.json").write_text(json.dumps(value, indent=2) + "\n")
    (output / "timing.json").write_text(json.dumps({"validation_seconds": elapsed}, indent=2))
    print(json.dumps({"valid": certificate["valid"], "errors": certificate["errors"], "validation_seconds": elapsed}))
    return 0 if certificate["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
