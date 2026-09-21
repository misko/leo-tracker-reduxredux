import numpy as np

from leo.analysis.research.identity_mixture import MixtureConfig
from leo.analysis.research.orbit_identity_mixture import (
    OrbitQuadratureConfig,
    SharedMapEpisode,
    fit_shared_satellite_map,
    omitted_signal_fraction,
    orbit_identity_statistics,
    ragged_shared_value_gradient,
)


def test_ragged_shared_gradient_matches_finite_difference():
    rates = np.array([0.03, -0.02])
    base = np.array([1.0, -2.0, 0.5, 3.0, -1.0])
    design = np.array([2.0, 1.0, -3.0, 0.5, 4.0])
    point_candidate = np.array([0, 0, 1, 2, 2])
    candidate_episode = np.array([0, 0, 1])
    candidate_rate = np.array([0, 1, 0])
    log_prior = np.log(np.array([0.2, 0.2, 0.1]))
    null = np.log(np.array([0.6, 0.9]))
    args = (
        base,
        design,
        point_candidate,
        candidate_episode,
        candidate_rate,
        log_prior,
        null,
        2.0,
        0.1,
    )
    value, gradient = ragged_shared_value_gradient(rates, *args)
    numerical = np.empty(2)
    step = 1e-6
    for index in range(2):
        delta = np.zeros(2)
        delta[index] = step
        numerical[index] = (
            ragged_shared_value_gradient(rates + delta, *args)[0]
            - ragged_shared_value_gradient(rates - delta, *args)[0]
        ) / (2 * step)
    assert np.isfinite(value)
    np.testing.assert_allclose(gradient, numerical, rtol=2e-6, atol=2e-7)


def test_ragged_shared_matches_loop_oracle_with_unassigned_and_shared_rate():
    rng = np.random.default_rng(7)
    rates = rng.normal(0, 0.03, 3)
    point_candidate = np.array([0, 0, 1, 1, 2, 2, 2, 3, 3])
    candidate_episode = np.array([0, 0, 1, 1])
    candidate_rate = np.array([0, 1, 0, 2])
    base = rng.normal(size=len(point_candidate))
    design = rng.normal(size=len(point_candidate))
    log_prior = np.array([np.log(0.2), -np.inf, np.log(0.15), np.log(0.15)])
    null = np.log(np.array([0.6, 0.7]))
    sigma, prior_sigma = 1.7, 0.09
    value, gradient = ragged_shared_value_gradient(
        rates,
        base,
        design,
        point_candidate,
        candidate_episode,
        candidate_rate,
        log_prior,
        null,
        sigma,
        prior_sigma,
    )
    components = []
    derivatives = []
    for candidate in range(4):
        selected = point_candidate == candidate
        residual = base[selected] - design[selected] * rates[candidate_rate[candidate]]
        z = residual / sigma
        components.append(
            -np.sum(np.sqrt(1 + z * z) - 1) - len(z) * np.log(sigma) + log_prior[candidate]
        )
        derivatives.append(
            np.sum(residual * design[selected] / (sigma * sigma * np.sqrt(1 + z * z)))
        )
    expected_value = 0.5 * np.sum((rates / prior_sigma) ** 2)
    expected_gradient = rates / prior_sigma**2
    for episode in range(2):
        chosen = np.flatnonzero(candidate_episode == episode)
        all_components = np.r_[np.asarray(components)[chosen], null[episode]]
        evidence = np.logaddexp.reduce(all_components)
        expected_value -= evidence
        posterior = np.exp(np.asarray(components)[chosen] - evidence)
        for index, candidate in enumerate(chosen):
            expected_gradient[candidate_rate[candidate]] -= (
                posterior[index] * derivatives[candidate]
            )
    np.testing.assert_allclose(value, expected_value, rtol=0, atol=1e-12)
    np.testing.assert_allclose(gradient, expected_gradient, rtol=0, atol=1e-12)


def _case():
    observed = np.array([10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0])
    training = np.array([True, False] * 4)
    segment = np.zeros(8, dtype=int)
    rates, weights = OrbitQuadratureConfig(node_count=5).nodes()
    base = np.stack([observed - 2, observed + np.linspace(-4, 4, 8)])
    prediction = base[:, None, :] + rates[None, :, None] * np.arange(8)[None, None, :]
    return observed, prediction, observed.copy(), segment, training, weights


