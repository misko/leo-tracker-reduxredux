from __future__ import annotations

import json
import math
from dataclasses import replace

import numpy as np
import pytest
from pydantic import ValidationError

from leo.analysis.catalogue_association import associate_catalogue_hypotheses
from leo.analysis.joint_frequency_calibration import (
    JointFrequencyCalibrationConfig,
    ReceiverComponentOffsetPrior,
    ReceiverHardwareDriftPrior,
    calibrate_joint_satellite_frequency,
)
from leo.analysis.satellite_correction_joint_replay import (
    JointSatelliteFrequencyCalibrationEstimate,
    build_joint_known_position_correction,
)
from leo.analysis.satellite_correction_replay import (
    SatelliteCorrectionInputError,
    SatelliteFrequencyCalibrationEstimate,
    build_single_emitter_known_position_correction,
    replay_known_position_correction,
)
from leo.contracts.catalogue_association import (
    CandidateObservationPredictionV1,
    CandidateTauStateV1,
    CatalogueAssociationConfigV1,
    CatalogueAssociationResultV1,
    CatalogueCandidatePredictionV1,
    CataloguePredictionBankV1,
    CataloguePredictionSupportV1,
    CatalogueVerifiedTleMemberV1,
    PhysicalCfoEpisodeV1,
    PhysicalEpisodeGraphV1,
    SupportIntegratedCfoObservationV1,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.satellite_pnt import (
    CalibrationSourceSpanV1,
    CorrectionEvidenceClass,
    KnownPositionCalibrationReceiptV1,
    SatelliteFrequencyScope,
)
from leo.contracts.satellite_pnt_joint_calibration import (
    JointSatelliteCorrectionProductV1,
)
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1
from leo.contracts.standard_pipeline import StandardScientificStatus

_BASE_UTC_NS = 1_800_000_000_000_000_000
_CATALOG_ONE = 10_001
_CATALOG_TWO = 10_002


def _digest(kind: str, value: object) -> str:
    return canonical_digest({kind: value})


def _curve(catalog_number: int, time_s: float) -> float:
    if catalog_number == _CATALOG_ONE:
        return -30.0 * time_s + 2.0 * time_s**2
    if catalog_number == _CATALOG_TWO:
        return 18.0 * time_s - 1.0 * time_s**2
    raise AssertionError(catalog_number)


def _graph(
    *,
    start_utc_ns: int,
    labels: tuple[int | None, ...],
    satellite_bias_hz: float = 0.0,
    target_component_offset_hz: float = 10_000.0,
) -> PhysicalEpisodeGraphV1:
    observations: list[SupportIntegratedCfoObservationV1] = []
    episodes: list[PhysicalCfoEpisodeV1] = []
    for episode_index, label in enumerate(labels):
        episode_id = _digest("episode", (start_utc_ns, episode_index))
        observation_ids: list[str] = []
        for sample_index, local_time_s in enumerate((-1.5, -0.5, 0.5, 1.5)):
            center_utc_ns = (
                start_utc_ns + episode_index * 5_000_000_000 + round((local_time_s + 1.5) * 1e9)
            )
            observation_id = _digest("observation", (start_utc_ns, episode_index, sample_index))
            deterministic_noise = (-0.2, 0.1, -0.1, 0.2)[sample_index]
            orbital = 0.0 if label is None else _curve(label, local_time_s)
            observations.append(
                SupportIntegratedCfoObservationV1(
                    observation_id=observation_id,
                    source_group_id=_digest(
                        "source-group", (start_utc_ns, episode_index, sample_index)
                    ),
                    episode_id=episode_id,
                    receiver_path_id=_digest("receiver-path", episode_index),
                    hardware_epoch_id="receiver-a",
                    raw_recording_authority_digest=_digest("raw-recording-authority", start_utc_ns),
                    recording_manifest_digest=_digest("manifest", start_utc_ns),
                    stream_id="stream-1",
                    source_binding_digest=_digest(
                        "binding", (start_utc_ns, episode_index, sample_index)
                    ),
                    source_sample_start=(episode_index * 10 + sample_index) * 100,
                    source_sample_end=(episode_index * 10 + sample_index) * 100 + 50,
                    support_start_utc_ns=center_utc_ns - 10_000_000,
                    support_center_utc_ns=center_utc_ns,
                    support_end_utc_ns=center_utc_ns + 10_000_000,
                    measured_cfo_hz=(
                        orbital
                        + satellite_bias_hz
                        + target_component_offset_hz
                        + deterministic_noise
                    ),
                    standard_uncertainty_hz=1.0,
                    factorial_support_moments_s=(1.0, 0.0, 0.000_016_666_666_7, 0.0),
                )
            )
            observation_ids.append(observation_id)
        episodes.append(
            PhysicalCfoEpisodeV1(
                episode_id=episode_id,
                dwell_id=_digest("dwell", (start_utc_ns, episode_index)),
                lane_id=_digest("lane", start_utc_ns),
                order_index=episode_index,
                continuity_component_id=_digest("component", (start_utc_ns, episode_index)),
                observation_ids=tuple(observation_ids),
            )
        )
    return PhysicalEpisodeGraphV1.create(
        observations=tuple(observations),
        episodes=tuple(episodes),
    )


def _snapshot() -> TleSnapshotRefV1:
    return TleSnapshotRefV1(
        provider="space-track",
        collected_utc_ns=_BASE_UTC_NS - 3_600_000_000_000,
        digest=_digest("tle-snapshot", "shared"),
        object_count=10_972,
    )


def _bank(
    graph: PhysicalEpisodeGraphV1,
    *,
    candidate_numbers: tuple[int, ...],
    tau_values: tuple[float, ...] = (0.0,),
) -> CataloguePredictionBankV1:
    episode_by_id = {item.episode_id: item for item in graph.episodes}
    candidates: list[CatalogueCandidatePredictionV1] = []
    for catalog_number in candidate_numbers:
        tau_states: list[CandidateTauStateV1] = []
        for tau_s in tau_values:
            predictions: list[CandidateObservationPredictionV1] = []
            for episode in graph.episodes:
                centers = tuple(
                    next(
                        row.support_center_utc_ns
                        for row in graph.observations
                        if row.observation_id == observation_id
                    )
                    for observation_id in episode.observation_ids
                )
                episode_center = (centers[0] + centers[-1]) / 2.0
                for observation_id, center_utc_ns in zip(
                    episode.observation_ids, centers, strict=True
                ):
                    local_time_s = (center_utc_ns - episode_center) / 1e9
                    predictions.append(
                        CandidateObservationPredictionV1(
                            observation_id=observation_id,
                            predicted_cfo_hz=_curve(catalog_number, local_time_s + tau_s),
                            standard_uncertainty_hz=0.2,
                        )
                    )
            tau_states.append(
                CandidateTauStateV1(
                    tau_s=tau_s,
                    log_prior_weight=0.0,
                    predictions=tuple(sorted(predictions, key=lambda item: item.observation_id)),
                )
            )
        element_epoch = _BASE_UTC_NS - 20_000_000_000_000
        candidates.append(
            CatalogueCandidatePredictionV1(
                catalog_number=catalog_number,
                object_name=f"STARLINK-{catalog_number}",
                selected_element_digest=_digest("element", catalog_number),
                element_epoch_utc_ns=element_epoch,
                element_age_s_at_reference=(
                    abs(
                        min(item.support_center_utc_ns for item in graph.observations)
                        - element_epoch
                    )
                    / 1e9
                ),
                eligible_episode_ids=tuple(sorted(episode_by_id)),
                tau_states=tuple(tau_states),
            )
        )
    ordered = tuple(sorted(candidates, key=lambda item: item.catalog_number))
    return CataloguePredictionBankV1.create(
        support=CataloguePredictionSupportV1.from_graph(graph),
        tle_snapshot=_snapshot(),
        observer_site=ObserverSiteV1(
            latitude_deg=37.0,
            longitude_deg=-122.0,
            altitude_m=10.0,
            label="known-synthetic-site",
        ),
        nominal_rf_hz=11_325_000_000.0,
        selection_protocol_digest=_digest("selection-protocol", "correction-test"),
        selection_policy_digest=_digest("selection-policy", "correction-test"),
        tle_membership_authority_digest=_digest("tle-membership", "correction-test"),
        verified_tle_members=tuple(
            CatalogueVerifiedTleMemberV1(
                catalog_number=item.catalog_number,
                selected_element_digest=item.selected_element_digest,
                element_epoch_utc_ns=item.element_epoch_utc_ns,
            )
            for item in ordered
        ),
        propagation_model="synthetic-support-integrated",
        candidates=ordered,
        tau_search_policy=(
            "fixed-tau-zero-v1" if tau_values == (0.0,) else "bounded-profile-minus5-plus5-v1"
        ),
    )


def _association(
    graph: PhysicalEpisodeGraphV1, bank: CataloguePredictionBankV1
) -> CatalogueAssociationResultV1:
    config = CatalogueAssociationConfigV1(
        maximum_active_satellites=1,
        active_count_log_weights=(-20.0, 0.0, -100.0),
        assigned_episode_log_weight=0.0,
        unassigned_episode_log_weight=-4.0,
        same_state_log_weight=0.0,
        handoff_log_weight=-0.5,
        component_offset_prior_sigma_hz=20_000.0,
        hardware_drift_prior_sigma_hz_per_s=20.0,
        maximum_evaluated_hypotheses=1_000_000,
        reported_hypothesis_limit=10_000,
    )
    return associate_catalogue_hypotheses(graph=graph, prediction_bank=bank, config=config)


def _joint_association(
    graph: PhysicalEpisodeGraphV1, bank: CataloguePredictionBankV1
) -> CatalogueAssociationResultV1:
    return associate_catalogue_hypotheses(
        graph=graph,
        prediction_bank=bank,
        config=CatalogueAssociationConfigV1(
            maximum_active_satellites=2,
            active_count_log_weights=(-20.0, -5.0, 0.0),
            assigned_episode_log_weight=0.0,
            unassigned_episode_log_weight=-4.0,
            same_state_log_weight=0.0,
            handoff_log_weight=-0.5,
            component_offset_prior_sigma_hz=20_000.0,
            hardware_drift_prior_sigma_hz_per_s=20.0,
            maximum_evaluated_hypotheses=1_000_000,
            reported_hypothesis_limit=10_000,
        ),
    )


def _source_span(graph: PhysicalEpisodeGraphV1) -> CalibrationSourceSpanV1:
    return CalibrationSourceSpanV1(
        source_fingerprint_authority_digest=_digest("source-authority", "test"),
        source_recording_fingerprint=_digest("recording-fingerprint", "calibration"),
        source_stream_index=0,
        source_sample_start=0,
        source_sample_stop=1_000,
        start_utc_ns=min(item.support_start_utc_ns for item in graph.observations) - 1,
        end_utc_ns=max(item.support_end_utc_ns for item in graph.observations) + 1,
    )


def _frequency_estimate(
    catalog_number: int,
    *,
    reference_utc_ns: int,
    bias_hz: float = 10.0,
    eligible: bool = True,
) -> SatelliteFrequencyCalibrationEstimate:
    return SatelliteFrequencyCalibrationEstimate(
        catalog_number=catalog_number,
        activity_epoch_id=f"activity-{catalog_number}",
        scope=SatelliteFrequencyScope.SATELLITE,
        beam_channel_id=None,
        reference_utc_ns=reference_utc_ns,
        bias_hz=bias_hz,
        drift_hz_s=0.0,
        bias_variance_hz2=0.0,
        drift_variance_hz2_s2=0.0,
        bias_drift_covariance_hz2_s=0.0,
        calibration_evidence_eligible=eligible,
    )


def _receipt(
    graph: PhysicalEpisodeGraphV1,
    bank: CataloguePredictionBankV1,
    *,
    frequency_estimates: tuple[SatelliteFrequencyCalibrationEstimate, ...] | None = None,
) -> KnownPositionCalibrationReceiptV1:
    association = _association(graph, bank)
    span = _source_span(graph)
    produced = span.end_utc_ns + 1_000_000_000
    positive_catalogs = tuple(
        item.catalog_number
        for item in association.catalogue_presence_posterior
        if item.posterior_probability > 0.0
    )
    estimates = frequency_estimates or tuple(
        _frequency_estimate(
            item,
            reference_utc_ns=(span.start_utc_ns + span.end_utc_ns) // 2,
        )
        for item in positive_catalogs
    )
    return build_single_emitter_known_position_correction(
        association=association,
        prediction_bank=bank,
        frequency_estimates=estimates,
        calibration_source_spans=(span,),
        calibration_site=bank.observer_site,
        calibration_site_authority_digest=_digest("site-authority", "test"),
        calibration_protocol_digest=_digest("calibration-protocol", "test"),
        full_joint_state_digest=_digest("full-joint-state", "test"),
        receiver_local_state_digest=_digest("receiver-local-state", "test"),
        produced_utc_ns=produced,
        sealed_utc_ns=produced + 1,
    )


def test_builds_solver_safe_single_emitter_correction() -> None:
    graph = _graph(start_utc_ns=_BASE_UTC_NS, labels=(_CATALOG_ONE, _CATALOG_ONE))
    bank = _bank(graph, candidate_numbers=(_CATALOG_ONE,))

    receipt = _receipt(graph, bank)
    product = receipt.correction_product

    assert product.status is StandardScientificStatus.COMPLETE
    assert len(product.modes) == 1
    assert product.modes[0].catalog_number == _CATALOG_ONE
    assert product.modes[0].ephemeris.offset_s == 0.0
    assert product.modes[0].ephemeris.variance_s2 == 0.0
    assert product.modes[0].navigation_eligible is True
    assert product.association_hypothesis_digest == _association(graph, bank).content_digest
    assert receipt.receiver_local_state_digest == _digest("receiver-local-state", "test")

    solver_safe = json.dumps(product.model_dump(mode="json"), sort_keys=True).lower()
    assert "latitude_deg" not in solver_safe
    assert "longitude_deg" not in solver_safe
    assert "receiver_local_state_digest" not in solver_safe
    assert "lnb" not in solver_safe
    assert "hardware_drift" not in solver_safe


def test_multiple_k1_alternatives_remain_ambiguity_modes() -> None:
    graph = _graph(start_utc_ns=_BASE_UTC_NS, labels=(_CATALOG_ONE, _CATALOG_ONE))
    bank = _bank(graph, candidate_numbers=(_CATALOG_ONE, _CATALOG_TWO))
    association = _association(graph, bank)
    span = _source_span(graph)
    positive = tuple(
        item.catalog_number
        for item in association.catalogue_presence_posterior
        if item.posterior_probability > 0.0
    )
    receipt = build_single_emitter_known_position_correction(
        association=association,
        prediction_bank=bank,
        frequency_estimates=tuple(
            _frequency_estimate(item, reference_utc_ns=(span.start_utc_ns + span.end_utc_ns) // 2)
            for item in positive
        ),
        calibration_source_spans=(span,),
        calibration_site=bank.observer_site,
        calibration_site_authority_digest=_digest("site-authority", "ambiguity"),
        calibration_protocol_digest=_digest("protocol", "ambiguity"),
        full_joint_state_digest=_digest("joint", "ambiguity"),
        receiver_local_state_digest=_digest("local", "ambiguity"),
        produced_utc_ns=span.end_utc_ns + 1,
        sealed_utc_ns=span.end_utc_ns + 2,
    )

    product = receipt.correction_product
    assert len(product.modes) == 2
    assert all(
        item.evidence_class is CorrectionEvidenceClass.AMBIGUITY_MEMBER for item in product.modes
    )
    assert math.isclose(
        product.unassigned_probability + sum(item.posterior_probability for item in product.modes),
        1.0,
        rel_tol=0.0,
        abs_tol=1e-12,
    )


def test_bounded_tau_posterior_keeps_interior_map_eligible_and_replays_variance() -> None:
    calibration_graph = _graph(
        start_utc_ns=_BASE_UTC_NS,
        labels=(_CATALOG_ONE, _CATALOG_ONE),
    )
    calibration_bank = _bank(
        calibration_graph,
        candidate_numbers=(_CATALOG_ONE,),
        tau_values=(-5.0, 0.0, 5.0),
    )
    receipt = _receipt(calibration_graph, calibration_bank)
    mode = receipt.correction_product.modes[0]

    assert mode.navigation_eligible is True
    assert abs(mode.ephemeris.offset_s) < 5.0
    assert mode.ephemeris.variance_s2 > 0.0

    target_graph = _graph(
        start_utc_ns=receipt.correction_product.produced_utc_ns + 1_000_000_000,
        labels=(_CATALOG_ONE, _CATALOG_ONE),
        satellite_bias_hz=10.0,
        target_component_offset_hz=250.0,
    )
    target_bank = _bank(
        target_graph,
        candidate_numbers=(_CATALOG_ONE,),
        tau_values=(-5.0, 0.0, 5.0),
    )
    result = replay_known_position_correction(
        graph=target_graph,
        prediction_bank=target_bank,
        correction_product=receipt.correction_product,
        target_component_offset_prior_sigma_hz=1_000.0,
    )
    assert len(result.mode_scores) == 1
    assert math.isfinite(result.mode_scores[0].negative_log_predictive_density)


def test_builder_rejects_k2_and_incomplete_frequency_inventory() -> None:
    graph = _graph(start_utc_ns=_BASE_UTC_NS, labels=(_CATALOG_ONE, _CATALOG_TWO))
    bank = _bank(graph, candidate_numbers=(_CATALOG_ONE, _CATALOG_TWO))
    k2_config = CatalogueAssociationConfigV1(
        maximum_active_satellites=2,
        active_count_log_weights=(-100.0, -100.0, 0.0),
        component_offset_prior_sigma_hz=20_000.0,
        hardware_drift_prior_sigma_hz_per_s=20.0,
        maximum_evaluated_hypotheses=1_000_000,
        reported_hypothesis_limit=10_000,
    )
    k2_result = associate_catalogue_hypotheses(graph=graph, prediction_bank=bank, config=k2_config)
    span = _source_span(graph)
    with pytest.raises(SatelliteCorrectionInputError, match="K=2"):
        build_single_emitter_known_position_correction(
            association=k2_result,
            prediction_bank=bank,
            frequency_estimates=(),
            calibration_source_spans=(span,),
            calibration_site=bank.observer_site,
            calibration_site_authority_digest=_digest("site", "k2"),
            calibration_protocol_digest=_digest("protocol", "k2"),
            full_joint_state_digest=_digest("joint", "k2"),
            receiver_local_state_digest=_digest("local", "k2"),
            produced_utc_ns=span.end_utc_ns + 1,
            sealed_utc_ns=span.end_utc_ns + 2,
        )

    one_result = _association(graph, bank)
    with pytest.raises(SatelliteCorrectionInputError, match="exactly cover"):
        build_single_emitter_known_position_correction(
            association=one_result,
            prediction_bank=bank,
            frequency_estimates=(),
            calibration_source_spans=(span,),
            calibration_site=bank.observer_site,
            calibration_site_authority_digest=_digest("site", "missing"),
            calibration_protocol_digest=_digest("protocol", "missing"),
            full_joint_state_digest=_digest("joint", "missing"),
            receiver_local_state_digest=_digest("local", "missing"),
            produced_utc_ns=span.end_utc_ns + 1,
            sealed_utc_ns=span.end_utc_ns + 2,
        )


def test_builder_rejects_site_or_stale_association_substitution() -> None:
    graph = _graph(start_utc_ns=_BASE_UTC_NS, labels=(_CATALOG_ONE,))
    bank = _bank(graph, candidate_numbers=(_CATALOG_ONE,))
    association = _association(graph, bank)
    span = _source_span(graph)
    estimates = (
        _frequency_estimate(
            _CATALOG_ONE,
            reference_utc_ns=(span.start_utc_ns + span.end_utc_ns) // 2,
        ),
    )
    with pytest.raises(SatelliteCorrectionInputError, match="observer site"):
        build_single_emitter_known_position_correction(
            association=association,
            prediction_bank=bank,
            frequency_estimates=estimates,
            calibration_source_spans=(span,),
            calibration_site=ObserverSiteV1(
                latitude_deg=38.0,
                longitude_deg=-122.0,
                altitude_m=10.0,
                label="wrong-site",
            ),
            calibration_site_authority_digest=_digest("site", "substitution"),
            calibration_protocol_digest=_digest("protocol", "substitution"),
            full_joint_state_digest=_digest("joint", "substitution"),
            receiver_local_state_digest=_digest("local", "substitution"),
            produced_utc_ns=span.end_utc_ns + 1,
            sealed_utc_ns=span.end_utc_ns + 2,
        )

    poisoned = association.model_copy(update={"graph_digest": _digest("graph", "poison")})
    with pytest.raises(ValidationError):
        build_single_emitter_known_position_correction(
            association=poisoned,
            prediction_bank=bank,
            frequency_estimates=estimates,
            calibration_source_spans=(span,),
            calibration_site=bank.observer_site,
            calibration_site_authority_digest=_digest("site", "substitution"),
            calibration_protocol_digest=_digest("protocol", "substitution"),
            full_joint_state_digest=_digest("joint", "substitution"),
            receiver_local_state_digest=_digest("local", "substitution"),
            produced_utc_ns=span.end_utc_ns + 1,
            sealed_utc_ns=span.end_utc_ns + 2,
        )


def test_replay_applies_frozen_frequency_and_fits_new_local_offsets() -> None:
    calibration_graph = _graph(
        start_utc_ns=_BASE_UTC_NS,
        labels=(_CATALOG_ONE, _CATALOG_ONE),
    )
    calibration_bank = _bank(calibration_graph, candidate_numbers=(_CATALOG_ONE,))
    receipt = _receipt(calibration_graph, calibration_bank)
    product = receipt.correction_product
    target_start = product.produced_utc_ns + 1_000_000_000
    target_graph = _graph(
        start_utc_ns=target_start,
        labels=(_CATALOG_ONE, _CATALOG_ONE),
        satellite_bias_hz=10.0,
        target_component_offset_hz=250.0,
    )
    target_bank = _bank(target_graph, candidate_numbers=(_CATALOG_ONE,))

    result = replay_known_position_correction(
        graph=target_graph,
        prediction_bank=target_bank,
        correction_product=product,
        target_component_offset_prior_sigma_hz=1_000.0,
    )

    assert result.identity_claimed is False
    assert result.navigation_fix_claimed is False
    assert result.null_model_scored is False
    assert result.receiver_local_state_exportable is False
    assert len(result.mode_scores) == 1
    score = result.mode_scores[0]
    assert score.root_mean_square_residual_hz < 0.25
    assert all(abs(item.mean_hz - 250.0) < 0.2 for item in score.target_component_offsets)


def test_replay_offset_evidence_matches_dense_gaussian() -> None:
    calibration_graph = _graph(
        start_utc_ns=_BASE_UTC_NS,
        labels=(_CATALOG_ONE,),
    )
    calibration_bank = _bank(calibration_graph, candidate_numbers=(_CATALOG_ONE,))
    product = _receipt(calibration_graph, calibration_bank).correction_product
    target_graph = _graph(
        start_utc_ns=product.produced_utc_ns + 1_000_000_000,
        labels=(_CATALOG_ONE,),
        satellite_bias_hz=10.0,
        target_component_offset_hz=250.0,
    )
    target_bank = _bank(target_graph, candidate_numbers=(_CATALOG_ONE,))
    prior_sigma = 1_000.0
    result = replay_known_position_correction(
        graph=target_graph,
        prediction_bank=target_bank,
        correction_product=product,
        target_component_offset_prior_sigma_hz=prior_sigma,
    )

    residual = np.asarray(
        [row.measured_cfo_hz - 10.0 for row in target_graph.observations], dtype=float
    )
    prediction_by_id = {
        item.observation_id: item.predicted_cfo_hz
        for item in target_bank.candidates[0].tau_states[0].predictions
    }
    residual -= np.asarray(
        [prediction_by_id[row.observation_id] for row in target_graph.observations]
    )
    diagonal_variance = np.full(len(residual), 1.0**2 + 0.2**2)
    covariance = np.diag(diagonal_variance) + prior_sigma**2 * np.ones(
        (len(residual), len(residual))
    )
    sign, logdet = np.linalg.slogdet(covariance)
    assert sign == 1.0
    direct_nll = 0.5 * (
        float(residual @ np.linalg.solve(covariance, residual))
        + float(logdet)
        + len(residual) * math.log(2.0 * math.pi)
    )
    assert result.mode_scores[0].negative_log_predictive_density == pytest.approx(
        direct_nll, abs=1e-8
    )


def test_replay_fails_closed_on_stale_or_expired_inputs() -> None:
    calibration_graph = _graph(
        start_utc_ns=_BASE_UTC_NS,
        labels=(_CATALOG_ONE,),
    )
    calibration_bank = _bank(calibration_graph, candidate_numbers=(_CATALOG_ONE,))
    product = _receipt(calibration_graph, calibration_bank).correction_product
    target_graph = _graph(
        start_utc_ns=product.produced_utc_ns + 1_000_000_000,
        labels=(_CATALOG_ONE,),
        satellite_bias_hz=10.0,
    )
    target_bank = _bank(target_graph, candidate_numbers=(_CATALOG_ONE,))

    poisoned_mode = product.modes[0].model_copy(
        update={"frequency": product.modes[0].frequency.model_copy(update={"bias_hz": 999.0})}
    )
    poisoned_product = product.model_copy(update={"modes": (poisoned_mode,)})
    with pytest.raises(ValidationError):
        replay_known_position_correction(
            graph=target_graph,
            prediction_bank=target_bank,
            correction_product=poisoned_product,
            target_component_offset_prior_sigma_hz=1_000.0,
        )

    late_graph = _graph(
        start_utc_ns=product.produced_utc_ns + 31_000_000_000,
        labels=(_CATALOG_ONE,),
        satellite_bias_hz=10.0,
    )
    late_bank = _bank(late_graph, candidate_numbers=(_CATALOG_ONE,))
    with pytest.raises(SatelliteCorrectionInputError, match="validity"):
        replay_known_position_correction(
            graph=late_graph,
            prediction_bank=late_bank,
            correction_product=product,
            target_component_offset_prior_sigma_hz=1_000.0,
        )

    stale_bank = target_bank.model_copy(
        update={
            "tle_snapshot": target_bank.tle_snapshot.model_copy(
                update={"digest": _digest("tle-snapshot", "poison")}
            )
        }
    )
    with pytest.raises(ValidationError):
        replay_known_position_correction(
            graph=target_graph,
            prediction_bank=stale_bank,
            correction_product=product,
            target_component_offset_prior_sigma_hz=1_000.0,
        )


def test_frequency_calibration_contract_rejects_receiver_like_poison_and_bad_covariance() -> None:
    with pytest.raises(TypeError):
        SatelliteFrequencyCalibrationEstimate(  # type: ignore[call-arg]
            catalog_number=_CATALOG_ONE,
            activity_epoch_id="activity",
            scope=SatelliteFrequencyScope.SATELLITE,
            beam_channel_id=None,
            reference_utc_ns=_BASE_UTC_NS,
            bias_hz=0.0,
            drift_hz_s=0.0,
            bias_variance_hz2=1.0,
            drift_variance_hz2_s2=1.0,
            bias_drift_covariance_hz2_s=0.0,
            calibration_evidence_eligible=True,
            receiver_lnb_drift_hz_s=1.0,
        )
    with pytest.raises(ValidationError):
        replace(
            _frequency_estimate(_CATALOG_ONE, reference_utc_ns=_BASE_UTC_NS),
            bias_variance_hz2=0.0,
            drift_variance_hz2_s2=0.0,
            bias_drift_covariance_hz2_s=1.0,
        )


def _joint_frequency_estimates(
    association: CatalogueAssociationResultV1,
    *,
    reference_utc_ns: int,
    gauge_resolved: bool = True,
) -> tuple[JointSatelliteFrequencyCalibrationEstimate, ...]:
    estimates: list[JointSatelliteFrequencyCalibrationEstimate] = []
    for mode in association.hypotheses:
        if not mode.active_catalog_numbers:
            continue
        states = tuple(
            SatelliteFrequencyCalibrationEstimate(
                catalog_number=number,
                activity_epoch_id=f"activity-{number}",
                scope=SatelliteFrequencyScope.SATELLITE,
                beam_channel_id=None,
                reference_utc_ns=reference_utc_ns,
                bias_hz=10.0 + index,
                drift_hz_s=0.1 * index,
                bias_variance_hz2=4.0,
                drift_variance_hz2_s2=1.0,
                bias_drift_covariance_hz2_s=0.2,
                calibration_evidence_eligible=True,
            )
            for index, number in enumerate(mode.active_catalog_numbers)
        )
        covariance = (
            ((4.0, 0.2), (0.2, 1.0))
            if len(states) == 1
            else (
                (4.0, 0.2, 1.0, 0.0),
                (0.2, 1.0, 0.0, 0.25),
                (1.0, 0.0, 4.0, 0.2),
                (0.0, 0.25, 0.2, 1.0),
            )
        )
        estimates.append(
            JointSatelliteFrequencyCalibrationEstimate(
                association_mode_digest=canonical_digest(mode.model_dump(mode="json")),
                states=states,
                frequency_covariance=covariance,
                receiver_frequency_gauge_resolved=gauge_resolved,
                calibration_evidence_eligible=True,
            )
        )
    return tuple(estimates)


def _joint_receipt(
    graph: PhysicalEpisodeGraphV1,
    bank: CataloguePredictionBankV1,
    *,
    gauge_resolved: bool = True,
):
    association = _joint_association(graph, bank)
    span = _source_span(graph)
    produced = span.end_utc_ns + 1
    return build_joint_known_position_correction(
        association=association,
        prediction_bank=bank,
        frequency_estimates=_joint_frequency_estimates(
            association,
            reference_utc_ns=(span.start_utc_ns + span.end_utc_ns) // 2,
            gauge_resolved=gauge_resolved,
        ),
        calibration_source_spans=(span,),
        calibration_site=bank.observer_site,
        calibration_site_authority_digest=_digest("joint-site-authority", "test"),
        calibration_protocol_digest=_digest("joint-protocol", "test"),
        frequency_calibration_authority_digest=_digest("frequency-authority", "test"),
        full_joint_state_digest=_digest("full-joint-state", "joint-test"),
        receiver_local_state_digest=_digest("receiver-local", "joint-test"),
        produced_utc_ns=produced,
        sealed_utc_ns=produced + 1,
    )


def _calibrate_joint_frequency(
    graph: PhysicalEpisodeGraphV1,
    bank: CataloguePredictionBankV1,
    association: CatalogueAssociationResultV1,
    *,
    gauge_resolved: bool = True,
    hardware_drift_sigma_hz_s: float = 2.0,
    hardware_random_walk_sigma_hz_s_per_sqrt_s: float | None = None,
):
    component_priors = tuple(
        ReceiverComponentOffsetPrior(
            continuity_component_id=item.continuity_component_id,
            mean_hz=10_000.0,
            standard_uncertainty_hz=0.25,
        )
        for item in graph.episodes
    )
    hardware_ids = tuple(sorted({item.hardware_epoch_id for item in graph.observations}))
    hardware_priors = tuple(
        ReceiverHardwareDriftPrior(
            hardware_epoch_id=item,
            reference_utc_ns=sum(
                row.support_center_utc_ns
                for row in graph.observations
                if row.hardware_epoch_id == item
            )
            // sum(1 for row in graph.observations if row.hardware_epoch_id == item),
            mean_hz_s=0.0,
            standard_uncertainty_hz_s=hardware_drift_sigma_hz_s,
        )
        for item in hardware_ids
    )
    return calibrate_joint_satellite_frequency(
        graph=graph,
        prediction_bank=bank,
        association=association,
        component_priors=component_priors,
        hardware_priors=hardware_priors,
        receiver_frequency_reference_authority_digest=_digest(
            "receiver-frequency-authority", "test"
        ),
        receiver_frequency_gauge_resolved=gauge_resolved,
        config=JointFrequencyCalibrationConfig(
            hardware_drift_random_walk_sigma_hz_s_per_sqrt_s=(
                hardware_random_walk_sigma_hz_s_per_sqrt_s
            )
        ),
    )


def test_joint_correction_preserves_k0_k1_k2_modes_and_cross_covariance() -> None:
    graph = _graph(
        start_utc_ns=_BASE_UTC_NS,
        labels=(_CATALOG_ONE, _CATALOG_TWO),
    )
    bank = _bank(graph, candidate_numbers=(_CATALOG_ONE, _CATALOG_TWO))
    association = _joint_association(graph, bank)

    receipt = _joint_receipt(graph, bank)
    product = receipt.joint_correction_product

    assert product.association_result_digest == association.content_digest
    assert len(product.modes) == len(association.hypotheses)
    assert {len(item.active_catalog_numbers) for item in product.modes} == {0, 1, 2}
    assert math.isclose(
        math.fsum(item.posterior_probability for item in product.modes),
        1.0,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    k2 = next(item for item in product.modes if len(item.active_catalog_numbers) == 2)
    assert k2.frequency_covariance[0][2] == 1.0
    assert k2.frequency_covariance[1][3] == 0.25
    assert product.receiver_local_state_excluded is True
    assert product.association_nuisance_treatment == (
        "marginalized-in-mode-evidence-not-exported-v1"
    )
    solver_safe = json.dumps(product.model_dump(mode="json"), sort_keys=True).lower()
    assert "component_offset" not in solver_safe
    assert "hardware_drift" not in solver_safe
    assert "lnb" not in solver_safe
    assert "latitude_deg" not in solver_safe


def test_joint_correction_requires_resolved_frequency_gauge_for_navigation() -> None:
    graph = _graph(
        start_utc_ns=_BASE_UTC_NS,
        labels=(_CATALOG_ONE, _CATALOG_TWO),
    )
    bank = _bank(graph, candidate_numbers=(_CATALOG_ONE, _CATALOG_TWO))

    receipt = _joint_receipt(graph, bank, gauge_resolved=False)

    assert receipt.joint_correction_product.status is StandardScientificStatus.PARTIAL
    assert not any(item.navigation_eligible for item in receipt.joint_correction_product.modes)
    assert all(
        not item.receiver_frequency_gauge_resolved
        for item in receipt.joint_correction_product.modes
        if item.active_catalog_numbers
    )


def test_joint_correction_rejects_missing_mode_and_indefinite_cross_covariance() -> None:
    graph = _graph(
        start_utc_ns=_BASE_UTC_NS,
        labels=(_CATALOG_ONE, _CATALOG_TWO),
    )
    bank = _bank(graph, candidate_numbers=(_CATALOG_ONE, _CATALOG_TWO))
    association = _joint_association(graph, bank)
    span = _source_span(graph)
    estimates = _joint_frequency_estimates(
        association,
        reference_utc_ns=(span.start_utc_ns + span.end_utc_ns) // 2,
    )
    common = {
        "association": association,
        "prediction_bank": bank,
        "calibration_source_spans": (span,),
        "calibration_site": bank.observer_site,
        "calibration_site_authority_digest": _digest("site", "joint-negative"),
        "calibration_protocol_digest": _digest("protocol", "joint-negative"),
        "frequency_calibration_authority_digest": _digest("frequency", "joint-negative"),
        "full_joint_state_digest": _digest("joint", "joint-negative"),
        "receiver_local_state_digest": _digest("local", "joint-negative"),
        "produced_utc_ns": span.end_utc_ns + 1,
        "sealed_utc_ns": span.end_utc_ns + 2,
    }
    with pytest.raises(SatelliteCorrectionInputError, match="exactly cover"):
        build_joint_known_position_correction(
            **common,
            frequency_estimates=estimates[:-1],
        )

    k2_index = next(index for index, item in enumerate(estimates) if len(item.states) == 2)
    poisoned = replace(
        estimates[k2_index],
        frequency_covariance=(
            (4.0, 0.2, 10.0, 0.0),
            (0.2, 1.0, 0.0, 0.25),
            (10.0, 0.0, 4.0, 0.2),
            (0.0, 0.25, 0.2, 1.0),
        ),
    )
    bad_estimates = estimates[:k2_index] + (poisoned,) + estimates[k2_index + 1 :]
    with pytest.raises(ValidationError, match="positive semidefinite"):
        build_joint_known_position_correction(
            **common,
            frequency_estimates=bad_estimates,
        )


def test_joint_correction_contract_rejects_receiver_local_poison() -> None:
    graph = _graph(
        start_utc_ns=_BASE_UTC_NS,
        labels=(_CATALOG_ONE, _CATALOG_TWO),
    )
    bank = _bank(graph, candidate_numbers=(_CATALOG_ONE, _CATALOG_TWO))
    product = _joint_receipt(graph, bank).joint_correction_product

    payload = product.model_dump(mode="json")
    payload["receiver_lnb_drift_hz_s"] = 1.0
    with pytest.raises(ValidationError):
        JointSatelliteCorrectionProductV1.model_validate(payload)


def test_known_position_batch_calibration_retains_cross_satellite_covariance() -> None:
    graph = _graph(
        start_utc_ns=_BASE_UTC_NS,
        labels=(_CATALOG_ONE, _CATALOG_TWO),
        satellite_bias_hz=10.0,
    )
    bank = _bank(graph, candidate_numbers=(_CATALOG_ONE, _CATALOG_TWO))
    association = _joint_association(graph, bank)

    result = _calibrate_joint_frequency(graph, bank, association)

    assert result.receiver_frequency_gauge_resolved is True
    assert result.receiver_local_state_exportable is False
    assert result.receiver_drift_model == "one-linear-state-per-hardware-epoch-v1"
    assert result.cross_dwell_random_walk_modeled is False
    assert result.receiver_local_priors_externally_supplied is True
    assert result.known_position_used is True
    assert result.identity_claimed is False
    assert len(result.frequency_estimates) == sum(
        bool(item.active_catalog_numbers) for item in association.hypotheses
    )
    k2 = next(item for item in result.frequency_estimates if len(item.states) == 2)
    assert len(k2.frequency_covariance) == 4
    assert abs(k2.frequency_covariance[0][2]) > 1e-9
    assert abs(k2.frequency_covariance[1][3]) > 1e-9
    assert all(item.calibration_evidence_eligible for item in result.frequency_estimates)


def test_shared_hardware_uncertainty_increases_cross_satellite_covariance() -> None:
    graph = _graph(
        start_utc_ns=_BASE_UTC_NS,
        labels=(_CATALOG_ONE, _CATALOG_TWO),
        satellite_bias_hz=10.0,
    )
    bank = _bank(graph, candidate_numbers=(_CATALOG_ONE, _CATALOG_TWO))
    association = _joint_association(graph, bank)

    tight = _calibrate_joint_frequency(
        graph,
        bank,
        association,
        hardware_drift_sigma_hz_s=0.01,
    )
    loose = _calibrate_joint_frequency(
        graph,
        bank,
        association,
        hardware_drift_sigma_hz_s=10.0,
    )
    tight_k2 = next(item for item in tight.frequency_estimates if len(item.states) == 2)
    loose_k2 = next(item for item in loose.frequency_estimates if len(item.states) == 2)

    assert abs(loose_k2.frequency_covariance[1][3]) > abs(tight_k2.frequency_covariance[1][3])


def test_time_local_hardware_random_walk_reduces_forced_cross_dwell_coupling() -> None:
    graph = _graph(
        start_utc_ns=_BASE_UTC_NS,
        labels=(_CATALOG_ONE, _CATALOG_TWO),
        satellite_bias_hz=10.0,
    )
    bank = _bank(graph, candidate_numbers=(_CATALOG_ONE, _CATALOG_TWO))
    association = _joint_association(graph, bank)

    nearly_shared = _calibrate_joint_frequency(
        graph,
        bank,
        association,
        hardware_random_walk_sigma_hz_s_per_sqrt_s=0.001,
    )
    time_local = _calibrate_joint_frequency(
        graph,
        bank,
        association,
        hardware_random_walk_sigma_hz_s_per_sqrt_s=10.0,
    )
    shared_k2 = next(item for item in nearly_shared.frequency_estimates if len(item.states) == 2)
    local_k2 = next(item for item in time_local.frequency_estimates if len(item.states) == 2)

    assert nearly_shared.receiver_drift_model == "dwell-local-hardware-drift-random-walk-v1"
    assert nearly_shared.cross_dwell_random_walk_modeled is True
    assert abs(local_k2.frequency_covariance[1][3]) < abs(shared_k2.frequency_covariance[1][3])


def test_batch_calibration_feeds_joint_product_without_exporting_receiver_state() -> None:
    graph = _graph(
        start_utc_ns=_BASE_UTC_NS,
        labels=(_CATALOG_ONE, _CATALOG_TWO),
        satellite_bias_hz=10.0,
    )
    bank = _bank(graph, candidate_numbers=(_CATALOG_ONE, _CATALOG_TWO))
    association = _joint_association(graph, bank)
    calibration = _calibrate_joint_frequency(graph, bank, association)
    span = _source_span(graph)
    produced = span.end_utc_ns + 1

    receipt = build_joint_known_position_correction(
        association=association,
        prediction_bank=bank,
        frequency_estimates=calibration.frequency_estimates,
        calibration_source_spans=(span,),
        calibration_site=bank.observer_site,
        calibration_site_authority_digest=_digest("site", "batch"),
        calibration_protocol_digest=_digest("protocol", "batch"),
        frequency_calibration_authority_digest=(
            calibration.receiver_frequency_reference_authority_digest
        ),
        full_joint_state_digest=calibration.full_joint_state_digest,
        receiver_local_state_digest=calibration.receiver_local_state_digest,
        produced_utc_ns=produced,
        sealed_utc_ns=produced + 1,
    )

    product = receipt.joint_correction_product
    assert product.status is StandardScientificStatus.COMPLETE
    serialized = json.dumps(product.model_dump(mode="json"), sort_keys=True).lower()
    assert calibration.receiver_local_state_digest not in serialized
    assert "receiver_local_state_digest" not in serialized
    assert "component_offset" not in serialized
    assert "hardware_drift" not in serialized


def test_unresolved_batch_frequency_gauge_cannot_become_navigation_eligible() -> None:
    graph = _graph(
        start_utc_ns=_BASE_UTC_NS,
        labels=(_CATALOG_ONE, _CATALOG_TWO),
        satellite_bias_hz=10.0,
    )
    bank = _bank(graph, candidate_numbers=(_CATALOG_ONE, _CATALOG_TWO))
    association = _joint_association(graph, bank)

    result = _calibrate_joint_frequency(
        graph,
        bank,
        association,
        gauge_resolved=False,
    )

    assert not any(item.calibration_evidence_eligible for item in result.frequency_estimates)
    assert all(not item.receiver_frequency_gauge_resolved for item in result.frequency_estimates)


def test_batch_frequency_calibration_rejects_incomplete_receiver_authority() -> None:
    graph = _graph(
        start_utc_ns=_BASE_UTC_NS,
        labels=(_CATALOG_ONE, _CATALOG_TWO),
    )
    bank = _bank(graph, candidate_numbers=(_CATALOG_ONE, _CATALOG_TWO))
    association = _joint_association(graph, bank)

    with pytest.raises(SatelliteCorrectionInputError, match="exactly cover"):
        calibrate_joint_satellite_frequency(
            graph=graph,
            prediction_bank=bank,
            association=association,
            component_priors=(),
            hardware_priors=(
                ReceiverHardwareDriftPrior(
                    hardware_epoch_id="receiver-a",
                    reference_utc_ns=_BASE_UTC_NS,
                    mean_hz_s=0.0,
                    standard_uncertainty_hz_s=1.0,
                ),
            ),
            receiver_frequency_reference_authority_digest=_digest("authority", "missing"),
            receiver_frequency_gauge_resolved=True,
        )
