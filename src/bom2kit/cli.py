"""Small command-line interface; CAD is imported only for STEP inspection."""

import argparse
import json
import math
from pathlib import Path
import sys


def _read(path):
    with Path(path).open(encoding="utf-8-sig") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def _positive_seconds(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Time limit must be finite and positive")
    return number


def parser():
    root = argparse.ArgumentParser(description="Traceable packing plans from measured envelopes")
    commands = root.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="Extract STEP or 3MF geometry evidence (STEP requires CAD extra)")
    inspect.add_argument("step", type=Path)
    inspect.add_argument("--output", type=Path)
    solve = commands.add_parser("solve", help="Search rectangular packing units and validate the result")
    solve.add_argument("input", type=Path)
    solve.add_argument("--output", type=Path, required=True)
    solve.add_argument("--time-limit", type=_positive_seconds, default=5.0)
    solve.add_argument("--seed", type=int, default=0)
    optimize = commands.add_parser("optimize", help="Search a container catalogue without exceeding reference volume")
    optimize.add_argument("input", type=Path)
    optimize.add_argument("--output", type=Path, required=True)
    optimize.add_argument("--time-limit", type=_positive_seconds, default=5.0)
    validate = commands.add_parser("validate", help="Independently check a layout against its input")
    validate.add_argument("input", type=Path)
    validate.add_argument("layout", type=Path)
    validate.add_argument("--output", type=Path)
    mesh_validate = commands.add_parser("mesh-validate", help="Validate fingerprinted static mesh poses (requires mesh extra)")
    mesh_validate.add_argument("input", type=Path)
    mesh_validate.add_argument("layout", type=Path)
    mesh_validate.add_argument("--output", type=Path)
    mesh_report = commands.add_parser("mesh-report", help="Render validated source triangle poses; requires mesh and report extras")
    mesh_report.add_argument("input", type=Path)
    mesh_report.add_argument("layout", type=Path)
    mesh_report.add_argument("--output", type=Path, required=True)
    mesh_pair = commands.add_parser("mesh-pair", help="Search two rigid meshes; requires mesh extra")
    mesh_pair.add_argument("input", type=Path)
    mesh_pair.add_argument("--output", type=Path, required=True)
    mesh_pair.add_argument("--time-limit", type=_positive_seconds, default=30.0)
    mesh_pair.add_argument("--pitch-mm", type=_positive_seconds, default=2.0)
    mesh_solve = commands.add_parser("mesh-solve", help="Bounded multi-part rigid mesh search; requires mesh extra")
    mesh_solve.add_argument("input", type=Path)
    mesh_solve.add_argument("--output", type=Path, required=True)
    mesh_solve.add_argument("--time-limit", type=_positive_seconds, default=300.0)
    mesh_solve.add_argument("--pitch-mm", type=_positive_seconds, default=2.0)
    mesh_solve.add_argument("--beam-width", type=int, default=8)
    mesh_solve.add_argument("--seed-layout", type=Path, help="Previously validated partial or complete recipe")
    reconcile = commands.add_parser("reconcile", help="Check declared SKU quantities and revisions independently of geometry")
    reconcile.add_argument("bom", type=Path)
    reconcile.add_argument("input", type=Path)
    reconcile.add_argument("--output", type=Path)
    report = commands.add_parser("report", help="Render illustrated HTML from canonical coordinates")
    report.add_argument("input", type=Path)
    report.add_argument("layout", type=Path)
    report.add_argument("--output", type=Path, required=True)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "inspect":
            if args.step.suffix.lower() == ".3mf":
                from .mesh_geometry import inspect_3mf

                result = inspect_3mf(args.step)
            else:
                from .geometry import inspect_step

                result = inspect_step(args.step)
            if args.output:
                _write(args.output, result)
            print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
            return 0

        from .validation import validate

        problem = _read(args.input)
        if args.command == "reconcile":
            from .bom import reconcile_bom

            result = reconcile_bom(_read(args.bom), problem)
            if args.output:
                _write(args.output, result)
            print(json.dumps(result, indent=2))
            return 0 if result['complete'] else 1
        if args.command == "mesh-pair":
            from .mesh_packing import solve_mesh_pair
            from .mesh_validation import validate_mesh_layout

            result = solve_mesh_pair(problem, time_limit=args.time_limit, pitch_mm=args.pitch_mm)
            validation = validate_mesh_layout(problem, result)
            _write(args.output / "input.json", problem)
            _write(args.output / "layout.json", result)
            _write(args.output / "validation.json", validation)
            print(json.dumps({'output': str(args.output.resolve()), 'valid': validation['valid']}))
            return 0 if validation['valid'] else 1
        if args.command == "mesh-solve":
            from .mesh_search import solve_mesh_kit
            from .mesh_validation import validate_mesh_layout

            seed = _read(args.seed_layout).get("placements") if args.seed_layout else None
            if args.seed_layout and not isinstance(seed, list):
                raise ValueError("Seed layout must contain a placements list")
            _write(args.output / "input.json", problem)
            _write(args.output / "validation.json", {"valid": False,
                   "errors": ["Search has not completed; previous results must not be reused."]})
            result = solve_mesh_kit(problem, time_limit=args.time_limit,
                                    pitch_mm=args.pitch_mm, beam_width=args.beam_width,
                                    seed_placements=seed, checkpoint_dir=args.output)
            validation = validate_mesh_layout(problem, result)
            _write(args.output / "layout.json", result)
            _write(args.output / "validation.json", validation)
            print(json.dumps({"output": str(args.output.resolve()), "valid": validation["valid"],
                              "status": result["status"]}))
            return 0 if validation["valid"] else 1
        if args.command in ("solve", "optimize"):
            if args.command == "optimize":
                from .optimization import optimize

                layout = optimize(problem, time_limit=args.time_limit)
                _write(args.output / "request.json", problem)
                if layout.get("status") == "feasible":
                    problem = {**problem, "container": layout["container"]}
            else:
                from .solver import solve

                layout = solve(problem, time_limit=args.time_limit, seed=args.seed)
            validation = validate(problem, layout)
            _write(args.output / "input.json", problem)
            _write(args.output / "layout.json", layout)
            _write(args.output / "validation.json", validation)
            print(json.dumps({"output": str(args.output.resolve()), "valid": validation["valid"]}))
            return 0 if validation["valid"] else 1

        layout = _read(args.layout)
        if args.command in ("mesh-validate", "mesh-report"):
            from .mesh_validation import validate_mesh_layout

            validation = validate_mesh_layout(problem, layout)
        else:
            validation = validate(problem, layout)
        if args.command in ("validate", "mesh-validate"):
            if args.output:
                _write(args.output, validation)
            print(json.dumps(validation, indent=2))
        elif args.command == "mesh-report":
            if not validation['valid']:
                print(json.dumps(validation, indent=2))
                return 1
            from .mesh_report import render_mesh_report

            print(render_mesh_report(problem, layout, args.output).resolve())
        elif args.command == "report":
            from .report import render_report

            path = render_report(problem, layout, validation, args.output)
            print(Path(path).resolve())
        return 0 if validation["valid"] else 1
    except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
        print(f"bom2kit: {error}", file=sys.stderr)
        return 2
