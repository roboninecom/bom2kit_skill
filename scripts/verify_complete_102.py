"""Refresh the independent SO-ARM-102 audit from prepared source-bound artifacts.

Run after assemble_102_complete.py has produced the final complete kit.
Use --recheck-motion to repeat every continuous insertion check as well.
Downloaded CAD and generated evidence remain in ignored directories.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bom2kit.bom import reconcile_bom
from bom2kit.mesh_motion import check_vertical_sequence
from bom2kit.mesh_validation import validate_mesh_layout
from bom2kit.report import fingerprint


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf8")


def same_rigid_group(source_problem, source_layout, final_problem, final_layout, unit_map=None):
    """Reject an internally rearranged or differently sourced final group."""
    unit_map = unit_map or {}
    final_poses = {p["unit_id"]: p for p in final_layout["placements"]}
    final_items = {i["id"]: i for i in final_problem["items"]}
    source_items = {i["id"]: i for i in source_problem["items"]}
    common = None
    for pose in source_layout["placements"]:
        target = final_poses[unit_map.get(pose["unit_id"], pose["unit_id"])]
        if source_items[pose["item_id"]]["mesh"]["sha256"] != final_items[target["item_id"]]["mesh"]["sha256"]:
            raise ValueError("Motion source differs from final mesh: " + pose["unit_id"])
        transform = np.asarray(target["transform"]) @ np.linalg.inv(np.asarray(pose["transform"]))
        rotation = transform[:3, :3]
        if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-7) or not np.isclose(np.linalg.det(rotation), 1, atol=1e-7):
            raise ValueError("Group mapping is not a proper rigid transform")
        if common is not None and not np.allclose(common, transform, atol=1e-7, rtol=0):
            raise ValueError("Final internal poses differ from motion evidence")
        common = transform
    return common.tolist()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recheck-motion", action="store_true")
    args = parser.parse_args()
    result = ROOT / "packaging-results/so-arm-102"
    folder = result / "complete-kit"
    problem, layout = read(folder / "input.json"), read(folder / "layout.json")
    mapping_path = ROOT / "packaging-inputs/benchmarks/so-arm-102-canonical-mapping.json"
    expected = read(mapping_path)["expected_bom"]
    coverage = reconcile_bom(expected, problem)
    geometry = validate_mesh_layout(problem, layout)
    assessment = read(folder / "assessment.json")
    if not coverage["complete"] or not geometry["valid"]:
        raise ValueError({"coverage": coverage, "geometry": geometry})
    for name, value in (("input", problem), ("layout", layout)):
        if assessment[name + "_sha256"] != fingerprint(value):
            raise ValueError("Stale complete-kit assessment: " + name)
    clamp = next(i for i in problem["items"] if i["id"] == "custom_106mm_clamp_proxy")
    if problem.get("custom_frame_length_mm") != 106 or clamp["mesh"]["sha256"] != (
            "854f9ef04e2b28fb09782abca7b97d384feaa805de71acb5393faff7d0187920"):
        raise ValueError("The restored custom 106 mm clamp source is required")
    group_transforms = {}
    final_items = {i["id"]: i for i in problem["items"]}
    for provenance in problem["provenance"]:
        for name in ("input", "layout"):
            if sha256(Path(provenance[name]).read_bytes()).hexdigest() != provenance[name + "_sha256"]:
                raise ValueError("Changed source group: " + provenance["group"])
        source_problem, source_layout = read(Path(provenance["input"])), read(Path(provenance["layout"]))
        expected_units = {a["unit_id"] for a in layout["placements"]
                          if final_items[a["item_id"]]["packing_group"] == provenance["group"]}
        if {a["unit_id"] for a in source_layout["placements"]} != expected_units:
            raise ValueError("Source group membership differs from final layout")
        group_transforms[provenance["group"]] = same_rigid_group(source_problem, source_layout, problem, layout)

    # Preserve the independently checked internal clamp coordinate frame.
    original = read(ROOT / "packaging-results/evidence-audit/purchased-assumptions/"
                    "clamp-custom106-four-y-assembly-motion.json")
    clamp_dir = folder / "internal-motion/custom-clamps"
    for name, key in (("input", "rotated_problem"), ("layout", "rotated_layout"),
                      ("motion-validation", "motion")):
        write(clamp_dir / (name + ".json"), original[key])

    sources = {
        "lower": (result / "lower-usb-fasteners", "input.json", "layout.json", "independent-grouped-motion.json"),
        "lower_base_internal": (folder / "internal-motion/lower-base-holder-cluster", "input.json", "layout.json", "motion-validation.json"),
        "lower_wrist_internal": (folder / "internal-motion/lower-wrist-clamp-pair", "input.json", "layout.json", "motion-validation.json"),
        "upper_clamps_servos": (result / "upper-clamps-servos", "input.json", "layout.json", "independent-grouped-motion.json"),
        "clamp_internal": (clamp_dir, "input.json", "layout.json", "motion-validation.json"),
        "upper_arms": (result / "current-four-arm-top", "input.json", "compact-65-layout.json", "independent-individual-motion.json"),
        "box7_individual": (result / "box7-independent-wrists", "input.json", "layout.json", "independent-motion-validation.json"),
        "complete_groups": (folder, "input.json", "layout.json", "independent-full-group-motion.json"),
    }
    evidence = {}
    for key, (base, pp, ll, cc) in sources.items():
        source_problem, source_layout = read(base / pp), read(base / ll)
        certificate = read(base / cc)
        if args.recheck_motion:
            groups = {step["group_id"]: step["unit_ids"] for step in certificate["packing_sequence"]
                      if len(step["unit_ids"]) > 1}
            certificate = check_vertical_sequence(source_problem, source_layout, groups=groups, time_limit=180)
            write(base / cc, certificate)
        if not certificate.get("valid"):
            raise ValueError("Invalid motion certificate: " + key)
        for name, value in (("input", source_problem), ("layout", source_layout)):
            if certificate.get(name + "_sha256") != fingerprint(value):
                raise ValueError("Stale motion certificate: " + key + " " + name)
        for item in source_problem["items"]:
            ref = item["mesh"]
            if sha256(Path(ref["path"]).read_bytes()).hexdigest() != ref["sha256"]:
                raise ValueError("Changed mesh in motion evidence: " + item["id"])
        if "source_input_sha256" in source_problem:
            if source_problem["source_input_sha256"] != fingerprint(problem) or source_problem["source_layout_sha256"] != fingerprint(layout):
                raise ValueError("Internal subassembly is bound to an older complete kit")
        same_rigid_group(source_problem, source_layout, problem, layout,
                         source_problem.get("source_unit_mapping"))
        evidence[key] = {"path": (base / cc).relative_to(ROOT).as_posix(),
                         "sha256": sha256((base / cc).read_bytes()).hexdigest()}

    binding = {"input_sha256": fingerprint(problem), "layout_sha256": fingerprint(layout)}
    audit = {**binding, "scope": "Independent current-BOM and static geometry audit",
             "expected_individual_quantity": sum(i["quantity"] for i in expected["components"]),
             "geometry_unit_count": geometry["placed_units"], "reconciliation": coverage,
             "geometry": geometry, "source_bom_mapping_sha256": sha256(mapping_path.read_bytes()).hexdigest(),
             "external_volume_l": assessment["external_volume_l"],
             "reference_external_volume_l": assessment["reference_external_volume_l"],
             "volume_no_worse": assessment["volume_no_worse"], "custom_frame_length_mm": 106,
             "assumptions": problem.get("assumptions", []), "physical_qualification": False}
    audit["source_group_rigid_transforms"] = group_transforms
    write(folder / "independent-audit.json", audit)
    write(ROOT / "packaging-inputs/benchmarks/so-arm-102-complete-reconciliation.json",
          {**binding, "bom": expected, "reconciliation": coverage,
           "source_mapping_sha256": sha256(mapping_path.read_bytes()).hexdigest()})
    write(folder / "independent-motion-readiness.json",
          {**binding, "complete_internal_motion_ready": True, "evidence": evidence,
           "scope": "Continuous insertion of final groups, with independently checked internal assembly sequences",
           "instructions": ["Preassemble the lower base cluster along its checked negative-Y sequence.",
                            "Preassemble the lower wrist/printed-clamp pair along its checked negative-X sequence.",
                            "Preassemble the custom clamps in their source coordinate frame before rotating the group.",
                            "Follow each subgroup certificate's packing_sequence, then the complete_groups sequence.",
                            "All 31 BOX7 parts insert individually; no interlocked wrist pair is used."],
           "limitations": ["Source geometry and declared packing envelopes only.",
                           "No hand access, support, bag seam, cushioning, tolerance or transport qualification."]})
    print(f"Verified {geometry['placed_units']} units and {audit['expected_individual_quantity']} BOM contents; motion evidence ready.")


if __name__ == "__main__":
    main()
