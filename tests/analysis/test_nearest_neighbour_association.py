from __future__ import annotations

import ast
import inspect
import math
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from leo.analysis import nearest_neighbour_association as nearest_module
from leo.analysis.nearest_neighbour_association import (
    NearestNeighbourAssociationConfig,
    NearestNeighbourInputError,
    NearestNeighbourNumericalError,
    associate_single_episode_nearest_neighbour,
    gaussian_innovation_score,
)
from leo.contracts.catalogue_association import (
    CandidateObservationPredictionV1,
    CandidateTauStateV1,
    CatalogueCandidatePredictionV1,
    CataloguePredictionBankV1,
    CataloguePredictionSupportV1,
    CatalogueVerifiedTleMemberV1,
    PhysicalCfoEpisodeV1,
    PhysicalEpisodeGraphV1,
    SupportIntegratedCfoObservationV1,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1

_BASE_UTC_NS = 1_800_000_000_000_000_000
_SELECTION_PROTOCOL_DIGEST = canonical_digest({"selection-protocol": "synthetic-frozen"})
_SELECTION_POLICY_DIGEST = canonical_digest({"selection-policy": "synthetic-frozen"})


def _digest(kind: str, identity: object) -> str:
    return canonical_digest({kind: identity})


def _graph(
    measured_cfo_hz: tuple[float, ...],
    *,
    observation_uncertainty_hz: float = 1.0,
    reverse_inputs: bool = False,
) -> PhysicalEpisodeGraphV1:
    episode_id = _digest("episode", "single")
    observations: list[SupportIntegratedCfoObservationV1] = []
    observation_ids: list[str] = []
    for index, measured in enumerate(measured_cfo_hz):
        center_utc_ns = _BASE_UTC_NS + index * 1_000_000_000
        observation_id = _digest("observation", index)
        observations.append(
            SupportIntegratedCfoObservationV1(
                observation_id=observation_id,
                source_group_id=_digest("source-group", index),
                episode_id=episode_id,
                receiver_path_id=_digest("receiver-path", "synthetic"),
                hardware_epoch_id="receiver-a",
                raw_recording_authority_digest=_digest("raw-authority", "synthetic"),
                recording_manifest_digest=_digest("recording-manifest", "synthetic"),
                stream_id="stream-1",
                source_binding_digest=_digest("source-binding", index),
                source_sample_start=index * 100,
                source_sample_end=index * 100 + 50,
                support_start_utc_ns=center_utc_ns - 10_000_000,
                support_center_utc_ns=center_utc_ns,
                support_end_utc_ns=center_utc_ns + 10_000_000,
                measured_cfo_hz=measured,
                standard_uncertainty_hz=observation_uncertainty_hz,
                factorial_support_moments_s=(1.0, 0.0, 0.000_016_666_666_7, 0.0),
            )
        )
        observation_ids.append(observation_id)
    episode = PhysicalCfoEpisodeV1(
        episode_id=episode_id,
        dwell_id=_digest("dwell", "synthetic"),
        lane_id=_digest("lane", "synthetic"),
        order_index=0,
        continuity_component_id=_digest("continuity", "synthetic"),
        observation_ids=tuple(observation_ids),
    )
    if reverse_inputs:
        observations.reverse()
    return PhysicalEpisodeGraphV1.create(
        observations=tuple(observations),
        episodes=(episode,),
    )


def _bank(
    graph: PhysicalEpisodeGraphV1,
    predictions_by_catalog: dict[int, dict[float, tuple[float, ...]]],
    *,
    prediction_uncertainty_by_catalog: dict[int, float] | None = None,
    tau_log_weights_by_catalog: dict[int, dict[float, float]] | None = None,
    reverse_inputs: bool = False,
    source_candidate_count: int | None = None,
) -> CataloguePredictionBankV1:
    prediction_uncertainty_by_catalog = (
        {} if prediction_uncertainty_by_catalog is None else prediction_uncertainty_by_catalog
    )
    tau_log_weights_by_catalog = (
        {} if tau_log_weights_by_catalog is None else tau_log_weights_by_catalog
    )
    episode = graph.episodes[0]
    observation_ids = episode.observation_ids
    prediction_reference_utc_ns = min(item.support_center_utc_ns for item in graph.observations)
    element_epoch_utc_ns = _BASE_UTC_NS - 20 * 3_600 * 1_000_000_000
    candidates: list[CatalogueCandidatePredictionV1] = []
    for catalog_number, states_by_tau in predictions_by_catalog.items():
        states: list[CandidateTauStateV1] = []
        for tau_s, predicted_values in states_by_tau.items():
            if len(predicted_values) != len(observation_ids):
                raise AssertionError("test prediction fixture must cover the episode")
            predictions = tuple(
                sorted(
                    (
                        CandidateObservationPredictionV1(
                            observation_id=observation_id,
                            predicted_cfo_hz=predicted,
                            standard_uncertainty_hz=prediction_uncertainty_by_catalog.get(
                                catalog_number, 0.2
                            ),
                        )
                        for observation_id, predicted in zip(
                            observation_ids, predicted_values, strict=True
                        )
                    ),
                    key=lambda item: item.observation_id,
                )
            )
            states.append(
                CandidateTauStateV1(
                    tau_s=tau_s,
                    log_prior_weight=tau_log_weights_by_catalog.get(catalog_number, {}).get(
                        tau_s, 0.0
                    ),
                    predictions=predictions,
                )
            )
        candidates.append(
            CatalogueCandidatePredictionV1(
                catalog_number=catalog_number,
                object_name=f"STARLINK-{catalog_number}",
                selected_element_digest=_digest("element", catalog_number),
                element_epoch_utc_ns=element_epoch_utc_ns,
                element_age_s_at_reference=(
                    abs(prediction_reference_utc_ns - element_epoch_utc_ns) / 1e9
                ),
                eligible_episode_ids=(episode.episode_id,),
                tau_states=tuple(sorted(states, key=lambda item: item.tau_s)),
            )
        )
    if reverse_inputs:
        candidates.reverse()
    bounded_tau = any(
        tuple(sorted(states_by_tau)) != (0.0,) for states_by_tau in predictions_by_catalog.values()
    )
    return CataloguePredictionBankV1.create(
        support=CataloguePredictionSupportV1.from_graph(graph),
        tle_snapshot=TleSnapshotRefV1(
            provider="space-track",
            collected_utc_ns=_BASE_UTC_NS - 3_600 * 1_000_000_000,
            digest=_digest("tle-snapshot", "synthetic"),
            object_count=100,
        ),
        observer_site=ObserverSiteV1(
            latitude_deg=37.0,
            longitude_deg=-122.0,
            altitude_m=10.0,
            label="synthetic-known-site",
        ),
        nominal_rf_hz=11_325_000_000.0,
        selection_protocol_digest=_SELECTION_PROTOCOL_DIGEST,
        selection_policy_digest=_SELECTION_POLICY_DIGEST,
        tle_membership_authority_digest=_digest("tle-membership", "synthetic"),
        verified_tle_members=tuple(
            CatalogueVerifiedTleMemberV1(
                catalog_number=item.catalog_number,
                selected_element_digest=item.selected_element_digest,
                element_epoch_utc_ns=item.element_epoch_utc_ns,
            )
            for item in candidates
        ),
        propagation_model="synthetic-support-integrated",
        candidates=tuple(candidates),
        source_candidate_count=source_candidate_count,
        tau_search_policy=(
            "bounded-profile-minus5-plus5-v1" if bounded_tau else "fixed-tau-zero-v1"
        ),
    )


def _config(
    graph: PhysicalEpisodeGraphV1,
    *,
    nuisance_sigma_hz: float = 100.0,
    null_prediction_uncertainty_hz: float = 1.0,
    ambiguity_margin: float | None = None,
    nis_threshold: float | None = None,
    expected_selection_protocol_digest: str = _SELECTION_PROTOCOL_DIGEST,
) -> NearestNeighbourAssociationConfig:
    observation_ids = graph.episodes[0].observation_ids
    return NearestNeighbourAssociationConfig(
        training_observation_ids=observation_ids[:3],
        evaluation_observation_ids=observation_ids[3:],
        expected_selection_protocol_digest=expected_selection_protocol_digest,
        expected_selection_policy_digest=_SELECTION_POLICY_DIGEST,
        nuisance_offset_prior_sigma_hz=nuisance_sigma_hz,
        restricted_null_prediction_standard_uncertainty_hz=(null_prediction_uncertainty_hz),
        descriptive_ambiguity_negative_log_score_margin=ambiguity_margin,
        descriptive_mean_normalized_innovation_squared_threshold=nis_threshold,
    )


def test_analytic_gaussian_score_matches_brute_force_matrix() -> None:
    residuals = (4.0, -2.0, 1.0)
    observation_sigmas = (1.0, 2.0, 0.5)
    prediction_sigmas = (0.5, 1.5, 2.0)
    prior_mean = 1.25
    prior_sigma = 3.0

    score = gaussian_innovation_score(
        residuals,
        observation_sigmas,
        prediction_sigmas,
        offset_prior_mean_hz=prior_mean,
        offset_prior_standard_uncertainty_hz=prior_sigma,
    )

    diagonal = np.square(observation_sigmas) + np.square(prediction_sigmas)
    covariance = np.diag(diagonal) + prior_sigma**2 * np.ones((3, 3))
    centered = np.asarray(residuals) - prior_mean
    sign, log_determinant = np.linalg.slogdet(covariance)
    expected_quadratic = float(centered @ np.linalg.solve(covariance, centered))
    expected_nll = 0.5 * (
        expected_quadratic + log_determinant + len(residuals) * math.log(2.0 * math.pi)
    )
    posterior_variance = 1.0 / (1.0 / prior_sigma**2 + float(np.sum(1.0 / diagonal)))
    posterior_mean = prior_mean + posterior_variance * float(
        np.sum((np.asarray(residuals) - prior_mean) / diagonal)
    )

    assert sign == 1.0
    assert score.mahalanobis_squared == pytest.approx(expected_quadratic, rel=1e-12)
    assert score.log_determinant_covariance == pytest.approx(log_determinant, rel=1e-12)
    assert score.marginal_negative_log_likelihood == pytest.approx(expected_nll, rel=1e-12)
    assert score.offset_posterior_mean_hz == pytest.approx(posterior_mean, rel=1e-12)
    assert score.offset_posterior_standard_uncertainty_hz == pytest.approx(
        math.sqrt(posterior_variance), rel=1e-12
    )
    assert score.measurement_prediction_standard_uncertainties_hz == pytest.approx(
        tuple(
            math.hypot(observation, prediction)
            for observation, prediction in zip(observation_sigmas, prediction_sigmas, strict=True)
        )
    )


def test_training_winner_persists_on_heldout_without_identity_claim() -> None:
    true_curve = (0.0, 10.0, 25.0, 45.0, 70.0, 100.0)
    distractor = (0.0, -10.0, -25.0, -45.0, -70.0, -100.0)
    graph = _graph(tuple(50.0 + item for item in true_curve))
    bank = _bank(
        graph,
        {
            10001: {0.0: true_curve},
            10002: {0.0: distractor},
        },
    )

    result = associate_single_episode_nearest_neighbour(graph, bank, config=_config(graph))

    assert result.training_nearest_catalog_number == 10001
    assert result.heldout_nearest_catalog_number == 10001
    assert result.training_nearest_persisted_on_heldout is True
    assert result.abstention_recommended is False
    assert result.descriptive_ambiguity_negative_log_score_margin is None
    assert result.training_ambiguous_under_descriptive_margin is None
    assert result.training_innovation_threshold_exceeded is None
    assert result.heldout_innovation_threshold_exceeded is None
    assert result.candidate_only is True
    assert result.identity_claimed is False
    assert result.likelihoods_are_calibrated_identity_probabilities is False
    assert result.training_response_consumed_during_fit is True
    assert result.evaluation_response_accessed_during_training_fit is False
    assert result.runner_isolation_required is True
    winner = result.scores[0]
    assert winner.training_innovation.offset_posterior_mean_hz == pytest.approx(50.0, abs=0.01)
    assert winner.heldout_innovation.offset_prior_mean_hz == pytest.approx(
        winner.frozen_training_offset_mean_hz
    )
    assert all(
        item == pytest.approx(math.hypot(1.0, 0.2))
        for item in winner.training_innovation.measurement_prediction_standard_uncertainties_hz
    )
    null = next(item for item in result.scores if item.kind == "restricted-zero-curve-null")
    assert all(
        item == pytest.approx(math.hypot(1.0, 1.0))
        for item in null.training_innovation.measurement_prediction_standard_uncertainties_hz
    )


def test_heldout_response_cannot_change_training_fit_but_exposes_instability() -> None:
    candidate_one = (0.0, 10.0, 20.0, 30.0, 40.0, 50.0)
    candidate_two = (0.2, 9.8, 20.2, 80.0, 60.0, 40.0)
    original_graph = _graph(tuple(50.0 + item for item in candidate_one))
    poisoned_future = candidate_one[:3] + candidate_two[3:]
    changed_graph = _graph(tuple(50.0 + item for item in poisoned_future))
    bank = _bank(
        original_graph,
        {
            10001: {0.0: candidate_one},
            10002: {0.0: candidate_two},
        },
    )

    original = associate_single_episode_nearest_neighbour(
        original_graph, bank, config=_config(original_graph)
    )
    changed = associate_single_episode_nearest_neighbour(
        changed_graph, bank, config=_config(changed_graph)
    )

    assert original.training_nearest_catalog_number == 10001
    assert changed.training_nearest_catalog_number == 10001
    assert original.observation_partition_digest == changed.observation_partition_digest
    assert tuple(item.catalog_number for item in original.scores) == tuple(
        item.catalog_number for item in changed.scores
    )
    assert tuple(
        item.training_total_negative_log_score for item in original.scores
    ) == pytest.approx(tuple(item.training_total_negative_log_score for item in changed.scores))
    assert original.heldout_nearest_catalog_number == 10001
    assert changed.heldout_nearest_catalog_number == 10002
    assert changed.training_nearest_persisted_on_heldout is False
    assert "heldout-rank-instability" in changed.abstention_diagnostics


def test_close_rate_candidates_are_ambiguity_diagnostic_without_hard_gate() -> None:
    true_curve = (0.0, 10.0, 20.0, 30.0, 40.0, 50.0)
    close_curve = (0.05, 9.95, 20.05, 30.05, 39.95, 50.05)
    graph = _graph(tuple(50.0 + item for item in true_curve))
    bank = _bank(
        graph,
        {
            10001: {0.0: true_curve},
            10002: {0.0: close_curve},
        },
    )

    result = associate_single_episode_nearest_neighbour(
        graph,
        bank,
        config=_config(graph, ambiguity_margin=0.1),
    )

    assert result.training_nearest_catalog_number == 10001
    assert result.training_runner_catalog_number == 10002
    assert result.training_runner_negative_log_score_margin is not None
    assert 0.0 < result.training_runner_negative_log_score_margin < 0.1
    assert result.training_ambiguous_under_descriptive_margin is True
    assert "training-ambiguity-margin-observed" in result.descriptive_diagnostics
    assert result.abstention_recommended is False
    assert result.thresholds_are_descriptive_only is True


def test_prediction_covariance_changes_nearest_candidate() -> None:
    curve = (0.0, 10.0, 20.0, 30.0, 40.0, 50.0)
    residual_a = (1.0, -1.0, 1.0, -1.0, 1.0, -1.0)
    residual_b = (0.2, -0.2, 0.2, -0.2, 0.2, -0.2)
    prediction_a = tuple(
        value - residual for value, residual in zip(curve, residual_a, strict=True)
    )
    prediction_b = tuple(
        value - residual for value, residual in zip(curve, residual_b, strict=True)
    )
    graph = _graph(tuple(50.0 + item for item in curve))
    predictions: dict[int, dict[float, tuple[float, ...]]] = {
        10001: {0.0: prediction_a},
        10002: {0.0: prediction_b},
    }
    high_uncertainty_bank = _bank(
        graph,
        predictions,
        prediction_uncertainty_by_catalog={10001: 0.1, 10002: 10.0},
    )
    low_uncertainty_bank = _bank(
        graph,
        predictions,
        prediction_uncertainty_by_catalog={10001: 0.1, 10002: 0.1},
    )

    high = associate_single_episode_nearest_neighbour(
        graph, high_uncertainty_bank, config=_config(graph)
    )
    low = associate_single_episode_nearest_neighbour(
        graph, low_uncertainty_bank, config=_config(graph)
    )

    assert high.training_nearest_catalog_number == 10001
    assert low.training_nearest_catalog_number == 10002
    high_b = next(item for item in high.scores if item.catalog_number == 10002)
    low_b = next(item for item in low.scores if item.catalog_number == 10002)
    assert high_b.training_innovation.measurement_prediction_standard_uncertainties_hz[0] == (
        pytest.approx(math.hypot(1.0, 10.0))
    )
    assert low_b.training_innovation.measurement_prediction_standard_uncertainties_hz[0] == (
        pytest.approx(math.hypot(1.0, 0.1))
    )


def test_exact_candidate_ties_are_order_invariant_and_abstention_safe() -> None:
    curve = (0.0, 10.0, 20.0, 30.0, 40.0, 50.0)
    graph = _graph(tuple(50.0 + item for item in curve))
    reverse_graph = _graph(tuple(50.0 + item for item in curve), reverse_inputs=True)
    specs: dict[int, dict[float, tuple[float, ...]]] = {
        10002: {0.0: curve},
        10001: {0.0: curve},
    }
    bank = _bank(graph, specs)
    reverse_bank = _bank(reverse_graph, specs, reverse_inputs=True)

    result = associate_single_episode_nearest_neighbour(graph, bank, config=_config(graph))
    reversed_result = associate_single_episode_nearest_neighbour(
        reverse_graph, reverse_bank, config=_config(reverse_graph)
    )

    assert result == reversed_result
    assert result.training_nearest_catalog_number == 10001
    assert result.training_runner_catalog_number == 10002
    assert result.training_exact_tie is True
    assert result.training_exact_tie_tolerance is not None
    assert result.training_runner_negative_log_score_margin == 0.0
    assert result.abstention_recommended is True
    assert "exact-training-tie" in result.abstention_diagnostics


def test_restricted_zero_curve_null_is_explicit_and_can_be_nearest() -> None:
    graph = _graph((50.0,) * 6)
    varying_candidate = (0.0, 10.0, 20.0, 30.0, 40.0, 50.0)
    bank = _bank(graph, {10001: {0.0: varying_candidate}})

    result = associate_single_episode_nearest_neighbour(graph, bank, config=_config(graph))

    assert result.training_nearest_kind == "restricted-zero-curve-null"
    assert result.training_nearest_catalog_number is None
    assert result.restricted_null_selected_on_training is True
    assert result.restricted_null_model == "restricted-zero-curve-plus-shared-offset-v1"
    assert result.abstention_recommended is True
    assert "restricted-zero-curve-null-nearest" in result.abstention_diagnostics


def test_tau_boundary_is_retained_as_structural_abstention_diagnostic() -> None:
    true_curve = (0.0, 10.0, 20.0, 30.0, 40.0, 50.0)
    negative_curve = tuple(-item for item in true_curve)
    very_negative_curve = tuple(-2.0 * item for item in true_curve)
    graph = _graph(tuple(50.0 + item for item in true_curve))
    bank = _bank(
        graph,
        {
            10001: {
                -5.0: very_negative_curve,
                0.0: negative_curve,
                5.0: true_curve,
            }
        },
    )

    result = associate_single_episode_nearest_neighbour(graph, bank, config=_config(graph))

    assert result.training_nearest_catalog_number == 10001
    assert result.scores[0].selected_tau_s == 5.0
    assert result.scores[0].tau_boundary_hit is True
    assert result.tau_boundary_diagnostic is True
    assert result.profiled_tau_state_count == 3
    assert all(item.profiled_tau_state_count == 3 for item in result.scores)
    assert result.abstention_recommended is True
    assert "tau-boundary" in result.abstention_diagnostics


def test_descriptive_nis_threshold_observes_but_does_not_drive_abstention() -> None:
    curve = (0.0, 10.0, 20.0, 30.0, 40.0, 50.0)
    slightly_wrong = (0.0, 9.0, 22.0, 29.0, 42.0, 49.0)
    graph = _graph(tuple(50.0 + item for item in curve))
    bank = _bank(graph, {10001: {0.0: slightly_wrong}})

    result = associate_single_episode_nearest_neighbour(
        graph, bank, config=_config(graph, nis_threshold=1e-6)
    )

    assert result.training_nearest_catalog_number == 10001
    assert result.training_innovation_threshold_exceeded is True
    assert result.heldout_innovation_threshold_exceeded is True
    assert "training-innovation-threshold-exceeded" in result.descriptive_diagnostics
    assert "heldout-innovation-threshold-exceeded" in result.descriptive_diagnostics
    assert result.abstention_recommended is False


def test_unequal_tau_opportunity_is_rejected() -> None:
    curve = (0.0, 10.0, 20.0, 30.0, 40.0, 50.0)
    graph = _graph(tuple(50.0 + item for item in curve))
    tau_states: dict[float, tuple[float, ...]] = {
        -5.0: curve,
        0.0: curve,
        5.0: curve,
    }
    bank = _bank(
        graph,
        {10001: tau_states, 10002: tau_states},
        tau_log_weights_by_catalog={
            10001: {-5.0: 0.0, 0.0: 0.0, 5.0: 0.0},
            10002: {-5.0: -1.0, 0.0: 0.0, 5.0: -1.0},
        },
    )

    with pytest.raises(NearestNeighbourInputError, match="same tau grid and prior"):
        associate_single_episode_nearest_neighbour(graph, bank, config=_config(graph))


def test_response_selection_partition_and_truncation_poison_are_rejected() -> None:
    curve = (0.0, 10.0, 20.0, 30.0, 40.0, 50.0)
    graph = _graph(tuple(50.0 + item for item in curve))
    bank = _bank(graph, {10001: {0.0: curve}})
    config = _config(graph)

    poisoned_response_bank = bank.model_copy(update={"response_accessed": True})
    with pytest.raises(NearestNeighbourInputError, match="response-free"):
        associate_single_episode_nearest_neighbour(graph, poisoned_response_bank, config=config)

    wrong_selection = replace(
        config,
        expected_selection_protocol_digest=_digest("selection-protocol", "wrong"),
    )
    with pytest.raises(NearestNeighbourInputError, match="predeclared"):
        associate_single_episode_nearest_neighbour(graph, bank, config=wrong_selection)

    ids = graph.episodes[0].observation_ids
    nonchronological = replace(
        config,
        training_observation_ids=(ids[0], ids[2]),
        evaluation_observation_ids=(ids[1], ids[3], ids[4], ids[5]),
    )
    with pytest.raises(NearestNeighbourInputError, match="precede"):
        associate_single_episode_nearest_neighbour(graph, bank, config=nonchronological)

    truncated = _bank(
        graph,
        {10001: {0.0: curve}},
        source_candidate_count=2,
    )
    with pytest.raises(NearestNeighbourInputError, match="truncated"):
        associate_single_episode_nearest_neighbour(graph, truncated, config=config)


def test_stale_nested_graph_and_bank_mutations_fail_roundtrip_validation() -> None:
    curve = (0.0, 10.0, 20.0, 30.0, 40.0, 50.0)
    graph = _graph(tuple(50.0 + item for item in curve))
    bank = _bank(graph, {10001: {0.0: curve}})
    config = _config(graph)

    poisoned_observation = graph.observations[0].model_copy(
        update={"measured_cfo_hz": graph.observations[0].measured_cfo_hz + 1.0}
    )
    stale_graph = graph.model_copy(
        update={"observations": (poisoned_observation, *graph.observations[1:])}
    )
    with pytest.raises(NearestNeighbourInputError, match="round-trip closure"):
        associate_single_episode_nearest_neighbour(
            stale_graph,
            bank,
            config=config,
        )

    candidate = bank.candidates[0]
    state = candidate.tau_states[0]
    poisoned_prediction = state.predictions[0].model_copy(
        update={"predicted_cfo_hz": state.predictions[0].predicted_cfo_hz + 1.0}
    )
    stale_state = state.model_copy(
        update={"predictions": (poisoned_prediction, *state.predictions[1:])}
    )
    stale_candidate = candidate.model_copy(update={"tau_states": (stale_state,)})
    stale_bank = bank.model_copy(update={"candidates": (stale_candidate,)})
    with pytest.raises(NearestNeighbourInputError, match="round-trip closure"):
        associate_single_episode_nearest_neighbour(
            graph,
            stale_bank,
            config=config,
        )


def test_tau_prior_normalization_is_shift_stable_and_extreme_range_fails_closed() -> None:
    curve = (0.0, 10.0, 20.0, 30.0, 40.0, 50.0)
    negative = tuple(-item for item in curve)
    very_negative = tuple(-2.0 * item for item in curve)
    graph = _graph(tuple(50.0 + item for item in curve))
    states: dict[float, tuple[float, ...]] = {
        -5.0: very_negative,
        0.0: curve,
        5.0: negative,
    }
    base = _bank(
        graph,
        {10001: states},
        tau_log_weights_by_catalog={10001: {-5.0: 0.0, 0.0: 0.0, 5.0: 0.0}},
    )
    shifted = _bank(
        graph,
        {10001: states},
        tau_log_weights_by_catalog={10001: {-5.0: 1e308, 0.0: 1e308, 5.0: 1e308}},
    )

    base_result = associate_single_episode_nearest_neighbour(graph, base, config=_config(graph))
    shifted_result = associate_single_episode_nearest_neighbour(
        graph, shifted, config=_config(graph)
    )

    assert base_result.scores[0].selected_tau_s == 0.0
    assert shifted_result.scores[0].selected_tau_s == 0.0
    assert base_result.scores[0].tau_negative_log_prior == pytest.approx(math.log(3.0))
    assert shifted_result.scores[0].tau_negative_log_prior == pytest.approx(math.log(3.0))
    assert shifted_result.scores[0].training_total_negative_log_score == pytest.approx(
        base_result.scores[0].training_total_negative_log_score
    )

    extreme = _bank(
        graph,
        {10001: states},
        tau_log_weights_by_catalog={10001: {-5.0: -1e308, 0.0: 1e308, 5.0: -1e308}},
    )
    with pytest.raises(NearestNeighbourNumericalError, match="dynamic range"):
        associate_single_episode_nearest_neighbour(
            graph,
            extreme,
            config=_config(graph),
        )


def test_subnormal_offset_prior_is_stable_when_representable_or_fails_closed() -> None:
    stable = gaussian_innovation_score(
        (1.0, 2.0),
        (1.0, 1.0),
        (0.0, 0.0),
        offset_prior_standard_uncertainty_hz=1e-160,
    )

    assert math.isfinite(stable.offset_posterior_standard_uncertainty_hz)
    assert stable.offset_posterior_standard_uncertainty_hz > 0.0
    assert stable.offset_posterior_standard_uncertainty_hz == pytest.approx(1e-160)

    with pytest.raises(NearestNeighbourNumericalError, match="representably positive"):
        gaussian_innovation_score(
            (1.0, 2.0),
            (1.0, 1.0),
            (0.0, 0.0),
            offset_prior_standard_uncertainty_hz=5e-324,
        )


def test_heldout_exact_tie_is_not_unique_persistence() -> None:
    curve = (0.0, 10.0, 20.0, 30.0, 40.0, 50.0)
    heldout_tied_runner = (-1.0, 10.0, 21.0, 30.0, 40.0, 50.0)
    graph = _graph(tuple(50.0 + item for item in curve))
    bank = _bank(
        graph,
        {
            10001: {0.0: curve},
            10002: {0.0: heldout_tied_runner},
        },
    )

    result = associate_single_episode_nearest_neighbour(
        graph,
        bank,
        config=_config(graph),
    )

    assert result.training_nearest_catalog_number == 10001
    assert result.training_nearest_heldout_rank == 1
    assert result.heldout_nearest_catalog_number == 10001
    assert result.heldout_runner_catalog_number == 10002
    assert result.heldout_exact_tie is True
    assert result.heldout_exact_tie_tolerance is not None
    assert result.heldout_runner_negative_log_score_margin == 0.0
    assert result.training_nearest_persisted_on_heldout is False
    assert "exact-heldout-tie" in result.abstention_diagnostics
    assert result.abstention_recommended is True


def test_restricted_null_configuration_is_exact_zero_and_reported() -> None:
    curve = (0.0, 10.0, 20.0, 30.0, 40.0, 50.0)
    graph = _graph(tuple(50.0 + item for item in curve))
    bank = _bank(graph, {10001: {0.0: curve}})

    with pytest.raises(NearestNeighbourInputError, match="exactly zero"):
        replace(_config(graph), restricted_null_prediction_cfo_hz=1e-300)

    bypassed_config = _config(graph)
    object.__setattr__(bypassed_config, "restricted_null_prediction_cfo_hz", 1.0)
    with pytest.raises(NearestNeighbourInputError, match="round-trip closure"):
        associate_single_episode_nearest_neighbour(
            graph,
            bank,
            config=bypassed_config,
        )

    result = associate_single_episode_nearest_neighbour(
        graph,
        bank,
        config=_config(graph, null_prediction_uncertainty_hz=2.5),
    )
    assert result.restricted_null_prediction_cfo_hz == 0.0
    assert result.restricted_null_prediction_standard_uncertainty_hz == 2.5


def test_tied_tau_boundaries_are_explicit_and_abstention_safe() -> None:
    curve = (0.0, 10.0, 20.0, 30.0, 40.0, 50.0)
    negative = tuple(-item for item in curve)
    graph = _graph(tuple(50.0 + item for item in curve))
    bank = _bank(
        graph,
        {
            10001: {
                -5.0: curve,
                0.0: negative,
                5.0: curve,
            }
        },
    )

    result = associate_single_episode_nearest_neighbour(
        graph,
        bank,
        config=_config(graph),
    )

    winner = result.scores[0]
    assert winner.catalog_number == 10001
    assert winner.selected_tau_s == -5.0
    assert winner.tau_profile_exact_tie is True
    assert winner.tau_profile_exact_tie_tolerance is not None
    assert winner.tau_profile_tied_values_s == (-5.0, 5.0)
    assert winner.tau_profile_boundary_tie is True
    assert result.training_nearest_tau_profile_exact_tie is True
    assert result.training_nearest_tau_profile_boundary_tie is True
    assert "tau-profile-exact-tie" in result.abstention_diagnostics
    assert "tau-profile-boundary-tie" in result.abstention_diagnostics
    assert result.abstention_recommended is True


def test_analyzer_signature_and_imports_exclude_response_and_runtime_boundaries() -> None:
    parameters = inspect.signature(associate_single_episode_nearest_neighbour).parameters
    assert tuple(parameters) == ("graph", "prediction_bank", "config")
    assert not {"truth", "label", "norad", "response"} & set(parameters)

    module_path_text = nearest_module.__file__
    assert module_path_text is not None
    tree = ast.parse(Path(module_path_text).read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert imported_modules <= {
        "__future__",
        "collections.abc",
        "dataclasses",
        "leo.contracts.catalogue_association",
        "leo.contracts.digests",
        "typing",
    }
    source = Path(module_path_text).read_text(encoding="utf-8")
    for forbidden in ("sqlalchemy", "psycopg", "fastapi", "requests", "leo.storage", "leo.cli"):
        assert forbidden not in source
