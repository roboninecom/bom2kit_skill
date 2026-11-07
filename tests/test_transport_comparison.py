"""A smaller carton must not hide reduced protection in a before/after report."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import pytest

scripts=Path(__file__).resolve().parents[1]/"scripts"
sys.path.insert(0,str(scripts))
spec=importlib.util.spec_from_file_location("transport_comparison",scripts/"compare_transport_designs.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def sample():
    return {"input":{"items":[{"id":"part","quantity":2,"mesh":{"sha256":"source"}}],
                     "container":{"wall_mm":[7]*3,"protection_mm":[15]*3,"reserved_top_mm":.8}},
            "logistics":{"policy":{"families":{"part":"printed"},"item_padding_mm":1,"clearance_mm":.2,
                                     "carton":{"inner_wall_mm":1.5,"gap_mm":.2,"dimension_increment_mm":1}}}}


@pytest.mark.parametrize("field",["item_padding_mm","clearance_mm","inner_wall_mm","gap_mm","dimension_increment_mm"])
def test_comparison_rejects_changed_allowances(field):
    before=sample();after=deepcopy(before);policy=after["logistics"]["policy"]
    target=policy if field in policy else policy["carton"]
    target[field]=0
    with pytest.raises(ValueError,match=field):module.check_comparable(before,after)


def test_comparison_allows_regrouping_but_not_changed_quantity():
    before=sample();after=deepcopy(before)
    after["logistics"]["policy"]["families"]["part"]="compatible-combined-family"
    module.check_comparable(before,after)
    after["input"]["items"][0]["quantity"]=1
    with pytest.raises(ValueError,match="quantities"):module.check_comparable(before,after)


def test_carton_sections_reveal_boxes_hidden_under_top_carton():
    import xml.etree.ElementTree as ET
    from render_transport_review import carton_layers_svg
    boxes=[{"position_mm":[15,15,15],"external_mm":[100,60,40]},
           {"position_mm":[15,75,15],"external_mm":[100,40,40]},
           {"position_mm":[15,15,55],"external_mm":[100,100,30]}]
    root=ET.fromstring(carton_layers_svg(boxes))
    labels=[e.text for e in root.iter('{http://www.w3.org/2000/svg}text')]
    assert labels==['Height 0–40 mm','1','2','Footprint 100 × 100 mm',
                    'Height 40–70 mm','3','Footprint 100 × 100 mm']
