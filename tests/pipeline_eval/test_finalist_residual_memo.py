from importlib import import_module
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("finalist_residual_memo"), import_module("finalist_rejection_bound")


def test_memo_preserves_exact_vector_and_isolated_model(modules):
    memo, _ = modules
    first = memo.ResidualMemo(lambda point: np.array([np.signbit(point[0]), 3.]))
    refreshed = memo.ResidualMemo(lambda point: np.array([np.signbit(point[0]), 5.]))
    origin = np.array([0., 0.])
    first(origin)[1] = 100.
    cached = first(origin)
    assert cached.tolist() == [0., 3.]
    cached[1] = 200.
    assert first(origin).tolist() == [0., 3.]
    assert first(np.array([-0., 0.])).tolist() == [1., 3.]
    assert refreshed(origin).tolist() == [0., 5.]
    assert first.receipt()["hits"] == 2
    assert first.receipt()["misses"] == 2
    assert refreshed.receipt()["hits"] == 0


def test_memo_evicts_least_recently_used_and_bypasses_other_types(modules):
    memo, _ = modules
    calls = []

    def residual(point):
        calls.append(point.dtype)
        return point * 2

    cached = memo.ResidualMemo(residual, capacity=2)
    origin, near, far = (np.array([i, 0.]) for i in range(3))
    for point in (origin, near, origin, far, origin, near):
        assert np.array_equal(cached(point), point * 2)
    assert cached(origin.astype(np.float32)).dtype == np.float32
    assert len(calls) == 5
    receipt = cached.receipt()
    assert receipt["hits"] == receipt["evictions"] == 2
    assert receipt["misses"] == 4
    assert receipt["peak_residual_bytes"] == 2 * origin.nbytes


def test_oracle_prices_only_archived_rejects_and_same_coordinate_scores(modules):
    _, oracle = modules
    points = [[0., 0.], [.001, 0.], [0., .001], [1., 0.], [1., 0.], [.25, 0.]]
    scores = [100., 100.1, 100.1, 101., 101., 98.]
    history = [dict(parameters=points[index], score=scores[index]) for index in (0, 5)]
    trace = dict(result=dict(history=history, jacobian_refreshes=1, rejected_trials=2, evaluations=6, stopped="test"),
                 full_calls=[dict(point=point, score=score, cpu_ns=cpu) for cpu, (point, score) in enumerate(zip(points, scores))],
                 cpu_ns=30, proposals={})
    summary, _ = oracle.audit_phase(trace, 3.)
    assert summary["history"] == history
    assert summary["ideal_hindsight"]["all_rejected"]["cpu_ns"] == 7
    assert summary["ideal_hindsight"]["after_first_rejection"]["cpu_ns"] == 4
    assert summary["ideal_hindsight"]["terminal_run"]["calls"] == 0
    assert summary["same_phase_coordinate_reuse"] == dict(calls=1, cpu_ns=4)

    trace["full_calls"][4]["score"] = 102.
    summary, _ = oracle.audit_phase(trace, 3.)
    assert summary["same_phase_coordinate_reuse"]["calls"] == 0
    assert summary["same_phase_score_conflicts"]["calls"] == 1
    trace["full_calls"][4]["score"] = 99.
    with pytest.raises(ValueError, match="violates the strict full-score gate"):
        oracle.audit_phase(trace, 3.)
