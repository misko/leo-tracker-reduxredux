from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from pydantic import JsonValue

from leo.analysis.adapters import (
    production_standard_v2_configuration,
    production_standard_v2_registry,
)
from leo.analysis.standard import (
    TRAJECTORY_BANK_PRODUCT,
    build_probe_schedule,
    build_standard_source_binding,
    build_standard_source_bindings,
    decode_standard_product,
)
from leo.analysis.standard import analyzers as standard_analyzers
from leo.analysis.standard import reports as standard_reports
from leo.analysis.standard.analyzers import (
    PathAlternateTracksAnalyzer,
    PathPilotScanAnalyzer,
    PathTrajectoryBankAnalyzer,
    PathTrajectoryFeedbackAnalyzer,
)
from leo.analysis.standard.products import (
    ALTERNATE_CFO_TRACK_BANK_PRODUCT,
    ALTERNATE_CFO_TRACKS_PNG_PRODUCT,
    GLRT64_TRAJECTORY_TABLE_PRODUCT,
    NUMERICAL_WATERFALL_PRODUCT,
    PATH_REPORT_V1_PRODUCT,
    PILOT_SCAN_PRODUCT,
    POWER_TIMELINE_PRODUCT,
    PROBE_SCHEDULE_PRODUCT,
    QUALITY_PRODUCT,
    TRAJECTORY_FEEDBACK_PRODUCT,
)
from leo.analysis.standard.source_bindings import (
    STANDARD_FINAL_SOURCE_BINDING_SPECS,
    STANDARD_SOURCE_BINDING_SPECS,
    build_standard_final_source_bindings,
)
from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.cfo_dealias import default_cfo_dealias_config
from leo.analysis.starlink.pilot_methods import PilotProbeDetection
from leo.artifacts import MemoryOutputSink, MemoryProductReader
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_pipeline import (
    PilotProbeCertificateV2,
    ProbeScheduleV2,
    StandardPathInputBindV3,
    StandardScientificStatus,
)
from leo.pipeline import AnalysisContext, ScopeIdentityV1, StageOutcome

_FROZEN = Path("corpus/goldens/trial-132-standard-v3-one-second-frozen.json")
_SESSION = "production-24h-20260819-01-trial-00000132"


class _NoIq:
    @property
    def sample_rate_hz(self) -> int:
        raise AssertionError("product-only stage read IQ")

    @property
    def center_frequency_hz(self) -> int:
        raise AssertionError("product-only stage read IQ")

    @property
    def sample_count(self) -> int:
        raise AssertionError("product-only stage read IQ")

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        raise AssertionError("product-only stage read IQ")

    def iter_blocks(self, *, block_samples: int):
        del block_samples
        raise AssertionError("product-only stage read IQ")


def test_production_registry_matches_frozen_stage_and_product_topology() -> None:
    registry = production_standard_v2_registry()
    configuration = production_standard_v2_configuration()
    assert set(configuration) == set(registry.keys)
    assert configuration["path-standard"] == {
        "waterfall": {
            "fft_samples": 1024,
            "frequency_bins": 256,
            "maximum_time_bins": 512,
        },
        "feedback": {
            "maximum_workers": 4,
            "maximum_scored_candidates_per_probe": 8,
            "probe_offsets_ms": [0, 25],
            "cfo_acquisition_mode": "independent_wide_per_probe",
            "cfo_search_min_hz": -400_000.0,
            "cfo_search_max_hz": 400_000.0,
        },
        "dealias": default_cfo_dealias_config().model_dump(mode="json"),
    }
    planned = tuple(item.key for item in registry.graph().plan())

    assert set(registry.keys) == {
        "path-standard",
        "path-alternate-tracks",
        "radio-scientific-report",
        "paired-scientific-report",
        "paired-presentation",
    }
    assert len(planned) == 5
    path_products = sum(
        len(registry.get(key).spec.output_products)
        for key in registry.keys
        if key.startswith("path-")
    )
    aggregate_products = sum(
        len(registry.get(key).spec.output_products)
        for key in ("radio-scientific-report", "paired-scientific-report")
    )
    assert path_products == 22
    paired_presentation_products = len(registry.get("paired-presentation").spec.output_products)
    assert (
        4 * path_products + 2 * (aggregate_products - 1) + 1 + paired_presentation_products == 106
    )


