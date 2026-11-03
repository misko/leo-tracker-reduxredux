import numpy as np
import pytest
from run_slope50 import build_variant, replace_once
from test_models import TinyData


def test_source_patch_fails_closed_on_missing_or_ambiguous_site():
    with pytest.raises(ValueError):
        replace_once("x x", "x", "y")
    with pytest.raises(ValueError):
        replace_once("z", "x", "y")


def test_track_slope_expansion_does_not_change_constant_model(tmp_path, monkeypatch):
    models, _ = build_variant(tmp_path)
    data = TinyData()
    arrays, numbers, initial, tracks = models._validate_data(data)
    context = models._Context(data, arrays, numbers, initial, tracks, float("inf"))
    monkeypatch.setattr(models, "fit_track_shared", lambda blocks, seed, slope: slope)
    assert models._track_evaluate(context, [0, 0], "linear") == 50
    assert models._track_evaluate(context, [0, 0], "constant") == 0
    assert "(10.0 / 3.0, 10.0)" in (tmp_path / "models.py").read_text()


def test_coherent_refinement_expands_actual_bounds_and_preserves_seed(tmp_path, monkeypatch):
    import scipy.optimize

    models, _ = build_variant(tmp_path)
    _, _, refinement = models._coherent_modules()
    data = TinyData()
    initial = data.initial.copy()
    initial[[3, 5]] = [30, -30]
    assignments = {
        "rows": np.array([0, 2, 3]),
        "satellites": np.array([0, 1, 2]),
        "weights": np.ones(3),
    }

    class Checked(Exception):
        pass

    def least_squares(function, start, bounds, **kwargs):
        np.testing.assert_array_equal(np.asarray(bounds[0])[[3, 5]], [-50, -50])
        np.testing.assert_array_equal(np.asarray(bounds[1])[[3, 5]], [50, 50])
        np.testing.assert_array_equal(start[[3, 5]], [30, -30])
        raise Checked

    monkeypatch.setattr(scipy.optimize, "least_squares", least_squares)
    with pytest.raises(Checked):
        refinement.fit_fixed(data, assignments, initial)


def test_glrt_profile_uses_expanded_slope_limit(tmp_path, monkeypatch):
    models, _ = build_variant(tmp_path)
    data = TinyData()
    arrays, numbers, initial, tracks = models._validate_data(data)
    context = models._Context(data, arrays, numbers, initial, tracks, float("inf"))
    limits = []

    def line_step(times, values, weights, line, limit):
        limits.append(limit)
        return line

    monkeypatch.setattr(models, "_line_step", line_step)
    prediction, visible = data.predict(initial)
    models._profile_receiver_glrt(context, prediction, visible, 16, 0, np.zeros(2))
    assert limits and set(limits) == {50}


def test_robust_variant_can_fit_slope_above_old_bound(tmp_path):
    from test_robust_weighted_drift import blocks

    _, robust = build_variant(tmp_path)
    data = blocks()
    for block in data:
        block["residual"] = (90000 + 20 * block["times"])[:, None]
    _, line = robust.fit_receiver(data, {index: 0 for index in range(len(data))})
    assert line[1] == pytest.approx(20, abs=0.01)
