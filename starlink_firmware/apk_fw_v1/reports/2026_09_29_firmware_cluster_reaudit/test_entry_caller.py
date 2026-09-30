import json

import entry_caller


def test_real_entry_caller_preserves_form_dependent_width(tmp_path, monkeypatch):
    (tmp_path / "local").mkdir()
    monkeypatch.setattr(entry_caller, "BASE", tmp_path)
    entry_caller.main()
    result = json.loads((tmp_path / "local/entry-caller.json").read_text())
    cases = result["cases"]
    assert len(cases) == 8
    assert {c["written_width"] for c in cases} == {16, 20}
    assert [c["packed"] >> 8 for c in cases if c["input_count"] == 256] == [0, 256]
    assert result["prefix_prologue_cases"] == [
        dict(input_form=i, prefix_form_register=i) for i in (0, 1)]
    assert result["coupling"]["prefix_configuration_base"] == (
        result["coupling"]["entry_configuration_base"])