@pytest.mark.parametrize(
    ("outcomes", "expected"),
    (
        ((StageOutcome.COMPLETE, StageOutcome.NO_RESULT), StageOutcome.COMPLETE),
        ((StageOutcome.NO_RESULT, StageOutcome.NO_RESULT), StageOutcome.NO_RESULT),
        ((StageOutcome.COMPLETE, StageOutcome.COMPLETE), StageOutcome.COMPLETE),
        (
            (StageOutcome.COMPLETE, StageOutcome.PARTIAL_COVERAGE),
            StageOutcome.PARTIAL_COVERAGE,
        ),
        (
            (StageOutcome.COMPLETE, StageOutcome.INSUFFICIENT_DATA),
            StageOutcome.INSUFFICIENT_DATA,
        ),
    ),
)
def test_paired_presentation_outcome_distinguishes_no_hit_from_incomplete_coverage(
    outcomes: tuple[StageOutcome, ...], expected: StageOutcome
) -> None:
    assert standard_analyzers._aggregate_outcome(outcomes) is expected


def test_strict_codecs_accept_frozen_one_second_products_and_reject_mutation() -> None:
    frozen = json.loads(_FROZEN.read_bytes())
    documents = frozen["documents"]
    products = (
        (QUALITY_PRODUCT, documents[QUALITY_PRODUCT.kind]),
        (POWER_TIMELINE_PRODUCT, documents[POWER_TIMELINE_PRODUCT.kind]),
        (NUMERICAL_WATERFALL_PRODUCT, documents[NUMERICAL_WATERFALL_PRODUCT.kind]),
        (PILOT_SCAN_PRODUCT, documents[PILOT_SCAN_PRODUCT.kind]),
        (TRAJECTORY_BANK_PRODUCT, documents[TRAJECTORY_BANK_PRODUCT.kind]),
        (TRAJECTORY_FEEDBACK_PRODUCT, documents[TRAJECTORY_FEEDBACK_PRODUCT.kind]),
        (
            GLRT64_TRAJECTORY_TABLE_PRODUCT,
            documents[GLRT64_TRAJECTORY_TABLE_PRODUCT.kind],
        ),
        (PATH_REPORT_V1_PRODUCT, frozen["products"]["report"]),
    )
    for product, document in products:
        assert decode_standard_product(product, document) == document

    mutated = deepcopy(documents[PILOT_SCAN_PRODUCT.kind])
    mutated["undeclared"] = True
    with pytest.raises(ValueError, match="closed schema"):
        decode_standard_product(PILOT_SCAN_PRODUCT, mutated)
    nonfinite = deepcopy(documents[PILOT_SCAN_PRODUCT.kind])
    nonfinite["detections"][0]["time_s"] = float("nan")
    with pytest.raises(ValueError, match="nan|finite"):
        decode_standard_product(PILOT_SCAN_PRODUCT, nonfinite)
    candidate_free_complete = deepcopy(documents[PILOT_SCAN_PRODUCT.kind])
    candidate_free_complete["detections"][0].update(
        status="complete",
        local_epoch_sample=None,
        acquired_cfo_hz=None,
        scores=[],
        qam_accuracy=None,
        qam_evm=None,
        source_candidate_count=0,
        truncated_candidate_count=0,
        candidates=[],
    )
    with pytest.raises(ValueError, match="complete pilot detection requires"):
        decode_standard_product(PILOT_SCAN_PRODUCT, candidate_free_complete)

    malformed = (
        (PILOT_SCAN_PRODUCT, "detections"),
        (TRAJECTORY_BANK_PRODUCT, "trajectories"),
        (TRAJECTORY_FEEDBACK_PRODUCT, "results"),
        (GLRT64_TRAJECTORY_TABLE_PRODUCT, "trajectories"),
    )
    for product, field in malformed:
        changed = deepcopy(documents[product.kind])
        changed[field] = [{"garbage": True}]
        with pytest.raises(ValueError):
            decode_standard_product(product, changed)


