import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def trial(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    import cold_finalist_race

    return cold_finalist_race


def test_paused_optimizer_returns_original_history(trial):
    from tools.pipeline_eval.variants.compact_cavity_optimizer import bounded_secant

    def residual(x):
        return np.array([3*x[0]**2 - 5*x[0] + 1, 2*x[1]**3 + x[1] - 1, .4*(x[0] + x[1])])

    lower, upper = np.full(2, -5.), np.full(2, 5.)
    original = bounded_secant(residual, np.zeros(2), lower, upper, iterations=trial.ITERATIONS)
    paused = trial.Pause(trial.stock_coroutine(bounded_secant), residual, lower, upper)
    prefix = paused.prefix()
    assert paused.done is None
    assert prefix["evaluations"] < original["evaluations"]
    assert prefix["drop"] > 0.
    continued = paused.finish()
    assert original.keys() == continued.keys()
    np.testing.assert_array_equal(original.pop("parameters"), continued.pop("parameters"))
    expected_history, got_history = original.pop("history"), continued.pop("history")
    assert original == continued
    for want, got in zip(expected_history, got_history, strict=True):
        np.testing.assert_array_equal(want["parameters"], got["parameters"])
        assert want["score"] == got["score"]
    assert paused.finish() is continued
    paused.close()


def test_natural_early_stop_has_no_recent_descent(trial):
    from tools.pipeline_eval.variants.compact_cavity_optimizer import bounded_secant

    lower, upper = np.full(2, -8.), np.full(2, 8.)
    paused = trial.Pause(trial.stock_coroutine(bounded_secant), lambda x: x, lower, upper)
    prefix = paused.prefix()
    assert prefix["score"] == 0.
    assert prefix["drop"] == 0.
    assert paused.done["evaluations"] == prefix["evaluations"]
    np.testing.assert_array_equal(paused.finish()["parameters"], np.zeros(2))


def test_reject_inactive_analysis_default(trial):
    from leo.analysis.research.continuous_curve_fit import bounded_gauss_newton

    with pytest.raises(ValueError, match="active installed nonlinear optimizer"):
        trial.stock_coroutine(bounded_gauss_newton)


def test_resume_preserves_endpoint_wrapper_and_restores_cell(trial):
    from tools.pipeline_eval.variants.algo08_endpoint_readout import measured_readout
    from tools.pipeline_eval.variants.compact_cavity_optimizer import bounded_secant

    port = SimpleNamespace(bounded_secant=bounded_secant)
    with measured_readout(port, reuse=True):
        position = SimpleNamespace(bounded_gauss_newton=port.bounded_secant)
        original, cell = trial.secant_port(position.bounded_gauss_newton)
        assert original is bounded_secant
        pause = SimpleNamespace(finish=lambda: {"parameters": np.zeros(2)})
        with trial.resume_port(position, cell, pause):
            assert position.bounded_gauss_newton is port.bounded_secant
            np.testing.assert_array_equal(position.bounded_gauss_newton(lambda x: x)["parameters"], np.zeros(2))
        assert cell.cell_contents is original


@pytest.mark.parametrize(("adjustment", "reason"), [
    (dict(), "winner_raced"),
    (dict(score=100.), "ambiguous_gap"),
    (dict(score=101.), "ambiguous_gap"),
    (dict(drop=4.), "ambiguous_gap"),
    (dict(parameters=[0., -9.501]), "near_region_face"),
    (dict(score=float("nan")), "invalid_prefix"),
    (dict(drop=-1.), "invalid_prefix"),
])
def test_frozen_gate(trial, adjustment, reason):
    prefix = [dict(score=114., parameters=[9.5, 0.], drop=1.),
              dict(score=100., parameters=[0., 0.], drop=1.),
              dict(score=116., parameters=[0., -9.5], drop=1.)]
    prefix[2].update(adjustment)
    leader, routing, gaps = trial.choose(prefix, 10.)
    assert routing == reason
    assert leader == (1 if reason == "winner_raced" else None)
    if leader is not None:
        assert gaps == [dict(other=1, gap=14., required=4.), dict(other=3, gap=16., required=4.)]


def test_incomplete_shortlist_cannot_prune(trial):
    assert trial.choose([], 10.) == (None, "not_three_finalists", [])


def test_invalid_prefix_receipt_can_be_written(trial):
    prefix = [dict(score=float("nan"), parameters=[5., float("inf")], drop=float("inf"))]
    trial.record_invalid_prefix(prefix)
    assert json.loads(json.dumps(prefix, allow_nan=False)) == [dict(score=None, parameters=[5., None], drop=None)]


def test_audit_overlap_requires_matching_norad_and_alias_for_each_track(trial):
    def node(pieces):
        rows = [dict(component=fragment, candidate_index=i, candidate_norad=norad)
                for i, (fragment, norad, _) in enumerate(pieces)]
        return dict(seed=dict(rows=rows), aliases=[alias for _, _, alias in pieces])

    first = node([(1, 7, 0), (2, 6, 0), (3, 1, -1), (4, 15, 1)])
    second = node([(10, 3, 0), (1, 7, 0), (2, 6, 1), (3, 8, -1)])
    assert trial.audit_overlap([first, second]) == [dict(ranks=[1, 2], left=4, right=4, shared_tracks=3,
                                                        same_norad=2, same_alias=2, same_assignment=1)]