def test_candidate_order_permutation_is_symmetric():
    args = _case()
    first = orbit_identity_statistics(*args[:-1], 100, node_weights=args[-1])
    swapped = orbit_identity_statistics(
        args[0], args[1][::-1], *args[2:-1], 100, node_weights=args[-1]
    )
    np.testing.assert_allclose(first["candidate_posterior"], swapped["candidate_posterior"][::-1])
    assert first["train_log_evidence"] == swapped["train_log_evidence"]


def test_heldout_isolation_and_frozen_offsets():
    args = list(_case())
    first = orbit_identity_statistics(*args[:-1], 100, node_weights=args[-1])
    args[0] = args[0].copy()
    args[0][~args[4]] += 1e6
    changed = orbit_identity_statistics(*args[:-1], 100, node_weights=args[-1])
    np.testing.assert_allclose(
        first["joint_candidate_node_posterior"], changed["joint_candidate_node_posterior"]
    )
    assert first["train_log_evidence"] == changed["train_log_evidence"]
    assert first["heldout_log_predictive"] != changed["heldout_log_predictive"]


def test_ambiguity_and_unassigned_are_preserved():
    args = _case()
    duplicate = np.repeat(args[1][:1], 2, axis=0)
    result = orbit_identity_statistics(
        args[0], duplicate, args[2], args[3], args[4], 100, node_weights=args[-1]
    )
    np.testing.assert_allclose(result["candidate_posterior"][0], result["candidate_posterior"][1])
    impossible = orbit_identity_statistics(
        args[0],
        duplicate,
        args[2],
        args[3],
        args[4],
        100,
        node_weights=args[-1],
        visible=np.zeros((2, 5), bool),
    )
    assert impossible["unassigned_posterior"] == 1.0


def test_underflowed_joint_component_remains_in_heldout_predictive():
    observed = np.zeros(8)
    training = np.array([True] * 4 + [False] * 4)
    predicted = np.zeros((1, 3, 8))
    predicted[:, :, :4] = [0.0, 300_000.0, -300_000.0, 300_000.0]
    null = np.array([0.0, 1.0, -1.0, 2.0, 1e9, -1e9, 1e9, -1e9])
    result = orbit_identity_statistics(
        observed, predicted, null, np.zeros(8, int), training, 10_000, node_weights=np.ones(3) / 3
    )
    assert result["candidate_posterior"][0] == 0.0
    assert np.isfinite(result["heldout_log_predictive"])
    assert result["heldout_log_predictive"] > -10_000


def test_shared_map_predictive_retains_underflowed_training_candidate():
    training = np.array([True] * 4 + [False] * 4)
    observed = np.array([0.0, 0.0, 0.0, 0.0, 1e9, -1e9, 1e9, -1e9])
    base = np.array([[0.0, 300_000.0, -300_000.0, 300_000.0, 1e9, -1e9, 1e9, -1e9]])
    episode = SharedMapEpisode(
        observed,
        base,
        np.zeros_like(base),
        np.array([10]),
        np.zeros(8, int),
        training,
        10_000,
    )
    result = fit_shared_satellite_map([episode])
    diagnostic = result["episodes"][0]
    assert diagnostic["candidate_posterior"][0] == 0.0
    assert np.isfinite(diagnostic["heldout_log_predictive"])
    assert diagnostic["heldout_log_predictive"] > -10_000


def test_quadrature_prior_moments_and_exact_node_predictions():
    config = OrbitQuadratureConfig(node_count=9)
    rates, weights = config.nodes()
    assert abs(weights @ rates) < 1e-15
    np.testing.assert_allclose(weights @ rates**2, config.phase_rate_sigma_s_h**2, rtol=1e-13)
    # A node-specific exact propagation wins; averaging states/predictions first would not.
    observed = np.array([0.0, 0.0, 10.0, 10.0])
    prediction = np.array(
        [[[0.0, 0.0, 10.0, 10.0], [0.0, 0.0, -10.0, -10.0], [0.0, 0.0, -20.0, -20.0]]]
    )
    result = orbit_identity_statistics(
        observed,
        prediction,
        observed,
        np.zeros(4, int),
        np.array([True, False, True, False]),
        1,
        node_weights=np.array([0.2, 0.3, 0.5]),
        config=MixtureConfig(signal_sigma_hz=1.0, unassigned_sigma_hz=100.0, signal_prior=0.99),
    )
    assert (
        result["joint_candidate_node_posterior"][0, 0]
        > result["joint_candidate_node_posterior"][0, 2]
    )