@pytest.mark.parametrize(
    ("probe_status", "expected_outcome"),
    (
        (NumericalStatus.NO_RESULT, StageOutcome.NO_RESULT),
        (NumericalStatus.INSUFFICIENT, StageOutcome.INSUFFICIENT_DATA),
    ),
)
def test_pilot_scan_preserves_candidate_free_probe_outcome(
    monkeypatch: pytest.MonkeyPatch,
    probe_status: NumericalStatus,
    expected_outcome: StageOutcome,
) -> None:
    binding, schedule, scope, reader = _scheduled_path()
    detections = tuple(
        PilotProbeDetection(
            probe_status,
            probe.sample_start,
            probe.time_s,
            None,
            None,
            (),
            None,
            None,
            f"synthetic {probe_status.value}",
            0,
            0,
            (),
        )
        for probe in schedule.probes
    )
    monkeypatch.setattr(
        standard_analyzers, "scan_pilot_detections", lambda *_args, **_kwargs: detections
    )

    result = PathPilotScanAnalyzer().analyze(
        _path_context(binding, scope, "pilot-outcome"),
        _ReplayIq(),
        reader,
        MemoryOutputSink(),
    )

    assert result.outcome is expected_outcome


def test_retained_candidate_truncation_is_partial_at_stage_and_report_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = json.loads(_FROZEN.read_bytes())
    frozen_detections = standard_analyzers._pilot_detections(
        frozen["documents"][PILOT_SCAN_PRODUCT.kind]
    )
    assert frozen_detections and all(item.candidates for item in frozen_detections)
    assert all(item.truncated_candidate_count for item in frozen_detections)
    binding, schedule, scope, reader = _scheduled_path()
    detections = tuple(
        replace(
            frozen_detections[index % len(frozen_detections)],
            sample_start=probe.sample_start,
            time_s=probe.time_s,
        )
        for index, probe in enumerate(schedule.probes)
    )
    monkeypatch.setattr(
        standard_analyzers, "scan_pilot_detections", lambda *_args, **_kwargs: detections
    )

    result = PathPilotScanAnalyzer().analyze(
        _path_context(binding, scope, "pilot-truncated"),
        _ReplayIq(),
        reader,
        MemoryOutputSink(),
    )
    assert result.outcome is StageOutcome.PARTIAL_COVERAGE

    certificates = tuple(
        PilotProbeCertificateV2.model_validate(item)
        for item in frozen["products"]["pilot_certificates"]
    )
    status, _reason = standard_reports._path_status(
        binding.declared_sample_count,
        binding.declared_sample_count,
        certificates,
        (),
        schedule_truncated=False,
        candidate_truncated=True,
        trajectory_truncated=False,
    )
    assert status.value == "partial"


def test_reviewed_full_corpus_truncation_algebra_is_partial() -> None:
    reviewed = json.loads(Path("corpus/goldens/trial-132-standard-v2-summary.json").read_bytes())
    summaries = reviewed["expected_full_path_summaries"]
    assert len(summaries) == 4
    for summary in summaries:
        assert summary["trajectory_count"] > 0
        assert summary["source_candidate_count"] > summary["returned_candidate_count"]
        assert (
            standard_analyzers._derived_science_outcome(
                (StageOutcome.COMPLETE,),
                has_result=True,
                truncated=True,
            )
            is StageOutcome.PARTIAL_COVERAGE
        )
    assert (
        standard_analyzers._derived_science_outcome(
            (StageOutcome.COMPLETE,),
            has_result=False,
            truncated=True,
            observations=(NumericalStatus.NO_RESULT,),
        )
        is StageOutcome.PARTIAL_COVERAGE
    )


