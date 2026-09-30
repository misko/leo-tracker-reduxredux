import json

import parser_gate


def test_real_parser_gate_execution(tmp_path, monkeypatch):
    (tmp_path / "local").mkdir()
    monkeypatch.setattr(parser_gate, "BASE", tmp_path)
    parser_gate.main()
    result = json.loads((tmp_path / "local/parser-gate.json").read_text())
    cases = result["cases"]
    assert len(cases) == 72
    assert sum(c["branch"] == "table" and not c["long_form"] for c in cases) == 6
    assert all(c["branch"] == "no_entry" for c in cases if c["count"] == 0)
