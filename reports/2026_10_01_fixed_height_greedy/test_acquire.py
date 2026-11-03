import numpy as np
from acquire import (
    FixedHeightTrackLikelihood,
    coarse_to_fine,
    distinct_top,
    fibonacci_disk,
)
from physics import PhysicsConfig, StateLayout
from physics_fixed import build_fixed_height_factor
from leo.analysis.robust_likelihood import student_t_logpdf
from test_physics_fixed import _bank, _track


def test_fibonacci_disk_is_deterministic_and_inside_uniform_disk():
    first=fibonacci_disk(1024,250.)
    second=fibonacci_disk(1024,250.)
    np.testing.assert_array_equal(first,second)
    assert np.all(np.linalg.norm(first,axis=1)<250.)
    # Equal increments in radius squared give equal represented area.
    np.testing.assert_allclose(np.diff(np.sort(np.linalg.norm(first,axis=1)**2)),250**2/1024)


def test_distinct_top_preserves_geographically_separate_modes():
    points=np.array([[0.,0.],[1.,0.],[100.,0.],[101.,0.]])
    indices=distinct_top(points,np.array([10.,9.,8.,7.]),2,20.)
    np.testing.assert_array_equal(indices,[0,2])


def test_coarse_to_fine_recovers_two_modes_without_winner_only_pruning():
    modes=np.array([[-91.,-79.],[120.,80.]])
    def score(points):
        values=np.stack([-np.sum((points-mode)**2,axis=1)/(2*5**2) for mode in modes],axis=1)
        maximum=values.max(axis=1)
        return maximum+np.log(np.exp(values-maximum[:,None]).sum(axis=1))
    seeds,scores,evaluated,spacing=coarse_to_fine(score,basin_count=4)
    assert min(np.linalg.norm(seeds-modes[0],axis=1))<2.
    assert min(np.linalg.norm(seeds-modes[1],axis=1))<2.
    assert evaluated<2200 and spacing==1.
    assert np.all(np.diff(scores)<=0)


def test_fast_full_state_branch_logs_match_frozen_candidates() -> None:
    bank = _bank()
    track = _track()
    config = PhysicsConfig()
    height = lambda east, north: 0.03048 + 0.001 * east - 0.002 * north
    port = FixedHeightTrackLikelihood(track, bank, config, height)
    frozen = build_fixed_height_factor(
        track, bank, StateLayout(bank.norad_ids), config, height
    ).factor
    states = (
        np.array([0.2, -0.1, 0.1, 0.03, -0.02, 0.2]),
        np.array([-0.3, 0.4, -0.2, -0.04, 0.05, -0.1]),
        np.array([0.7, 0.5, 0.3, 0.02, 0.01, -0.3]),
    )
    for state in states:
        actual = port.branch_loglik_at_state(state)
        prediction = frozen.candidates[0].predict(state)
        residual = frozen.observation - prediction.mean
        sign, logdet = np.linalg.slogdet(prediction.covariance)
        assert sign == 1
        expected_signal = (
            np.log(frozen.candidates[0].prior(state))
            - 0.5
            * (
                len(residual) * np.log(2 * np.pi)
                + logdet
                + residual @ np.linalg.solve(prediction.covariance, residual)
            )
        )
        expected_background = (
            np.log(frozen.background_prior(state)) + frozen.background_log_likelihood
        )
        np.testing.assert_allclose(
            actual, [expected_signal, expected_background], rtol=1e-11, atol=1e-9
        )


def test_student_t_branch_scores_are_normalized_for_signal_and_background() -> None:
    bank = _bank()
    track = _track()
    config = PhysicsConfig()
    port = FixedHeightTrackLikelihood(track, bank, config, 0.03048, 4.0)
    state = np.array([0.2, -0.1, 0.1, 0.03, -0.02, 0.2])
    factor = build_fixed_height_factor(
        track, bank, StateLayout(bank.norad_ids), config, lambda _e, _n: 0.03048
    ).factor
    prediction = factor.candidates[0].predict(state)
    expected_signal = np.log(factor.candidates[0].prior(state)) + student_t_logpdf(
        factor.observation - prediction.mean, prediction.covariance, 4.0
    )
    expected_background = np.log(factor.background_prior(state)) + student_t_logpdf(
        factor.observation, port.background_covariance, 4.0
    )
    np.testing.assert_allclose(
        port.branch_loglik_at_state(state),
        [expected_signal, expected_background],
        rtol=1e-11,
        atol=1e-9,
    )


def test_student_t_proposal_and_full_state_ports_agree_at_fixed_nuisance() -> None:
    port = FixedHeightTrackLikelihood(_track(), _bank(), PhysicsConfig(), 0.03048, 4.0)
    point = np.array([[0.2, -0.1]])
    proposal = port(point, np.empty((1, 0)))[0, 0]
    state = np.r_[point[0], np.zeros(4)]
    np.testing.assert_allclose(proposal, port.branch_loglik_at_state(state), atol=1e-9)
