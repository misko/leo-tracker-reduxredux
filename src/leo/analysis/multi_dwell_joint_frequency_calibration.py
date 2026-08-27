"""Known-position frequency calibration keyed to sequential history modes.

The sequential retained-history posterior is not relabelled as a one-shot
``CatalogueAssociationResultV1``.  This analyzer validates its exact adapter
lineage, builds an ephemeral merged graph/bank only for the shared Gaussian
calibration kernel, and returns satellite-frequency estimates keyed to the
original history-mode digests.  Receiver-local states remain opaque and no
transferable correction product is emitted by this slice.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from leo.analysis.joint_frequency_calibration import (
    JointFrequencyCalibrationConfig,
    JointFrequencyModeDiagnostic,
    ReceiverComponentOffsetPrior,
    ReceiverHardwareDriftPrior,
    _exact_component_priors,
    _exact_hardware_priors,
    _mode_reference_utc_ns,
    _solve_mode,
)
from leo.analysis.multi_dwell_catalogue_adapter import (
    MultiDwellCatalogueAdapterConfig,
    MultiDwellCatalogueAdapterResult,
    adapt_catalogue_dwells_to_filter_inputs,
)
from leo.analysis.satellite_correction_joint_replay import (
    JointSatelliteFrequencyCalibrationEstimate,
)
from leo.analysis.satellite_correction_replay import (
    SatelliteCorrectionInputError,
    SatelliteFrequencyCalibrationEstimate,
)
from leo.contracts.catalogue_association import (
    CandidateTauStateV1,
    CatalogueAssociationModeV1,
    CatalogueCandidatePredictionV1,
    CataloguePredictionBankV1,
    CataloguePredictionSupportV1,
    CatalogueTauChoiceV1,
    ComponentOffsetEstimateV1,
    EpisodeCatalogueAssignmentV1,
    HardwareDriftEstimateV1,
    PhysicalCfoEpisodeV1,
    PhysicalEpisodeGraphV1,
)
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.multi_dwell_catalogue import (
    MultiDwellCataloguePosteriorV1,
    MultiDwellHistoryModeV1,
)
from leo.contracts.satellite_pnt import SatelliteFrequencyScope


@dataclass(frozen=True, slots=True)
class MultiDwellHistoryFrequencyCalibration:
    history_mode_digest: Sha256Digest
    history_posterior_probability: float
    active_catalog_numbers: tuple[int, ...]
    estimate: JointSatelliteFrequencyCalibrationEstimate
    diagnostic: JointFrequencyModeDiagnostic


@dataclass(frozen=True, slots=True)
class MultiDwellJointFrequencyCalibrationResult:
    source_posterior_digest: Sha256Digest
    adapter_result_digest: Sha256Digest
    merged_graph_digest: Sha256Digest
    merged_prediction_bank_digest: Sha256Digest
    receiver_frequency_reference_authority_digest: Sha256Digest
    receiver_frequency_gauge_resolved: bool
    mode_calibrations: tuple[MultiDwellHistoryFrequencyCalibration, ...]
    null_history_mode_digests: tuple[Sha256Digest, ...]
    full_joint_state_digest: Sha256Digest
    receiver_local_state_digest: Sha256Digest
    known_position_used: bool
    sequential_history_posterior_preserved: bool
    association_result_relabelled: bool
    receiver_local_state_exportable: bool
    transferable_correction_emitted: bool
    identity_claimed: bool
    content_digest: Sha256Digest


def calibrate_multi_dwell_history_frequencies(
    *,
    posterior: MultiDwellCataloguePosteriorV1,
    graphs: tuple[PhysicalEpisodeGraphV1, ...],
    prediction_banks: tuple[CataloguePredictionBankV1, ...],
    component_priors: tuple[ReceiverComponentOffsetPrior, ...],
    hardware_priors: tuple[ReceiverHardwareDriftPrior, ...],
    receiver_frequency_reference_authority_digest: Sha256Digest,
    receiver_frequency_gauge_resolved: bool,
    adapter_config: MultiDwellCatalogueAdapterConfig | None = None,
    calibration_config: JointFrequencyCalibrationConfig | None = None,
) -> MultiDwellJointFrequencyCalibrationResult:
    """Calibrate every positive non-null sequential history without relabelling it."""

    posterior = MultiDwellCataloguePosteriorV1.model_validate(posterior.model_dump(mode="json"))
    adapter = adapt_catalogue_dwells_to_filter_inputs(
        graphs=graphs,
        prediction_banks=prediction_banks,
        config=adapter_config,
    )
    _validate_posterior_lineage(posterior, adapter)
    merged_graph = _merge_graphs(graphs)
    merged_bank = _merge_prediction_banks(
        graphs=graphs,
        banks=prediction_banks,
        merged_graph=merged_graph,
    )
    config = _revalidate_calibration_config(calibration_config)
    component_priors = tuple(
        ReceiverComponentOffsetPrior(
            continuity_component_id=item.continuity_component_id,
            mean_hz=item.mean_hz,
            standard_uncertainty_hz=item.standard_uncertainty_hz,
        )
        for item in component_priors
    )
    hardware_priors = tuple(
        ReceiverHardwareDriftPrior(
            hardware_epoch_id=item.hardware_epoch_id,
            reference_utc_ns=item.reference_utc_ns,
            mean_hz_s=item.mean_hz_s,
            standard_uncertainty_hz_s=item.standard_uncertainty_hz_s,
        )
        for item in hardware_priors
    )
    component_by_id = _exact_component_priors(merged_graph, component_priors)
    hardware_by_id = _exact_hardware_priors(merged_graph, hardware_priors)
    if not isinstance(receiver_frequency_gauge_resolved, bool):
        raise SatelliteCorrectionInputError("frequency-gauge verdict must be boolean")
    positive_histories = tuple(item for item in posterior.modes if item.active_catalog_numbers)
    total_work = len(merged_graph.observations) * len(positive_histories)
    if total_work > config.maximum_mode_observation_evaluations:
        raise SatelliteCorrectionInputError(
            "multi-dwell joint frequency calibration exceeds the work cap"
        )
    episode_by_dwell = {episode.dwell_id: episode.episode_id for episode in merged_graph.episodes}
    calibrations = []
    full_state_digests = []
    receiver_state_digests = []
    for history in positive_histories:
        ephemeral_mode = _history_as_calibration_mode(history, episode_by_dwell)
        solve = _solve_mode(
            graph=merged_graph,
            bank=merged_bank,
            mode=ephemeral_mode,
            component_by_id=component_by_id,
            hardware_by_id=hardware_by_id,
            config=config,
        )
        eligible = (
            receiver_frequency_gauge_resolved
            and solve.minimum_catalogue_observation_count
            >= config.minimum_observations_per_satellite
            and solve.minimum_catalogue_span_s >= config.minimum_span_s_per_satellite
        )
        reference_utc_ns = _mode_reference_utc_ns(
            graph=merged_graph,
            mode=ephemeral_mode,
        )
        satellite_covariance = solve.covariance[
            : solve.satellite_dimension, : solve.satellite_dimension
        ]
        states = tuple(
            SatelliteFrequencyCalibrationEstimate(
                catalog_number=number,
                activity_epoch_id=f"multi-dwell-frequency-{number}-{history.mode_digest[-12:]}",
                scope=SatelliteFrequencyScope.SATELLITE,
                beam_channel_id=None,
                reference_utc_ns=reference_utc_ns,
                bias_hz=float(solve.mean[2 * index]),
                drift_hz_s=float(solve.mean[2 * index + 1]),
                bias_variance_hz2=float(satellite_covariance[2 * index, 2 * index]),
                drift_variance_hz2_s2=float(satellite_covariance[2 * index + 1, 2 * index + 1]),
                bias_drift_covariance_hz2_s=float(satellite_covariance[2 * index, 2 * index + 1]),
                calibration_evidence_eligible=eligible,
            )
            for index, number in enumerate(history.active_catalog_numbers)
        )
        estimate = JointSatelliteFrequencyCalibrationEstimate(
            association_mode_digest=history.mode_digest,
            states=states,
            frequency_covariance=tuple(
                tuple(float(value) for value in row) for row in satellite_covariance
            ),
            receiver_frequency_gauge_resolved=receiver_frequency_gauge_resolved,
            calibration_evidence_eligible=eligible,
        )
        diagnostic = JointFrequencyModeDiagnostic(
            association_mode_digest=history.mode_digest,
            active_catalog_numbers=history.active_catalog_numbers,
            observation_count=solve.observation_count,
            normal_condition_number=solve.condition_number,
            minimum_catalogue_observation_count=solve.minimum_catalogue_observation_count,
            minimum_catalogue_span_s=solve.minimum_catalogue_span_s,
            calibration_evidence_eligible=eligible,
        )
        calibrations.append(
            MultiDwellHistoryFrequencyCalibration(
                history_mode_digest=history.mode_digest,
                history_posterior_probability=history.posterior_probability,
                active_catalog_numbers=history.active_catalog_numbers,
                estimate=estimate,
                diagnostic=diagnostic,
            )
        )
        full_state_digests.append(solve.full_state_digest)
        receiver_state_digests.append(solve.receiver_state_digest)
    null_mode_digests = tuple(
        item.mode_digest for item in posterior.modes if not item.active_catalog_numbers
    )
    full_digest = canonical_digest(tuple(full_state_digests))
    receiver_digest = canonical_digest(tuple(receiver_state_digests))
    values = {
        "source_posterior_digest": posterior.content_digest,
        "adapter_result_digest": adapter.content_digest,
        "merged_graph_digest": merged_graph.content_digest,
        "merged_prediction_bank_digest": merged_bank.content_digest,
        "receiver_frequency_reference_authority_digest": (
            receiver_frequency_reference_authority_digest
        ),
        "receiver_frequency_gauge_resolved": receiver_frequency_gauge_resolved,
        "mode_calibrations": tuple(asdict(item) for item in calibrations),
        "null_history_mode_digests": null_mode_digests,
        "full_joint_state_digest": full_digest,
        "receiver_local_state_digest": receiver_digest,
        "known_position_used": True,
        "sequential_history_posterior_preserved": True,
        "association_result_relabelled": False,
        "receiver_local_state_exportable": False,
        "transferable_correction_emitted": False,
        "identity_claimed": False,
    }
    return MultiDwellJointFrequencyCalibrationResult(
        source_posterior_digest=posterior.content_digest,
        adapter_result_digest=adapter.content_digest,
        merged_graph_digest=merged_graph.content_digest,
        merged_prediction_bank_digest=merged_bank.content_digest,
        receiver_frequency_reference_authority_digest=(
            receiver_frequency_reference_authority_digest
        ),
        receiver_frequency_gauge_resolved=receiver_frequency_gauge_resolved,
        mode_calibrations=tuple(calibrations),
        null_history_mode_digests=null_mode_digests,
        full_joint_state_digest=full_digest,
        receiver_local_state_digest=receiver_digest,
        known_position_used=True,
        sequential_history_posterior_preserved=True,
        association_result_relabelled=False,
        receiver_local_state_exportable=False,
        transferable_correction_emitted=False,
        identity_claimed=False,
        content_digest=canonical_digest(values),
    )


def _validate_posterior_lineage(
    posterior: MultiDwellCataloguePosteriorV1,
    adapter: MultiDwellCatalogueAdapterResult,
) -> None:
    evidence_digest = canonical_digest(
        {
            "dwells": tuple(asdict(item) for item in adapter.dwells),
            "response_accessed": True,
        }
    )
    prediction_digest = canonical_digest(
        {
            "prediction_bank": asdict(adapter.prediction_bank),
            "response_accessed": adapter.prediction_bank.response_accessed,
            "tau_policy": adapter.prediction_bank.tau_policy,
        }
    )
    if (
        posterior.source_evidence_digest != evidence_digest
        or posterior.response_free_prediction_bank_digest != prediction_digest
        or posterior.dwell_ids != adapter.dwell_ids
        or posterior.catalog_numbers != adapter.catalog_numbers
    ):
        raise SatelliteCorrectionInputError(
            "multi-dwell posterior does not bind the exact graph/bank adapter inputs"
        )


def _merge_graphs(
    graphs: tuple[PhysicalEpisodeGraphV1, ...],
) -> PhysicalEpisodeGraphV1:
    observations = tuple(item for graph in graphs for item in graph.observations)
    episodes = tuple(
        PhysicalCfoEpisodeV1(
            episode_id=graph.episodes[0].episode_id,
            dwell_id=graph.episodes[0].dwell_id,
            lane_id=graph.episodes[0].lane_id,
            order_index=index,
            continuity_component_id=graph.episodes[0].continuity_component_id,
            observation_ids=graph.episodes[0].observation_ids,
            replica_group_id=graph.episodes[0].replica_group_id,
            exclusion_group_ids=graph.episodes[0].exclusion_group_ids,
        )
        for index, graph in enumerate(graphs)
    )
    return PhysicalEpisodeGraphV1.create(observations=observations, episodes=episodes)


def _merge_prediction_banks(
    *,
    graphs: tuple[PhysicalEpisodeGraphV1, ...],
    banks: tuple[CataloguePredictionBankV1, ...],
    merged_graph: PhysicalEpisodeGraphV1,
) -> CataloguePredictionBankV1:
    first = banks[0]
    if any(
        bank.tle_snapshot != first.tle_snapshot
        or bank.tle_membership_authority_digest != first.tle_membership_authority_digest
        or bank.verified_tle_members != first.verified_tle_members
        for bank in banks[1:]
    ):
        raise SatelliteCorrectionInputError(
            "multi-dwell frequency calibration requires one exact TLE member inventory"
        )
    candidates = []
    for candidate_index, first_candidate in enumerate(first.candidates):
        candidate_rows = tuple(bank.candidates[candidate_index] for bank in banks)
        if any(
            item.catalog_number != first_candidate.catalog_number
            or item.selected_element_digest != first_candidate.selected_element_digest
            or item.element_epoch_utc_ns != first_candidate.element_epoch_utc_ns
            for item in candidate_rows
        ):
            raise SatelliteCorrectionInputError(
                "multi-dwell candidate element identity changes across banks"
            )
        predictions = tuple(
            prediction for item in candidate_rows for prediction in item.tau_states[0].predictions
        )
        candidates.append(
            CatalogueCandidatePredictionV1(
                catalog_number=first_candidate.catalog_number,
                object_name=first_candidate.object_name,
                selected_element_digest=first_candidate.selected_element_digest,
                element_epoch_utc_ns=first_candidate.element_epoch_utc_ns,
                element_age_s_at_reference=abs(
                    min(item.support_center_utc_ns for item in merged_graph.observations)
                    - first_candidate.element_epoch_utc_ns
                )
                / 1e9,
                eligible_episode_ids=tuple(
                    sorted(graph.episodes[0].episode_id for graph in graphs)
                ),
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
    return CataloguePredictionBankV1.create(
        support=CataloguePredictionSupportV1.from_graph(merged_graph),
        tle_snapshot=first.tle_snapshot,
        observer_site=first.observer_site,
        nominal_rf_hz=first.nominal_rf_hz,
        selection_protocol_digest=first.selection_protocol_digest,
        selection_policy_digest=first.selection_policy_digest,
        tle_membership_authority_digest=first.tle_membership_authority_digest,
        verified_tle_members=first.verified_tle_members,
        propagation_model=first.propagation_model,
        candidates=tuple(candidates),
        source_candidate_count=len(candidates),
        tau_search_policy="fixed-tau-zero-v1",
    )


def _history_as_calibration_mode(
    history: MultiDwellHistoryModeV1,
    episode_by_dwell: dict[str, Sha256Digest],
) -> CatalogueAssociationModeV1:
    assignments = tuple(
        EpisodeCatalogueAssignmentV1(
            episode_id=episode_by_dwell[item.dwell_id],
            catalog_number=item.catalog_number,
        )
        for item in history.assignments
    )
    return CatalogueAssociationModeV1(
        rank=history.rank,
        active_catalog_numbers=history.active_catalog_numbers,
        assignments=assignments,
        tau_choices=tuple(
            CatalogueTauChoiceV1(catalog_number=number, tau_s=0.0)
            for number in history.active_catalog_numbers
        ),
        data_negative_log_evidence=history.cumulative_negative_log_joint,
        active_count_negative_log_prior=0.0,
        active_set_negative_log_prior=0.0,
        assignment_negative_log_prior=0.0,
        tau_negative_log_prior=0.0,
        total_negative_log_joint=history.cumulative_negative_log_joint,
        log_posterior_probability=history.log_posterior_probability,
        posterior_probability=history.posterior_probability,
        component_offsets=tuple[ComponentOffsetEstimateV1, ...](),
        hardware_drifts=tuple[HardwareDriftEstimateV1, ...](),
        handoff_count=history.handoff_count,
        tau_boundary_hit=False,
    )


def _revalidate_calibration_config(
    supplied: JointFrequencyCalibrationConfig | None,
) -> JointFrequencyCalibrationConfig:
    source = supplied or JointFrequencyCalibrationConfig()
    return JointFrequencyCalibrationConfig(
        satellite_bias_prior_sigma_hz=source.satellite_bias_prior_sigma_hz,
        satellite_drift_prior_sigma_hz_s=source.satellite_drift_prior_sigma_hz_s,
        minimum_observations_per_satellite=source.minimum_observations_per_satellite,
        minimum_span_s_per_satellite=source.minimum_span_s_per_satellite,
        hardware_drift_random_walk_sigma_hz_s_per_sqrt_s=(
            source.hardware_drift_random_walk_sigma_hz_s_per_sqrt_s
        ),
        maximum_condition_number=source.maximum_condition_number,
        maximum_mode_observation_evaluations=source.maximum_mode_observation_evaluations,
    )
