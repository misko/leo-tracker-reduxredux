from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

import pytest


@pytest.fixture
def research(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))


def test_profiled_fit_is_disabled_inside_the_original_grid_scope(research, monkeypatch):
    from leo.presentation import localization_v3
    import profiled_gamma_live as gamma

    scope = {}

    @contextmanager
    def profile(_port, _library, *, allowed, activity):
        scope["allowed"] = allowed
        scope["activity"] = activity
        yield dict(activated=1)

    simple_grid = lambda operation: operation()
    monkeypatch.setattr(localization_v3, "sample_position_grid", simple_grid)
    monkeypatch.setattr(gamma, "checked_library", lambda _: {"grid_posterior": "installed"})
    monkeypatch.setattr(gamma, "run_path", lambda _: {"profiled_gamma": profile})
    with gamma.outside_grid(object(), Path("not-read.so")) as receipt:
        allowed = scope["allowed"]
        assert allowed()
        assert not localization_v3.sample_position_grid(allowed)
        assert allowed()
        with pytest.raises(ValueError):
            localization_v3.sample_position_grid(lambda: int("invalid"))
        assert allowed()
    assert localization_v3.sample_position_grid is simple_grid
    assert receipt["provenance"]["grid_posterior"] == "installed"


def test_saved_option_forwarded_and_raw_option_rejected(research, monkeypatch, tmp_path):
    import full_short_run

    calls = []
    monkeypatch.setattr(full_short_run, "run", lambda args, **options: calls.append(options))
    monkeypatch.setattr(full_short_run, "write", lambda *_: None)
    argv = ["--recording", "recording", "--archive", "archive", "--region", "region", "--output", str(tmp_path)]
    saved = ["--saved", "example.json", "--saved-digest", "pin"]
    gate = ["--profiled-gamma-library", "gamma.so"]
    full_short_run.main(argv + saved)
    full_short_run.main(argv + saved + gate)
    assert "profiled_gamma_library" not in calls[0]
    assert calls[1]["profiled_gamma_library"] == Path("gamma.so")
    with pytest.raises(SystemExit):
        full_short_run.main(argv + ["--short-binary", "receiver.so"] + gate)


def test_grid_gate_checks_finite_coarse_objectives_and_minima_for_both_arms(research):
    from profiled_gamma_live_score import grid_comparison

    points = [dict(east_km=e, north_km=n, scores=dict(c0=float(i), fitted_c=float(3-i)))
              for i, (e, n) in enumerate([(-1., -1.), (-1., 1.), (1., -1.), (1., 1.)])]
    control = dict(grid=dict(points=points, complete=True, box_width_km=2., coarse_size=2))
    candidate = deepcopy(control)
    candidate["grid"]["points"][0]["scores"]["fitted_c"] += 7e-5
    qualified = grid_comparison(control, candidate)
    assert qualified["finite"] and qualified["same_coarse"] and qualified["score_gate"] and qualified["minimum_gate"]
    candidate["grid"]["points"][0]["scores"]["fitted_c"] += .002
    assert not grid_comparison(control, candidate)["score_gate"]
    candidate["grid"]["points"][0]["scores"]["fitted_c"] = None
    assert not grid_comparison(control, candidate)["finite"]


def test_posterior_gate_accepts_matched_curved_grid_without_predictive_export(research):
    from profiled_gamma_live_score import posterior_coverage

    control = dict(handoff=dict(arithmetic="permuted native posterior factor"), grid_kernel=dict(grid_calls=1))
    candidate = dict(deepcopy(control), gamma=dict(activity=dict(ordinary_grid_bypasses=286)))
    assert posterior_coverage(control, candidate)
    candidate["gamma"]["activity"].clear()
    assert not posterior_coverage(control, candidate)
    candidate["gamma"]["activity"]["ordinary_grid_bypasses"] = 286
    candidate["handoff"]["factor_calls"] = 1
    assert not posterior_coverage(control, candidate)
