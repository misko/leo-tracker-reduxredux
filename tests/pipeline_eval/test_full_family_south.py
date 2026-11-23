from importlib import import_module
from pathlib import Path

import pytest


@pytest.fixture
def study(monkeypatch):
    directory = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
    monkeypatch.syspath_prepend(str(directory))
    return import_module("full_family_south_score")


def test_position_gate_covers_both_calibration_arms(study):
    fit = {arm: {"delta_error_km": 0.25} for arm in study.ARMS}
    assert study.passed({"status": "ok"}, fit, containing=True)
    fit["c0"]["delta_error_km"] = 0.251
    assert not study.passed({"status": "ok"}, fit, containing=True)


def test_missing_region_requires_explicit_corroborated_withholding(study):
    assert not study.passed({"status": "withheld", "reason": "repair_rejection_cap"}, {}, containing=False)
    assert study.passed({"status": "withheld", "reason": "both_receivers_support_far_exterior"}, {}, containing=False)


def test_paid_south_cannot_change_original_contrast_trial(study):
    run = import_module("full_family_amortized_trial").run
    with pytest.raises(ValueError, match="original full nominations"):
        run("south-containing", "contrast", None, paid_south=True)
    with pytest.raises(ValueError, match="southern offer"):
        run("DS30-0008", "control", None, paid_south=True)
