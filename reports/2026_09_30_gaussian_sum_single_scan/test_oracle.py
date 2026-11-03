import numpy as np
import pytest

from oracle import LinearAlternative, OracleComponent, exact_linear_update, regional_grid_oracle


def test_direct_joint_conditioning_matches_dense_regional_grid():
    prior = OracleComponent(1.0, np.array([0.2]), np.array([[1.3]]))
    alt = LinearAlternative("sat", 1.0, np.array([[1.4]]), np.array([-0.1]), np.array([[0.7]]))
    exact = exact_linear_update([prior], np.array([0.8]), [alt])
    axis = np.linspace(-6, 6, 24001)
    grid = regional_grid_oracle(
        (axis,), lambda x: -0.5 * ((x[0] - .2) ** 2 / 1.3 + np.log(2*np.pi*1.3)),
        {"sat": (1.0, lambda x: -0.5 * ((.8 - (1.4*x[0]-.1)) ** 2/.7 + np.log(2*np.pi*.7)))})
    np.testing.assert_allclose(grid.mean, exact.mean, atol=2e-5)
    np.testing.assert_allclose(grid.covariance, exact.covariance, atol=3e-5)
    assert abs(grid.log_evidence - exact.log_evidence) < 2e-7


def test_separated_modes_and_replication_with_conserved_mass():
    prior = OracleComponent(1.0, np.array([0.0]), np.array([[9.0]]))
    a = LinearAlternative("left", .5, np.array([[1.0]]), np.array([2.0]), np.array([[.1]]))
    b = LinearAlternative("right", .5, np.array([[1.0]]), np.array([-2.0]), np.array([[.1]]))
    base = exact_linear_update([prior], np.array([0.0]), [a, b])
    replicas = [LinearAlternative("left", .25, a.matrix, a.intercept, a.covariance), LinearAlternative("left", .25, a.matrix, a.intercept, a.covariance), b]
    replicated = exact_linear_update([prior], np.array([0.0]), replicas)
    assert base.association["left"] == pytest.approx(.5)
    assert base.association["right"] == pytest.approx(.5)
    np.testing.assert_allclose(replicated.mean, base.mean, atol=1e-14)
    np.testing.assert_allclose(replicated.covariance, base.covariance, atol=1e-14)
    assert abs(replicated.log_evidence - base.log_evidence) < 1e-14


def test_outlier_selects_background_and_extreme_logs_normalize():
    prior = OracleComponent(1.0, np.array([0.0]), np.array([[1.0]]))
    alt = LinearAlternative("absent", .9, np.array([[1.0]]), np.zeros(1), np.array([[.01]]))
    result = exact_linear_update([prior], np.array([1000.0]), [alt], background_prior=.1, background_log_likelihood=-1000.)
    assert result.association["background"] > 1 - 1e-12
    assert np.isfinite(result.log_evidence)
    np.testing.assert_array_equal(result.mean, prior.mean)


def test_shared_nuisance_creates_cross_covariance_and_bounded_uncertainty():
    # state = position, common clock; the two measurements share clock exactly.
    prior = OracleComponent(1.0, np.zeros(2), np.diag([4.0, 9.0]))
    alt = LinearAlternative("sat", 1.0, np.array([[1., 1.], [-1., 1.]]), np.zeros(2), np.eye(2)*.2)
    result = exact_linear_update([prior], np.array([2., -2.]), [alt])
    eig = np.linalg.eigvalsh(result.covariance)
    assert np.all(np.isfinite(result.covariance)) and np.all(eig > 0)
    assert result.covariance[0, 0] < .11
    # A common-mode measurement cannot falsely provide twice-independent clock precision.
    one_common = LinearAlternative("sat", 1.0, np.array([[0., 1.]]), np.zeros(1), np.array([[.2]]))
    once = exact_linear_update([prior], np.array([0.]), [one_common])
    assert result.covariance[1, 1] > once.covariance[1, 1] * .49


def test_later_evidence_recovers_retained_wrong_early_mode():
    prior = OracleComponent(1., np.array([0.]), np.array([[4.]]))
    early = [LinearAlternative("wrong", .8, np.array([[1.]]), np.array([2.]), np.array([[.2]])), LinearAlternative("true", .2, np.array([[1.]]), np.array([-2.]), np.array([[.2]]))]
    first = exact_linear_update([prior], np.array([0.]), early)
    assert first.association["wrong"] > first.association["true"]
    later = LinearAlternative("confirm", 1., np.array([[1.]]), np.array([-2.]), np.array([[.05]]))
    second = exact_linear_update(first.components, np.array([0.]), [later])
    true_histories = sum(c.weight for c in second.components if c.history[0] == "true")
    assert true_histories > .99


def test_known_truth_monte_carlo_coverage_is_calibrated():
    rng = np.random.default_rng(8217)
    prior = OracleComponent(1., np.array([0.]), np.array([[1.]]))
    alt = LinearAlternative("sat", 1., np.array([[1.]]), np.zeros(1), np.array([[.5]]))
    covered = 0
    for _ in range(80):
        truth = rng.normal()
        y = truth + rng.normal(scale=np.sqrt(.5))
        posterior = exact_linear_update([prior], np.array([y]), [alt])
        covered += abs(truth - posterior.mean[0]) <= 1.96*np.sqrt(posterior.covariance[0, 0])
    assert 69 <= covered <= 80  # frozen broad binomial gate for nominal 95%, n=80


def test_sequential_and_batch_evidence_and_moments_agree():
    prior = OracleComponent(1., np.array([.3, -.2]), np.array([[2., .4], [.4, 1.]]))
    first_alt = LinearAlternative("one", 1., np.array([[1., .2]]), np.array([.1]), np.array([[.3]]))
    second_alt = LinearAlternative("two", 1., np.array([[-.4, 1.]]), np.array([-.2]), np.array([[.6]]))
    first = exact_linear_update([prior], np.array([.7]), [first_alt])
    sequential = exact_linear_update(first.components, np.array([-.5]), [second_alt])
    stacked = LinearAlternative(
        "batch", 1., np.vstack([first_alt.matrix, second_alt.matrix]),
        np.concatenate([first_alt.intercept, second_alt.intercept]), np.diag([.3, .6]))
    batch = exact_linear_update([prior], np.array([.7, -.5]), [stacked])
    np.testing.assert_allclose(sequential.mean, batch.mean, atol=2e-14)
    np.testing.assert_allclose(sequential.covariance, batch.covariance, atol=2e-14)
    assert first.log_evidence + sequential.log_evidence == pytest.approx(batch.log_evidence, abs=2e-14)


def test_low_information_factor_preserves_prior_to_roundoff():
    prior = OracleComponent(1., np.array([2., -3.]), np.array([[4., 1.], [1., 2.]]))
    weak = LinearAlternative("weak", 1., np.zeros((1, 2)), np.zeros(1), np.array([[1e12]]))
    result = exact_linear_update([prior], np.array([0.]), [weak])
    np.testing.assert_allclose(result.mean, prior.mean, atol=0.)
    np.testing.assert_allclose(result.covariance, prior.covariance, atol=0.)
