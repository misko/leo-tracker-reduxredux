import json

import format_budget


def test_actual_format_capacity_tables_and_saturation(tmp_path, monkeypatch):
    (tmp_path / "local").mkdir()
    monkeypatch.setattr(format_budget, "BASE", tmp_path)
    format_budget.main()
    result = json.loads((tmp_path / "local/format-budget.json").read_text())
    assert len(result["cases"]) == 72
    assert result["coded_table"] == [114, 228]
    assert result["linked_diagnostics"]["0x110080"] == "mac_ul_scheduler.c"
    assert all(c["result"] == 0 for c in result["cases"] if c["duration"] == 1)
