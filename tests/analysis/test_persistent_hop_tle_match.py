from __future__ import annotations

from leo.analysis.catalogue_population import select_response_free_starlink_population
from leo.analysis.catalogue_prediction import (
    ExactTauPolicy,
    KnownSiteRfAuthority,
    build_sgp4_catalogue_prediction_bank,
)
from leo.analysis.persistent_hop_tle_match import (
    PersistentHopTleMatchConfig,
    match_persistent_hop_track_to_tles,
)
from leo.contracts.catalogue_association import (
    CataloguePredictionSupportV1,
    PhysicalCfoEpisodeV1,
    PhysicalEpisodeGraphV1,
    SupportIntegratedCfoObservationV1,
)
from leo.contracts.digests import canonical_digest, sha256_digest
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1
from leo.sky.propagation import element_line_checksum, parse_element_sets

_BASE_LINE_ONE = "1 44714U 19074B   26232.62719907  .00001103  00000-0  92799-4 0  9995"
_BASE_LINE_TWO = "2 44714  53.0537 172.0234 0001334  87.1234 273.0021 15.06393004260123"


def _valid_element_line(line: str) -> str:
    return f"{line[:68]}{element_line_checksum(line)}"


def _snapshot_payload() -> str:
    records: list[str] = []
    for index, mean_anomaly_deg in enumerate(range(0, 360, 30)):
        catalog_number = 44714 + index
        first = _valid_element_line(f"1 {catalog_number:05d}{_BASE_LINE_ONE[7:]}")
        second = f"2 {catalog_number:05d}{_BASE_LINE_TWO[7:]}"
        second = _valid_element_line(
            second[:43] + f"{mean_anomaly_deg:8.4f}" + second[51:]
        )
        records.extend((f"STARLINK-{catalog_number}", first, second))
    return "\n".join(records) + "\n"


def _site() -> ObserverSiteV1:
    return ObserverSiteV1(
        latitude_deg=37.858988,
        longitude_deg=-122.478103,
        altitude_m=-29.0,
        label="synthetic-known-site",
    )


def _with_cfo(
    item: SupportIntegratedCfoObservationV1, measured_cfo_hz: float
) -> SupportIntegratedCfoObservationV1:
    return SupportIntegratedCfoObservationV1.model_validate(
        {**item.model_dump(mode="json"), "measured_cfo_hz": measured_cfo_hz}
    )


def _zero_response_graph(payload: str) -> PhysicalEpisodeGraphV1:
    epoch_ns = parse_element_sets(payload).element_epoch_utc_ns()[0]
    first_center_ns = epoch_ns + 58_000 * 1_000_000_000
    episode_id = canonical_digest({"episode": "persistent-hop-synthetic"})
    observations = tuple(
        SupportIntegratedCfoObservationV1(
            observation_id=canonical_digest({"observation": index}),
            source_group_id=canonical_digest({"source": index}),
            episode_id=episode_id,
            receiver_path_id=canonical_digest({"receiver": 0}),
            hardware_epoch_id="hw-persistent-hop-synthetic",
            raw_recording_authority_digest=canonical_digest({"raw": "synthetic"}),
            recording_manifest_digest=canonical_digest({"manifest": "synthetic"}),
            stream_id="rx-0",
            source_binding_digest=canonical_digest({"binding": index}),
            source_sample_start=index * 50_000,
            source_sample_end=(index + 1) * 50_000,
            support_start_utc_ns=first_center_ns + index * 2_000_000_000 - 10_000_000,
            support_center_utc_ns=first_center_ns + index * 2_000_000_000,
            support_end_utc_ns=first_center_ns + index * 2_000_000_000 + 10_000_000,
            measured_cfo_hz=0.0,
            standard_uncertainty_hz=400.0,
            factorial_support_moments_s=(1.0, 0.0, 1.0 / 60_000.0, 0.0),
        )
        for index in range(151)
    )
    episode = PhysicalCfoEpisodeV1(
        episode_id=episode_id,
        dwell_id=canonical_digest({"dwell": "persistent-hop-synthetic"}),
        lane_id=canonical_digest({"lane": "persistent-hop-synthetic"}),
        order_index=0,
        continuity_component_id=canonical_digest({"continuity": "synthetic"}),
        observation_ids=tuple(item.observation_id for item in observations),
    )
    return PhysicalEpisodeGraphV1.create(observations=observations, episodes=(episode,))