def test_catalogue_prior_and_final_tail_use_orbit_marginalization():
    args = _case()
    small = orbit_identity_statistics(*args[:-1], 10, node_weights=args[-1])
    large = orbit_identity_statistics(*args[:-1], 10_000, node_weights=args[-1])
    assert small["train_log_evidence"] > large["train_log_evidence"]
    likelihood = np.array([[0.0, -100.0], [-100.0, 0.0], [-2.0, -2.0]])
    fraction = omitted_signal_fraction(
        likelihood, np.array([True, False, False]), np.array([0.5, 0.5])
    )
    assert 0.5 < fraction < 0.9


def test_quadrature_converges_for_synthetic_phase_uncertainty():
    # Integral E exp(-(a*r)^2/2) has a closed form under r~N(0,sigma^2).
    sigma = OrbitQuadratureConfig().phase_rate_sigma_s_h
    slope = 12.0
    exact = 1.0 / np.sqrt(1.0 + (slope * sigma) ** 2)
    errors = []
    for count in (3, 5, 7, 9):
        rates, weights = OrbitQuadratureConfig(node_count=count).nodes()
        estimate = weights @ np.exp(-0.5 * (slope * rates) ** 2)
        errors.append(abs(estimate - exact))
    assert errors[-1] < errors[0]
    assert errors[-1] < 2e-3


def test_shared_map_reuses_one_satellite_rate_and_is_candidate_symmetric():
    training = np.array([True, True, False, False])
    segment = np.zeros(4, int)
    episodes = []
    for scale in (1.0, 1.5):
        design = np.array(
            [[0.0, scale, 2 * scale, 3 * scale], [0.0, -scale, -2 * scale, -3 * scale]]
        )
        observed = design[0] * 0.08
        episodes.append(
            SharedMapEpisode(
                observed, np.zeros((2, 4)), design, np.array([10, 20]), segment, training, 100
            )
        )
    result = fit_shared_satellite_map(
        episodes,
        config=MixtureConfig(signal_sigma_hz=0.01, unassigned_sigma_hz=100.0, signal_prior=0.99),
    )
    rates = dict(zip(result["norad"], result["rate_corrections_s_h"], strict=True))
    assert rates[10] > 0.05
    swapped = [
        SharedMapEpisode(
            e.observed_hz,
            e.base_predicted_hz[::-1],
            e.design_hz_per_s_h[::-1],
            e.candidate_norad[::-1],
            e.segment,
            e.training,
            e.catalogue_size,
        )
        for e in episodes
    ]
    other = fit_shared_satellite_map(
        swapped,
        config=MixtureConfig(signal_sigma_hz=0.01, unassigned_sigma_hz=100.0, signal_prior=0.99),
    )
    np.testing.assert_allclose(
        result["rate_corrections_s_h"], other["rate_corrections_s_h"], atol=1e-6
    )
    np.testing.assert_allclose(
        result["negative_log_posterior"], other["negative_log_posterior"], atol=1e-9
    )

    heldout_changed = []
    for episode in episodes:
        observed = episode.observed_hz.copy()
        observed[~training] += 1e6
        heldout_changed.append(
            SharedMapEpisode(
                observed,
                episode.base_predicted_hz,
                episode.design_hz_per_s_h,
                episode.candidate_norad,
                episode.segment,
                episode.training,
                episode.catalogue_size,
            )
        )
    isolated = fit_shared_satellite_map(
        heldout_changed,
        config=MixtureConfig(signal_sigma_hz=0.01, unassigned_sigma_hz=100.0, signal_prior=0.99),
    )
    np.testing.assert_allclose(
        result["rate_corrections_s_h"], isolated["rate_corrections_s_h"], atol=1e-9
    )
