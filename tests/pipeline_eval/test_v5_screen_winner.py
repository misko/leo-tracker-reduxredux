import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.variants import v5_screen_winner as receiver


@pytest.fixture
def bench(monkeypatch):
    visits = []

    class Model:
        labels = np.array([2, 0])

        def __init__(self, scan, node, sigma, fitted, *, reference):
            assert sigma == scan.radio_sigma_hz and not fitted
            self.reference = np.array(reference)
            self.node = node
            self.rows = [node["name"]]
            self.alias = [0]

        def state(self, xy):
            return {"phases": np.array([xy[0] + 0.25, 0.0, 17 + xy[0]])}

    def fit(model, start, *, iterations):
        assert iterations == 48
        epoch = int(start[0])
        visits.append((model.node["name"], epoch, model.reference.tolist()))
        return dict(
            parameters=np.array([epoch + 1.0, start[1] + 0.1]), score=model.node["scores"][epoch]
        )

    def refreshed(scan, sigma, node, arm, *, rounds, iterations):
        assert arm == "c0"
        ref, start, history = np.zeros(2), np.zeros(2), []
        for _ in range(rounds):
            p = Model(scan, node, sigma, False, reference=ref)
            result = fit(p, start, iterations=iterations)
            start = result["parameters"]
            phase = p.state(start)["phases"][p.labels]
            history.append({"posterior_phase_s": phase})
            ref = np.clip(phase, -15, 15)
        return p, result, history

    def actual_metrics(model, checkpoint, arm, xy):
        assert arm == "c0" and checkpoint["rows"] == model.rows
        assert np.array_equal(checkpoint["state"]["phases"], model.state(xy)["phases"])
        return {"xy": xy.tolist(), "loss": checkpoint["fits"][0]["score"]}

    parent = ModuleType("leo.analysis.localization_v3")
    parent.position = SimpleNamespace(NormalPosition=Model, fit=fit, refreshed=refreshed)
    parent.acceptance = ModuleType(parent.__name__ + ".acceptance")
    parent.acceptance.actual_metrics = actual_metrics
    monkeypatch.setitem(sys.modules, parent.__name__, parent)
    monkeypatch.setitem(sys.modules, parent.acceptance.__name__, parent.acceptance)
    monkeypatch.setitem(sys.modules, parent.__name__ + ".position", parent.position)
    return visits, SimpleNamespace(radio_sigma_hz=121)


def node(name, scores):
    return {"name": name, "scores": scores}


def test_winning_assignment_resumes_from_the_second_position_and_clipped_phase(bench):
    visits, scan = bench
    nodes = [node("a", [4, 3, 3, 3, 3]), node("b", [4, 1, 2, 2, 1]), node("c", [4, 2, 2, 2, 2])]
    metrics = {}
    (selected, n) = receiver.screen_nodes(scan, nodes, metrics)
    assert n == 3
    assert [i for name, i, _ in visits if name == "b"] == list(range(5))
    assert len(visits) == metrics["initial_phase_fits"] == 9
    assert visits[6] == ("b", 2, [15.0, 2.25])
    assert metrics["ranks"] == [0, 1, 2] and metrics["screen_c0_scores"] == [3, 1, 2]
    assert metrics["winning_rank"] == 1 and metrics["completed_c0_score"] == 1
    assert not metrics["fallback"]
    assert (selected, n) == receiver.v5_core.fit_initial_nodes(scan, nodes)


def test_ties_keep_first_and_crossing_trajectories_are_an_explicit_limit(bench):
    _, scan = bench
    nodes = [node("a", [8, 3, 3, 2, 2]), node("b", [8, 3, 2, 1, 0])]
    metrics = {}
    selected, _ = receiver.screen_nodes(scan, nodes, metrics)
    assert metrics["winning_rank"] == 0 and selected["choices"][0]["node"]["name"] == "a"
    full, _ = receiver.v5_core.fit_initial_nodes(scan, nodes)
    assert full["choices"][0]["node"]["name"] == "b"


def test_nonfinite_intermediate_score_replays_every_assignment_at_full_budget(bench):
    visits, scan = bench
    nodes = [node("a", [8, float("nan"), 1, 1, 1]), node("b", [8, 3, 2, 1, 0])]
    metrics = {}
    selected, _ = receiver.screen_nodes(scan, nodes, metrics)
    assert metrics["fallback"] and metrics["screen_c0_scores"] == [None, 3]
    assert metrics["winning_rank"] is None and selected["choices"][0]["node"] is nodes[1]
    assert len(visits) == metrics["initial_phase_fits"] == 14


def test_single_assignment_still_completes_five_fits_and_empty_list_fails(bench):
    visits, scan = bench
    metrics = {}
    receiver.screen_nodes(scan, [node("only", [5, 4, 3, 2, 1])], metrics)
    assert len(visits) == metrics["initial_phase_fits"] == 5
    with pytest.raises(ValueError, match="requires a ranked"):
        receiver.screen_nodes(scan, [], {})


def test_unknown_optimizer_fails_before_compilation(tmp_path):
    with pytest.raises(ValueError, match="unknown"):
        receiver.run({}, tmp_path, mode="unregistered")
    assert not list(tmp_path.iterdir())
