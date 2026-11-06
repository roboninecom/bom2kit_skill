"""Read one XLSX BOM table without changing the source or evaluating formulas."""
import argparse
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import posixpath
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile

NS = {"s":"http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def extract(path, sheet_name=None):
    path = Path(path).resolve()
    raw = path.read_bytes()
    with ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheets = workbook.findall("s:sheets/s:sheet",NS)
        selected = [s for s in sheets if sheet_name is None or s.get("name")==sheet_name]
        if len(selected) != 1:
            raise ValueError("Select exactly one source worksheet")
        sheet = selected[0]
        rel_id = sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relation = next(r for r in relations if r.get("Id")==rel_id)
        if relation.get("TargetMode")=="External":
            raise ValueError("External worksheet unsupported")
        target = relation.get("Target")
        target = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/"+target)
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ["".join(si.itertext()) for si in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall("s:si",NS)]
        table = ET.fromstring(archive.read(target))
        rows, headers, quantity_column, name_column = [], None, None, None
        for row in table.findall("s:sheetData/s:row",NS):
            cells, formulas = {}, {}
            for cell in row:
                address = cell.get("r")
                column = re.fullmatch(r"([A-Z]+)[0-9]+",address).group(1)
                value = cell.find("s:v",NS)
                text = value.text if value is not None else ""
                if cell.get("t")=="s":
                    text = strings[int(text)]
                elif cell.get("t")=="inlineStr":
                    text = "".join(cell.find("s:is",NS).itertext())
                if text:
                    cells[column] = text.strip()
                if cell.find("s:f",NS) is not None:
                    formulas[column] = cell.find("s:f",NS).text
            qty = [c for c,v in cells.items() if v.casefold() in ("qty","quantity")]
            if qty:
                names = [c for c,v in cells.items() if v.casefold() in ("name","item","part")]
                if headers is not None or len(qty)!=1 or len(names)!=1:
                    raise ValueError("Ambiguous BOM header")
                headers,quantity_column,name_column = cells,qty[0],names[0]
                continue
            if headers is None or not cells:
                continue
            if quantity_column in formulas:
                raise ValueError("Formula quantities require independently evaluated source values")
            value = cells.get(quantity_column,"")
            if not value:
                if cells.get(name_column):
                    raise ValueError("Named BOM row has no quantity")
                continue
            try:
                count = Decimal(value)
                if not count.is_finite() or count<=0 or count!=count.to_integral_value():
                    raise ValueError("Positive integer BOM quantity required")
            except InvalidOperation as error:
                raise ValueError("Invalid BOM quantity") from error
            if not cells.get(name_column):
                raise ValueError("Quantity has no item name")
            index = int(row.get("r"))
            rows.append({"source_line":index,"source_sheet":sheet.get("name"),
                         "source_cells":{c+str(index):v for c,v in cells.items()},
                         "item":cells[name_column],"quantity":int(count),
                         "columns":[{"name":name,"value":cells.get(c,"")} for c,name in headers.items()],
                         "optional_alternative":any("alternative" in v.casefold() for v in cells.values())})
    if not rows:
        raise ValueError("No BOM rows found")
    return {"source":str(path),"source_sha256":sha256(raw).hexdigest(),"rows":rows,
            "nonalternative_table_quantity":sum(r["quantity"] for r in rows if not r["optional_alternative"]),
            "scope":"Source table only; sets, packaging and shipping additions require explicit reconciliation"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path)
    parser.add_argument("--sheet")
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    result = extract(args.source,args.sheet)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding="utf8")
    print(json.dumps({"rows":len(result["rows"]),"declared_quantity":result["nonalternative_table_quantity"]}))