@pytest.mark.parametrize(
    ("certificate_status", "expected_status"),
    (
        ("no_result", StandardScientificStatus.NO_RESULT),
        ("insufficient_data", StandardScientificStatus.INSUFFICIENT_DATA),
    ),
)
def test_path_report_status_preserves_candidate_free_pilot_semantics(
    certificate_status: str,
    expected_status: StandardScientificStatus,
) -> None:
    frozen = json.loads(_FROZEN.read_bytes())
    certificates = []
    for item in frozen["products"]["pilot_certificates"]:
        changed = deepcopy(item)
        changed.update(
            status=certificate_status,
            source_candidate_count=0,
            returned_candidate_count=0,
            truncated_candidate_count=0,
            candidates=[],
            reason=f"synthetic {certificate_status}",
        )
        certificates.append(PilotProbeCertificateV2.model_validate(changed))
    status, _reason = standard_reports._path_status(
        2_500_000,
        2_500_000,
        tuple(certificates),
        (),
        schedule_truncated=False,
        candidate_truncated=False,
        trajectory_truncated=False,
    )
    assert status is expected_status


def test_product_only_bank_consumes_exact_bound_frozen_pilot() -> None:
    frozen = json.loads(_FROZEN.read_bytes())
    documents = dict(frozen["documents"])
    binding = _path_binding()
    schedule = build_probe_schedule(
        sample_rate_hz=2_500_000,
        sample_count=2_500_000,
        maximum_coarse_windows=1,
    )
    sources = {**documents, PROBE_SCHEDULE_PRODUCT.kind: schedule.model_dump(mode="json")}
    bindings = build_standard_source_bindings(binding, sources)
    final_sources = {
        item.product_kind: {"fixture_product_kind": item.product_kind}
        for item in STANDARD_FINAL_SOURCE_BINDING_SPECS
    }
    bindings.update(build_standard_final_source_bindings(binding, final_sources, bindings))
    scope = ScopeIdentityV1.receiver_path(
        session_id=_SESSION,
        stream_id="stream-0",
        receiver_id=0,
    )
    reader = MemoryProductReader(
        {
            (PILOT_SCAN_PRODUCT.kind, PILOT_SCAN_PRODUCT.schema_version): documents[
                PILOT_SCAN_PRODUCT.kind
            ]
        },
        memberships={
            (PILOT_SCAN_PRODUCT.kind, PILOT_SCAN_PRODUCT.schema_version): {
                "standard_source_bindings": bindings
            }
        },
        producer_scope=scope,
    )
    sink = MemoryOutputSink()
    result = PathTrajectoryBankAnalyzer().analyze(
        AnalysisContext(
            session_id=_SESSION,
            run_id="run-standard-test",
            pipeline_release="1" * 40,
            scope_key="stream-0.rx-0",
            scope=scope,
            job_node_id="path-00-stage-06",
        ),
        _NoIq(),
        reader,
        sink,
    )

    assert result.products[0].product == TRAJECTORY_BANK_PRODUCT
    assert (
        sink.documents[(TRAJECTORY_BANK_PRODUCT.kind, 2)] == documents[TRAJECTORY_BANK_PRODUCT.kind]
    )
    assert "standard_source_bindings" in result.summary
    assert result.outcome is StageOutcome.PARTIAL_COVERAGE

    foreign = ScopeIdentityV1.receiver_path(
        session_id=_SESSION,
        stream_id="stream-1",
        receiver_id=0,
    )
    reader.producer_scope = foreign
    with pytest.raises(ValueError, match="different receiver path"):
        PathTrajectoryBankAnalyzer().analyze(
            AnalysisContext(
                session_id=_SESSION,
                run_id="run-standard-test",
                pipeline_release="1" * 40,
                scope_key="stream-0.rx-0",
                scope=scope,
            ),
            _NoIq(),
            reader,
            MemoryOutputSink(),
        )


