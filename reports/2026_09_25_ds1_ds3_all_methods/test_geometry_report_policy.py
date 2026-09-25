from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


def module():
    path = HERE / "geometry_report_policy.py"
    spec = importlib.util.spec_from_file_location("geometry_report_policy_test", path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def source():
    return {
        "results": [
            {"session_ids": ["scan-a", "scan-b", "scan-c"]},
            {"session_ids": ["scan-c", "scan-d", "scan-e"]},
        ]
    }


def test_bare_qualified_label_is_not_an_explicit_gate() -> None:
    m = module()
    projection = {
        "terminal_status": "qualified",
        "qualified": True,
        "reference_used_for_inference": False,
        "held_used_for_selection": False,
        "support": {
            "supported_tracks": 62,
            "unsupported_tracks": 14,
            "supported_occupied_second_fraction": 0.725,
        },
    }
    result = m.publication_metadata(projection, source())
    assert result["terminal_status"] == "geometry_position_diagnostic"
    assert result["ranking_eligible"] is False
    assert result["effective_scope"]["label"] == "DS3/geometry5"
    assert result["effective_scope"]["session_count"] == 5
    assert result["effective_scope"]["supported_tracks"] == 62


def test_explicit_gate_requires_all_criteria_and_truth_separation() -> None:
    m = module()
    projection = {
        "reference_used_for_inference": False,
        "held_used_for_selection": False,
        "qualification_gate": {
            "passed": True,
            "criteria": {"held_predictive": True, "interior": True},
        },
    }
    assert m.explicit_qualification_gate(projection) is True
    projection["qualification_gate"]["criteria"]["interior"] = False
    assert m.explicit_qualification_gate(projection) is False
    projection["qualification_gate"]["criteria"]["interior"] = True
    projection["reference_used_for_inference"] = True
    assert m.explicit_qualification_gate(projection) is False


def test_effective_scope_rejects_mismatched_reported_session_count() -> None:
    m = module()
    with pytest.raises(ValueError, match="session-count provenance mismatch"):
        m.effective_scope(
            {"support": {"geometry_valid_sessions": 4}},
            source(),
        )
