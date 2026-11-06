"""Try moving the unchanged USB packet out of BOX6 for custom clamps."""
import json
from pathlib import Path
from bom2kit.mesh_search import solve_mesh_kit

base = Path("packaging-results/so-arm-101")
problem = json.loads((base / "regrouped-without-camera/problem.json").read_text())
seed = json.loads((base / "regrouped-without-camera/layout.json").read_text())["placements"]
power = json.loads((base / "box6-folded-packets/input.json").read_text())
problem["items"].append(next(item for item in power["items"] if item["id"] == "USB_packet"))
problem["packing_assumption"] = "Unchanged USB packet 110 x 60 x 20 mm moves into the printed group; custom clamps may occupy BOX6."
output = base / "lower-with-usb"
output.mkdir(exist_ok=True)
(output / "input.json").write_text(json.dumps(problem, indent=2))
result = solve_mesh_kit(problem, seed_placements=seed, time_limit=180, beam_width=8,
                        pitch_mm=2, positions_per_rotation=32, voxel_overlap_cells=200,
                        checkpoint_dir=output, progress=lambda e: print(json.dumps(e), flush=True))
(output / "layout.json").write_text(json.dumps(result, indent=2))
print(json.dumps({"status": result["status"], "count": len(result["placements"]),
                  "validation": result["validation"]}), flush=True)
