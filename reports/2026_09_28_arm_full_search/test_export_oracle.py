import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "export_oracle", Path(__file__).with_name("export_oracle.py")
)
oracle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(oracle)


def row(edge, ordinal):
    return {"ordinal": ordinal, "rate_hz": 2_500_000, "target": {"edge": edge}}


def test_selection_is_metadata_ordered_and_bounded_to_one_case_per_edge():
    rows = [
        row("upper", 9),
        row("lower", 8),
        row("upper", 7),
        {"rate_hz": 5_000_000, "target": {"edge": "lower"}},
    ]
    selected = oracle.select_cases(rows)
    assert [(item["target"]["edge"], item["ordinal"]) for item in selected] == [
        ("lower", 8),
        ("upper", 9),
    ]


def test_all_rates_selection_uses_first_metadata_case_for_each_rate_and_edge():
    rows = [
        {"ordinal": 10, "rate_hz": 5_000_000, "target": {"edge": "upper"}},
        {"ordinal": 11, "rate_hz": 2_500_000, "target": {"edge": "upper"}},
        {"ordinal": 12, "rate_hz": 2_500_000, "target": {"edge": "lower"}},
        {"ordinal": 13, "rate_hz": 5_000_000, "target": {"edge": "lower"}},
        {"ordinal": 14, "rate_hz": 7_500_000, "target": {"edge": "lower"}},
        {"ordinal": 15, "rate_hz": 7_500_000, "target": {"edge": "upper"}},
        {"ordinal": 16, "rate_hz": 10_000_000, "target": {"edge": "lower"}},
        {"ordinal": 17, "rate_hz": 10_000_000, "target": {"edge": "upper"}},
        {"ordinal": 18, "rate_hz": 5_000_000, "target": {"edge": "upper"}},
    ]
    selected = oracle.select_cases(rows, all_rates=True)
    assert [item["ordinal"] for item in selected] == [12, 11, 13, 10, 14, 15, 16, 17]


def test_baseline_match_rejects_rank_epoch_and_numerical_drift():
    candidate = {"rank": 0, "refined_epoch_sample": 4, "absolute_cfo_hz": 2.0}
    final = {
        "residual_cfo_hz": 3.0,
        "tracking_cfo_hz": 5.0,
        "exact_score": 0.6,
        "control_score": 0.1,
        "margin": 0.5,
    }
    baseline = [
        {
            "candidate_rank": 0,
            "epoch_sample": 4,
            "acquired_cfo_hz": 2.0,
            "residual_cfo_hz": 3.0,
            "tracking_cfo_hz": 5.0,
            "exact_score": 0.6,
            "control_score": 0.1,
            "margin": 0.5,
        }
    ]
    oracle.assert_matches_baseline([candidate], [final], baseline)
    baseline[0]["margin"] = 0.5001
    with pytest.raises(ValueError, match="margin"):
        oracle.assert_matches_baseline([candidate], [final], baseline)
