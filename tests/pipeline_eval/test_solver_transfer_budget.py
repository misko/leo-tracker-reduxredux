from importlib import import_module
from pathlib import Path

import pytest


@pytest.fixture
def model(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("solver_transfer_budget")


def test_interpolation_matches_anchors_and_extends_last_segment(model):
    anchors = [(0, 0), (2, 1.5), (10, 4)]
    assert [model.interpolate(x, anchors) for x in (0, 1, 2, 10, 18)] == [0, .75, 1.5, 4, 6.5]
    with pytest.raises(ValueError):
        model.interpolate(1, [(0, 0), (0, 1)])


def test_unsplit_failure_is_fully_charged_and_can_preclude_half_time(model):
    rows = [dict(stages=[10, 2, 1], compressed_MB=20), dict(stages=[0, 0, 30], compressed_MB=100)]
    anchors = [(0, 0), (2, 1)]
    assert model.ratios(rows, 10, 1, anchors) == pytest.approx(((5 / 13 + 1) / 2, 35 / 43))
    assert model.required_rates(rows, 1, anchors) == [None, None]


def test_authentic_dense_only_reproduction_and_medium_transfer_error(model):
    result = model.study()
    dense = result["stock_candidate_solve_cpu_s"]["DS30-0008"]
    medium = result["stock_candidate_solve_cpu_s"]["DS30-0057"]
    assert medium[1] - medium[0] * dense[1] / dense[0] > 3
    scenarios = result["panels_by_scenario"]
    assert max(scenarios["dense_only_graph_reuse"]["4"]["required_MB_s"]) == pytest.approx(282.986, abs=.001)
    assert scenarios["all_sizes_dense_graph_reuse"]["4"]["at_weak_rate"][0] > .5
