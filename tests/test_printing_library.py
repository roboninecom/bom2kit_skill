import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("prepare_printing_library", Path(__file__).resolve().parents[1] / "scripts/prepare_printing_library.py")
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def test_quantity_and_identity_come_from_table():
    rows = adapter.read_rows("| Part | Name | Qty |\n| P-12 | Body | 3 |\n| — | Handle | 1 |")
    assert [(r["source_stem"], r["quantity"]) for r in rows] == [("P-12 Body", 3), ("Handle", 1)]


def test_source_geometry_is_preserved_without_source_translation(tmp_path):
    trimesh = pytest.importorskip("trimesh")
    models = tmp_path / "models"
    models.mkdir()
    mesh = trimesh.creation.box([12, 23, 34])
    mesh.apply_translation([100, -80, 7])
    mesh.export(models / "P Body.stl")
    document = tmp_path / "bom.md"
    document.write_text("| P | Body | 2 |")
    result = adapter.prepare(document, models, tmp_path / "out")
    assert result["part_count"] == 2
    assert result["items"][0]["dimensions_mm"] == pytest.approx([12, 23, 34])
    assert result["all_meshes_valid_volumes"]
    (models / "variant").mkdir()
    mesh.export(models / "variant/P Body.stl")
    with pytest.raises(ValueError, match="found 2"):
        adapter.prepare(document, models, tmp_path / "other")
