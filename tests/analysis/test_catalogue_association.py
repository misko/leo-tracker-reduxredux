from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np
import pytest
from pydantic import ValidationError

from leo.analysis import catalogue_association as association_module
from leo.analysis.catalogue_association import (
    HypothesisSearchLimitError,
    associate_catalogue_hypotheses,
    support_integrated_doppler_hz,
)
from leo.contracts.catalogue_association import (
    CandidateObservationPredictionV1,
    CandidateTauStateV1,
    CatalogueAssociationConfigV1,
    CatalogueAssociationResultV1,
    CatalogueCandidatePredictionV1,
    CataloguePredictionBankV1,
    CataloguePredictionSupportObservationV1,
    CataloguePredictionSupportV1,
    CatalogueVerifiedTleMemberV1,
    PhysicalCfoEpisodeV1,
    PhysicalEpisodeGraphV1,
    SupportIntegratedCfoObservationV1,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.sky import DopplerPolynomialV1, ObserverSiteV1, TleSnapshotRefV1

_BASE_UTC_NS = 1_800_000_000_000_000_000


def _digest(kind: str, identity: object) -> str:
    return canonical_digest({kind: identity})


def _curve_one(local_time_s: float) -> float:
    return -35.0 * local_time_s + 5.0 * local_time_s**2


def _curve_two(local_time_s: float) -> float:
    return 18.0 * local_time_s - 4.0 * local_time_s**2


def _curve_distractor(local_time_s: float) -> float:
    return -8.0 * local_time_s + 0.25 * local_time_s**2


_CURVES: dict[int, Callable[[float], float]] = {
    10001: _curve_one,
    10002: _curve_two,
    10003: _curve_distractor,
}


def _graph(
    labels: tuple[int | None, ...],
    *,
    hardware_drift_hz_per_s: float = 2.0,
    replica_groups: dict[int, str] | None = None,
    exclusion_groups: dict[int, tuple[str, ...]] | None = None,
    reverse_inputs: bool = False,
) -> PhysicalEpisodeGraphV1:
    replica_groups = {} if replica_groups is None else replica_groups
    exclusion_groups = {} if exclusion_groups is None else exclusion_groups
    observations = []
    episodes = []
    global_reference_s = (len(labels) * 6.0) / 2.0
    for episode_index, label in enumerate(labels):
        episode_id = _digest("episode", episode_index)
        observation_ids = []
        for sample_index, local_time_s in enumerate((-1.5, -0.5, 0.5, 1.5)):
            absolute_time_s = episode_index * 6.0 + local_time_s + 1.5
            center_utc_ns = _BASE_UTC_NS + round(absolute_time_s * 1e9)
            observation_id = _digest("observation", (episode_index, sample_index))
            source_curve = 0.0 if label is None else _CURVES[label](local_time_s)
            deterministic_noise = (-0.15, 0.05, -0.05, 0.15)[sample_index]
            measured_cfo_hz = (
                100_000.0
                + episode_index * 200.0
                + source_curve
                + hardware_drift_hz_per_s * (absolute_time_s - global_reference_s)
                + deterministic_noise
            )
            observations.append(
                SupportIntegratedCfoObservationV1(
                    observation_id=observation_id,
                    source_group_id=_digest("source-group", (episode_index, sample_index)),
                    episode_id=episode_id,
                    receiver_path_id=_digest("receiver-path", episode_index),
                    hardware_epoch_id="receiver-a",
                    raw_recording_authority_digest=_digest("raw-recording-authority", "synthetic"),
                    recording_manifest_digest=_digest("recording-manifest", "synthetic"),
                    stream_id="stream-1",
                    source_binding_digest=_digest("source-binding", (episode_index, sample_index)),
                    source_sample_start=(episode_index * 10 + sample_index) * 100,
                    source_sample_end=(episode_index * 10 + sample_index) * 100 + 50,
                    support_start_utc_ns=center_utc_ns - 10_000_000,
                    support_center_utc_ns=center_utc_ns,
                    support_end_utc_ns=center_utc_ns + 10_000_000,
                    measured_cfo_hz=measured_cfo_hz,
                    standard_uncertainty_hz=1.0,
                    factorial_support_moments_s=(1.0, 0.0, 0.000_016_666_666_7, 0.0),
                )
            )
            observation_ids.append(observation_id)
        episodes.append(
            PhysicalCfoEpisodeV1(
                episode_id=episode_id,
                dwell_id=_digest("dwell", episode_index),
                lane_id=_digest("lane", "sequential"),
                order_index=episode_index,
                continuity_component_id=_digest("component", episode_index),
                observation_ids=tuple(observation_ids),
                replica_group_id=(
                    None
                    if episode_index not in replica_groups
                    else _digest("replica", replica_groups[episode_index])
                ),
                exclusion_group_ids=tuple(
                    sorted(
                        _digest("exclusion", item)
                        for item in exclusion_groups.get(episode_index, ())
                    )
                ),
            )
        )
    if reverse_inputs:
        observations.reverse()
        episodes.reverse()
    return PhysicalEpisodeGraphV1.create(
        observations=tuple(observations),
        episodes=tuple(episodes),
    )


def _bank(
    graph: PhysicalEpisodeGraphV1,
    *,
    candidate_numbers: tuple[int, ...],
    identical_candidates: bool = False,
    eligible_by_candidate: dict[int, set[str]] | None = None,
    reverse_inputs: bool = False,
    source_candidate_count: int | None = None,
) -> CataloguePredictionBankV1:
    eligible_by_candidate = {} if eligible_by_candidate is None else eligible_by_candidate
    episode_by_id = {item.episode_id: item for item in graph.episodes}
    candidates = []
    for catalog_number in candidate_numbers:
        eligible_episode_ids = eligible_by_candidate.get(
            catalog_number,
            set(episode_by_id),
        )
        curve = _curve_one if identical_candidates else _CURVES[catalog_number]
        predictions = []
        for episode_id in eligible_episode_ids:
            episode = episode_by_id[episode_id]
            centers = [
                next(
                    observation.support_center_utc_ns
                    for observation in graph.observations
                    if observation.observation_id == observation_id
                )
                for observation_id in episode.observation_ids
            ]
            episode_center = (centers[0] + centers[-1]) / 2.0
            for observation_id, center_utc_ns in zip(
                episode.observation_ids,
                centers,
                strict=True,
            ):
                local_time_s = (center_utc_ns - episode_center) / 1e9
                predictions.append(
                    CandidateObservationPredictionV1(
                        observation_id=observation_id,
                        predicted_cfo_hz=curve(local_time_s),
                        standard_uncertainty_hz=0.2,
                    )
                )
        candidates.append(
            CatalogueCandidatePredictionV1(
                catalog_number=catalog_number,
                object_name=f"STARLINK-{catalog_number}",
                selected_element_digest=_digest("element", catalog_number),
                element_epoch_utc_ns=_BASE_UTC_NS - 20 * 3_600 * 1_000_000_000,
                element_age_s_at_reference=20 * 3_600.0,
                eligible_episode_ids=tuple(sorted(eligible_episode_ids)),
                tau_states=(
                    CandidateTauStateV1(
                        tau_s=0.0,
                        log_prior_weight=0.0,
                        predictions=tuple(
                            sorted(predictions, key=lambda item: item.observation_id)
                        ),
                    ),
                ),
            )
        )
    if reverse_inputs:
        candidates.reverse()
    return CataloguePredictionBankV1.create(
        support=CataloguePredictionSupportV1.from_graph(graph),
        tle_snapshot=TleSnapshotRefV1(
            provider="space-track",
            collected_utc_ns=_BASE_UTC_NS - 3_600 * 1_000_000_000,
            digest=_digest("tle-snapshot", "synthetic"),
            object_count=10_972,
        ),
        observer_site=ObserverSiteV1(
            latitude_deg=37.0,
            longitude_deg=-122.0,
            altitude_m=10.0,
            label="synthetic-known-site",
        ),
        nominal_rf_hz=11_325_000_000.0,
        selection_protocol_digest=_digest("selection-protocol", "synthetic"),
        selection_policy_digest=_digest("selection-policy", "synthetic"),
        tle_membership_authority_digest=_digest("tle-membership-authority", "synthetic"),
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
    )


def _config(**updates: object) -> CatalogueAssociationConfigV1:
    values: dict[str, object] = {
        "active_count_log_weights": (0.0, -3.0, -6.0),
        "assigned_episode_log_weight": 0.0,
        "unassigned_episode_log_weight": 0.0,
        "same_state_log_weight": 0.0,
        "handoff_log_weight": -0.5,
        "component_offset_prior_sigma_hz": 1_000_000.0,
        "hardware_drift_prior_sigma_hz_per_s": 20.0,
        "maximum_evaluated_hypotheses": 1_000_000,
        "reported_hypothesis_limit": 256,
        "maximum_normal_condition_number": 1e15,
    }
    values.update(updates)
    return CatalogueAssociationConfigV1.model_validate(values)


def _zero_prediction_bank(
    graph: PhysicalEpisodeGraphV1,
    candidate_numbers: tuple[int, ...],
    *,
    eligible_by_candidate: dict[int, set[str]] | None = None,
) -> CataloguePredictionBankV1:
    bank = _bank(
        graph,
        candidate_numbers=candidate_numbers,
        eligible_by_candidate=eligible_by_candidate,
    )
    candidates = tuple(
        candidate.model_copy(
            update={
                "tau_states": tuple(
                    state.model_copy(
                        update={
                            "predictions": tuple(
                                prediction.model_copy(
                                    update={
                                        "predicted_cfo_hz": 0.0,
                                        "standard_uncertainty_hz": 0.0,
                                    }
                                )
                                for prediction in state.predictions
                            )
                        }
                    )
                    for state in candidate.tau_states
                )
            }
        )
        for candidate in bank.candidates
    )
    return CataloguePredictionBankV1.create(
        support=CataloguePredictionSupportV1.from_graph(graph),
        tle_snapshot=bank.tle_snapshot,
        observer_site=bank.observer_site,
        nominal_rf_hz=bank.nominal_rf_hz,
        selection_protocol_digest=bank.selection_protocol_digest,
        selection_policy_digest=bank.selection_policy_digest,
        tle_membership_authority_digest=bank.tle_membership_authority_digest,
        verified_tle_members=bank.verified_tle_members,
        propagation_model=bank.propagation_model,
        candidates=candidates,
    )


def _map_assignments(result: CatalogueAssociationResultV1) -> tuple[int | None, ...]:
    return tuple(item.catalog_number for item in result.hypotheses[0].assignments)


def test_radio_only_null_wins_without_catalogue_curvature() -> None:
    graph = _graph((None, None, None, None))
    result = associate_catalogue_hypotheses(
        graph,
        _bank(graph, candidate_numbers=(10001,)),
        config=_config(maximum_active_satellites=1),
    )

    assert result.hypotheses[0].active_catalog_numbers == ()
    assert result.active_count_posterior[0].posterior_probability > 0.99
    assert result.identity_claimed is False


def test_single_satellite_ten_episode_fragments_pool_to_one_mode() -> None:
    graph = _graph((10001,) * 10, hardware_drift_hz_per_s=3.0)
    result = associate_catalogue_hypotheses(
        graph,
        _bank(graph, candidate_numbers=(10001, 10003)),
        config=_config(),
    )

    best = result.hypotheses[0]
    assert best.active_catalog_numbers == (10001,)
    assert _map_assignments(result) == (10001,) * 10
    assert best.hardware_drifts[0].mean_hz_per_s == pytest.approx(3.0, abs=0.15)
    assert result.active_count_posterior[1].posterior_probability > 0.99


def test_exact_two_satellite_model_recovers_eight_two_minority_mix() -> None:
    labels = (10001,) * 8 + (10002,) * 2
    graph = _graph(labels)
    result = associate_catalogue_hypotheses(
        graph,
        _bank(graph, candidate_numbers=(10001, 10002)),
        config=_config(),
    )

    assert result.hypotheses[0].active_catalog_numbers == (10001, 10002)
    assert _map_assignments(result) == labels
    assert result.active_count_posterior[2].posterior_probability > 0.99


def test_five_five_mix_is_not_majority_voted_into_one_satellite() -> None:
    labels = (10001, 10002) * 5
    graph = _graph(labels)
    result = associate_catalogue_hypotheses(
        graph,
        _bank(graph, candidate_numbers=(10001, 10002)),
        config=_config(),
    )

    assert result.hypotheses[0].active_catalog_numbers == (10001, 10002)
    assert _map_assignments(result) == labels


def test_unmodeled_episode_remains_unassigned_instead_of_forcing_identity() -> None:
    graph = _graph((10001, 10001, None))
    result = associate_catalogue_hypotheses(
        graph,
        _bank(graph, candidate_numbers=(10001,)),
        config=_config(maximum_active_satellites=1),
    )

    assert result.hypotheses[0].active_catalog_numbers == (10001,)
    assert _map_assignments(result) == (10001, 10001, None)


def test_close_identical_candidates_preserve_ambiguity_and_deterministic_tie() -> None:
    graph = _graph((10001,) * 4)
    result = associate_catalogue_hypotheses(
        graph,
        _bank(
            graph,
            candidate_numbers=(10001, 10002),
            identical_candidates=True,
        ),
        config=_config(maximum_active_satellites=1),
    )

    presence = {
        item.catalog_number: item.posterior_probability
        for item in result.catalogue_presence_posterior
    }
    assert presence[10001] == pytest.approx(presence[10002], abs=1e-12)
    assert result.hypotheses[0].active_catalog_numbers == (10001,)
    assert result.identity_claimed is False


def test_replica_and_simultaneous_exclusion_constraints_apply_to_every_mode() -> None:
    replica_graph = _graph(
        (10001, 10001, 10002),
        replica_groups={0: "same-emission", 1: "same-emission"},
    )
    replica_result = associate_catalogue_hypotheses(
        replica_graph,
        _bank(replica_graph, candidate_numbers=(10001, 10002)),
        config=_config(),
    )
    assert all(
        mode.assignments[0].catalog_number == mode.assignments[1].catalog_number
        for mode in replica_result.hypotheses
    )

    exclusion_graph = _graph(
        (10001, 10002),
        exclusion_groups={0: ("simultaneous",), 1: ("simultaneous",)},
    )
    exclusion_result = associate_catalogue_hypotheses(
        exclusion_graph,
        _bank(exclusion_graph, candidate_numbers=(10001, 10002)),
        config=_config(),
    )
    assert exclusion_result.hypotheses[0].active_catalog_numbers == (10001, 10002)
    assert _map_assignments(exclusion_result) == (10001, 10002)
    assert all(
        not (
            mode.assignments[0].catalog_number is not None
            and mode.assignments[0].catalog_number == mode.assignments[1].catalog_number
        )
        for mode in exclusion_result.hypotheses
    )


def test_input_order_is_canonical_and_byte_deterministic() -> None:
    labels = (10001, 10002, 10001)
    first_graph = _graph(labels)
    second_graph = _graph(labels, reverse_inputs=True)
    first_bank = _bank(first_graph, candidate_numbers=(10001, 10002))
    second_bank = _bank(
        second_graph,
        candidate_numbers=(10001, 10002),
        reverse_inputs=True,
    )

    first = associate_catalogue_hypotheses(first_graph, first_bank, config=_config())
    second = associate_catalogue_hypotheses(second_graph, second_bank, config=_config())

    assert first_graph.model_dump_json() == second_graph.model_dump_json()
    assert first_bank.model_dump_json() == second_bank.model_dump_json()
    assert first.model_dump_json() == second.model_dump_json()


def test_truncated_or_incomplete_bank_and_work_overflow_fail_closed() -> None:
    graph = _graph((10001, 10002, 10001))
    truncated_bank = _bank(
        graph,
        candidate_numbers=(10001, 10002),
        source_candidate_count=3,
    )
    with pytest.raises(ValueError, match="truncated candidate bank"):
        associate_catalogue_hypotheses(graph, truncated_bank, config=_config())

    with pytest.raises(HypothesisSearchLimitError, match="configured limit"):
        associate_catalogue_hypotheses(
            graph,
            _bank(graph, candidate_numbers=(10001, 10002)),
            config=_config(maximum_evaluated_hypotheses=2),
        )

    bank_document = _bank(graph, candidate_numbers=(10001,)).model_dump(mode="python")
    predictions = bank_document["candidates"][0]["tau_states"][0]["predictions"]
    bank_document["candidates"][0]["tau_states"][0]["predictions"] = predictions[:-1]
    bank_document["content_digest"] = canonical_digest(
        {key: value for key, value in bank_document.items() if key != "content_digest"}
    )
    with pytest.raises(ValidationError, match="exact response-free support"):
        CataloguePredictionBankV1.model_validate(bank_document)


def test_contract_digest_is_tamper_evident() -> None:
    graph = _graph((10001, 10001))
    document = graph.model_dump(mode="python")
    document["observations"][0]["measured_cfo_hz"] += 1.0
    with pytest.raises(ValidationError, match="digest does not match"):
        PhysicalEpisodeGraphV1.model_validate(document)

    bank = _bank(graph, candidate_numbers=(10001,))
    bank_document = bank.model_dump(mode="python", exclude={"content_digest"})
    bank_document["candidates"][0]["selected_element_digest"] = _digest(
        "substituted-element", 10001
    )
    bank_document["content_digest"] = canonical_digest(bank_document)
    with pytest.raises(ValidationError, match="verified TLE membership inventory"):
        CataloguePredictionBankV1.model_validate(bank_document)

    bank_document["verified_tle_members"][0]["selected_element_digest"] = _digest(
        "substituted-element", 10001
    )
    bank_document["content_digest"] = canonical_digest(bank_document)
    with pytest.raises(ValidationError, match="candidate universe digest"):
        CataloguePredictionBankV1.model_validate(bank_document)

    with pytest.raises(ValidationError, match="strictly pre-measurement"):
        CataloguePredictionBankV1.create(
            support=bank.support,
            tle_snapshot=bank.tle_snapshot.model_copy(
                update={
                    "collected_utc_ns": min(
                        item.support_start_utc_ns for item in bank.support.observations
                    )
                }
            ),
            observer_site=bank.observer_site,
            nominal_rf_hz=bank.nominal_rf_hz,
            selection_protocol_digest=bank.selection_protocol_digest,
            selection_policy_digest=bank.selection_policy_digest,
            tle_membership_authority_digest=bank.tle_membership_authority_digest,
            verified_tle_members=bank.verified_tle_members,
            propagation_model=bank.propagation_model,
            candidates=bank.candidates,
        )

    stale_age_candidate = bank.candidates[0].model_copy(update={"element_age_s_at_reference": 1.0})
    with pytest.raises(ValidationError, match="element age"):
        CataloguePredictionBankV1.create(
            support=bank.support,
            tle_snapshot=bank.tle_snapshot,
            observer_site=bank.observer_site,
            nominal_rf_hz=bank.nominal_rf_hz,
            selection_protocol_digest=bank.selection_protocol_digest,
            selection_policy_digest=bank.selection_policy_digest,
            tle_membership_authority_digest=bank.tle_membership_authority_digest,
            verified_tle_members=bank.verified_tle_members,
            propagation_model=bank.propagation_model,
            candidates=(stale_age_candidate,),
        )


def test_conjugate_evidence_matches_direct_marginal_gaussian() -> None:
    graph = _graph((None, None), hardware_drift_hz_per_s=1.25)
    config = _config(
        maximum_active_satellites=0,
        component_offset_prior_sigma_hz=1_000.0,
    )
    result = associate_catalogue_hypotheses(
        graph,
        _bank(graph, candidate_numbers=()),
        config=config,
    )

    component_ids = tuple(sorted({episode.continuity_component_id for episode in graph.episodes}))
    component_index = {identity: index for index, identity in enumerate(component_ids)}
    hardware_ids = tuple(sorted({item.hardware_epoch_id for item in graph.observations}))
    hardware_reference = {
        identity: sum(
            item.support_center_utc_ns
            for item in graph.observations
            if item.hardware_epoch_id == identity
        )
        // sum(1 for item in graph.observations if item.hardware_epoch_id == identity)
        for identity in hardware_ids
    }
    episode_by_id = {episode.episode_id: episode for episode in graph.episodes}
    design = np.zeros(
        (len(graph.observations), len(component_ids) + len(hardware_ids)),
        dtype=np.float64,
    )
    for row, observation in enumerate(graph.observations):
        episode = episode_by_id[observation.episode_id]
        design[row, component_index[episode.continuity_component_id]] = 1.0
        design[row, len(component_ids)] = (
            observation.support_center_utc_ns - hardware_reference[observation.hardware_epoch_id]
        ) / 1e9
    prior = np.diag(
        [config.component_offset_prior_sigma_hz**2] * len(component_ids)
        + [config.hardware_drift_prior_sigma_hz_per_s**2] * len(hardware_ids)
    )
    measurement_covariance = np.diag(
        [item.standard_uncertainty_hz**2 for item in graph.observations]
    )
    marginal_covariance = measurement_covariance + design @ prior @ design.T
    observed = np.asarray([item.measured_cfo_hz for item in graph.observations], dtype=np.float64)
    sign, log_determinant = np.linalg.slogdet(marginal_covariance)
    assert sign == 1.0
    direct_negative_log_evidence = 0.5 * (
        observed @ np.linalg.solve(marginal_covariance, observed)
        + log_determinant
        + observed.size * math.log(2.0 * math.pi)
    )

    assert result.hypotheses[0].data_negative_log_evidence == pytest.approx(
        direct_negative_log_evidence,
        rel=1e-7,
        abs=1e-7,
    )


def test_normalized_priors_prevent_catalogue_and_assignment_count_bias() -> None:
    graph = _graph((None, None))
    requested = (math.log(0.2), math.log(0.3), math.log(0.5))
    result = associate_catalogue_hypotheses(
        graph,
        _zero_prediction_bank(graph, (10001, 10002, 10003)),
        config=_config(
            active_count_log_weights=requested,
            handoff_log_weight=0.0,
        ),
    )

    posterior = {
        item.active_count: item.posterior_probability for item in result.active_count_posterior
    }
    assert posterior == pytest.approx({0: 0.2, 1: 0.3, 2: 0.5}, abs=1e-10)
    assert result.null_model == "zero-curve-component-offset-hardware-drift-v1"


def test_support_integration_uses_aperture_center_and_exact_cubic_moments() -> None:
    center_utc_ns = _BASE_UTC_NS + 2_000_000_000
    half_width_s = 0.01
    observation = CataloguePredictionSupportObservationV1(
        observation_id=_digest("integration-observation", 1),
        episode_id=_digest("integration-episode", 1),
        support_start_utc_ns=center_utc_ns - 10_000_000,
        support_center_utc_ns=center_utc_ns,
        support_end_utc_ns=center_utc_ns + 10_000_000,
        factorial_support_moments_s=(
            1.0,
            0.0,
            half_width_s**2 / 6.0,
            0.0,
        ),
    )
    polynomial = DopplerPolynomialV1(
        degree=3,
        reference_utc_ns=_BASE_UTC_NS,
        downlink_frequency_hz=11_325_000_000.0,
        frequency_at_reference_hz=1_000.0,
        slope_hz_s=-3_500.0,
        acceleration_hz_s2=12.0,
        jerk_hz_s3=3.0,
        residual_rms_hz=1.0,
    )
    center_s = 2.0
    expected = (
        1_000.0
        - 3_500.0 * center_s
        + 12.0 * center_s**2 / 2.0
        + 3.0 * center_s**3 / 6.0
        + (12.0 + 3.0 * center_s) * half_width_s**2 / 6.0
    )

    assert support_integrated_doppler_hz(observation, polynomial) == pytest.approx(
        expected,
        abs=1e-12,
    )
    start_stamped_value = (
        1_000.0
        - 3_500.0 * (center_s - half_width_s)
        + 12.0 * (center_s - half_width_s) ** 2 / 2.0
        + 3.0 * (center_s - half_width_s) ** 3 / 6.0
    )
    assert abs(start_stamped_value - expected) > 34.0


def test_work_cap_fails_before_exponential_assignment_materialization() -> None:
    graph = _graph((None,) * 30)
    with pytest.raises(HypothesisSearchLimitError, match="enumeration bound"):
        associate_catalogue_hypotheses(
            graph,
            _zero_prediction_bank(graph, (10001,)),
            config=_config(
                maximum_active_satellites=1,
                maximum_evaluated_hypotheses=1_000,
            ),
        )


def test_active_count_prior_is_conditioned_on_feasible_constraint_family() -> None:
    graph = _graph(
        (None, None),
        replica_groups={0: "one-physical-emission", 1: "one-physical-emission"},
    )
    result = associate_catalogue_hypotheses(
        graph,
        _zero_prediction_bank(
            graph,
            (10001, 10002),
            eligible_by_candidate={10002: {graph.episodes[0].episode_id}},
        ),
        config=_config(
            active_count_log_weights=(math.log(0.2), math.log(0.3), math.log(0.5)),
            handoff_log_weight=0.0,
        ),
    )

    posterior = {
        item.active_count: item.posterior_probability for item in result.active_count_posterior
    }
    assert posterior == pytest.approx({0: 0.4, 1: 0.6, 2: 0.0}, abs=1e-10)


def test_marginal_evidence_is_stable_for_large_cfo_and_weak_prior() -> None:
    residual = np.asarray([1e18], dtype=np.float64)
    variance = np.asarray([1.0], dtype=np.float64)
    layout = association_module._NuisanceLayout(
        design=np.asarray([[1.0]], dtype=np.float64),
        prior_variances=np.asarray([1e32], dtype=np.float64),
        component_ids=(_digest("component", "large-scale"),),
        hardware_ids=(),
        hardware_reference_utc_ns=(),
    )

    evidence = association_module._marginal_evidence(
        residual=residual,
        variance=variance,
        layout=layout,
        maximum_condition_number=1e15,
    )
    marginal_variance = 1.0 + 1e32
    expected = 0.5 * (
        1e36 / marginal_variance + math.log(marginal_variance) + math.log(2.0 * math.pi)
    )

    assert evidence.negative_log_evidence == pytest.approx(expected, rel=1e-12)


def test_support_moments_must_be_possible_for_declared_interval() -> None:
    values = {
        "observation_id": _digest("moment-observation", 1),
        "source_group_id": _digest("moment-source", 1),
        "episode_id": _digest("moment-episode", 1),
        "receiver_path_id": _digest("moment-path", 1),
        "hardware_epoch_id": "receiver-a",
        "raw_recording_authority_digest": _digest("moment-raw-authority", 1),
        "recording_manifest_digest": _digest("moment-manifest", 1),
        "stream_id": "stream-1",
        "source_binding_digest": _digest("moment-binding", 1),
        "source_sample_start": 0,
        "source_sample_end": 100,
        "support_start_utc_ns": _BASE_UTC_NS,
        "support_center_utc_ns": _BASE_UTC_NS + 2_000_000,
        "support_end_utc_ns": _BASE_UTC_NS + 10_000_000,
        "measured_cfo_hz": 0.0,
        "standard_uncertainty_hz": 1.0,
        "factorial_support_moments_s": (1.0, 0.0, 0.000_015, 0.0),
    }
    with pytest.raises(ValidationError, match="second support moment"):
        SupportIntegratedCfoObservationV1.model_validate(values)

    values["factorial_support_moments_s"] = (1.0, 0.0, 0.0, 1e-6)
    with pytest.raises(ValidationError, match="third support moment"):
        SupportIntegratedCfoObservationV1.model_validate(values)

    values["factorial_support_moments_s"] = (1.0, 0.0, 0.0, 1e-8)
    with pytest.raises(ValidationError, match="inconsistent with the second"):
        SupportIntegratedCfoObservationV1.model_validate(values)

    values["support_center_utc_ns"] = _BASE_UTC_NS + 10_000_000
    values["support_end_utc_ns"] = _BASE_UTC_NS + 20_000_000
    values["factorial_support_moments_s"] = (1.0, 0.0, 0.000_05, 1e-8 / 6.0)
    with pytest.raises(ValidationError, match="bounded support moment sequence"):
        SupportIntegratedCfoObservationV1.model_validate(values)


def test_prediction_support_port_excludes_response_values() -> None:
    graph = _graph((10001,))
    support = CataloguePredictionSupportV1.from_graph(graph)
    dumped = support.model_dump(mode="json")
    serialized = repr(dumped)

    assert "measured_cfo_hz" not in serialized
    assert "standard_uncertainty_hz" not in serialized
    assert "receiver_path_id" not in serialized
    assert "hardware_epoch_id" not in serialized

    changed_graph = PhysicalEpisodeGraphV1.create(
        observations=tuple(
            item.model_copy(update={"measured_cfo_hz": item.measured_cfo_hz + 1_000.0})
            for item in graph.observations
        ),
        episodes=graph.episodes,
    )
    assert changed_graph.content_digest != graph.content_digest
    assert CataloguePredictionSupportV1.from_graph(changed_graph).content_digest == (
        support.content_digest
    )

    poisoned = support.model_dump(mode="python")
    poisoned["observations"][0]["measured_cfo_hz"] = 123.0
    with pytest.raises(ValidationError, match="Extra inputs"):
        CataloguePredictionSupportV1.model_validate(poisoned)


def test_diagonal_error_contract_rejects_rewrapped_overlapping_source_apertures() -> None:
    graph = _graph((10001,))
    observations = list(graph.observations)
    first = observations[0]
    observations[1] = observations[1].model_copy(
        update={
            "source_sample_start": first.source_sample_start,
            "source_sample_end": first.source_sample_end,
            "source_binding_digest": _digest("rewrapped-binding", 2),
            "recording_manifest_digest": _digest("rewrapped-manifest", 2),
        }
    )

    with pytest.raises(ValueError, match="overlapping source spans"):
        PhysicalEpisodeGraphV1.create(
            observations=tuple(observations),
            episodes=graph.episodes,
        )


def test_source_sample_order_must_agree_with_support_chronology() -> None:
    graph = _graph((10001,))
    observations = list(graph.observations)
    first_start = observations[0].source_sample_start
    first_end = observations[0].source_sample_end
    second_start = observations[1].source_sample_start
    second_end = observations[1].source_sample_end
    observations[0] = observations[0].model_copy(
        update={"source_sample_start": second_start, "source_sample_end": second_end}
    )
    observations[1] = observations[1].model_copy(
        update={"source_sample_start": first_start, "source_sample_end": first_end}
    )

    with pytest.raises(ValueError, match="sample order must follow"):
        PhysicalEpisodeGraphV1.create(
            observations=tuple(observations),
            episodes=graph.episodes,
        )


def test_episode_markov_order_must_follow_support_chronology() -> None:
    graph = _graph((10001, 10001, 10002))
    episodes = tuple(
        episode.model_copy(
            update={
                "order_index": (
                    2
                    if episode.order_index == 0
                    else 0
                    if episode.order_index == 2
                    else episode.order_index
                )
            }
        )
        for episode in graph.episodes
    )

    with pytest.raises(ValueError, match="support chronology"):
        PhysicalEpisodeGraphV1.create(
            observations=graph.observations,
            episodes=episodes,
        )


def test_rank_one_tau_boundary_forces_partial_abstention() -> None:
    graph = _graph((10001,), hardware_drift_hz_per_s=0.0)
    bank = _bank(graph, candidate_numbers=(10001,))
    correct_state = bank.candidates[0].tau_states[0]
    distractor_predictions = tuple(
        prediction.model_copy(update={"predicted_cfo_hz": _curve_distractor(local_time_s)})
        for prediction, local_time_s in zip(
            correct_state.predictions,
            (-1.5, -0.5, 0.5, 1.5),
            strict=True,
        )
    )
    candidate = bank.candidates[0].model_copy(
        update={
            "tau_states": (
                CandidateTauStateV1(
                    tau_s=-5.0,
                    log_prior_weight=0.0,
                    predictions=distractor_predictions,
                ),
                CandidateTauStateV1(
                    tau_s=0.0,
                    log_prior_weight=0.0,
                    predictions=distractor_predictions,
                ),
                CandidateTauStateV1(
                    tau_s=5.0,
                    log_prior_weight=0.0,
                    predictions=correct_state.predictions,
                ),
            )
        }
    )
    boundary_bank = CataloguePredictionBankV1.create(
        support=CataloguePredictionSupportV1.from_graph(graph),
        tle_snapshot=bank.tle_snapshot,
        observer_site=bank.observer_site,
        nominal_rf_hz=bank.nominal_rf_hz,
        selection_protocol_digest=bank.selection_protocol_digest,
        selection_policy_digest=bank.selection_policy_digest,
        tle_membership_authority_digest=bank.tle_membership_authority_digest,
        verified_tle_members=bank.verified_tle_members,
        propagation_model=bank.propagation_model,
        candidates=(candidate,),
        tau_search_policy="bounded-profile-minus5-plus5-v1",
    )

    result = associate_catalogue_hypotheses(
        graph,
        boundary_bank,
        config=_config(
            maximum_active_satellites=1,
            active_count_log_weights=(-20.0, 0.0, -20.0),
        ),
    )

    assert result.hypotheses[0].tau_choices[0].tau_s == 5.0
    assert result.hypotheses[0].tau_boundary_hit is True
    assert result.tau_boundary_abstention is True
    assert result.status.value == "partial"
    assert "without widening" in result.reason

    truncated_candidate = bank.candidates[0].model_copy(
        update={
            "tau_states": (
                correct_state.model_copy(update={"tau_s": 0.0}),
                correct_state.model_copy(update={"tau_s": 1.0}),
            )
        }
    )
    with pytest.raises(ValidationError, match=r"close the exact \[-5,\+5\]"):
        CataloguePredictionBankV1.create(
            support=CataloguePredictionSupportV1.from_graph(graph),
            tle_snapshot=bank.tle_snapshot,
            observer_site=bank.observer_site,
            nominal_rf_hz=bank.nominal_rf_hz,
            selection_protocol_digest=bank.selection_protocol_digest,
            selection_policy_digest=bank.selection_policy_digest,
            tle_membership_authority_digest=bank.tle_membership_authority_digest,
            verified_tle_members=bank.verified_tle_members,
            propagation_model=bank.propagation_model,
            candidates=(truncated_candidate,),
            tau_search_policy="bounded-profile-minus5-plus5-v1",
        )


def test_active_set_cap_fails_before_catalogue_combinations_are_materialized() -> None:
    graph = _graph((None,))
    candidate_numbers = tuple(range(20_000, 20_100))
    bank = _bank(
        graph,
        candidate_numbers=candidate_numbers,
        identical_candidates=True,
    )

    with pytest.raises(HypothesisSearchLimitError, match="active-set inventory"):
        associate_catalogue_hypotheses(
            graph,
            bank,
            config=_config(maximum_evaluated_hypotheses=1_000),
        )


def test_small_exact_family_matches_independent_combinatorial_oracle() -> None:
    graph = _graph((None, None))
    result = associate_catalogue_hypotheses(
        graph,
        _zero_prediction_bank(graph, (10001, 10002)),
        config=_config(handoff_log_weight=0.0),
    )

    modes = {
        (
            mode.active_catalog_numbers,
            tuple(item.catalog_number for item in mode.assignments),
        )
        for mode in result.hypotheses
    }
    expected = {
        ((), (None, None)),
        ((10001,), (10001, None)),
        ((10001,), (None, 10001)),
        ((10001,), (10001, 10001)),
        ((10002,), (10002, None)),
        ((10002,), (None, 10002)),
        ((10002,), (10002, 10002)),
        ((10001, 10002), (10001, 10002)),
        ((10001, 10002), (10002, 10001)),
    }

    assert result.evaluated_hypothesis_count == 9
    assert modes == expected


def test_tau_prior_is_normalized_within_candidate_hypothesis() -> None:
    graph = _graph((10001,), hardware_drift_hz_per_s=0.0)
    bank = _bank(graph, candidate_numbers=(10001,))
    state = bank.candidates[0].tau_states[0]
    candidate = bank.candidates[0].model_copy(
        update={
            "tau_states": (
                state.model_copy(update={"tau_s": -5.0, "log_prior_weight": math.log(0.1)}),
                state.model_copy(update={"tau_s": 0.0, "log_prior_weight": math.log(0.8)}),
                state.model_copy(update={"tau_s": 5.0, "log_prior_weight": math.log(0.1)}),
            )
        }
    )
    two_tau_bank = CataloguePredictionBankV1.create(
        support=CataloguePredictionSupportV1.from_graph(graph),
        tle_snapshot=bank.tle_snapshot,
        observer_site=bank.observer_site,
        nominal_rf_hz=bank.nominal_rf_hz,
        selection_protocol_digest=bank.selection_protocol_digest,
        selection_policy_digest=bank.selection_policy_digest,
        tle_membership_authority_digest=bank.tle_membership_authority_digest,
        verified_tle_members=bank.verified_tle_members,
        propagation_model=bank.propagation_model,
        candidates=(candidate,),
        tau_search_policy="bounded-profile-minus5-plus5-v1",
    )
    result = associate_catalogue_hypotheses(
        graph,
        two_tau_bank,
        config=_config(
            maximum_active_satellites=1,
            active_count_log_weights=(-20.0, 0.0, -20.0),
        ),
    )

    assigned_modes = tuple(
        mode for mode in result.hypotheses if mode.active_catalog_numbers == (10001,)
    )
    probability_by_tau = {
        mode.tau_choices[0].tau_s: mode.posterior_probability for mode in assigned_modes
    }
    conditional_total = sum(probability_by_tau.values())

    assert probability_by_tau[0.0] / conditional_total == pytest.approx(0.8, abs=1e-12)
    assert probability_by_tau[-5.0] / conditional_total == pytest.approx(0.1, abs=1e-12)
    assert probability_by_tau[5.0] / conditional_total == pytest.approx(0.1, abs=1e-12)


def test_prediction_uncertainty_determinant_penalizes_vague_candidate() -> None:
    graph = _graph((10001,), hardware_drift_hz_per_s=0.0)
    bank = _bank(
        graph,
        candidate_numbers=(10001, 10002),
        identical_candidates=True,
    )
    vague = bank.candidates[1].model_copy(
        update={
            "tau_states": tuple(
                state.model_copy(
                    update={
                        "predictions": tuple(
                            prediction.model_copy(update={"standard_uncertainty_hz": 20.0})
                            for prediction in state.predictions
                        )
                    }
                )
                for state in bank.candidates[1].tau_states
            )
        }
    )
    uncertainty_bank = CataloguePredictionBankV1.create(
        support=CataloguePredictionSupportV1.from_graph(graph),
        tle_snapshot=bank.tle_snapshot,
        observer_site=bank.observer_site,
        nominal_rf_hz=bank.nominal_rf_hz,
        selection_protocol_digest=bank.selection_protocol_digest,
        selection_policy_digest=bank.selection_policy_digest,
        tle_membership_authority_digest=bank.tle_membership_authority_digest,
        verified_tle_members=bank.verified_tle_members,
        propagation_model=bank.propagation_model,
        candidates=(bank.candidates[0], vague),
    )
    result = associate_catalogue_hypotheses(
        graph,
        uncertainty_bank,
        config=_config(
            maximum_active_satellites=1,
            active_count_log_weights=(-20.0, 0.0, -20.0),
        ),
    )
    presence = {
        item.catalog_number: item.posterior_probability
        for item in result.catalogue_presence_posterior
    }

    assert presence[10001] > presence[10002]


def test_resealed_contradictory_result_marginals_and_scores_are_rejected() -> None:
    graph = _graph((10001, 10001))
    result = associate_catalogue_hypotheses(
        graph,
        _bank(graph, candidate_numbers=(10001,)),
        config=_config(maximum_active_satellites=1),
    )

    score_poison = result.model_dump(mode="python")
    score_poison["hypotheses"][0]["total_negative_log_joint"] += 1.0
    with pytest.raises(ValidationError, match="score decomposition"):
        CatalogueAssociationResultV1.model_validate(score_poison)

    normalized_score_poison = result.model_dump(mode="python", exclude={"content_digest"})
    normalized_score_poison["hypotheses"][0]["data_negative_log_evidence"] += 100.0
    normalized_score_poison["hypotheses"][0]["total_negative_log_joint"] += 100.0
    normalized_score_poison["content_digest"] = canonical_digest(normalized_score_poison)
    with pytest.raises(ValidationError, match="negative log joint"):
        CatalogueAssociationResultV1.model_validate(normalized_score_poison)

    negative_prior_poison = result.model_dump(mode="python", exclude={"content_digest"})
    negative_prior_poison["hypotheses"][0]["data_negative_log_evidence"] += 1.0
    negative_prior_poison["hypotheses"][0]["active_count_negative_log_prior"] = -1.0
    negative_prior_poison["content_digest"] = canonical_digest(negative_prior_poison)
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        CatalogueAssociationResultV1.model_validate(negative_prior_poison)

    log_probability_poison = result.model_dump(mode="python", exclude={"content_digest"})
    log_probability_poison["hypotheses"][0]["log_posterior_probability"] -= 1.0
    log_probability_poison["content_digest"] = canonical_digest(log_probability_poison)
    with pytest.raises(ValidationError, match="log posterior"):
        CatalogueAssociationResultV1.model_validate(log_probability_poison)

    marginal_poison = result.model_dump(mode="python", exclude={"content_digest"})
    marginal_poison["active_count_posterior"][0]["posterior_probability"] += 0.01
    marginal_poison["active_count_posterior"][1]["posterior_probability"] -= 0.01
    marginal_poison["content_digest"] = canonical_digest(marginal_poison)
    with pytest.raises(ValidationError, match="expected active count"):
        CatalogueAssociationResultV1.model_validate(marginal_poison)

    inventory_poison = result.model_dump(mode="python", exclude={"content_digest"})
    episode = inventory_poison["episode_assignment_posterior"][0]
    removed = episode["catalogue_probabilities"][-1]
    episode["catalogue_probabilities"] = episode["catalogue_probabilities"][:-1]
    episode["unassigned_probability"] += removed["posterior_probability"]
    inventory_poison["content_digest"] = canonical_digest(inventory_poison)
    with pytest.raises(ValidationError, match="catalogue inventory is incomplete"):
        CatalogueAssociationResultV1.model_validate(inventory_poison)

    active_inventory_poison = result.model_dump(mode="python", exclude={"content_digest"})
    active_inventory_poison["active_count_posterior"] = (
        {
            "schema_version": 1,
            "active_count": 0,
            "posterior_probability": 1.0,
        },
    )
    active_inventory_poison["content_digest"] = canonical_digest(active_inventory_poison)
    with pytest.raises(ValidationError, match="does not cover reported hypotheses"):
        CatalogueAssociationResultV1.model_validate(active_inventory_poison)


def test_truncated_report_still_bounds_persisted_marginals() -> None:
    graph = _graph((10001, 10001))
    result = associate_catalogue_hypotheses(
        graph,
        _bank(graph, candidate_numbers=(10001,)),
        config=_config(
            maximum_active_satellites=1,
            active_count_log_weights=(-30.0, 0.0, -30.0),
            reported_hypothesis_limit=1,
        ),
    )
    assert result.unreported_hypothesis_count > 0
    assert result.unreported_posterior_mass < 1e-9

    poisoned = result.model_dump(mode="python", exclude={"content_digest"})
    poisoned["catalogue_presence_posterior"][0]["posterior_probability"] = 0.0
    poisoned["content_digest"] = canonical_digest(poisoned)
    with pytest.raises(ValidationError, match="expected active count"):
        CatalogueAssociationResultV1.model_validate(poisoned)


def test_truncated_marginals_retain_cross_inventory_probability_identities() -> None:
    graph = _graph((None,))
    result = associate_catalogue_hypotheses(
        graph,
        _zero_prediction_bank(graph, (10001,)),
        config=_config(
            maximum_active_satellites=1,
            active_count_log_weights=(0.0, 0.0, -20.0),
            reported_hypothesis_limit=1,
        ),
    )
    assert result.reported_posterior_mass == pytest.approx(0.5)
    assert result.unreported_posterior_mass == pytest.approx(0.5)

    poisoned = result.model_dump(mode="python", exclude={"content_digest"})
    poisoned["catalogue_presence_posterior"][0]["posterior_probability"] = 0.0
    poisoned["content_digest"] = canonical_digest(poisoned)
    with pytest.raises(ValidationError, match="expected active count"):
        CatalogueAssociationResultV1.model_validate(poisoned)

    rank_poison = result.model_dump(mode="python", exclude={"content_digest"})
    rank_poison["hypotheses"][0]["posterior_probability"] = 0.1
    rank_poison["hypotheses"][0]["log_posterior_probability"] = math.log(0.1)
    rank_poison["reported_posterior_mass"] = 0.1
    rank_poison["unreported_posterior_mass"] = 0.9
    rank_poison["content_digest"] = canonical_digest(rank_poison)
    with pytest.raises(ValidationError, match="rank ordering"):
        CatalogueAssociationResultV1.model_validate(rank_poison)
