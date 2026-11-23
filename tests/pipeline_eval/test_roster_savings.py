import importlib
from pathlib import Path

import pytest


@pytest.fixture
def budget(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return importlib.import_module("roster_savings")


def test_gate_can_move_while_unsplit_case_keeps_its_full_time(budget):
    rows = [dict(modeled_s=8., v3_s=10., adjustable=True),
            dict(modeled_s=1., v3_s=1., adjustable=False),
            dict(modeled_s=7., v3_s=8., adjustable=True)]
    measured = budget.gate_savings(rows)
    assert measured["median_s"] == pytest.approx(3.)
    assert measured["summed_s"] == pytest.approx(3.25)
    assert budget.ratios(rows, 3.) == pytest.approx((.5, 10/19))


def test_unattainable_and_already_met(budget):
    fixed = [dict(modeled_s=10., v3_s=10., adjustable=False)]
    assert budget.gate_savings(fixed) == dict(median_s=None, summed_s=None)
    fast = [dict(modeled_s=4., v3_s=10., adjustable=True)]
    assert budget.gate_savings(fast) == dict(median_s=0., summed_s=0.)
