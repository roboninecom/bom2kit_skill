"""Complete a partial SO101 merged group with explicitly estimated electronics."""
from hashlib import sha256
import json
from pathlib import Path
import trimesh
from bom2kit.mesh_search import solve_mesh_kit

ROOT = Path(__file__).resolve().parents[1]


def main():
    base = ROOT / "packaging-results/so-arm-101/regrouped"
    out = ROOT / "packaging-results/so-arm-101/regrouped-complete"
    out.mkdir(parents=True, exist_ok=True)
    problem = json.loads((base / "input.json").read_text())
    packets_path = ROOT / "packaging-inputs/benchmarks/purchased-assumptions/101-box4.json"
    packets = json.loads(packets_path.read_text())["problem"]["items"]
    for item in packets:
        mesh = trimesh.creation.box(item["dimensions_mm"])
        target = out / (item["id"] + ".json")
        target.write_text(json.dumps({"units": "mm", "vertices_mm": mesh.vertices.tolist(),
                                     "triangles": mesh.faces.tolist()}))
        problem["items"].append({**item, "mesh": {"path": str(target),
            "sha256": sha256(target.read_bytes()).hexdigest()}, "geometry_evidence": "Estimated packed envelope, not measured CAD"})
    problem["scope"] = "All26 robot printed pieces plus declared BOX4 electronics packets; purchased dimensions are explicit assumptions"
    problem["purchased_assumptions_sha256"] = sha256(packets_path.read_bytes()).hexdigest()
    (out / "input.json").write_text(json.dumps(problem, indent=2))
    seed = json.loads((ROOT / "packaging-results/so-arm-101/regrouped-restart/checkpoint.json").read_text())["placements"]
    result = solve_mesh_kit(problem, time_limit=300, beam_width=8, pitch_mm=2,
                           seed_placements=seed, checkpoint_dir=out,
                           progress=lambda record: print(json.dumps(record), flush=True))
    (out / "result.json").write_text(json.dumps(result, indent=2))
    print(result["status"], flush=True)


if __name__ == "__main__":
    main()
