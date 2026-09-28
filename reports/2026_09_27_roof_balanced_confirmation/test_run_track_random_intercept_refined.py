import numpy as np

import mixture_reception_core as core
import run_track_random_intercept_refined as runner


def fixture():
    track = core.TrackData(
        [-np.log(2)] * 2,
        np.array([[[1., -1.], [1., .5], [1., 1.]],
                  [[1., 1.], [1., -.5], [1., -1.]]]),
        [True, False, True],
        np.ones((2, 3, 1)), [.2, 0., -.1])
    layout = core.ParameterLayout(2, 1, [False, True], [False])
    return (track,), np.array([.1, -.3, .2, np.log(1.2)]), layout


def test_configuration_changes_only_integrator_and_orders():
    runner.configure_refined_quadrature()
    assert runner.original_experiment.random_core is runner.refined_core
    assert runner.original_experiment.FIT_ORDER == 64
    assert runner.original_experiment.VERIFY_ORDER == 128
    assert runner.original_experiment.GRID == (0., .25, .5, 1., 2., 4., 8.)


def test_refined_sigma_zero_reproduces_existing_core():
    runner.configure_refined_quadrature(); tracks, theta, layout = fixture()
    assert runner.original_experiment.sigma_zero_parity(tracks, theta, layout)["passed"]


def test_refined_selection_preserves_boundary_refinement(monkeypatch):
    runner.configure_refined_quadrature(); tracks, theta, layout = fixture()
    monkeypatch.setattr(runner.original_experiment, "score_tracks",
                        lambda _t, _x, _l, sigma, _o: {
                            "joint_nll_sum": sigma,
                            "candidate_detection_log_likelihood": []})
    selected = runner.original_experiment.select_sigma(tracks, theta, layout)
    assert selected["sigma"] == 0.
    assert selected["refinement"]["bounds"] == [0., .25]


def test_original_full_failure_is_bound_and_preserved():
    value, digest = runner.original_failure_receipt()
    assert value["all_numerically_accepted"] is False
    assert digest.startswith("sha256:")