def test_alternate_tracks_consumes_only_exact_bound_pilot_and_publishes_two_products() -> None:
    frozen = json.loads(_FROZEN.read_bytes())
    documents = dict(frozen["documents"])
    binding = _path_binding()
    schedule = build_probe_schedule(
        sample_rate_hz=2_500_000, sample_count=2_500_000, maximum_coarse_windows=1
    )
    sources = {**documents, PROBE_SCHEDULE_PRODUCT.kind: schedule.model_dump(mode="json")}
    bindings = build_standard_source_bindings(binding, sources)
    final_sources = {
        item.product_kind: {"fixture_product_kind": item.product_kind}
        for item in STANDARD_FINAL_SOURCE_BINDING_SPECS
    }
    bindings.update(build_standard_final_source_bindings(binding, final_sources, bindings))
    scope = ScopeIdentityV1.receiver_path(session_id=_SESSION, stream_id="stream-0", receiver_id=0)
    reader = MemoryProductReader(
        {
            (PILOT_SCAN_PRODUCT.kind, PILOT_SCAN_PRODUCT.schema_version): documents[
                PILOT_SCAN_PRODUCT.kind
            ]
        },
        memberships={
            (PILOT_SCAN_PRODUCT.kind, PILOT_SCAN_PRODUCT.schema_version): {
                "standard_source_bindings": bindings
            }
        },
        producer_scope=scope,
    )
    context = AnalysisContext(
        session_id=_SESSION,
        run_id="run-alternate",
        pipeline_release="1" * 40,
        scope_key="stream-0.rx-0",
        scope=scope,
        stage_config=production_standard_v2_configuration()["path-alternate-tracks"],
    )
    first_sink = MemoryOutputSink()
    result = PathAlternateTracksAnalyzer().analyze(context, _NoIq(), reader, first_sink)
    second_sink = MemoryOutputSink()
    PathAlternateTracksAnalyzer().analyze(context, _NoIq(), reader, second_sink)

    assert tuple(item.product for item in result.products) == (
        ALTERNATE_CFO_TRACK_BANK_PRODUCT,
        ALTERNATE_CFO_TRACKS_PNG_PRODUCT,
    )
    assert first_sink.documents == second_sink.documents
    assert first_sink.payloads == second_sink.payloads
    bank = first_sink.documents[(ALTERNATE_CFO_TRACK_BANK_PRODUCT.kind, 1)]
    assert bank["pilot_scan_content_digest"] == canonical_digest(documents[PILOT_SCAN_PRODUCT.kind])
    assert first_sink.payloads[(ALTERNATE_CFO_TRACKS_PNG_PRODUCT.kind, 1)].startswith(
        b"\x89PNG\r\n\x1a\n"
    )


