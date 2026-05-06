import os
import time as time_mod
from pathlib import Path
import openpyxl
from data_sources.routing_excel import find_latest_routing_file, load_latest_routing


def _make_xlsx(path: Path, sheet: str, rows: list):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    for row in rows:
        ws.append(row)
    wb.save(str(path))


def test_find_latest_returns_newest_xlsx(tmp_path):
    f1 = tmp_path / "old.xlsx"
    f2 = tmp_path / "new.xlsx"
    _make_xlsx(f1, "Articles and phases", [["Article", "ASM"]])
    time_mod.sleep(0.05)
    _make_xlsx(f2, "Articles and phases", [["Article", "ASM"]])
    assert find_latest_routing_file(str(tmp_path)) == str(f2)


def test_find_latest_ignores_temp_files(tmp_path):
    f1 = tmp_path / "good.xlsx"
    f2 = tmp_path / "~$lock.xlsx"
    _make_xlsx(f1, "S", [["A"]])
    f2.write_bytes(b"")
    assert find_latest_routing_file(str(tmp_path)) == str(f1)


def test_find_latest_returns_none_for_empty_dir(tmp_path):
    assert find_latest_routing_file(str(tmp_path)) is None


def test_load_routing_parses_cycles(tmp_path):
    f = tmp_path / "r.xlsx"
    _make_xlsx(f, "Articles and phases", [
        ["Article", "ASSEMBLY", "COATING", "EOLTEST"],
        ["P1",      "x",        2.5,        8.18],
        ["P2",      14.35,      "x",        "x"],
    ])
    cycles, src, _mtime = load_latest_routing(str(tmp_path), "Articles and phases")
    assert cycles[("P1", "COATING")] == 2.5
    assert cycles[("P1", "EOLTEST")] == 8.18
    assert cycles[("P2", "ASSEMBLY")] == 14.35
    # 'x' cells must NOT be in the dict
    assert ("P1", "ASSEMBLY") not in cycles
    assert ("P2", "COATING") not in cycles
    assert src.endswith("r.xlsx")


def test_load_routing_skips_non_numeric_with_warning(tmp_path, caplog):
    import logging
    f = tmp_path / "r.xlsx"
    _make_xlsx(f, "Articles and phases", [
        ["Article", "ASSEMBLY"],
        ["P1",      "garbage"],
    ])
    with caplog.at_level(logging.WARNING):
        cycles, _src, _mtime = load_latest_routing(str(tmp_path), "Articles and phases")
    assert cycles == {}
    assert any("non-numeric" in r.message.lower() for r in caplog.records)


def test_load_routing_missing_folder_returns_empty(tmp_path):
    cycles, src, mtime = load_latest_routing(str(tmp_path / "nope"), "Articles and phases")
    assert cycles == {}
    assert src == ""
    assert mtime is None
