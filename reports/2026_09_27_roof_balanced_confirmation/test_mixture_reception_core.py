import importlib.util
import math
from pathlib import Path
import sys

import numpy as np
import pytest


PATH = Path(__file__).with_name("mixture_reception_core.py")
SPEC = importlib.util.spec_from_file_location("mixture_reception_core", PATH)
CORE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = CORE
SPEC.loader.exec_module(CORE)


LAYOUT = CORE.ParameterLayout(2, 2, [False, True], [False, True])


def track(log_weights=(-math.log(2), -math.log(2))):
    detection = np.array([
        [[1., -1.], [1., -.5], [1., .2]],
        [[1., 1.], [1., .5], [1., -.2]],
    ])
    ratio = np.array([
        [[1., -1.], [1., -.5], [1., .2]],
        [[1., 1.], [1., .5], [1., -.2]],
    ])
    return CORE.TrackData(log_weights, detection, [True, False, True], ratio,
                          [.2, 999., -.1])


def assert_result_close(left, right, absolute=1e-10):
    assert left[0] == pytest.approx(right[0], abs=absolute)
    assert np.asarray(left[1]) == pytest.approx(np.asarray(right[1]), abs=absolute)


def test_analytic_gradient_matches_central_difference():
    theta = np.array([.2, -.4, .1, .3, math.log(.7)])
    analytic = CORE.objective_gradient(theta, [track()], LAYOUT)[1]
    numeric = CORE.finite_difference_gradient(theta, [track()], LAYOUT)
    assert analytic == pytest.approx(numeric, abs=2e-7)


def test_candidate_permutation_and_identical_component_split_invariance():
    original = track((-math.log(3), math.log(2 / 3)))
    theta = np.array([.2, -.4, .1, .3, math.log(.7)])
    first = CORE.objective_gradient(theta, [original], LAYOUT)
    permuted = CORE.TrackData(
        np.asarray(original.log_weights)[::-1],
        np.asarray(original.detection_design)[::-1], original.matched,
        np.asarray(original.ratio_design)[::-1], original.log_ratio)
    assert_result_close(CORE.objective_gradient(theta, [permuted], LAYOUT), first)
    # Split candidate zero into two identical components with half its mass.
    split = CORE.TrackData(
        [original.log_weights[0] - math.log(2),
         original.log_weights[0] - math.log(2), original.log_weights[1]],
        np.asarray(original.detection_design)[[0, 0, 1]], original.matched,
        np.asarray(original.ratio_design)[[0, 0, 1]], original.log_ratio)
    assert_result_close(CORE.objective_gradient(theta, [split], LAYOUT), first)


def test_one_hot_identity_equals_single_candidate():
    theta = np.array([.1, -.2, .3, .4, math.log(1.2)])
    source = track((0., -1000.))
    single = CORE.TrackData([0.], np.asarray(source.detection_design)[:1],
                            source.matched, np.asarray(source.ratio_design)[:1],
                            source.log_ratio)
    assert_result_close(CORE.objective_gradient(theta, [source], LAYOUT),
                        CORE.objective_gradient(theta, [single], LAYOUT))


def test_candidate_free_same_objective_oracle_and_invalid_non_m0():
    source = track()
    invariant = CORE.TrackData(
        source.log_weights,
        np.repeat(np.asarray(source.detection_design)[:1], 2, axis=0),
        source.matched,
        np.repeat(np.asarray(source.ratio_design)[:1], 2, axis=0),
        source.log_ratio)
    theta = np.array([.1, -.2, .3, .4, math.log(1.2)])
    assert_result_close(CORE.objective_gradient(theta, [invariant], LAYOUT),
                        CORE.candidate_free_objective_gradient(theta, [invariant], LAYOUT))
    with pytest.raises(ValueError, match="invariant"):
        CORE.candidate_free_objective_gradient(theta, [source], LAYOUT)


def test_candidate_free_oracle_does_not_call_mixture_objective(monkeypatch):
    source = track()
    invariant = CORE.TrackData(
        source.log_weights,
        np.repeat(np.asarray(source.detection_design)[:1], 2, axis=0),
        source.matched,
        np.repeat(np.asarray(source.ratio_design)[:1], 2, axis=0),
        source.log_ratio)
    monkeypatch.setattr(CORE, "objective_gradient", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("mixture objective called")))
    value, gradient = CORE.candidate_free_objective_gradient(
        np.array([.1, -.2, .3, .4, math.log(1.2)]), [invariant], LAYOUT)
    assert math.isfinite(value) and np.all(np.isfinite(gradient))