@pytest.mark.parametrize(
    ("upstream_outcome", "expected_outcome"),
    (
        (StageOutcome.INSUFFICIENT_DATA, StageOutcome.INSUFFICIENT_DATA),
        (StageOutcome.PARTIAL_COVERAGE, StageOutcome.PARTIAL_COVERAGE),
    ),
)
def test_incomplete_pilot_cannot_become_trajectory_miss(
    upstream_outcome: StageOutcome,
    expected_outcome: StageOutcome,
) -> None:
    frozen = json.loads(_FROZEN.read_bytes())
    documents = dict(frozen["documents"])
    pilot = deepcopy(documents[PILOT_SCAN_PRODUCT.kind])
    pilot["detections"] = []
    binding = _path_binding()
    schedule = build_probe_schedule(
        sample_rate_hz=2_500_000,
        sample_count=2_500_000,
        maximum_coarse_windows=1,
    )
    sources = {**documents, PILOT_SCAN_PRODUCT.kind: pilot}
    sources[PROBE_SCHEDULE_PRODUCT.kind] = schedule.model_dump(mode="json")
    bindings = build_standard_source_bindings(binding, sources)
    pilot_wrapper = next(
        item.wrapper_kind
        for item in STANDARD_SOURCE_BINDING_SPECS
        if item.product_kind == PILOT_SCAN_PRODUCT.kind
    )
    scope = ScopeIdentityV1.receiver_path(session_id=_SESSION, stream_id="stream-0", receiver_id=0)
    reader = MemoryProductReader(
        {(PILOT_SCAN_PRODUCT.kind, PILOT_SCAN_PRODUCT.schema_version): pilot},
        memberships={
            (PILOT_SCAN_PRODUCT.kind, PILOT_SCAN_PRODUCT.schema_version): {
                "standard_source_bindings": {pilot_wrapper: bindings[pilot_wrapper]}
            }
        },
        outcomes={(PILOT_SCAN_PRODUCT.kind, PILOT_SCAN_PRODUCT.schema_version): upstream_outcome},
        producer_scope=scope,
    )
    result = PathTrajectoryBankAnalyzer().analyze(
        AnalysisContext(
            session_id=_SESSION,
            run_id="run-insufficient",
            pipeline_release="1" * 40,
            scope_key="stream-0.rx-0",
            scope=scope,
        ),
        _NoIq(),
        reader,
        MemoryOutputSink(),
    )
    assert result.outcome is expected_outcome


class _ReplayIq:
    sample_rate_hz = 2_500_000
    center_frequency_hz = 1_709_687_500
    sample_count = 2_500_000
    receiver_ids = (0,)

    def iter_blocks(self, *, block_samples: int):
        del block_samples
        raise AssertionError("stubbed replay must not read IQ")


def test_feedback_consumes_durable_bank_without_refitting(monkeypatch) -> None:
    frozen = json.loads(_FROZEN.read_bytes())
    documents = dict(frozen["documents"])
    binding = _path_binding()
    schedule = build_probe_schedule(
        sample_rate_hz=2_500_000,
        sample_count=2_500_000,
        maximum_coarse_windows=1,
    )
    sources = {**documents, PROBE_SCHEDULE_PRODUCT.kind: schedule.model_dump(mode="json")}
    bindings = build_standard_source_bindings(binding, sources)
    memberships: dict[tuple[str, int], dict[str, JsonValue]] = {}
    for product in (PILOT_SCAN_PRODUCT, TRAJECTORY_BANK_PRODUCT):
        wrapper = next(
            item.wrapper_kind
            for item in STANDARD_SOURCE_BINDING_SPECS
            if item.product_kind == product.kind
        )
        memberships[(product.kind, product.schema_version)] = {
            "standard_source_bindings": {wrapper: bindings[wrapper]}
        }
    scope = ScopeIdentityV1.receiver_path(session_id=_SESSION, stream_id="stream-0", receiver_id=0)
    reader = MemoryProductReader(
        {
            (PILOT_SCAN_PRODUCT.kind, PILOT_SCAN_PRODUCT.schema_version): documents[
                PILOT_SCAN_PRODUCT.kind
            ],
            (TRAJECTORY_BANK_PRODUCT.kind, 2): documents[TRAJECTORY_BANK_PRODUCT.kind],
        },
        memberships=memberships,
        producer_scope=scope,
        subject_binding=binding.model_dump(mode="json"),
    )

    def forbidden_refit(*args, **kwargs):
        del args, kwargs
        raise AssertionError("feedback recomputed the trajectory bank")

    monkeypatch.setattr(standard_analyzers, "fit_pilot_trajectories", forbidden_refit)
    monkeypatch.setattr(standard_analyzers, "replay_pilot_trajectories", lambda *args, **kwargs: ())
    result = PathTrajectoryFeedbackAnalyzer().analyze(
        AnalysisContext(
            session_id=_SESSION,
            run_id="run-feedback",
            pipeline_release="1" * 40,
            scope_key="stream-0.rx-0",
            scope=scope,
            job_node_id="path-00-stage-07",
        ),
        _ReplayIq(),
        reader,
        MemoryOutputSink(),
    )
    assert result.outcome is StageOutcome.PARTIAL_COVERAGE


