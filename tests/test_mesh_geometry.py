from zipfile import ZipFile

import pytest

from bom2kit.mesh_geometry import inspect_3mf, load_instance_mesh


NS = 'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06"'
MESH = '<mesh><vertices><vertex x="0" y="0" z="0"/><vertex x="2" y="0" z="0"/><vertex x="0" y="1" z="3"/></vertices><triangles><triangle v1="0" v2="1" v3="2"/></triangles></mesh>'


def write_archive(tmp_path, root, other=None, config=None):
    path = tmp_path / "sample.3mf"
    with ZipFile(path, "w") as archive:
        archive.writestr("3D/3dmodel.model", root)
        if other:
            archive.writestr("3D/Objects/a.model", other)
        if config:
            archive.writestr("Metadata/model_settings.config", config)
    return path


def test_components_units_build_transforms_and_metadata(tmp_path):
    root = f'''<model {NS} unit="centimeter"><resources>
      <object id="2"><components><component objectid="1" p:path="/3D/Objects/a.model" transform="0 1 0 -1 0 0 0 0 1 5 0 0"/></components></object>
      </resources><build><item objectid="2" transform="1 0 0 0 1 0 0 0 1 100 0 0"/><item objectid="2"/></build></model>'''
    other = f'<model {NS} unit="centimeter"><resources><object id="1">{MESH}</object></resources></model>'
    config = '<config><object id="2"><metadata key="name" value="assembly"/><part id="1" subtype="normal_part"><metadata key="name" value="part A"/></part></object></config>'
    path = write_archive(tmp_path, root, other, config)
    inventory = inspect_3mf(path)
    assert inventory["mesh_count"] == 1
    assert inventory["candidate_instance_count"] == 2
    instance = inventory["instances"][0]
    assert instance["name"] == "part A"
    assert instance["local_mesh"]["dimensions_mm"] == [20, 10, 30]
    assert instance["object_frame"]["bounds_mm"] == [[40, 0, 0], [50, 20, 30]]
    assert instance["printer_frame"]["bounds_mm"] == [[1040, 0, 0], [1050, 20, 30]]
    mesh = load_instance_mesh(path, instance["instance_id"])
    assert mesh["vertices_mm"][1] == [50, 20, 0]
    assert not inventory["packing_validated"]


def test_explicit_support_and_unknown_roles_do_not_become_bom(tmp_path):
    root = f'<model {NS}><resources><object id="1">{MESH}</object><object id="2">{MESH}</object></resources><build><item objectid="1"/><item objectid="2"/></build></model>'
    config = '<config><object id="1"><part id="1" subtype="support_blocker"/></object></config>'
    inventory = inspect_3mf(write_archive(tmp_path, root, config=config))
    assert [i["classification"] for i in inventory["instances"]] == ["excluded_nonpart", "requires_review"]
    assert inventory["candidate_instance_count"] == 0


def test_cyclic_component_rejected(tmp_path):
    root = f'<model {NS}><resources><object id="1"><components><component objectid="1"/></components></object></resources><build><item objectid="1"/></build></model>'
    with pytest.raises(ValueError, match="Cyclic"):
        inspect_3mf(write_archive(tmp_path, root))


def test_nested_transform_order(tmp_path):
    root = f'''<model {NS}><resources>
    <object id="1">{MESH}</object>
    <object id="2"><components><component objectid="1" transform="1 0 0 0 1 0 0 0 1 10 0 0"/></components></object>
    <object id="3"><components><component objectid="2" transform="0 1 0 -1 0 0 0 0 1 0 0 0"/></components></object>
    </resources><build><item objectid="3"/></build></model>'''
    instance = inspect_3mf(write_archive(tmp_path, root))["instances"][0]
    assert instance["object_frame"]["bounds_mm"] == [[-1, 10, 0], [0, 12, 3]]


def test_invalid_vertex_index_rejected(tmp_path):
    invalid_mesh = MESH.replace('v3="2"', 'v3="99"')
    root = f'<model {NS}><resources><object id="1">{invalid_mesh}</object></resources><build><item objectid="1"/></build></model>'
    with pytest.raises(ValueError, match="triangle index"):
        inspect_3mf(write_archive(tmp_path, root))
