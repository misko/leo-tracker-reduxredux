import json

import pytest
from followup import ROOT, corrected_method


def test_direct_control_is_not_rerun():
    with pytest.raises(ValueError, match="corrected"):
        corrected_method("direct")


def test_followup_preserves_base_design():
    revision = json.loads((ROOT / "protocol-v2.json").read_text())
    base = json.loads((ROOT / revision["base_protocol"]).read_text())
    assert revision["models"] == ["gem", "block"]
    assert base["resources"]["fit_budget_s"] == 30
    assert len(base["sessions"]) * len(base["tolerances"]) * len(revision["models"]) == 12


def test_missing_followup_blocks_even_old_reference_report_read(tmp_path, monkeypatch):
    import evaluate_followup

    monkeypatch.setattr(evaluate_followup, "ROOT", tmp_path)
    (tmp_path / "protocol.json").write_text(json.dumps({
        "sessions": ["scan"], "tolerances": ["medium"],
    }))
    with pytest.raises(ValueError, match="all corrected"):
        evaluate_followup.evaluate()
