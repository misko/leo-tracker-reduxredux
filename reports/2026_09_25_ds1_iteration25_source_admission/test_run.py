from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def module():
    path = Path(__file__).with_name("run.py")
    spec = importlib.util.spec_from_file_location("i25_test", path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def score(held_rms: float, training_rms: float = 80.0):
    return {
        "equal_session_training_capped_loss": (training_rms / 800.0) ** 2,
        "equal_session_held_capped_loss": (held_rms / 800.0) ** 2,
        "session_scores": [
            {
                "session_id": "s",
                "occupied_second_weight": 2.0,
                "training_capped_loss": (training_rms / 800.0) ** 2,
                "held_capped_loss": (held_rms / 800.0) ** 2,
            }
        ],
        "track_scores": [
            {
                "track_id": "s:t",
                "session_id": "s",
                "source": "68739",
                "train_observations": 3,
                "held_observations": 2,
                "occupied_second_weight": 2.0,
                "training_rms_hz": training_rms,
                "held_rms_hz": held_rms,
            }
        ],
    }


def test_plan_seals_gate_before_evaluation() -> None:
    m = module()
    plan = m.verified_json(Path(__file__).with_name("plan.json"))
    gate = plan["predeclared_gate"]
    assert gate["per_group_superiority"].startswith("in each group")
    assert gate["session_breadth"].startswith("in each group at least four")
    assert gate["session_regression_guard"].endswith("0.05")
    assert plan["geographic_search_run"] is False
    assert plan["truth_used"] is False


def test_frozen_rates_enable_only_crossfit_passers() -> None:
    m = module()
    source_group = {
        "rate_schedule": [
            {"rate_bound_s_h": 0.25, "fit": {"rates_s_h": {"1": 0.1, "2": 0.2, "3": 0.3}}},
            {"rate_bound_s_h": 0.5, "fit": {"rates_s_h": {"1": 0.1, "2": 0.2, "3": 0.3}}},
            {"rate_bound_s_h": 1.0, "fit": {"rates_s_h": {"1": 0.11, "2": -0.22, "3": 0.33}}},
        ]
    }
    crossfit_group = {
        "sources": [
            {
                "source": "1",
                "support": {"eligible": True},
                "gate": {"passed": True},
                "iteration23_full_training_diagnostic_rate_s_h": 0.11,
            },
            {
                "source": "2",
                "support": {"eligible": True},
                "gate": {"passed": False},
                "iteration23_full_training_diagnostic_rate_s_h": -0.22,
            },
            {
                "source": "3",
                "support": {"eligible": False},
                "gate": {"passed": None},
                "iteration23_full_training_diagnostic_rate_s_h": 0.33,
            },
        ]
    }
    rates, enabled, zeroed = m.frozen_rates(crossfit_group, source_group)
    assert enabled == ["1"]
    assert zeroed == ["2", "3"]
    assert rates == {"1": 0.11, "2": 0.0, "3": 0.0}


def test_session_changes_reports_all_fixed_controls() -> None:
    m = module()
    candidate = score(80.0)
    changes = m.session_changes(
        candidate,
        {
            "zero_rate": score(100.0),
            "all_source_bound_0.25_s_h": score(90.0),
            "all_source_bound_1_s_h": score(70.0),
        },
    )
    assert len(changes) == 1
    assert changes[0]["candidate_minus_zero_rate_held"] < 0
    assert changes[0]["candidate_minus_all_source_bound_1_s_h_held"] > 0


def test_68739_zero_sensitivity_is_reconstructed_without_rescore() -> None:
    m = module()
    candidate = score(80.0, 40.0)
    zero = score(160.0, 80.0)
    result = m.source_zero_sensitivity(candidate, zero, "68739")
    assert result["track_count"] == 1
    assert result["method"].endswith("no additional HELD model score")
    assert result["source_zeroed_held_capped_loss"] == pytest.approx((160.0 / 800.0) ** 2)
    assert result["candidate_minus_source_zeroed_held"] < 0


def test_final_artifact_is_sealed_and_fixed() -> None:
    m = module()
    artifact = m.verified_json(Path(__file__).with_name("evaluation.json"))
    assert artifact["complete"] is True
    assert artifact["truth_used"] is False
    assert artifact["held_used_for_model_choice"] is False
    assert artifact["candidate_held_score_calls_per_group"] == 1
    assert artifact["geographic_search_run"] is False
    assert artifact["summary"]["enabled_source_count"] == 65
    assert artifact["summary"]["zero_source_count"] == 186
    assert artifact["summary"]["group_source_count"] == 251
    assert artifact["bindings"]["runner"] == m.digest(Path(__file__).with_name("run.py"))
