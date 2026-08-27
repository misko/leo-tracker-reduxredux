from __future__ import annotations

from collections.abc import Callable

import pytest
from pydantic import ValidationError

from leo.analysis.multi_dwell_catalogue_adapter import (
    MultiDwellCatalogueAdapterConfig,
    MultiDwellCatalogueAdapterError,
    adapt_catalogue_dwells_to_filter_inputs,
)
from leo.analysis.multi_dwell_catalogue_smoothing import (
    MultiDwellFilterConfig,
    filter_multi_dwell_catalogue_modes,
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


def _digest(label: str, value: object) -> str:
    return canonical_digest({label: value})


def _curve_one(time_s: float) -> float:
    return -35.0 * time_s + 5.0 * time_s**2


def _curve_two(time_s: float) -> float:
    return 18.0 * time_s - 4.0 * time_s**2


_CURVES: dict[int, Callable[[float], float]] = {
    10_001: _curve_one,
    10_002: _curve_two,
}


def _dwell_graph(index: int, *, response_shift_hz: float = 0.0) -> PhysicalEpisodeGraphV1:
    episode_id = _digest("episode", index)
    observations = []
    for row_index, local_time_s in enumerate((-1.5, -0.5, 0.5, 1.5)):
        center_utc_ns = _BASE_UTC_NS + index * 10_000_000_000 + round((local_time_s + 1.5) * 1e9)
        observation_id = _digest("observation", (index, row_index))
        observations.append(
            SupportIntegratedCfoObservationV1(
                observation_id=observation_id,
                source_group_id=_digest("source-group", (index, row_index)),
                episode_id=episode_id,
                receiver_path_id=_digest("path", index),
                hardware_epoch_id="receiver-a",
                raw_recording_authority_digest=_digest("authority", "synthetic"),
                recording_manifest_digest=_digest("manifest", "synthetic"),
                stream_id="stream-1",
                source_binding_digest=_digest("binding", (index, row_index)),
                source_sample_start=(index * 100 + row_index) * 100,
                source_sample_end=(index * 100 + row_index) * 100 + 50,
                support_start_utc_ns=center_utc_ns - 10_000_000,
                support_center_utc_ns=center_utc_ns,
                support_end_utc_ns=center_utc_ns + 10_000_000,
                measured_cfo_hz=20.0 + _curve_one(local_time_s) + response_shift_hz,
                standard_uncertainty_hz=1.0,
                factorial_support_moments_s=(1.0, 0.0, 0.000_016_666_666_7, 0.0),
            )
        )
    episode = PhysicalCfoEpisodeV1(
        episode_id=episode_id,
        dwell_id=_digest("dwell", index),
        lane_id=_digest("lane", "sequential"),
        order_index=0,
        continuity_component_id=_digest("component", index),
        observation_ids=tuple(item.observation_id for item in observations),
    )
    return PhysicalEpisodeGraphV1.create(
        observations=tuple(observations),
        episodes=(episode,),
    )


def _prediction_bank(
    graph: PhysicalEpisodeGraphV1,
    *,
    candidate_numbers: tuple[int, ...] = (10_001, 10_002),
    source_candidate_count: int | None = None,
    bounded_tau: bool = False,
) -> CataloguePredictionBankV1:
    episode = graph.episodes[0]
    rows = tuple(
        next(item for item in graph.observations if item.observation_id == observation_id)
        for observation_id in episode.observation_ids
    )
    center_ns = (rows[0].support_center_utc_ns + rows[-1].support_center_utc_ns) / 2.0
    prediction_reference_utc_ns = min(item.support_center_utc_ns for item in rows)
    element_epoch_utc_ns = _BASE_UTC_NS - 10_000_000_000
    candidates = []
    for catalog_number in candidate_numbers:
        predictions = tuple(
            sorted(
                (
                    CandidateObservationPredictionV1(
                        observation_id=row.observation_id,
                        predicted_cfo_hz=_CURVES[catalog_number](
                            (row.support_center_utc_ns - center_ns) / 1e9
                        ),
                        standard_uncertainty_hz=0.2,
                    )
                    for row in rows
                ),
                key=lambda item: item.observation_id,
            )
        )
        tau_values = (-5.0, 0.0, 5.0) if bounded_tau else (0.0,)
        candidates.append(
            CatalogueCandidatePredictionV1(
                catalog_number=catalog_number,
                object_name=f"STARLINK-{catalog_number}",
                selected_element_digest=_digest("element", catalog_number),
                element_epoch_utc_ns=element_epoch_utc_ns,
                element_age_s_at_reference=(prediction_reference_utc_ns - element_epoch_utc_ns)
                / 1e9,
                eligible_episode_ids=(episode.episode_id,),
                tau_states=tuple(
                    CandidateTauStateV1(
                        tau_s=tau,
                        log_prior_weight=0.0,
                        predictions=predictions,
                    )
                    for tau in tau_values
                ),
            )
        )
    candidates_tuple = tuple(candidates)
    return CataloguePredictionBankV1.create(
        support=CataloguePredictionSupportV1.from_graph(graph),
        tle_snapshot=TleSnapshotRefV1(
            provider="space-track",
            collected_utc_ns=_BASE_UTC_NS - 1_000_000_000,
            digest=_digest("snapshot", "synthetic"),
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
        tle_membership_authority_digest=_digest("membership", "synthetic"),
        verified_tle_members=tuple(
            CatalogueVerifiedTleMemberV1(
                catalog_number=item.catalog_number,
                selected_element_digest=item.selected_element_digest,
                element_epoch_utc_ns=item.element_epoch_utc_ns,
            )
            for item in candidates_tuple
        ),
        propagation_model="synthetic-support-integrated",
        candidates=candidates_tuple,
        source_candidate_count=source_candidate_count,
        tau_search_policy=(
            "bounded-profile-minus5-plus5-v1" if bounded_tau else "fixed-tau-zero-v1"
        ),
    )


def test_contract_adapter_drives_the_causal_filter_without_response_ranking() -> None:
    graphs = (_dwell_graph(0), _dwell_graph(1))
    banks = tuple(_prediction_bank(item) for item in graphs)

    adapted = adapt_catalogue_dwells_to_filter_inputs(
        graphs=graphs,
        prediction_banks=banks,
    )
    filtered = filter_multi_dwell_catalogue_modes(
        adapted.dwells,
        adapted.prediction_bank,
        config=MultiDwellFilterConfig(
            initial_candidate_log_weight=2.0,
            initial_null_log_weight=-2.0,
            dwell_offset_prior_standard_uncertainty_hz=100.0,
            null_prediction_standard_uncertainty_hz=1.0,
        ),
    )

    assert adapted.dwell_ids == tuple(item.episodes[0].dwell_id for item in graphs)
    assert adapted.catalog_numbers == (10_001, 10_002)
    assert adapted.response_free_prediction_bank is True
    assert adapted.simultaneous_emitters_supported is False
    assert filtered.final_modes[0].assignments == (10_001, 10_001)


def test_response_change_does_not_change_prediction_bank_lineage() -> None:
    first_graphs = (_dwell_graph(0), _dwell_graph(1))
    changed_graphs = (_dwell_graph(0), _dwell_graph(1, response_shift_hz=50.0))
    banks = tuple(_prediction_bank(item) for item in first_graphs)
    changed_banks = tuple(_prediction_bank(item) for item in changed_graphs)

    first = adapt_catalogue_dwells_to_filter_inputs(
        graphs=first_graphs,
        prediction_banks=banks,
    )
    changed = adapt_catalogue_dwells_to_filter_inputs(
        graphs=changed_graphs,
        prediction_banks=changed_banks,
    )

    assert first.prediction_bank == changed.prediction_bank
    assert first.prediction_bank_content_digests == changed.prediction_bank_content_digests
    assert first.graph_content_digests != changed.graph_content_digests
    assert first.dwells != changed.dwells


def test_adapter_rejects_truncated_or_inconsistent_candidate_universe() -> None:
    graphs = (_dwell_graph(0), _dwell_graph(1))
    with pytest.raises(MultiDwellCatalogueAdapterError, match="truncated"):
        adapt_catalogue_dwells_to_filter_inputs(
            graphs=graphs,
            prediction_banks=(
                _prediction_bank(graphs[0], source_candidate_count=3),
                _prediction_bank(graphs[1], source_candidate_count=3),
            ),
        )

    with pytest.raises(MultiDwellCatalogueAdapterError, match="same complete"):
        adapt_catalogue_dwells_to_filter_inputs(
            graphs=graphs,
            prediction_banks=(
                _prediction_bank(graphs[0]),
                _prediction_bank(graphs[1], candidate_numbers=(10_001,)),
            ),
        )


def test_adapter_rejects_tau_profiling_and_wrong_support() -> None:
    graphs = (_dwell_graph(0), _dwell_graph(1))
    with pytest.raises(MultiDwellCatalogueAdapterError, match="fixed tau=0"):
        adapt_catalogue_dwells_to_filter_inputs(
            graphs=graphs,
            prediction_banks=tuple(_prediction_bank(item, bounded_tau=True) for item in graphs),
        )

    with pytest.raises(MultiDwellCatalogueAdapterError, match="exact response-free"):
        adapt_catalogue_dwells_to_filter_inputs(
            graphs=graphs,
            prediction_banks=(
                _prediction_bank(graphs[1]),
                _prediction_bank(graphs[1]),
            ),
        )


def test_adapter_rejects_reversed_chronology_and_work_overrun() -> None:
    graphs = (_dwell_graph(0), _dwell_graph(1))
    banks = tuple(_prediction_bank(item) for item in graphs)
    with pytest.raises(MultiDwellCatalogueAdapterError, match="chronological"):
        adapt_catalogue_dwells_to_filter_inputs(
            graphs=tuple(reversed(graphs)),
            prediction_banks=tuple(reversed(banks)),
        )
    with pytest.raises(MultiDwellCatalogueAdapterError, match="candidate-row"):
        adapt_catalogue_dwells_to_filter_inputs(
            graphs=graphs,
            prediction_banks=banks,
            config=MultiDwellCatalogueAdapterConfig(maximum_candidate_row_evaluations=15),
        )


def test_adapter_revalidates_graph_before_conversion() -> None:
    graph = _dwell_graph(0)
    bank = _prediction_bank(graph)
    poisoned = graph.model_copy(update={"content_digest": _digest("stale", "graph")})

    with pytest.raises(ValidationError, match="digest"):
        adapt_catalogue_dwells_to_filter_inputs(
            graphs=(poisoned,),
            prediction_banks=(bank,),
        )
