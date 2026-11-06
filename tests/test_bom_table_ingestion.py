import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("extract_bom_tables", Path(__file__).resolve().parents[1] / "scripts/extract_bom_tables.py")
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def test_repeated_names_retain_variant_and_optional_rows(tmp_path):
    source = tmp_path / "bom.md"
    source.write_text("# Servos\n| Item | Qty | Selection |\n|---|---|---|\n| Motor | 2 | 5V |\n| Motor | 4 | 12V |\n\n# Rods\n| Item | Size | Quantity |\n|---|---|---|\n| Steel | 6x125 | 2 |\n| Carbon alternative | 6x125 | 2 |\n")
    result = adapter.extract(source)
    assert len(result["rows"]) == 4
    assert result["nonalternative_table_quantity"] == 8
    assert result["rows"][0]["columns"][-1]["value"] == "5V"
    assert result["rows"][1]["columns"][-1]["value"] == "12V"
