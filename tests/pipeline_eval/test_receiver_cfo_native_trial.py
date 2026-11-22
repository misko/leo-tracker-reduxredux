from importlib import import_module
from pathlib import Path

import pytest


@pytest.fixture
def trial(monkeypatch):
    reports = Path(__file__).resolve().parents[2] / "reports/ALGO08/single-core-2x"
    monkeypatch.syspath_prepend(str(reports))
    return import_module("receiver_cfo_native_trial")


def row(previous, measured, before_choice=(0, None, [0, 0]), after_choice=(0, None, [0, 0])):
    return dict(key="saved:one", receiver_id=1, arms={
        "packed": dict(factors=previous, continuation=before_choice),
        "restored": dict(factors=measured, continuation=after_choice),
    })


def test_reordering_preserves_rank_matched_fields(trial):
    factors = [(0, 2814, 0.125, 1050., .86, .09), (1, 7914, -0.25, -970., .7, .2)]
    result = trial.compare([row(factors, factors[::-1])], "packed", "restored")
    assert result["counts"]["rank_order_changed"] == 1
    assert result["counts"]["lanes_changed"] == 1
    assert result["counts"]["added_factors"] == result["counts"]["removed_factors"] == 0
    assert result["counts"]["signed_cfo_hz"] == 0
    assert result["changed_cfo"] == []


def test_removed_factor_and_signed_cfo_are_reported_independently(trial):
    old = [(0, 15, .25, -40., .9, 0.), (1, 42, 0., 20., .5, .1)]
    new = [(0, 16, 0., -39.5, .9, -0.)]
    result = trial.compare([row(old, new, after_choice=(0, None, [0]))], "packed", "restored")
    assert result["counts"]["removed_factors"] == 1
    assert result["counts"]["continuation_changed"] == 1
    assert result["counts"]["signed_cfo_hz"] == 1
    assert result["counts"]["control_score"] == 1
    assert result["maximum_absolute_delta"]["integer_epoch"] == 1
    assert result["maximum_absolute_delta"]["fractional_epoch"] == .25
    assert result["maximum_absolute_delta"]["control_score"] == 0.
    assert result["changed_cfo"][0]["delta_hz"] == .5
