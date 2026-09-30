import json

import sysinfo_format


def test_actual_sysinfo_decision_and_label_boundaries(tmp_path, monkeypatch):
    (tmp_path / "local").mkdir()
    monkeypatch.setattr(sysinfo_format, "BASE", tmp_path)
    sysinfo_format.main()
    rows = json.loads((tmp_path / "local/sysinfo-format.json").read_text())["cases"]
    labels = {(r["enable"], r["compared_value"]): r["diagnostic_label"] for r in rows}
    assert len(rows) == 1024
    assert labels[0, 255] == labels[1, 5] == "LONG"
    assert labels[1, 6] == labels[255, 255] == "SHORT"