def test_shared_identity_differs_from_row_redrawn_identity():
    # Detection rows favor opposite candidates. Shared identity must compromise;
    # redrawing identity per row can select the favorable candidate twice.
    design = np.array([[[1., 6.], [1., -6.]], [[1., -6.], [1., 6.]]])
    source = CORE.TrackData([-math.log(2)] * 2, design, [True, True],
                            np.ones((2, 2, 1)), [0., 0.])
    layout = CORE.ParameterLayout(2, 1, [False, False], [False])
    theta = np.array([0., 1., 0., math.log(100.)])
    shared = CORE.objective_gradient(theta, [source], layout, ridge=0.)[0]
    logits = design @ theta[:2]
    per_candidate = logits - np.logaddexp(0., logits)
    redrawn_detection = -sum(CORE._logsumexp(
        np.array([-math.log(2), -math.log(2)]) + per_candidate[:, i])
        for i in range(2)) / 2
    # Ratio is common to both identities; subtract its common normalized term.
    ratio_common = (-.5 * math.log(2 * math.pi * 100**2))
    assert shared - ratio_common > redrawn_detection


def test_all_row_denominator_halves_one_matched_ratio_contribution():
    design_d = np.ones((1, 2, 1)); design_r = np.ones((1, 2, 1))
    two = CORE.TrackData([0.], design_d, [True, False], design_r, [2., 0.])
    one = CORE.TrackData([0.], design_d[:, :1], [True], design_r[:, :1], [2.])
    layout = CORE.ParameterLayout(1, 1, [False], [False])
    theta = np.array([0., 0., 0.])
    _, _, detail_two = CORE.objective_gradient(theta, [two], layout, 0., return_details=True)
    _, _, detail_one = CORE.objective_gradient(theta, [one], layout, 0., return_details=True)
    # Remove detection contributions, leaving the normalized ratio log density.
    ratio_logpdf = -.5 * (math.log(2 * math.pi) + 4.)
    assert detail_two[0]["negative_log_likelihood"] == pytest.approx(
        math.log(2) - ratio_logpdf / 2)
    assert detail_one[0]["negative_log_likelihood"] == pytest.approx(
        math.log(2) - ratio_logpdf)


def test_score_components_sum_under_one_shared_identity_marginal():
    theta = np.array([.2, -.4, .1, .3, math.log(.7)])
    score = CORE.score_tracks(theta, [track()], LAYOUT)[0]
    assert score["joint_nll"] == pytest.approx(
        score["detection_marginal_nll"] +
        score["conditional_ratio_increment_nll"])
    objective = CORE.objective_gradient(theta, [track()], LAYOUT, ridge=0.)[0]
    assert score["joint_nll"] == pytest.approx(objective)


def test_multistart_reports_gradient_stability_and_curvature():
    # A small well-conditioned fixture with ridge on both slopes.
    result = CORE.optimize_multistart(
        [track()], LAYOUT, starts=[np.zeros(5), np.full(5, .05)],
        gradient_tolerance=2e-5, stability_tolerance=1e-6)
    assert len(result["runs"]) == 2
    assert math.isfinite(result["objective"])
    assert result["objective_range"] >= 0
    assert result["objective_per_track_range"] == result["objective_range"]
    assert set(result["curvature"]) >= {
        "minimum_eigenvalue", "near_zero_or_negative_eigenvalues", "identifiable"}
    assert "stable_predictions" in result
    assert set(result["failure_reasons"]) == {
        "numerical_inconclusive", "identifiability_concerns"}


def test_objective_stability_uses_total_not_per_track_spread():
    # Total spread 1.5e-7 fails the frozen 1e-7 gate even though dividing by
    # 100 tracks would make it much smaller.
    stable, total, per_track = CORE.objective_stability([10., 10.00000015], 100)
    assert not stable
    assert total == pytest.approx(1.5e-7)
    assert per_track == pytest.approx(1.5e-9)


def test_default_starts_are_fixed_and_shared_across_layouts():
    starts = CORE.default_starts(LAYOUT)
    assert len(starts) == 3
    assert starts[0] == pytest.approx(np.zeros(5))
    assert starts[1][:-1] == pytest.approx(np.full(4, .2))
    assert starts[1][-1] == pytest.approx(.25)
    assert starts[2] == pytest.approx(-starts[1])


def test_global_direction_reversal_is_parameter_sign_invariance():
    source = track()
    theta = np.array([.2, -.4, .1, .3, math.log(.7)])
    reversed_track = CORE.TrackData(
        source.log_weights, np.asarray(source.detection_design) * [1., -1.],
        source.matched, np.asarray(source.ratio_design) * [1., -1.],
        source.log_ratio)
    reversed_theta = theta.copy()
    reversed_theta[1] *= -1
    reversed_theta[3] *= -1
    original = CORE.objective_gradient(theta, [source], LAYOUT)
    reversed_result = CORE.objective_gradient(reversed_theta, [reversed_track], LAYOUT)
    assert original[0] == pytest.approx(reversed_result[0])
    expected_gradient = np.asarray(original[1]).copy()
    expected_gradient[[1, 3]] *= -1
    assert reversed_result[1] == pytest.approx(expected_gradient)


def test_validation_rejects_nonfinite_and_unnormalized_weights():
    theta = np.zeros(5)
    invalid = track((0., 0.))
    with pytest.raises(ValueError, match="normalized"):
        CORE.objective_gradient(theta, [invalid], LAYOUT)
    bad = track(); bad.log_ratio[0] = float("nan")
    with pytest.raises(ValueError, match="ratios"):
        CORE.objective_gradient(theta, [bad], LAYOUT)
