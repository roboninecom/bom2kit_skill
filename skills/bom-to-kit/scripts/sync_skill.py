"""Copy the authoritative skill into both repository-local discovery paths."""

from pathlib import Path
import shutil


def main() -> None:
    source = Path(__file__).resolve().parents[1]
    root = source.parents[1]
    for agent in (".agents", ".claude"):
        destination = root / agent / "skills" / "bom-to-kit"
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / "SKILL.md", destination / "SKILL.md")
        print(destination / "SKILL.md")


if __name__ == "__main__":
    main()