def _path_binding() -> StandardPathInputBindV3:
    digest = "sha256:" + "1" * 64
    values = {
        "schema_version": 3,
        "algorithm_version": "standard-path-input-bind-v3",
        "session_id": _SESSION,
        "stream_id": "stream-0",
        "radio_id": "radio-0",
        "receiver_id": 0,
        "manifest_digest": digest,
        "raw_integrity_attestation_digest": digest,
        "selected_stream_digest": digest,
        "compressed_chunk_closure_digest": digest,
        "uncompressed_chunk_closure_digest": digest,
        "synchronization_inventory_digest": digest,
        "profile_revision_digest": digest,
        "capture_plan_digest": digest,
        "receiver_settings_digest": digest,
        "science_configuration_digest": digest,
        "science_implementation_digest": digest,
        "capture_lineage_resolution": "legacy_unresolved",
        "physical_receiver_id": None,
        "hardware_epoch_id": None,
        "tuned_center_frequency_hz": 1_709_687_500,
        "sample_rate_hz": 2_500_000,
        "declared_sample_count": 2_500_000,
        "starlink_channel": 4,
        "starlink_edge": "lower",
        "starlink_tuning_evidence_source": "capture_profile",
        "timing": {
            "schema_version": 1,
            "first_estimate_utc_ns": 1,
            "first_earliest_utc_ns": 1,
            "first_latest_utc_ns": 1,
            "last_estimate_utc_ns": 1_000_000_001,
            "last_earliest_utc_ns": 1_000_000_001,
            "last_latest_utc_ns": 1_000_000_001,
        },
        "frequency_reference": {
            "schema_version": 1,
            "reference": "uncalibrated_prior",
            "center_frequency_hz": None,
            "uncertainty_hz": None,
            "calibration_digest": None,
        },
    }
    return StandardPathInputBindV3.model_validate(
        {**values, "binding_digest": canonical_digest(values)}
    )


def _scheduled_path() -> tuple[
    StandardPathInputBindV3,
    ProbeScheduleV2,
    ScopeIdentityV1,
    MemoryProductReader,
]:
    binding = _path_binding()
    schedule = build_probe_schedule(
        sample_rate_hz=binding.sample_rate_hz,
        sample_count=binding.declared_sample_count,
        maximum_coarse_windows=1,
    )
    document = schedule.model_dump(mode="json")
    spec = next(
        item
        for item in STANDARD_SOURCE_BINDING_SPECS
        if item.product_kind == PROBE_SCHEDULE_PRODUCT.kind
    )
    wrapper = build_standard_source_binding(spec, document, input_bind=binding)
    scope = ScopeIdentityV1.receiver_path(
        session_id=binding.session_id,
        stream_id=binding.stream_id,
        receiver_id=binding.receiver_id,
    )
    reader = MemoryProductReader(
        {(PROBE_SCHEDULE_PRODUCT.kind, PROBE_SCHEDULE_PRODUCT.schema_version): document},
        memberships={
            (PROBE_SCHEDULE_PRODUCT.kind, PROBE_SCHEDULE_PRODUCT.schema_version): cast(
                dict[str, JsonValue],
                {"standard_source_bindings": {spec.wrapper_kind: wrapper}},
            )
        },
        producer_scope=scope,
        subject_binding=binding.model_dump(mode="json"),
    )
    return binding, schedule, scope, reader


def _path_context(
    binding: StandardPathInputBindV3,
    scope: ScopeIdentityV1,
    run_id: str,
) -> AnalysisContext:
    return AnalysisContext(
        session_id=binding.session_id,
        run_id=run_id,
        pipeline_release="1" * 40,
        scope_key=f"{binding.stream_id}.rx-{binding.receiver_id}",
        scope=scope,
        job_node_id="path-00-stage-05",
    )
