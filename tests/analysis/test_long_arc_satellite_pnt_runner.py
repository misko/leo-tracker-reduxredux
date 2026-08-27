from __future__ import annotations

import inspect

import pytest

from leo.analysis.research import long_arc_satellite_pnt_runner as runner_module
from leo.analysis.research.long_arc_satellite_pnt_runner import (
    LongArcExecutionDesign,
    LongArcRunnerInputError,
    long_arc_development_result_payload,
    run_long_arc_development_analysis,
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
_VISIBLE_OFFSET_S = 59_460


def _valid_element_line(line: str) -> str:
    return f"{line[:68]}{element_line_checksum(line)}"


def _element_record(
    catalog_number: int,
    name: str,
    *,
    mean_anomaly_deg: float = 273.0021,
) -> str:
    first = _valid_element_line(f"1 {catalog_number:05d}{_BASE_LINE_ONE[7:]}")
    line_two = _BASE_LINE_TWO.replace("273.0021", f"{mean_anomaly_deg:8.4f}")
    second = _valid_element_line(f"2 {catalog_number:05d}{line_two[7:]}")
    return f"{name}\n{first}\n{second}"


def _snapshot_payload() -> str:
    starlinks = tuple(
        _element_record(
            44714 + index,
            f"STARLINK-{44714 + index}",
            mean_anomaly_deg=index * 30.0,
        )
        for index in range(12)
    )
    return "\n".join((*starlinks, _element_record(44799, "ONEWEB-44799"))) + "\n"


def _graph() -> PhysicalEpisodeGraphV1:
    payload = _snapshot_payload()
    catalogue = parse_element_sets(payload)
    anchor = catalogue.element_epoch_utc_ns()[0] + _VISIBLE_OFFSET_S * 1_000_000_000
    episode_id = canonical_digest({"episode": "long-arc-synthetic"})
    observations = tuple(
        SupportIntegratedCfoObservationV1(
            observation_id=canonical_digest({"observation": index}),
            source_group_id=canonical_digest({"source-group": index}),
            episode_id=episode_id,
            receiver_path_id=canonical_digest({"receiver-path": "synthetic"}),
            hardware_epoch_id="rx_lnb_synthetic",
            raw_recording_authority_digest=canonical_digest({"raw-authority": "synthetic"}),
            recording_manifest_digest=canonical_digest({"manifest": "synthetic"}),
            stream_id="stream_1",
            source_binding_digest=canonical_digest({"source-binding": index}),
            source_sample_start=index * 1_250_000,
            source_sample_end=index * 1_250_000 + 50_000,
            support_start_utc_ns=anchor + index * 500_000_000 - 10_000_000,
            support_center_utc_ns=anchor + index * 500_000_000,
            support_end_utc_ns=anchor + index * 500_000_000 + 10_000_000,
            measured_cfo_hz=(-100_000.0 - 3_000.0 * index * 0.5 + 4.0 * (index * 0.5) ** 2),
            standard_uncertainty_hz=50.0,
            factorial_support_moments_s=(1.0, 0.0, 1.0 / 60_000.0, 0.0),
        )
        for index in range(20)
    )
    episode = PhysicalCfoEpisodeV1(
        episode_id=episode_id,
        dwell_id=canonical_digest({"dwell": "synthetic"}),
        lane_id=canonical_digest({"lane": "synthetic"}),
        order_index=0,
        continuity_component_id=canonical_digest({"continuity": "synthetic"}),
        observation_ids=tuple(item.observation_id for item in observations),
    )
    return PhysicalEpisodeGraphV1.create(observations=observations, episodes=(episode,))


def _snapshot_ref(graph: PhysicalEpisodeGraphV1) -> TleSnapshotRefV1:
    payload = _snapshot_payload()
    return TleSnapshotRefV1(
        provider="space-track",
        collected_utc_ns=min(item.support_start_utc_ns for item in graph.observations)
        - 3_600_000_000_000,
        digest=sha256_digest(payload.encode("ascii")),
        object_count=len(parse_element_sets(payload)),
    )


def _site() -> ObserverSiteV1:
    return ObserverSiteV1(
        latitude_deg=37.858988,
        longitude_deg=-122.478103,
        altitude_m=-29.0,
        label="synthetic-known-site",
    )


def _run(graph: PhysicalEpisodeGraphV1 | None = None):  # type: ignore[no-untyped-def]
    selected_graph = _graph() if graph is None else graph
    return run_long_arc_development_analysis(
        arc_id="synthetic-opened-development-arc",
        graph=selected_graph,
        prediction_support=CataloguePredictionSupportV1.from_graph(selected_graph),
        snapshot_payload=_snapshot_payload(),
        tle_snapshot=_snapshot_ref(selected_graph),
        observer_site=_site(),
        design=LongArcExecutionDesign(
            selection_protocol_digest=canonical_digest({"protocol": "synthetic"}),
        ),
    )


def test_runner_builds_all_fields_before_scoring_and_reports_all_partitions() -> None:
    result = _run()

    assert tuple(item.field_delta_s for item in result.field_banks) == (-500, 0, 500)
    assert all(item.propagation_complete_for_association for item in result.field_banks)
    assert tuple(item.label for item in result.partitions) == (
        "main-60-to-100",
        "rolling-40-to-60",
        "rolling-60-to-80",
        "rolling-80-to-100",
    )
    assert tuple(
        (len(item.training_observation_ids), len(item.evaluation_observation_ids))
        for item in result.partitions
    ) == ((12, 8), (8, 4), (12, 4), (16, 4))
    for partition in result.partitions:
        assert tuple(item.field_delta_s for item in partition.field_scores) == (-500, 0, 500)
        assert len(partition.wrong_epoch_observations) == 2
        assert tuple(item.polynomial_degree for item in partition.orbit_radio_comparisons) == (
            1,
            2,
            3,
        )
        assert all(item.observe_only for item in partition.wrong_epoch_observations)
        for field_score in partition.field_scores:
            assert field_score.association.thresholds_are_descriptive_only is True
            assert field_score.catalogue_future_pooled_rms_hz > 0.0
            assert field_score.catalogue_future_equal_calendar_block_rms_hz > 0.0
            assert sum(
                item.observation_count for item in field_score.catalogue_future_calendar_blocks
            ) == len(partition.evaluation_observation_ids)
            candidate_scores = tuple(
                item
                for item in field_score.association.scores
                if item.kind == "catalogue-candidate"
            )
            assert all(len(item.tau_profile_training_scores) == 41 for item in candidate_scores)
    assert result.all_response_free_banks_built_before_response_scoring is True
    assert result.wrong_epoch_is_observe_only is True
    assert result.numerical_thresholds_applied is False
    assert result.identity_claimed is False
    assert result.secure_norad_claimed is False
    assert result.positioning_validation_claimed is False
    payload = long_arc_development_result_payload(result)
    assert payload["result_digest"] == result.result_digest


def test_future_response_change_preserves_banks_and_training_fit() -> None:
    graph = _graph()
    changed_rows = list(graph.observations)
    for index in range(12, len(changed_rows)):
        changed_rows[index] = changed_rows[index].model_copy(
            update={"measured_cfo_hz": changed_rows[index].measured_cfo_hz + 20_000.0}
        )
    changed_graph = PhysicalEpisodeGraphV1.create(
        observations=tuple(changed_rows),
        episodes=graph.episodes,
    )

    original = _run(graph)
    changed = _run(changed_graph)

    assert original.field_banks == changed.field_banks
    assert original.result_digest != changed.result_digest
    original_main = original.partitions[0]
    changed_main = changed.partitions[0]
    assert tuple(
        item.association.training_nearest_catalog_number for item in original_main.field_scores
    ) == tuple(
        item.association.training_nearest_catalog_number for item in changed_main.field_scores
    )
    assert tuple(
        item.association.scores[0].training_total_negative_log_score
        for item in original_main.field_scores
    ) == pytest.approx(
        tuple(
            item.association.scores[0].training_total_negative_log_score
            for item in changed_main.field_scores
        )
    )
    assert tuple(
        item.association.scores[0].heldout_predictive_negative_log_score
        for item in original_main.field_scores
    ) != pytest.approx(
        tuple(
            item.association.scores[0].heldout_predictive_negative_log_score
            for item in changed_main.field_scores
        )
    )

    object.__setattr__(original, "partitions", original.partitions[1:])
    with pytest.raises(LongArcRunnerInputError, match="result digest"):
        long_arc_development_result_payload(original)


def test_stale_response_graph_is_rejected_before_population_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _graph()
    poisoned = graph.model_copy(update={"content_digest": "sha256:" + "0" * 64})

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("population work started before graph validation")

    monkeypatch.setattr(runner_module, "select_response_free_starlink_population", forbidden)
    with pytest.raises(LongArcRunnerInputError, match="response graph is invalid"):
        _run(poisoned)


def test_design_and_prediction_support_are_fail_closed() -> None:
    graph = _graph()
    support = CataloguePredictionSupportV1.from_graph(graph)
    poisoned_support = support.model_copy(update={"content_digest": "sha256:" + "0" * 64})
    with pytest.raises(LongArcRunnerInputError, match="prediction support is invalid"):
        run_long_arc_development_analysis(
            arc_id="synthetic",
            graph=graph,
            prediction_support=poisoned_support,
            snapshot_payload=_snapshot_payload(),
            tle_snapshot=_snapshot_ref(graph),
            observer_site=_site(),
            design=LongArcExecutionDesign(
                selection_protocol_digest=canonical_digest({"protocol": "synthetic"})
            ),
        )

    valid = LongArcExecutionDesign(
        selection_protocol_digest=canonical_digest({"protocol": "synthetic"})
    )
    object.__setattr__(valid, "catalogue_fields_s", (-500, 0, 30))
    with pytest.raises(LongArcRunnerInputError, match="execution design is invalid"):
        _run_with_design(graph, valid)


def _run_with_design(graph: PhysicalEpisodeGraphV1, design: LongArcExecutionDesign):  # type: ignore[no-untyped-def]
    return run_long_arc_development_analysis(
        arc_id="synthetic",
        graph=graph,
        prediction_support=CataloguePredictionSupportV1.from_graph(graph),
        snapshot_payload=_snapshot_payload(),
        tle_snapshot=_snapshot_ref(graph),
        observer_site=_site(),
        design=design,
    )


def test_runner_import_and_signature_boundaries() -> None:
    source = inspect.getsource(runner_module)
    signature = inspect.signature(run_long_arc_development_analysis)

    assert "leo.storage" not in source
    assert "leo.infrastructure" not in source
    assert "read_iq" not in source
    assert "write_text" not in source
    assert set(signature.parameters) == {
        "arc_id",
        "graph",
        "prediction_support",
        "snapshot_payload",
        "tle_snapshot",
        "observer_site",
        "design",
    }
