from __future__ import annotations

import math

import pytest

from leo.analysis.research.multi_dwell_catalogue_adapter_v2 import (
    MultiDwellCatalogueAdapterV2CompatibilityError,
    MultiDwellCatalogueAdapterV2Config,
    MultiDwellCatalogueAdapterV2Error,
    MultiDwellCatalogueAdapterV2WorkLimitError,
    lower_staged_catalogue_v2_to_v1_filter_inputs,
    multi_dwell_catalogue_adapter_v2_payload,
    multi_dwell_catalogue_v2_input_inventory_digest,
    stage_multi_dwell_catalogue_inputs_v2,
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
_CATALOGUE_ONE = 10_001
_CATALOGUE_TWO = 10_002
_TAU_VALUES = (-5.0, 0.0, 5.0)


def _digest(label: str, value: object) -> str:
    return canonical_digest({label: value})


def _graph(
    dwell_index: int,
    *,
    episode_count: int,
    response_shift_hz: float = 0.0,
) -> PhysicalEpisodeGraphV1:
    dwell_id = _digest("v2-dwell", dwell_index)
    observations: list[SupportIntegratedCfoObservationV1] = []
    episodes: list[PhysicalCfoEpisodeV1] = []
    for episode_index in range(episode_count):
        episode_id = _digest("v2-episode", (dwell_index, episode_index))
        episode_rows: list[SupportIntegratedCfoObservationV1] = []
        for row_index in range(2):
            center_ns = (
                _BASE_UTC_NS
                + dwell_index * 30_000_000_000
                + episode_index * 3_000_000_000
                + row_index * 1_000_000_000
            )
            row = SupportIntegratedCfoObservationV1(
                observation_id=_digest(
                    "v2-observation",
                    (dwell_index, episode_index, row_index),
                ),
                source_group_id=_digest(
                    "v2-source-group",
                    (dwell_index, episode_index, row_index),
                ),
                episode_id=episode_id,
                receiver_path_id=_digest("v2-path", episode_index),
                hardware_epoch_id="receiver-a",
                raw_recording_authority_digest=_digest("v2-authority", "synthetic"),
                recording_manifest_digest=_digest("v2-manifest", "synthetic"),
                stream_id=f"stream-{episode_index}",
                source_binding_digest=_digest(
                    "v2-source-binding",
                    (dwell_index, episode_index, row_index),
                ),
                source_sample_start=(dwell_index * 1_000 + row_index * 10) * 100,
                source_sample_end=(dwell_index * 1_000 + row_index * 10) * 100 + 50,
                support_start_utc_ns=center_ns - 10_000_000,
                support_center_utc_ns=center_ns,
                support_end_utc_ns=center_ns + 10_000_000,
                measured_cfo_hz=(
                    100.0 + 2.0 * dwell_index + 5.0 * episode_index + row_index + response_shift_hz
                ),
                standard_uncertainty_hz=1.0 + 0.1 * row_index,
                factorial_support_moments_s=(1.0, 0.0, 0.000_001, 0.0),
            )
            observations.append(row)
            episode_rows.append(row)
        episodes.append(
            PhysicalCfoEpisodeV1(
                episode_id=episode_id,
                dwell_id=dwell_id,
                lane_id=_digest("v2-lane", episode_index),
                order_index=0,
                continuity_component_id=_digest(
                    "v2-continuity",
                    (dwell_index, episode_index),
                ),
                observation_ids=tuple(item.observation_id for item in episode_rows),
            )
        )
    return PhysicalEpisodeGraphV1.create(
        observations=tuple(observations),
        episodes=tuple(episodes),
    )


def _bank(
    graph: PhysicalEpisodeGraphV1,
    dwell_index: int,
    *,
    eligibility_by_catalogue: dict[int, tuple[int, ...]],
    tau_log_weights: tuple[float, float, float] = (0.0, 0.0, 0.0),
    source_candidate_count: int | None = None,
) -> CataloguePredictionBankV1:
    chronological_episodes = sorted(
        graph.episodes,
        key=lambda item: min(
            row.support_start_utc_ns
            for row in graph.observations
            if row.episode_id == item.episode_id
        ),
    )
    episode_by_index = {index: item for index, item in enumerate(chronological_episodes)}
    prediction_reference_ns = min(item.support_center_utc_ns for item in graph.observations)
    element_epoch_ns = _BASE_UTC_NS - 100_000_000_000
    candidates: list[CatalogueCandidatePredictionV1] = []
    for catalog_number in sorted(eligibility_by_catalogue):
        eligible_episode_ids = tuple(
            sorted(
                episode_by_index[index].episode_id
                for index in eligibility_by_catalogue[catalog_number]
            )
        )
        eligible_rows = tuple(
            item for item in graph.observations if item.episode_id in eligible_episode_ids
        )
        tau_states = []
        for tau_s, log_weight in zip(_TAU_VALUES, tau_log_weights, strict=True):
            predictions = tuple(
                sorted(
                    (
                        CandidateObservationPredictionV1(
                            observation_id=row.observation_id,
                            predicted_cfo_hz=(
                                catalog_number / 1_000.0
                                + (row.support_center_utc_ns - prediction_reference_ns) / 1e9
                                + 0.25 * tau_s
                            ),
                            standard_uncertainty_hz=0.3,
                        )
                        for row in eligible_rows
                    ),
                    key=lambda item: item.observation_id,
                )
            )
            tau_states.append(
                CandidateTauStateV1(
                    tau_s=tau_s,
                    log_prior_weight=log_weight,
                    predictions=predictions,
                )
            )
        candidates.append(
            CatalogueCandidatePredictionV1(
                catalog_number=catalog_number,
                object_name=f"STARLINK-{catalog_number}",
                selected_element_digest=_digest(
                    "v2-element",
                    (dwell_index, catalog_number),
                ),
                element_epoch_utc_ns=element_epoch_ns,
                element_age_s_at_reference=abs(prediction_reference_ns - element_epoch_ns) / 1e9,
                eligible_episode_ids=eligible_episode_ids,
                tau_states=tuple(tau_states),
            )
        )
    candidate_tuple = tuple(candidates)
    return CataloguePredictionBankV1.create(
        support=CataloguePredictionSupportV1.from_graph(graph),
        tle_snapshot=TleSnapshotRefV1(
            provider="space-track",
            collected_utc_ns=_BASE_UTC_NS - 1_000_000_000,
            digest=_digest("v2-tle-snapshot", dwell_index),
            object_count=12_000,
        ),
        observer_site=ObserverSiteV1(
            latitude_deg=37.0,
            longitude_deg=-122.0,
            altitude_m=10.0,
            label="v2-synthetic-site",
        ),
        nominal_rf_hz=11_325_000_000.0,
        selection_protocol_digest=_digest("v2-selection-protocol", "shared"),
        selection_policy_digest=_digest("v2-selection-policy", "shared"),
        tle_membership_authority_digest=_digest("v2-membership", dwell_index),
        verified_tle_members=tuple(
            CatalogueVerifiedTleMemberV1(
                catalog_number=item.catalog_number,
                selected_element_digest=item.selected_element_digest,
                element_epoch_utc_ns=item.element_epoch_utc_ns,
            )
            for item in candidate_tuple
        ),
        propagation_model="synthetic-support-integrated",
        candidates=candidate_tuple,
        source_candidate_count=source_candidate_count,
        tau_search_policy="bounded-profile-minus5-plus5-v1",
    )


def _inputs(
    *,
    final_response_shift_hz: float = 0.0,
) -> tuple[
    tuple[PhysicalEpisodeGraphV1, ...],
    tuple[CataloguePredictionBankV1, ...],
]:
    graphs = (
        _graph(0, episode_count=1),
        _graph(1, episode_count=2),
        _graph(2, episode_count=1),
        _graph(3, episode_count=1, response_shift_hz=final_response_shift_hz),
    )
    banks = (
        _bank(
            graphs[0],
            0,
            eligibility_by_catalogue={_CATALOGUE_ONE: (0,)},
        ),
        _bank(
            graphs[1],
            1,
            eligibility_by_catalogue={
                _CATALOGUE_ONE: (0,),
                _CATALOGUE_TWO: (1,),
            },
        ),
        _bank(
            graphs[2],
            2,
            eligibility_by_catalogue={_CATALOGUE_TWO: (0,)},
        ),
        _bank(
            graphs[3],
            3,
            eligibility_by_catalogue={
                _CATALOGUE_ONE: (0,),
                _CATALOGUE_TWO: (0,),
            },
        ),
    )
    return graphs, banks


def _config(
    graphs: tuple[PhysicalEpisodeGraphV1, ...],
    banks: tuple[CataloguePredictionBankV1, ...],
    **overrides: object,
) -> MultiDwellCatalogueAdapterV2Config:
    values: dict[str, object] = {
        "expected_input_inventory_digest": (
            multi_dwell_catalogue_v2_input_inventory_digest(graphs, banks)
        )
    }
    values.update(overrides)
    return MultiDwellCatalogueAdapterV2Config(**values)  # type: ignore[arg-type]


def test_visibility_birth_death_null_and_handoff_opportunity_are_explicit() -> None:
    graphs, banks = _inputs()
    staged = stage_multi_dwell_catalogue_inputs_v2(
        graphs=graphs,
        prediction_banks=banks,
        config=_config(graphs, banks),
    )

    assert tuple(item.visible_catalog_numbers for item in staged.dwells) == (
        (_CATALOGUE_ONE,),
        (_CATALOGUE_ONE, _CATALOGUE_TWO),
        (_CATALOGUE_TWO,),
        (_CATALOGUE_ONE, _CATALOGUE_TWO),
    )
    assert tuple(item.entered_visibility_catalog_numbers for item in staged.dwells) == (
        (_CATALOGUE_ONE,),
        (_CATALOGUE_TWO,),
        (),
        (_CATALOGUE_ONE,),
    )
    assert tuple(item.departed_visibility_catalog_numbers for item in staged.dwells) == (
        (),
        (),
        (_CATALOGUE_ONE,),
        (),
    )
    null_mode_id = staged.dwell_mode_opportunities[0].mode_ids[0]
    assert all(item.mode_ids[0] == null_mode_id for item in staged.dwell_mode_opportunities)
    assert null_mode_id not in {item.mode_id for item in staged.persistent_modes}
    assert {item.kind for item in staged.transitions} == {
        "null-stay",
        "birth-from-null",
        "death-to-null",
        "same-catalogue-tau",
        "catalogue-handoff",
    }
    modes = {item.mode_id: item for item in staged.persistent_modes}
    handoffs = tuple(item for item in staged.transitions if item.kind == "catalogue-handoff")
    assert handoffs
    assert all(
        modes[item.from_mode_id].catalog_number != modes[item.to_mode_id].catalog_number
        for item in handoffs
    )
    assert staged.changing_visibility_present is True
    assert staged.complete_response_free_banks is True
    assert staged.measured_response_used_for_mode_construction is False
    assert staged.likelihood_evaluated is False
    assert staged.real_evidence_claimed is False
    assert staged.identity_claimed is False


def test_multiple_episodes_keep_episode_local_candidate_opportunity_and_stop_at_staging() -> None:
    graphs, banks = _inputs()
    staged = stage_multi_dwell_catalogue_inputs_v2(
        graphs=graphs,
        prediction_banks=banks,
        config=_config(graphs, banks),
    )
    modes = {item.mode_id: item.catalog_number for item in staged.persistent_modes}
    second_dwell_episodes = tuple(
        item for item in staged.episode_mode_opportunities if item.dwell_index == 1
    )

    assert staged.multiple_episodes_per_dwell_present is True
    assert len(staged.dwells[1].graph.episodes) == 2
    assert staged.dwells[1].graph == graphs[1]
    assert staged.dwells[1].prediction_bank == banks[1]
    assert len(second_dwell_episodes) == 2
    episode_catalogues = tuple(
        {modes[mode_id] for mode_id in opportunity.mode_ids[1:]}
        for opportunity in second_dwell_episodes
    )
    assert episode_catalogues == ({_CATALOGUE_ONE}, {_CATALOGUE_TWO})
    assert all(item.null_mode_explicit for item in second_dwell_episodes)
    assert staged.staging_only is True
    assert staged.v1_filter_lowering_supported is False
    assert len(staged.v1_downstream_incompatibilities) == 3
    with pytest.raises(MultiDwellCatalogueAdapterV2CompatibilityError, match="cannot be lowered"):
        lower_staged_catalogue_v2_to_v1_filter_inputs(staged)


def test_catalogue_tau_mode_is_persistent_and_cannot_switch_per_dwell() -> None:
    graphs, banks = _inputs()
    staged = stage_multi_dwell_catalogue_inputs_v2(
        graphs=graphs,
        prediction_banks=banks,
        config=_config(graphs, banks),
    )
    constraints = {item.catalog_number: item for item in staged.tau_persistence_constraints}
    modes = {item.mode_id: item for item in staged.persistent_modes}

    assert tuple(item.tau_s for item in staged.persistent_tau_grid) == _TAU_VALUES
    assert math.fsum(
        math.exp(item.normalized_log_prior_weight) for item in staged.persistent_tau_grid
    ) == pytest.approx(1.0, abs=1e-15)
    assert constraints[_CATALOGUE_ONE].visible_dwell_indices == (0, 1, 3)
    assert constraints[_CATALOGUE_ONE].persists_across_null_or_invisible_gaps is True
    assert set(constraints[_CATALOGUE_ONE].mode_ids) <= set(staged.dwells[0].mode_ids)
    assert set(constraints[_CATALOGUE_ONE].mode_ids) <= set(staged.dwells[3].mode_ids)
    same_catalogue = tuple(item for item in staged.transitions if item.kind == "same-catalogue-tau")
    assert same_catalogue
    assert all(
        modes[item.from_mode_id].catalog_number == modes[item.to_mode_id].catalog_number
        and modes[item.from_mode_id].tau_s == modes[item.to_mode_id].tau_s
        and item.from_mode_id == item.to_mode_id
        for item in same_catalogue
    )
    assert not any(
        item.from_mode_id in modes
        and item.to_mode_id in modes
        and modes[item.from_mode_id].catalog_number == modes[item.to_mode_id].catalog_number
        and modes[item.from_mode_id].tau_s != modes[item.to_mode_id].tau_s
        for item in staged.transitions
    )


def test_future_response_mutation_changes_no_response_free_or_earlier_staging() -> None:
    graphs, banks = _inputs()
    changed_graphs, changed_banks = _inputs(final_response_shift_hz=250.0)
    first = stage_multi_dwell_catalogue_inputs_v2(
        graphs=graphs,
        prediction_banks=banks,
        config=_config(graphs, banks),
    )
    changed = stage_multi_dwell_catalogue_inputs_v2(
        graphs=changed_graphs,
        prediction_banks=changed_banks,
        config=_config(changed_graphs, changed_banks),
    )

    assert first.response_free_inventory_digest == changed.response_free_inventory_digest
    assert first.prediction_bank_content_digests == changed.prediction_bank_content_digests
    assert first.persistent_tau_grid == changed.persistent_tau_grid
    assert first.persistent_modes == changed.persistent_modes
    assert first.tau_persistence_constraints == changed.tau_persistence_constraints
    assert first.episode_mode_opportunities == changed.episode_mode_opportunities
    assert first.dwell_mode_opportunities == changed.dwell_mode_opportunities
    assert first.transitions == changed.transitions
    assert first.dwells[:3] == changed.dwells[:3]
    assert first.dwells[3].prediction_bank == changed.dwells[3].prediction_bank
    assert first.dwells[3].graph != changed.dwells[3].graph
    assert first.graph_content_digests != changed.graph_content_digests
    assert first.input_inventory_digest != changed.input_inventory_digest
    assert first.content_digest != changed.content_digest


def test_contract_poison_wrong_support_and_result_digest_fail_closed() -> None:
    graphs, banks = _inputs()
    stale_graph = graphs[0].model_copy(update={"content_digest": _digest("v2-stale", "graph")})
    stale_graphs = (stale_graph, *graphs[1:])
    with pytest.raises(MultiDwellCatalogueAdapterV2Error, match="digest closure"):
        stage_multi_dwell_catalogue_inputs_v2(
            graphs=stale_graphs,
            prediction_banks=banks,
            config=_config(stale_graphs, banks),
        )

    poisoned_bank = banks[0].model_copy(update={"response_accessed": True})
    poisoned_banks = (poisoned_bank, *banks[1:])
    with pytest.raises(MultiDwellCatalogueAdapterV2Error, match="digest closure"):
        stage_multi_dwell_catalogue_inputs_v2(
            graphs=graphs,
            prediction_banks=poisoned_banks,
            config=_config(graphs, poisoned_banks),
        )

    wrong_support_banks = (banks[1], *banks[1:])
    with pytest.raises(MultiDwellCatalogueAdapterV2Error, match="exact response-free"):
        stage_multi_dwell_catalogue_inputs_v2(
            graphs=graphs,
            prediction_banks=wrong_support_banks,
            config=_config(graphs, wrong_support_banks),
        )

    staged = stage_multi_dwell_catalogue_inputs_v2(
        graphs=graphs,
        prediction_banks=banks,
        config=_config(graphs, banks),
    )
    payload = multi_dwell_catalogue_adapter_v2_payload(staged)
    claimed = payload.pop("content_digest")
    assert claimed == canonical_digest(payload)
    object.__setattr__(staged, "content_digest", _digest("v2-tamper", "result"))
    with pytest.raises(MultiDwellCatalogueAdapterV2Error, match="does not close"):
        multi_dwell_catalogue_adapter_v2_payload(staged)


def test_persistent_grid_completeness_chronology_digest_and_work_caps_are_strict() -> None:
    graphs, banks = _inputs()
    mismatched_last = _bank(
        graphs[3],
        3,
        eligibility_by_catalogue={
            _CATALOGUE_ONE: (0,),
            _CATALOGUE_TWO: (0,),
        },
        tau_log_weights=(0.0, -1.0, 0.0),
    )
    mismatched_banks = (*banks[:3], mismatched_last)
    with pytest.raises(MultiDwellCatalogueAdapterV2Error, match="persistent tau grid"):
        stage_multi_dwell_catalogue_inputs_v2(
            graphs=graphs,
            prediction_banks=mismatched_banks,
            config=_config(graphs, mismatched_banks),
        )

    truncated_first = _bank(
        graphs[0],
        0,
        eligibility_by_catalogue={_CATALOGUE_ONE: (0,)},
        source_candidate_count=2,
    )
    truncated_banks = (truncated_first, *banks[1:])
    with pytest.raises(MultiDwellCatalogueAdapterV2Error, match="complete, not truncated"):
        stage_multi_dwell_catalogue_inputs_v2(
            graphs=graphs,
            prediction_banks=truncated_banks,
            config=_config(graphs, truncated_banks),
        )

    reversed_graphs = tuple(reversed(graphs))
    reversed_banks = tuple(reversed(banks))
    with pytest.raises(MultiDwellCatalogueAdapterV2Error, match="chronological"):
        stage_multi_dwell_catalogue_inputs_v2(
            graphs=reversed_graphs,
            prediction_banks=reversed_banks,
            config=_config(reversed_graphs, reversed_banks),
        )

    with pytest.raises(MultiDwellCatalogueAdapterV2Error, match="predeclared"):
        stage_multi_dwell_catalogue_inputs_v2(
            graphs=graphs,
            prediction_banks=banks,
            config=MultiDwellCatalogueAdapterV2Config(
                expected_input_inventory_digest=_digest("v2-wrong", "inventory")
            ),
        )

    with pytest.raises(
        MultiDwellCatalogueAdapterV2WorkLimitError,
        match="prediction rows",
    ):
        stage_multi_dwell_catalogue_inputs_v2(
            graphs=graphs,
            prediction_banks=banks,
            config=_config(
                graphs,
                banks,
                maximum_candidate_tau_prediction_rows=1,
            ),
        )
