"""Height and receiver-prior controls must compose without shifting priors."""

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest
from test_dsx01_rf_clock_tool import problem_inputs

from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid


@pytest.fixture
def tool():
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        yield importlib.import_module("prototype_dsx01_receiver_geometry")
    finally:
        sys.path.remove(path)


def test_height_zero_recovers_original_and_nonzero_matches_dense_geometry(tool):
    scan, seed = problem_inputs()
    base = tool.AnchoredFamilies(scan, seed, "shared_phase", False, (0, 0))
    height = tool.HeightFamilies(scan, seed, "shared_phase", False, (0, 0), sigma=500)
    np.testing.assert_allclose(base.residual(base.initial), height.residual(height.initial)[:-1])
    x = height.initial.copy()
    x[-1] = 0.55
    assert height.decode(x)["altitude_m"] == pytest.approx(275)
    f, e = height.predicted(x)
    ff, ee = phase_frequency_grid(scan.sky, height.flat_times, *tool.CENTER, altitude_m=275)
    np.testing.assert_allclose(f, ff[height.flat_labels, np.arange(len(f))], atol=1e-8)
    np.testing.assert_allclose(e, ee[height.flat_labels, np.arange(len(e))], atol=1e-10)
    assert height.residual(x)[-1] == pytest.approx(0.55)


def test_receiver_prior_replaces_only_drift_coordinates_leaving_height_phase_priors(tool):
    scan, seed = problem_inputs()
    p = tool.geometry_problem(
        scan, seed, "shared_phase", True, (0, 0), mean_sigma=5, height_sigma=500
    )
    x = p.initial.copy()
    low, high, *_ = p.pairs[0]
    x[low], x[high], x[-1] = 1.0, 0.6, 0.8
    r = p.residual(x)
    native = p.problem.residual(p.native_parameters(x))
    start = len(r) - 1 - len(p.labels) - 4
    np.testing.assert_allclose(r[:start], native[:start])
    np.testing.assert_allclose(r[start : start + 4], [1, 0.6, 0, 0])
    np.testing.assert_allclose(r[start + 4 :], native[start + 4 :])
    assert r[-1] == pytest.approx(0.8)
    np.testing.assert_allclose(p.decode(x)["beta"][4:6] / 150, [4.7, 5.3])
    assert p.decode(x)["altitude_m"] == pytest.approx(400)


def test_phase_scaling_preserves_data_radio_and_height_priors(tool):
    phase_tool = importlib.import_module("prototype_dsx01_receiver_phase")
    scan, seed = problem_inputs()
    p = tool.geometry_problem(
        scan, seed, "shared_phase", True, (0, 0), mean_sigma=5, height_sigma=500
    )
    scaled = phase_tool.PhaseScaleProblem(p, factor=3)
    x = p.initial.copy()
    phase_k = next(k for k, (key, _) in enumerate(p.coordinates) if key[0] == "phases")
    x[phase_k] = 0.9
    x[-1] = 0.6
    expected = p.residual(x)
    expected[scaled.phase_slice] /= 3
    np.testing.assert_allclose(scaled.residual(x), expected)
    assert scaled.residual(x)[scaled.phase_slice][0] == pytest.approx(0.3)
    assert scaled.residual(x)[-1] == pytest.approx(0.6)
    np.testing.assert_array_equal(scaled.lower, p.lower)
    np.testing.assert_array_equal(scaled.upper, p.upper)


def test_frequency_report_uses_supplied_height_and_drift_factory(tool):
    reporter = importlib.import_module("report_dsx01_model_iterations")
    scan, seed = problem_inputs()
    p = tool.geometry_problem(
        scan, seed, "shared_phase", False, (0, 0), mean_sigma=10, height_sigma=500
    )
    x = p.initial.copy()
    x[-1] = 0.4
    fit = dict(
        rows=p.rows,
        state=p.decode(x),
        aliases=p.alias,
        east_north_km=[0, 0],
        fits=[dict(parameters=x, score=0)],
    )
    item = dict(fit=fit, method="shared_phase", arm="c0", experiment="receiver_geometry")
    calls = []

    def factory(*args):
        calls.append(args)
        return tool.geometry_problem(*args, mean_sigma=10, height_sigma=500)

    metrics = reporter.nominated_metrics(scan, item, problem_factory=factory)
    assert len(calls) == 1
    assert metrics["curved_points"] == 4 * 31
    assert len(metrics["tracks"]) == 4


def test_family_consensus_never_caps_receiver_calibration_prior(tool):
    family = importlib.import_module("prototype_dsx01_family_consensus")
    scan, seed = problem_inputs()
    scan.sky["phase_sigma_s"] = np.ones(1)
    base = family.ConsensusFamilies(
        scan, seed, "shared_phase", False, (0, 0), mode="consensus_floor"
    )
    p = tool.ReceiverDriftProblem(base, mean_sigma=10)
    x = p.initial.copy()
    x[p.pairs[0][0]] = 0.8
    r = p.residual(x)
    start = len(r) - len(p.labels) - 4
    np.testing.assert_allclose(r[start : start + 4], [0.8, 0, 0, 0])
