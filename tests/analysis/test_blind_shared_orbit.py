from dataclasses import replace

import numpy as np
import pytest

from leo.analysis.research.blind_shared_orbit import (
    BlindOrbitCandidateBatch,
    BlindOrbitEpisode,
    BlindSharedOrbitConfig,
    acquire_blind_orbit_episode,
    fit_blind_shared_orbit,
    fit_blind_shared_orbit_branches,
    fit_retained_blind_shared_orbit,
    score_retained_blind_shared_orbit_transfer,
)


def _episode(name, *, poison=0.0, permutation=(0, 1, 2)):
    count = 12
    time = np.linspace(-1, 1, count)
    true_age = 10.0 if name == "one" else 13.0
    age = np.vstack([np.full(count, true_age), np.full(count, 7.0), np.full(count, 4.0)])
    norad = np.asarray([100, 200, 300])
    nominal = np.vstack((300 * time, -500 * time**2, 800 * np.sin(time)))
    derivative_hz_s = np.vstack((3.0 + 4.0 * time, -2.0 + 3.0 * time**2, 1.0 + np.sin(2.0 * time)))
    nodes = {offset: nominal + derivative_hz_s * offset for offset in (-2, -1, 1, 2)}
    true_rate = 0.12
    observed = nominal[0] + derivative_hz_s[0] * age[0] * true_rate + 12.0
    training = np.asarray([True] * 7 + [False] * 5)
    observed = observed.copy()
    observed[~training] += poison
    order = np.asarray(permutation)
    batch = BlindOrbitCandidateBatch(
        norad=norad[order],
        nominal_hz=nominal[order],
        phase_minus1_hz=nodes[-1][order],
        phase_plus1_hz=nodes[1][order],
        phase_minus2_hz=nodes[-2][order],
        phase_plus2_hz=nodes[2][order],
        age_h=age[order],
    )
    return BlindOrbitEpisode(
        episode_id=name,
        observed_hz=observed,
        segment=np.asarray([name] * count),
        training=training,
        catalogue_size=3,
        batches=(batch,),
    )


class _Exact:
    def __init__(self, episodes):
        self._episodes = {episode.episode_id: episode for episode in episodes}

    def predict_hz(self, episode_id, norad, phase_offset_s):
        batch = tuple(self._episodes[episode_id].batches)[0]
        index = list(batch.norad).index(norad)
        derivative = (batch.phase_plus1_hz[index] - batch.phase_minus1_hz[index]) / 2
        return batch.nominal_hz[index] + derivative * phase_offset_s


def _config(limit=2, *, gradient=False):
    return BlindSharedOrbitConfig(
        refinement_candidates_per_episode=limit,
        signal_sigma_hz=2.0,
        unassigned_sigma_hz=1000.0,
        validate_analytic_gradient=gradient,
    )


def test_recovers_one_shared_norad_rate_and_reports_truncated_support():
    episodes = (_episode("one"), _episode("two"))
    result = fit_blind_shared_orbit(
        episodes, config=_config(gradient=True), exact_prediction=_Exact(episodes)
    )

    assert result["recurrent_norad_episode_count"][100] == 2
    assert abs(result["rate_corrections_s_h"][100] - 0.12) < 0.02
    assert result["corrected_support_certified"] is False
    assert result["corrected_support_status"] == "uncertified-truncated-corrected-support"
    assert all(audit["maximum_error_hz"] < 1e-10 for audit in result["exact_replay_audits"])
    assert result["analytic_gradient_check_maximum_error"] < 1e-5
    assert (
        result["outer_position_scores"]["matched_shortlist_shared_negative_log_posterior"]
        <= result["outer_position_scores"]["matched_shortlist_nominal_negative_log_posterior"]
    )


def test_candidate_permutation_preserves_shared_solution():
    original = (_episode("one"), _episode("two"))
    permuted = (_episode("one", permutation=(2, 0, 1)), _episode("two", permutation=(1, 2, 0)))
    left = fit_blind_shared_orbit(original, config=_config())
    right = fit_blind_shared_orbit(permuted, config=_config())

    assert left["rate_corrections_s_h"].keys() == right["rate_corrections_s_h"].keys()
    for norad in left["rate_corrections_s_h"]:
        assert np.isclose(left["rate_corrections_s_h"][norad], right["rate_corrections_s_h"][norad])


def test_heldout_poisoning_cannot_change_acquisition_or_fitted_rates():
    clean = (_episode("one"), _episode("two"))
    poisoned = (_episode("one", poison=1e6), _episode("two", poison=-1e6))
    left = fit_blind_shared_orbit(clean, config=_config())
    right = fit_blind_shared_orbit(poisoned, config=_config())

    assert left["rate_corrections_s_h"] == right["rate_corrections_s_h"]
    for a, b in zip(
        left["full_catalogue_acquisition"],
        right["full_catalogue_acquisition"],
        strict=True,
    ):
        assert a == b
    assert (
        left["shared_fit"]["episodes"][0]["heldout_log_predictive"]
        != right["shared_fit"]["episodes"][0]["heldout_log_predictive"]
    )


