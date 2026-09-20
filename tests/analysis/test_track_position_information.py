"""Track information uses fitting measurements and exposes timing degeneracy."""

import importlib.util
from pathlib import Path

import numpy as np


def test_track_geometry_ignores_evaluation_values_and_clock_cannot_add_information(monkeypatch):
    root = Path(__file__).resolve().parents[2] / "tools"
    monkeypatch.syspath_prepend(str(root))
    spec = importlib.util.spec_from_file_location(
        "track_information", root / "study_track_position_information.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    t = np.linspace(-30, 30, 60)
    a = t * 7.5 / 6900

    def states(shift):
        angle = a + shift * 7.5 / 6900
        p = 6900 * np.column_stack([np.cos(angle), np.sin(angle), np.full(60, 0.05)])
        v = 7.5 * np.column_stack([-np.sin(angle), np.cos(angle), np.zeros(60)])
        return p, v

    p, v = states(0)
    data = dict(
        y=t * 30,
        p=p,
        v=v,
        training=np.arange(60) % 5 < 3,
        segment=np.zeros(60, int),
        session=np.zeros(60, int),
        norad=np.ones(60, int),
        time=t,
    )
    for shift in [-0.5, 0.5]:
        data["p" + str(shift)], data["v" + str(shift)] = states(shift)
    first, matrices = module.analyse(data, 1, 1)
    data["y"][~data["training"]] += 1e9
    second, again = module.analyse(data, 1, 1)
    assert first == second
    np.testing.assert_array_equal(matrices, again)
    fixed = first["fixed_clock"]["horizontal_rms_m"]
    free = first["free_shared_clock"]["horizontal_rms_m"]
    assert fixed is not None
    assert free is None or free >= fixed
    # The cumulative shared-clock information must equal direct projection.
    normal = matrices.sum(axis=0)
    marginal = normal[:2, :2] - np.outer(normal[:2, 2], normal[2, :2]) / normal[2, 2]
    if free is not None:
        # Compare information, not an unstable inverse for this nearly degenerate single pass.
        direct = np.linalg.inv(np.array(first["free_shared_clock"]["covariance_m2"]) / 1e6)
        np.testing.assert_allclose(marginal, direct, rtol=1e-8, atol=1e-10)


def test_subset_fits_gate_and_rank_using_fitting_diagnostics(monkeypatch):
    root = Path(__file__).resolve().parents[2] / "tools"
    monkeypatch.syspath_prepend(str(root))
    import compare_positioning_cohorts
    import study_track_position_information as module

    masks = []

    def fake_fit(data, region, initial, weighting, robust, subset, fit_clock):
        masks.append(np.flatnonzero(subset).tolist())
        assert fit_clock
        return {}

    monkeypatch.setattr(compare_positioning_cohorts, "fit", fake_fit)
    data = dict(p=np.zeros((5, 3)), segment=np.arange(5))
    rows = [
        dict(
            segment=i,
            span_s=20,
            training_rms_hz=rms,
            information_eigenvalues_per_km2=[i + 1, i + 2],
            curvature_rms_hz=5 - i,
        )
        for i, rms in enumerate([20, 30, 40, 101, 50])
    ]
    rows[4]["span_s"] = 14
    result = module.refit_subsets(
        data,
        dict(tracks=rows),
        dict(region=dict(latitude_deg=40, longitude_deg=-100, width_km=5000, height_km=5000)),
        [0, 0],
    )
    assert result["eligible_segments"] == 3
    assert masks == [[0, 1, 2]] * 4
    assert result["models"][0]["segments"] == [2, 1, 0]
    assert result["models"][2]["segments"] == [0, 1, 2]
