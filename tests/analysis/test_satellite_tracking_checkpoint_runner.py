from __future__ import annotations

from dataclasses import asdict, replace

import pytest

from leo.analysis.catalogue_prediction_array_view import (
    CataloguePredictionArrayViewError,
    catalogue_prediction_array_view_from_bank,
    verify_catalogue_prediction_array_bank_view,
)
from leo.analysis.research import satellite_tracking_checkpoint_runner as checkpoint_runner
from leo.analysis.research.block_predictive_evidence import CalendarBlockCovariance
from leo.analysis.research.satellite_tracking_checkpoint_runner import (
    LongArcBlockEvidenceDesign,
    LongArcCatalogueConnectedNeighborhoodReceipt,
    SatelliteTrackingCheckpointInputError,
    close_long_arc_block_evidence_run,
    long_arc_block_evidence_run_payload,
    score_registered_long_arc_model_families,
    seal_long_arc_catalogue_connected_neighborhood_binding,
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


def _digest(label: str, value: object) -> str:
    return canonical_digest({label: value})


def _graph(
    *, future_delta_hz: float = 0.0, support_time_shift_ns: int = 0
) -> PhysicalEpisodeGraphV1:
    episode_id = _digest("episode", 1)
    start_ns = 1_800_000_000_100_000_000
    observations = tuple(
        SupportIntegratedCfoObservationV1(
            observation_id=_digest("observation", index),
            source_group_id=_digest("source", index),
            episode_id=episode_id,
            receiver_path_id=_digest("path", 1),
            hardware_epoch_id="rx_lnb_fixture",
            raw_recording_authority_digest=_digest("raw", 1),
            recording_manifest_digest=_digest("manifest", 1),
            stream_id="stream_1",
            source_binding_digest=_digest("binding", index),
            source_sample_start=index * 50_000,
            source_sample_end=(index + 1) * 50_000,
            support_start_utc_ns=(start_ns + support_time_shift_ns + index * 500_000_000),
            support_center_utc_ns=(
                start_ns + support_time_shift_ns + index * 500_000_000 + 10_000_000
            ),
            support_end_utc_ns=(
                start_ns + support_time_shift_ns + index * 500_000_000 + 20_000_000
            ),
            measured_cfo_hz=(1_000.0 + 25.0 * index + (future_delta_hz if index >= 6 else 0.0)),
            standard_uncertainty_hz=10.0,
            factorial_support_moments_s=(1.0, 0.0, 0.0, 0.0),
        )
        for index in range(12)
    )
    episode = PhysicalCfoEpisodeV1(
        episode_id=episode_id,
        dwell_id=_digest("dwell", 1),
        lane_id=_digest("lane", 1),
        order_index=0,
        continuity_component_id=_digest("continuity", 1),
        observation_ids=tuple(item.observation_id for item in observations),
    )
    return PhysicalEpisodeGraphV1.create(observations=observations, episodes=(episode,))


def _bank(graph: PhysicalEpisodeGraphV1) -> CataloguePredictionBankV1:
    support = CataloguePredictionSupportV1.from_graph(graph)
    ordered = tuple(sorted(graph.observations, key=lambda item: item.support_center_utc_ns))
    members = tuple(
        CatalogueVerifiedTleMemberV1(
            catalog_number=number,
            selected_element_digest=_digest("element", number),
            element_epoch_utc_ns=1_799_999_000_000_000_000 + number,
        )
        for number in (10001, 10002)
    )
    candidates = tuple(
        CatalogueCandidatePredictionV1(
            catalog_number=member.catalog_number,
            object_name=f"STARLINK-{member.catalog_number}",
            selected_element_digest=member.selected_element_digest,
            element_epoch_utc_ns=member.element_epoch_utc_ns,
            element_age_s_at_reference=(
                min(row.support_center_utc_ns for row in support.observations)
                - member.element_epoch_utc_ns
            )
            / 1e9,
            eligible_episode_ids=support.episode_ids,
            tau_states=(
                CandidateTauStateV1(
                    tau_s=0.0,
                    log_prior_weight=0.0,
                    predictions=tuple(
                        sorted(
                            (
                                CandidateObservationPredictionV1(
                                    observation_id=row.observation_id,
                                    predicted_cfo_hz=(
                                        (25.0 if member.catalog_number == 10001 else 22.0) * index
                                    ),
                                    standard_uncertainty_hz=1.0,
                                )
                                for index, row in enumerate(ordered)
                            ),
                            key=lambda item: item.observation_id,
                        )
                    ),
                ),
            ),
        )
        for member in members
    )
    return CataloguePredictionBankV1.create(
        support=support,
        tle_snapshot=TleSnapshotRefV1(
            provider="space-track",
            collected_utc_ns=1_799_000_000_000_000_000,
            digest=_digest("tle", 1),
            object_count=2,
        ),
        observer_site=ObserverSiteV1(
            latitude_deg=37.0,
            longitude_deg=-122.0,
            altitude_m=0.0,
            label="fixture-site",
        ),
        nominal_rf_hz=11_440_312_498.0,
        selection_protocol_digest=_digest("protocol", 1),
        selection_policy_digest=_digest("selection", 1),
        tle_membership_authority_digest=_digest("membership", 1),
        verified_tle_members=members,
        propagation_model="fixture-propagation-v1",
        candidates=candidates,
    )


def _design() -> LongArcBlockEvidenceDesign:
    return LongArcBlockEvidenceDesign(
        covariance=CalendarBlockCovariance(
            measurement_variance_scale=1.0,
            independent_variance_floor_hz2=0.0,
            block_common_variance_hz2=25.0,
            calibration_authority_digest=_digest("covariance", 1),
            calibrated=False,
        ),
        receiver_nuisance_prior_authority_digest=_digest("receiver-nuisance-prior", 1),
        training_block_fraction=0.5,
    )


def _connected_neighborhood_binding(run):
    return seal_long_arc_catalogue_connected_neighborhood_binding(
        source_observability_result_digest=_digest("c1-result", 1),
        source_profiled_tau_atlas_digest=_digest("c1-profiled-tau-atlas", 1),
        prediction_bank_content_digest=run.prediction_bank_content_digest,
        c2_receiver_nuisance_basis_digest=run.receiver_nuisance_basis_digest,
        tau_values_s=(0.0,),
        nuisance_model="offset-plus-ridge-drift-v1",
        drift_prior_sigma_hz_per_s=20.0,
        reference_measurement_sigma_hz=50.0,
        floor_history_ms=125.0,
        floor_hz=57.75,
        floor_source_digest=_digest("c1-floor", 125),
        floor_calibrated=False,
        complete_tau_cross_product_evaluated=True,
        tau_pairing_semantics="independent-complete-cross-product-minimum-v1",
        candidate_node_semantics=("one-node-per-catalogue-identity-all-tau-states-unified-v1"),
        threshold_graph_semantics=("edge-if-any-profiled-state-pair-within-floor-v1"),
        identity_gate_applied=False,
        receipts=tuple(
            LongArcCatalogueConnectedNeighborhoodReceipt(
                state_id=item.state_id,
                catalog_number=item.catalog_number,
                tau_s=item.tau_s,
                connected_neighborhood_label=_digest("c1-component", item.catalog_number),
            )
            for item in run.state_receipts
            if item.state_kind == "catalogue"
            and item.catalog_number is not None
            and item.tau_s is not None
        ),
    )


def _binding_authority(binding):
    return {
        "source_observability_result_digest": (binding.source_observability_result_digest),
        "source_profiled_tau_atlas_digest": binding.source_profiled_tau_atlas_digest,
        "prediction_bank_content_digest": binding.prediction_bank_content_digest,
        "c2_receiver_nuisance_basis_digest": (binding.c2_receiver_nuisance_basis_digest),
        "tau_values_s": binding.tau_values_s,
        "nuisance_model": binding.nuisance_model,
        "drift_prior_sigma_hz_per_s": binding.drift_prior_sigma_hz_per_s,
        "reference_measurement_sigma_hz": binding.reference_measurement_sigma_hz,
        "floor_history_ms": binding.floor_history_ms,
        "floor_hz": binding.floor_hz,
        "floor_source_digest": binding.floor_source_digest,
        "floor_calibrated": binding.floor_calibrated,
        "complete_tau_cross_product_evaluated": (binding.complete_tau_cross_product_evaluated),
        "tau_pairing_semantics": binding.tau_pairing_semantics,
        "candidate_node_semantics": binding.candidate_node_semantics,
        "threshold_graph_semantics": binding.threshold_graph_semantics,
        "identity_gate_applied": binding.identity_gate_applied,
    }


def _reseal_run(run, **changes):
    candidate = replace(run, **changes)
    body = {
        "graph_content_digest": candidate.graph_content_digest,
        "prediction_bank_content_digest": candidate.prediction_bank_content_digest,
        "design_digest": candidate.design_digest,
        "receiver_nuisance_basis_digest": candidate.receiver_nuisance_basis_digest,
        "training_observation_ids": candidate.training_observation_ids,
        "evaluation_observation_ids": candidate.evaluation_observation_ids,
        "state_receipts": tuple(asdict(item) for item in candidate.state_receipts),
        "evidence_result_digest": candidate.evidence.result_digest,
        "algorithm_version": candidate.algorithm_version,
        "full_catalogue_tau_inventory_scored": True,
        "common_block_covariance_used": True,
        "common_receiver_nuisance_basis_used": True,
        "receiver_nuisance_parameters_calibrated": False,
        "opportunity_inventory_complete": False,
        "missing_opportunities_retained": False,
        "coverage_conditioned_on_observed_rows": True,
        "posterior_claim_abstained": True,
        "posterior_probability_calibrated": False,
        "empirical_calibration_applied": False,
        "identity_claimed": False,
    }
    return replace(candidate, content_digest=canonical_digest(body))


@pytest.mark.parametrize(
    "tau_values_s",
    (
        (False,),
        (0,),
        (float("nan"),),
        (0.0, 0.0),
        (1.0, 0.0),
    ),
)
def test_c1_profiled_binding_requires_exact_ordered_float_tau_grid(
    tau_values_s: object,
) -> None:
    run = score_registered_long_arc_model_families(_graph(), _bank(_graph()), design=_design())
    binding = _connected_neighborhood_binding(run)

    with pytest.raises(SatelliteTrackingCheckpointInputError, match="ordered finite tau grid"):
        seal_long_arc_catalogue_connected_neighborhood_binding(
            **{
                **_binding_authority(binding),
                "tau_values_s": tau_values_s,
            },  # type: ignore[arg-type]
            receipts=binding.receipts,
        )


def test_c1_profiled_candidate_label_propagates_across_exact_tau_grid() -> None:
    run = score_registered_long_arc_model_families(_graph(), _bank(_graph()), design=_design())
    source = _connected_neighborhood_binding(run)
    primary = source.receipts[0]
    sensitivity = replace(
        primary,
        state_id=_digest("c1-sensitivity-state", 1),
        tau_s=1.0,
    )
    binding = seal_long_arc_catalogue_connected_neighborhood_binding(
        **{
            **_binding_authority(source),
            "tau_values_s": (0.0, 1.0),
        },
        receipts=(primary, sensitivity),
    )

    assert binding.tau_values_s == (0.0, 1.0)
    assert len({item.connected_neighborhood_label for item in binding.receipts}) == 1
    with pytest.raises(SatelliteTrackingCheckpointInputError, match="propagate across tau states"):
        seal_long_arc_catalogue_connected_neighborhood_binding(
            **{
                **_binding_authority(source),
                "tau_values_s": (0.0, 1.0),
            },
            receipts=(
                primary,
                replace(
                    sensitivity,
                    connected_neighborhood_label=_digest("different-c1-component", 1),
                ),
            ),
        )


def test_c1_profiled_binding_rejects_tau_inventory_or_semantic_substitution() -> None:
    run = score_registered_long_arc_model_families(_graph(), _bank(_graph()), design=_design())
    binding = _connected_neighborhood_binding(run)

    with pytest.raises(SatelliteTrackingCheckpointInputError, match="exactly the profiled tau"):
        seal_long_arc_catalogue_connected_neighborhood_binding(
            **{
                **_binding_authority(binding),
                "tau_values_s": (1.0,),
            },
            receipts=binding.receipts,
        )
    with pytest.raises(SatelliteTrackingCheckpointInputError, match="pairing semantics"):
        seal_long_arc_catalogue_connected_neighborhood_binding(
            **{
                **_binding_authority(binding),
                "tau_pairing_semantics": "same-tau-only-v1",
            },  # type: ignore[arg-type]
            receipts=binding.receipts,
        )
    with pytest.raises(SatelliteTrackingCheckpointInputError, match="graph semantics"):
        seal_long_arc_catalogue_connected_neighborhood_binding(
            **{
                **_binding_authority(binding),
                "threshold_graph_semantics": "edge-at-tau-zero-v1",
            },  # type: ignore[arg-type]
            receipts=binding.receipts,
        )
    with pytest.raises(SatelliteTrackingCheckpointInputError, match="complete tau cross product"):
        seal_long_arc_catalogue_connected_neighborhood_binding(
            **{
                **_binding_authority(binding),
                "complete_tau_cross_product_evaluated": False,
            },  # type: ignore[arg-type]
            receipts=binding.receipts,
        )


def test_runner_scores_complete_catalogue_and_radio_inventory() -> None:
    graph = _graph()
    result = score_registered_long_arc_model_families(
        graph,
        _bank(graph),
        design=_design(),
    )
    payload = long_arc_block_evidence_run_payload(result)

    assert len(result.state_receipts) == 6
    assert sum(item.state_kind == "catalogue" for item in result.state_receipts) == 2
    assert tuple(
        item.polynomial_degree for item in result.state_receipts if item.state_kind == "radio"
    ) == (1, 2, 3)
    assert not set(result.training_observation_ids) & set(result.evaluation_observation_ids)
    assert result.evidence.shared_measurement_covariance_across_families is True
    assert result.evidence.score_before_assimilate is True
    assert result.evidence.empirical_rank_calibration_applied is False
    assert result.evidence.identity_claimed is False
    assert result.receiver_nuisance_parameters_calibrated is False
    assert result.common_receiver_nuisance_basis_used is True
    assert result.evidence.opportunity_inventory_complete is False
    assert result.evidence.missing_opportunities_retained is False
    assert result.evidence.coverage_conditioned_on_observed_rows is True
    assert result.evidence.evaluation_observation_coverage is None
    assert result.evidence.evaluation_block_coverage is None
    assert result.evidence.abstention_recommended is True
    assert "incomplete-opportunity-inventory" in result.evidence.abstention_diagnostics
    assert (
        tuple(
            observation_id
            for block in result.evidence.blocks
            for observation_id in block.observation_ids
        )
        == result.evaluation_observation_ids
    )
    final_family_mass = sum(item.normalized_model_mass_final for item in result.evidence.families)
    assert final_family_mass == pytest.approx(1.0)
    assert payload["content_digest"] == result.content_digest


def test_runner_future_response_changes_scores_not_frozen_inventory() -> None:
    graph = _graph()
    changed = _graph(future_delta_hz=300.0)
    bank = _bank(graph)
    first = score_registered_long_arc_model_families(graph, bank, design=_design())
    second = score_registered_long_arc_model_families(changed, bank, design=_design())

    assert first.prediction_bank_content_digest == second.prediction_bank_content_digest
    assert first.design_digest == second.design_digest
    assert first.state_receipts == second.state_receipts
    assert first.evidence.hypothesis_inventory_digest == second.evidence.hypothesis_inventory_digest
    assert (
        first.evidence.evaluation_mixture_prequential_negative_log_likelihood
        != second.evidence.evaluation_mixture_prequential_negative_log_likelihood
    )


def test_every_family_uses_the_same_receiver_offset_and_drift_basis() -> None:
    graph = _graph()
    design = _design()
    observations = checkpoint_runner._observations(graph)
    states, receipts, basis_digest, compact_axes = checkpoint_runner._states(
        observations,
        _bank(graph),
        design,
    )
    assert compact_axes is None

    expected_shared_covariance = (
        (design.receiver_offset_prior_sigma_hz**2, 0.0),
        (0.0, design.receiver_drift_prior_sigma_hz_per_s**2),
    )
    for state, receipt in zip(states, receipts, strict=True):
        assert receipt.receiver_nuisance_basis_digest == basis_digest
        assert receipt.receiver_nuisance_parameter_count == 2
        assert state.parameter_prior_mean[:2] == (0.0, 0.0)
        assert tuple(row[:2] for row in state.parameter_prior_covariance[:2]) == (
            expected_shared_covariance
        )
        assert all(
            model.design_row[:2]
            == (
                1.0,
                (observation.support_center_utc_ns - observations[0].support_center_utc_ns) / 1e9,
            )
            for model, observation in zip(
                state.observation_models,
                observations,
                strict=True,
            )
        )
        assert receipt.structural_parameter_count == (
            receipt.polynomial_degree if receipt.state_kind == "radio" else 0
        )

    radio_degree_one = next(
        state
        for state, receipt in zip(states, receipts, strict=True)
        if receipt.state_kind == "radio" and receipt.polynomial_degree == 1
    )
    assert all(
        model.design_row[1] == model.design_row[2] for model in radio_degree_one.observation_models
    )


def test_array_bank_view_matches_public_bank_without_retaining_catalogue_rows() -> None:
    graph = _graph()
    public_bank = _bank(graph)
    array_view = catalogue_prediction_array_view_from_bank(public_bank, field_delta_s=0)
    design = _design()

    public_run = score_registered_long_arc_model_families(
        graph,
        public_bank,
        design=design,
    )
    array_run = score_registered_long_arc_model_families(
        graph,
        array_view,
        design=design,
    )

    assert array_run.state_receipts == public_run.state_receipts
    assert tuple(
        item.training_predictive_negative_log_likelihood for item in array_run.evidence.states
    ) == pytest.approx(
        tuple(
            item.training_predictive_negative_log_likelihood for item in public_run.evidence.states
        )
    )
    assert tuple(
        item.evaluation_predictive_negative_log_likelihood for item in array_run.evidence.states
    ) == pytest.approx(
        tuple(
            item.evaluation_predictive_negative_log_likelihood
            for item in public_run.evidence.states
        )
    )
    states, _, _, state_axes = checkpoint_runner._states(
        checkpoint_runner._observations(graph),
        array_view,
        design,
    )
    assert state_axes is not None
    catalogue_states = tuple(item for item in states if item.family == "catalogue-orbit")
    assert all(item.observation_models == () for item in catalogue_states)
    assert all(
        item.prediction_inventory_reference_digest
        == array_view.prediction_inventory_authority_digest
        for item in catalogue_states
    )


def test_array_bank_view_revalidation_rejects_same_shape_read_only_cube_substitution() -> None:
    array_view = catalogue_prediction_array_view_from_bank(_bank(_graph()), field_delta_s=0)
    substituted = array_view.predicted_cfo_hz.copy()
    substituted[0, 0, 0] += 1.0
    substituted.setflags(write=False)
    assert substituted.shape == array_view.predicted_cfo_hz.shape
    assert substituted.dtype == array_view.predicted_cfo_hz.dtype
    object.__setattr__(array_view, "predicted_cfo_hz", substituted)

    with pytest.raises(
        CataloguePredictionArrayViewError,
        match="prediction array view is invalid",
    ) as error:
        verify_catalogue_prediction_array_bank_view(array_view)
    assert error.value.__cause__ is not None
    assert "axes or cube bytes" in str(error.value.__cause__)


def test_runner_rejects_support_and_design_poison() -> None:
    graph = _graph()
    other = _graph(support_time_shift_ns=1_000_000)
    with pytest.raises(SatelliteTrackingCheckpointInputError, match="does not bind"):
        score_registered_long_arc_model_families(
            other,
            _bank(graph),
            design=_design(),
        )
    with pytest.raises(SatelliteTrackingCheckpointInputError, match="proper"):
        replace(_design(), receiver_offset_prior_sigma_hz=0.0)


def test_c2_run_closes_through_c3_with_external_c1_classes() -> None:
    graph = _graph()
    run = score_registered_long_arc_model_families(
        graph,
        _bank(graph),
        design=_design(),
    )
    binding = _connected_neighborhood_binding(run)

    closure = close_long_arc_block_evidence_run(
        run,
        sequence_label="fixture-long-arc",
        connected_neighborhood_binding=binding,
    )

    assert closure.graph_content_digest == run.graph_content_digest
    assert closure.connected_neighborhood_map_digest == binding.content_digest
    assert closure.development_limitations == ("incomplete-opportunity-inventory",)
    assert closure.final_summary.outcome is not None
    assert closure.final_summary.outcome.outcome == "unresolved"
    assert closure.final_summary.outcome.reason == "incomplete-opportunity-inventory"
    assert len(closure.rolling_summaries) == len(run.evidence.blocks)
    assert len(closure.final_hypothesis_posterior) == len(run.state_receipts)
    family_counts = {
        item.family: item.evaluated_state_count for item in closure.final_summary.family_posterior
    }
    assert family_counts["h0-radio-null"] == 4
    assert family_counts["h1-single-candidate"] == 2
    assert family_counts["h1-switch"] == 0
    assert family_counts["k2-two-candidate"] == 0
    assert tuple(item.status for item in closure.optional_family_availability) == (
        "structurally-inapplicable",
        "structurally-inapplicable",
    )
    source_summary = run.evidence.states[1]
    bridged = next(
        item
        for item in closure.final_hypothesis_posterior
        if item.hypothesis_id == source_summary.state_id
    )
    assert bridged.normalized_log_prior_probability == (
        source_summary.normalized_log_model_mass_after_training
    )
    expected_cumulative_score = -sum(
        block.state_scores[1].predictive_negative_log_likelihood for block in run.evidence.blocks
    )
    assert bridged.cumulative_proper_log_score == pytest.approx(expected_cumulative_score)
    assert closure.candidate_selection_performed is False
    assert closure.rf_response_accessed is False
    assert closure.likelihood_fitted is False
    assert closure.identity_claimed is False


def test_c2_to_c3_bridge_preserves_underflowed_training_log_mass() -> None:
    graph = _graph()
    run = score_registered_long_arc_model_families(
        graph,
        _bank(graph),
        design=replace(_design(), family_log_weights=(-5_000.0, 0.0, 0.0)),
    )
    source_null = next(item for item in run.evidence.states if item.family == "null")
    assert source_null.normalized_log_model_mass_after_training < -1_000.0
    assert source_null.normalized_model_mass_after_training == 0.0

    closure = close_long_arc_block_evidence_run(
        run,
        sequence_label="underflow-log-prior",
        connected_neighborhood_binding=_connected_neighborhood_binding(run),
    )

    bridged_null = next(
        item
        for item in closure.final_hypothesis_posterior
        if item.hypothesis_id == source_null.state_id
    )
    assert bridged_null.normalized_log_prior_probability == (
        source_null.normalized_log_model_mass_after_training
    )
    assert bridged_null.prior_probability == 0.0
    assert bridged_null.prior_probability_representable is False


def test_c2_to_c3_bridge_rejects_incomplete_or_poisoned_c1_receipts() -> None:
    graph = _graph()
    run = score_registered_long_arc_model_families(
        graph,
        _bank(graph),
        design=_design(),
    )
    binding = _connected_neighborhood_binding(run)
    incomplete = seal_long_arc_catalogue_connected_neighborhood_binding(
        **_binding_authority(binding),
        receipts=binding.receipts[:-1],
    )
    with pytest.raises(SatelliteTrackingCheckpointInputError, match="one-to-one"):
        close_long_arc_block_evidence_run(
            run,
            sequence_label="incomplete-c1",
            connected_neighborhood_binding=incomplete,
        )

    poisoned_receipt = replace(
        binding.receipts[0],
        catalog_number=binding.receipts[0].catalog_number + 100,
    )
    poisoned_identity = seal_long_arc_catalogue_connected_neighborhood_binding(
        **_binding_authority(binding),
        receipts=(poisoned_receipt, *binding.receipts[1:]),
    )
    with pytest.raises(
        SatelliteTrackingCheckpointInputError,
        match="catalogue/tau identity differs",
    ):
        close_long_arc_block_evidence_run(
            run,
            sequence_label="poisoned-c1-identity",
            connected_neighborhood_binding=poisoned_identity,
        )

    with pytest.raises(SatelliteTrackingCheckpointInputError, match="digest"):
        close_long_arc_block_evidence_run(
            run,
            sequence_label="poisoned-c1-digest",
            connected_neighborhood_binding=replace(
                binding,
                content_digest=_digest("wrong-binding-content", 1),
            ),
        )

    with pytest.raises(SatelliteTrackingCheckpointInputError, match="digest"):
        close_long_arc_block_evidence_run(
            run,
            sequence_label="poisoned-profiled-atlas-digest",
            connected_neighborhood_binding=replace(
                binding,
                source_profiled_tau_atlas_digest=_digest("different-profiled-atlas", 1),
            ),
        )

    wrong_basis = seal_long_arc_catalogue_connected_neighborhood_binding(
        **{
            **_binding_authority(binding),
            "c2_receiver_nuisance_basis_digest": _digest("different-c2-basis", 1),
        },
        receipts=binding.receipts,
    )
    with pytest.raises(SatelliteTrackingCheckpointInputError, match="receiver nuisance basis"):
        close_long_arc_block_evidence_run(
            run,
            sequence_label="poisoned-c2-nuisance-basis",
            connected_neighborhood_binding=wrong_basis,
        )


def test_c2_to_c3_bridge_rejects_mutated_c2_score_receipt() -> None:
    graph = _graph()
    run = score_registered_long_arc_model_families(
        graph,
        _bank(graph),
        design=_design(),
    )
    first_block = run.evidence.blocks[0]
    first_score = first_block.state_scores[0]
    poisoned_block = replace(
        first_block,
        state_scores=(
            replace(
                first_score,
                predictive_negative_log_likelihood=(
                    first_score.predictive_negative_log_likelihood + 1.0
                ),
            ),
            *first_block.state_scores[1:],
        ),
    )
    poisoned_evidence = replace(
        run.evidence,
        blocks=(poisoned_block, *run.evidence.blocks[1:]),
    )
    poisoned_run = replace(run, evidence=poisoned_evidence)

    with pytest.raises(
        SatelliteTrackingCheckpointInputError,
        match="does not digest-close",
    ):
        close_long_arc_block_evidence_run(
            poisoned_run,
            sequence_label="poisoned-c2-score",
            connected_neighborhood_binding=_connected_neighborhood_binding(run),
        )


def test_c2_to_c3_bridge_rejects_relabelled_canonical_catalogue_receipt() -> None:
    graph = _graph()
    run = score_registered_long_arc_model_families(graph, _bank(graph), design=_design())
    index = next(
        index for index, item in enumerate(run.state_receipts) if item.state_kind == "catalogue"
    )
    original = run.state_receipts[index]
    assert original.catalog_number is not None
    poisoned = replace(original, catalog_number=original.catalog_number + 100)
    receipts = (*run.state_receipts[:index], poisoned, *run.state_receipts[index + 1 :])
    poisoned_run = _reseal_run(run, state_receipts=receipts)

    with pytest.raises(SatelliteTrackingCheckpointInputError, match="kind and metadata"):
        close_long_arc_block_evidence_run(
            poisoned_run,
            sequence_label="relabelled-catalogue-receipt",
            connected_neighborhood_binding=_connected_neighborhood_binding(poisoned_run),
        )


def test_c2_to_c3_bridge_rejects_permuted_evaluation_observation_receipts() -> None:
    graph = _graph()
    run = score_registered_long_arc_model_families(graph, _bank(graph), design=_design())
    poisoned_run = _reseal_run(
        run,
        evaluation_observation_ids=tuple(reversed(run.evaluation_observation_ids)),
    )

    with pytest.raises(SatelliteTrackingCheckpointInputError, match="exact ordered"):
        close_long_arc_block_evidence_run(
            poisoned_run,
            sequence_label="permuted-evaluation-receipts",
            connected_neighborhood_binding=_connected_neighborhood_binding(run),
        )


def test_c2_to_c3_bridge_rejects_permuted_training_observation_receipts() -> None:
    graph = _graph()
    run = score_registered_long_arc_model_families(graph, _bank(graph), design=_design())
    poisoned_run = _reseal_run(
        run,
        training_observation_ids=tuple(reversed(run.training_observation_ids)),
    )

    with pytest.raises(SatelliteTrackingCheckpointInputError, match="partition digest"):
        close_long_arc_block_evidence_run(
            poisoned_run,
            sequence_label="permuted-training-receipts",
            connected_neighborhood_binding=_connected_neighborhood_binding(run),
        )
