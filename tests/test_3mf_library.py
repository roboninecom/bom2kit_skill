import importlib.util
from pathlib import Path

import pytest

trimesh = pytest.importorskip("trimesh")
pytest.importorskip("fcl")

spec = importlib.util.spec_from_file_location("prepare_3mf_library", Path(__file__).resolve().parents[1] / "scripts/prepare_3mf_library.py")
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def test_material_islands_attach_only_to_contacting_panel():
    panel = trimesh.creation.box([40,40,4])
    island = trimesh.creation.box([5,5,.05])
    island.apply_translation([0,0,2.025])
    separate = trimesh.creation.box([4,4,4])
    separate.apply_translation([50,0,0])
    assert adapter.contact_groups([panel,island,separate]) == [[0,1],[2]]


def test_small_gap_does_not_join_separate_printed_parts():
    a = trimesh.creation.box([4,4,4])
    b = a.copy()
    b.apply_translation([4.01,0,0])
    assert adapter.contact_groups([a,b]) == [[0],[1]]


def test_unknown_source_role_is_not_silently_counted(tmp_path, monkeypatch):
    monkeypatch.setattr(adapter, "inspect_3mf", lambda _: {"instances": [
        {"classification": "requires_review", "instance_id": "unknown"}]})
    with pytest.raises(ValueError, match="Unreviewed"):
        adapter.prepare([tmp_path / "source.3mf"], tmp_path / "out")