def test_matches_a_frozen_300_second_style_track_and_keeps_identity_abstaining() -> None:
    payload = _snapshot_payload()
    graph = _zero_response_graph(payload)
    support = CataloguePredictionSupportV1.from_graph(graph)
    snapshot = TleSnapshotRefV1(
        provider="space-track",
        collected_utc_ns=min(item.support_start_utc_ns for item in graph.observations)
        - 3_600_000_000_000,
        digest=sha256_digest(payload.encode("ascii")),
        object_count=len(parse_element_sets(payload)),
    )
    config = PersistentHopTleMatchConfig(
        selection_protocol_digest=canonical_digest({"protocol": "synthetic-long-scan"}),
        nominal_rf_hz=11_200_000_000.0,
        tau_policy=ExactTauPolicy.fixed_zero(),
    )
    population = select_response_free_starlink_population(
        support,
        payload,
        tle_snapshot=snapshot,
        observer_site=_site(),
        tau_policy=config.tau_policy,
        field_delta_s=0,
        selection_protocol_digest=config.selection_protocol_digest,
        policy=config.population_policy,
    )
    bank = build_sgp4_catalogue_prediction_bank(
        support,
        payload,
        tle_snapshot=snapshot,
        site_rf_authority=KnownSiteRfAuthority.create(
            observer_site=_site(), nominal_rf_hz=config.nominal_rf_hz
        ),
        candidate_universe=population.universe,
        verified_tle_members=population.verified_tle_members,
        tau_policy=config.tau_policy,
        prediction_policy=config.prediction_policy,
    )
    expected = bank.candidates[0]
    predicted = {
        item.observation_id: item.predicted_cfo_hz
        for item in expected.tau_states[0].predictions
    }
    measured = tuple(
        _with_cfo(item, predicted[item.observation_id] + 25_000.0)
        for item in graph.observations
    )
    measured_graph = PhysicalEpisodeGraphV1.create(
        observations=measured,
        episodes=graph.episodes,
    )

    result = match_persistent_hop_track_to_tles(
        measured_graph,
        payload,
        tle_snapshot=snapshot,
        observer_site=_site(),
        config=config,
    )

    assert tuple(item.field_delta_s for item in result.field_matches) == (-500, 0, 500)
    assert result.leading_catalog_number == expected.catalog_number
    assert result.leading_candidate_persisted_on_heldout
    assert result.candidate_only
    assert result.identity_claimed is False
    assert result.all_banks_built_before_response_scoring
    assert result.source_observation_count == 151
    assert result.scored_observation_count == 128
    assert result.support_span_s == 300.02


def test_time_balanced_scoring_keeps_the_endpoints_and_work_bound() -> None:
    payload = _snapshot_payload()
    graph = _zero_response_graph(payload)
    support = CataloguePredictionSupportV1.from_graph(graph)
    snapshot = TleSnapshotRefV1(
        provider="space-track",
        collected_utc_ns=min(item.support_start_utc_ns for item in graph.observations)
        - 3_600_000_000_000,
        digest=sha256_digest(payload.encode("ascii")),
        object_count=len(parse_element_sets(payload)),
    )
    config = PersistentHopTleMatchConfig(
        selection_protocol_digest=canonical_digest({"protocol": "bounded-support"}),
        nominal_rf_hz=11_200_000_000.0,
        maximum_support_observations=20,
        minimum_support_observations=20,
        tau_policy=ExactTauPolicy.fixed_zero(),
    )
    population = select_response_free_starlink_population(
        support,
        payload,
        tle_snapshot=snapshot,
        observer_site=_site(),
        tau_policy=config.tau_policy,
        field_delta_s=0,
        selection_protocol_digest=config.selection_protocol_digest,
        policy=config.population_policy,
    )
    bank = build_sgp4_catalogue_prediction_bank(
        support,
        payload,
        tle_snapshot=snapshot,
        site_rf_authority=KnownSiteRfAuthority.create(
            observer_site=_site(), nominal_rf_hz=config.nominal_rf_hz
        ),
        candidate_universe=population.universe,
        verified_tle_members=population.verified_tle_members,
        tau_policy=config.tau_policy,
        prediction_policy=config.prediction_policy,
    )
    predictions = {
        item.observation_id: item.predicted_cfo_hz
        for item in bank.candidates[0].tau_states[0].predictions
    }
    measured_graph = PhysicalEpisodeGraphV1.create(
        observations=tuple(
            _with_cfo(item, predictions[item.observation_id])
            for item in graph.observations
        ),
        episodes=graph.episodes,
    )

    result = match_persistent_hop_track_to_tles(
        measured_graph,
        payload,
        tle_snapshot=snapshot,
        observer_site=_site(),
        config=config,
    )

    assert result.source_observation_count == 151
    assert result.scored_observation_count == 20
    assert result.support_span_s == 300.02


def test_restricted_null_track_abstains_instead_of_forcing_a_norad() -> None:
    payload = _snapshot_payload()
    graph = _zero_response_graph(payload)
    snapshot = TleSnapshotRefV1(
        provider="space-track",
        collected_utc_ns=min(item.support_start_utc_ns for item in graph.observations)
        - 3_600_000_000_000,
        digest=sha256_digest(payload.encode("ascii")),
        object_count=len(parse_element_sets(payload)),
    )
    config = PersistentHopTleMatchConfig(
        selection_protocol_digest=canonical_digest({"protocol": "null-track"}),
        nominal_rf_hz=11_200_000_000.0,
        tau_policy=ExactTauPolicy.fixed_zero(),
    )

    result = match_persistent_hop_track_to_tles(
        graph,
        payload,
        tle_snapshot=snapshot,
        observer_site=_site(),
        config=config,
    )

    assert result.leading_catalog_number is None
    assert result.abstention_recommended
    assert "restricted-null-led-training" in result.abstention_reasons
    assert result.identity_claimed is False