def test_full_corrected_support_remains_uncertified_with_fixed_visibility():
    episodes = (_episode("one"), _episode("two"))
    without = fit_blind_shared_orbit(episodes, config=_config(limit=3))
    with_exact = fit_blind_shared_orbit(
        episodes, config=_config(limit=3), exact_prediction=_Exact(episodes)
    )

    assert without["corrected_support_certified"] is False
    assert with_exact["corrected_support_certified"] is False
    assert with_exact["corrected_support_status"] == "uncertified-fixed-nominal-visibility"


def test_truth_coordinates_are_not_an_input_and_causal_age_is_required():
    episode = _episode("one")
    assert "latitude" not in BlindOrbitEpisode.__dataclass_fields__
    batch = tuple(episode.batches)[0]
    try:
        replace(batch, age_h=-np.ones_like(batch.age_h))
    except ValueError as error:
        assert "causal TLE ages" in str(error)
    else:
        raise AssertionError("negative causal ages were accepted")


def test_spatial_branches_are_independent_and_ranked_by_training_only():
    left = tuple(
        replace(episode, spatial_branch_id="left") for episode in (_episode("one"), _episode("two"))
    )
    right = tuple(
        replace(episode, spatial_branch_id="right")
        for episode in (_episode("one"), _episode("two"))
    )
    result = fit_blind_shared_orbit_branches({"left": left, "right": right}, config=_config())

    assert set(result["branch_ranking"]) == {"left", "right"}
    assert result["distinct_basins_retained"] is True
    try:
        fit_blind_shared_orbit((left[0], right[1]), config=_config())
    except ValueError as error:
        assert "common spatial branch" in str(error)
    else:
        raise AssertionError("mixed spatial branches were accepted")


def test_acquisition_token_reuses_only_bound_retained_support():
    full = (_episode("one"), _episode("two"))
    tokens = tuple(acquire_blind_orbit_episode(ep, config=_config()) for ep in full)
    retained = []
    for episode, token in zip(full, tokens, strict=True):
        batch = tuple(episode.batches)[0]
        indices = np.asarray([list(batch.norad).index(norad) for norad in token.retained_norad])
        retained.append(
            replace(
                episode,
                spatial_branch_id="refined-position",
                batches=(
                    BlindOrbitCandidateBatch(
                        norad=batch.norad[indices],
                        nominal_hz=batch.nominal_hz[indices],
                        phase_minus1_hz=batch.phase_minus1_hz[indices],
                        phase_plus1_hz=batch.phase_plus1_hz[indices],
                        phase_minus2_hz=batch.phase_minus2_hz[indices],
                        phase_plus2_hz=batch.phase_plus2_hz[indices],
                        age_h=batch.age_h[indices],
                    ),
                ),
            )
        )
    direct = fit_blind_shared_orbit(full, config=_config())
    reused = fit_retained_blind_shared_orbit(tuple(retained), tokens, config=_config())

    assert direct["rate_corrections_s_h"] == reused["rate_corrections_s_h"]
    assert reused["corrected_support_certified"] is False
    scores = reused["outer_position_scores"]
    assert scores["current_branch_full_catalogue_nominal_training_negative_log_evidence"] is None
    assert scores["frozen_acquisition_origin_spatial_branch_ids"] == (
        "caller-supplied-common-position",
        "caller-supplied-common-position",
    )


def test_acquisition_token_rejects_changed_training_or_configuration_but_not_heldout():
    episode = _episode("one")
    config = _config()
    token = acquire_blind_orbit_episode(episode, config=config)
    retained_norad = np.asarray(token.retained_norad)
    batch = tuple(episode.batches)[0]
    indices = np.asarray([list(batch.norad).index(norad) for norad in retained_norad])
    retained_batch = replace(
        batch,
        norad=batch.norad[indices],
        nominal_hz=batch.nominal_hz[indices],
        phase_minus1_hz=batch.phase_minus1_hz[indices],
        phase_plus1_hz=batch.phase_plus1_hz[indices],
        phase_minus2_hz=batch.phase_minus2_hz[indices],
        phase_plus2_hz=batch.phase_plus2_hz[indices],
        age_h=batch.age_h[indices],
    )
    retained = replace(episode, batches=(retained_batch,), spatial_branch_id="new-position")
    poisoned = replace(retained, observed_hz=retained.observed_hz + (~retained.training) * 1e6)
    fit_retained_blind_shared_orbit((poisoned,), (token,), config=config)

    changed_training = np.asarray(retained.training).copy()
    changed_training[5] = False
    changed_training[7] = True
    with pytest.raises(ValueError, match="does not bind"):
        fit_retained_blind_shared_orbit(
            (replace(retained, training=changed_training),), (token,), config=config
        )
    with pytest.raises(ValueError, match="does not bind"):
        fit_retained_blind_shared_orbit(
            (retained,), (token,), config=replace(config, signal_sigma_hz=3.0)
        )


