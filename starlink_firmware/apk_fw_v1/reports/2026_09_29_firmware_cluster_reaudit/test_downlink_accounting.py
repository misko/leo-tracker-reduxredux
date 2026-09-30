import json

import downlink_accounting


def test_actual_downlink_unit_crossings(tmp_path, monkeypatch):
    (tmp_path / "local").mkdir()
    monkeypatch.setattr(downlink_accounting, "BASE", tmp_path)
    downlink_accounting.main()
    result = json.loads((tmp_path / "local/downlink-accounting.json").read_text())
    cases = {(c["initial_bits"], c["added_bits"]): c for c in result["cases"]}
    assert len(cases) == 2112
    assert cases[0, 31]["added_symbols"] == 0
    assert cases[31, 1]["added_symbols"] == 114
    assert cases[31, 65]["added_symbols"] == 342
    assert len(result["caller_cases"]) == 384
    assert all(c["new_statistic"] == 65535 for c in result["caller_cases"]
               if c["old_statistic"] >= 65534)
    assert "GMH REPLENISH" in result["linked_diagnostic"]
