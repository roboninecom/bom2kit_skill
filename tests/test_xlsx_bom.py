import importlib.util
from pathlib import Path
from zipfile import ZipFile
import pytest

spec = importlib.util.spec_from_file_location("extract_xlsx_bom",Path(__file__).resolve().parents[1]/"scripts/extract_xlsx_bom.py")
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def source(tmp_path,quantity="3.0",formula=""):
    path = tmp_path/"bom.xlsx"
    with ZipFile(path,"w") as z:
        z.writestr("xl/workbook.xml",'<workbook xmlns="'+adapter.NS["s"]+'" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Parts" r:id="r1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",'<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml",'<worksheet xmlns="'+adapter.NS["s"]+'"><sheetData>'
                    '<row r="1"><c r="A1" t="inlineStr"><is><t>Name</t></is></c><c r="B1" t="inlineStr"><is><t>Quantity</t></is></c></row>'
                    '<row r="7"><c r="A7" t="inlineStr"><is><t>Motor 5V</t></is></c><c r="B7">'+formula+'<v>'+quantity+'</v></c></row>'
                    '</sheetData></worksheet>')
    return path


def test_reads_quantities_and_cell_evidence_without_modifying_workbook(tmp_path):
    path = source(tmp_path)
    original = path.read_bytes()
    result = adapter.extract(path)
    assert result["rows"][0]["quantity"] == 3
    assert result["rows"][0]["source_line"] == 7
    assert result["rows"][0]["source_cells"]["A7"] == "Motor 5V"
    assert path.read_bytes() == original


@pytest.mark.parametrize("quantity,formula",[("2.5",""),("0",""),("3","<f>1+2</f>")])
def test_rejects_fractional_zero_or_unevaluated_quantity(tmp_path,quantity,formula):
    with pytest.raises(ValueError):
        adapter.extract(source(tmp_path,quantity,formula))
