import importlib
from pathlib import Path

import pytest


@pytest.fixture
def budget(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return importlib.import_module("receiver_mask_budget")


def test_pool_prices_only_short_opportunities(budget):
    for lengths in ([0], [1, 1], [8, 16], [2, 5, 9], [6765]):
        exact = 2 * sum(n - (n + 7) // 8 for n in lengths)
        assert exact <= budget.short_calls_upper_bound(sum(lengths))
    assert budget.short_calls_upper_bound(16) == 28


def test_both_gates_include_unchanged_failed_case(budget):
    rows = [dict(modeled_s=8., v3_s=10., short_lanes=8, adjustable=True),
            dict(modeled_s=1., v3_s=1., short_lanes=9, adjustable=False)]
    assert budget.ratios(rows, .5, 1., 0.) == pytest.approx((.7, 5 / 11))
    assert budget.minimum_fraction(rows, 1., 0.) == pytest.approx(1.)
    assert budget.minimum_fraction(rows, 1., .1) is None
    assert budget.minimum_fraction(rows[:1], 1., 0.) == pytest.approx(3 / 8)