@pytest.mark.parametrize(
    "field",
    (
        "signal_sigma_hz",
        "unassigned_sigma_hz",
        "signal_prior",
        "phase_rate_sigma_s_h",
        "phase_rate_bound_s_h",
        "exact_audit_maximum_error_hz",
    ),
)
def test_configuration_rejects_nonfinite_values(field):
    with pytest.raises(ValueError, match="finite"):
        BlindSharedOrbitConfig(**{field: float("nan")})


def test_nominal_only_refit_reuses_acquisition_and_keeps_rates_zero():
    episode = _episode("one")
    shared_config = _config()
    token = acquire_blind_orbit_episode(episode, config=shared_config)
    batch = tuple(episode.batches)[0]
    indices = np.asarray([list(batch.norad).index(norad) for norad in token.retained_norad])
    retained = replace(
        episode,
        batches=(
            replace(
                batch,
                norad=batch.norad[indices],
                nominal_hz=batch.nominal_hz[indices],
                phase_minus1_hz=batch.phase_minus1_hz[indices],
                phase_plus1_hz=batch.phase_plus1_hz[indices],
                phase_minus2_hz=batch.phase_minus2_hz[indices],
                phase_plus2_hz=batch.phase_plus2_hz[indices],
                age_h=batch.age_h[indices],
            ),
        ),
    )
    result = fit_retained_blind_shared_orbit(
        (retained,),
        (token,),
        config=replace(shared_config, optimize_shared_rates=False),
    )

    assert set(result["rate_corrections_s_h"].values()) == {0.0}
    assert result["shared_fit"]["iterations"] == 0
    frozen = {int(norad): 0.05 for norad in token.retained_norad}
    transfer = score_retained_blind_shared_orbit_transfer(
        (retained,), (token,), frozen, config=shared_config
    )
    assert transfer["rate_corrections_s_h"] == frozen
    assert transfer["shared_fit"]["iterations"] == 0


def test_nonlinear_quartic_recovery_matches_independent_polynomial_oracle():
    count = 16
    time = np.linspace(-1.0, 1.0, count)
    ages = np.vstack((np.linspace(8.0, 12.0, count), np.linspace(5.0, 7.0, count)))
    nominal = np.vstack((200.0 * time, -300.0 * time**2))
    coefficients = np.stack(
        (
            np.vstack((4.0 + time, -2.0 + time**2)),
            np.vstack((0.7 * time, 0.3 + 0.1 * time)),
            np.vstack((0.08 + 0.02 * time, -0.04 * time)),
            np.vstack((0.01 * time, 0.005 + 0.002 * time)),
        )
    )

    def polynomial(candidate, phase):
        return nominal[candidate] + sum(
            coefficients[degree - 1, candidate] * phase**degree for degree in range(1, 5)
        )

    nodes = {
        phase: np.vstack([polynomial(candidate, phase) for candidate in range(2)])
        for phase in (-2.0, -1.0, 1.0, 2.0)
    }
    true_rate = 0.09
    observed = polynomial(0, true_rate * ages[0]) + 19.0
    batch = BlindOrbitCandidateBatch(
        norad=np.asarray([111, 222]),
        nominal_hz=nominal,
        phase_minus1_hz=nodes[-1.0],
        phase_plus1_hz=nodes[1.0],
        phase_minus2_hz=nodes[-2.0],
        phase_plus2_hz=nodes[2.0],
        age_h=ages,
    )
    episode = BlindOrbitEpisode(
        episode_id="quartic",
        observed_hz=observed,
        segment=np.asarray(["quartic"] * count),
        training=np.asarray([True] * 10 + [False] * 6),
        catalogue_size=2,
        batches=(batch,),
    )

    class Oracle:
        def __init__(self, perturb=0.0):
            self.perturb = perturb

        def predict_hz(self, episode_id, norad, phase_offset_s):
            assert episode_id == "quartic"
            return polynomial([111, 222].index(norad), phase_offset_s) + self.perturb

    config = replace(_config(limit=2, gradient=True), signal_sigma_hz=1.0)
    result = fit_blind_shared_orbit((episode,), config=config, exact_prediction=Oracle())
    assert abs(result["rate_corrections_s_h"][111] - true_rate) < 0.01
    assert result["analytic_gradient_check_maximum_error"] < 1e-5
    assert result["exact_replay_audits"][0]["maximum_error_hz"] < 1e-8

    perturbed = fit_blind_shared_orbit(
        (episode,), config=config, exact_prediction=Oracle(perturb=0.3)
    )
    assert perturbed["exact_replay_audits"][0]["maximum_error_hz"] > 0.2
    assert perturbed["corrected_support_certified"] is False
