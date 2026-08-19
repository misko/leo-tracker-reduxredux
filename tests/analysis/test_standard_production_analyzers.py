from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from leo.analysis.adapters import (
    production_standard_v2_configuration,
    production_standard_v2_registry,
)
from leo.analysis.standard import (
    TRAJECTORY_BANK_PRODUCT,
    build_probe_schedule,
    build_standard_source_bindings,
    decode_standard_product,
)
from leo.analysis.standard import analyzers as standard_analyzers
from leo.analysis.standard.analyzers import (
    PathTrajectoryBankAnalyzer,
    PathTrajectoryFeedbackAnalyzer,
)
from leo.analysis.standard.products import (
    GLRT64_TRAJECTORY_TABLE_PRODUCT,
    NUMERICAL_WATERFALL_PRODUCT,
    PATH_REPORT_PRODUCT,
    PILOT_SCAN_PRODUCT,
    POWER_TIMELINE_PRODUCT,
    PROBE_SCHEDULE_PRODUCT,
    QUALITY_PRODUCT,
    TRAJECTORY_FEEDBACK_PRODUCT,
)
from leo.analysis.standard.source_bindings import STANDARD_SOURCE_BINDING_SPECS
from leo.artifacts import MemoryOutputSink, MemoryProductReader
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_pipeline import StandardPathInputBindV2
from leo.pipeline import AnalysisContext, ScopeIdentityV1, StageOutcome

_FROZEN = Path("corpus/goldens/trial-132-standard-v2-one-second-frozen.json")
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
    assert set(production_standard_v2_configuration()) == set(registry.keys)
    planned = tuple(item.key for item in registry.graph().plan())

    assert set(registry.keys) == {
        "path-input-bind",
        "path-quality",
        "path-power",
        "path-waterfall",
        "path-probe-schedule",
        "path-pilot-scan",
        "path-trajectory-bank",
        "path-trajectory-feedback",
        "path-scientific-report",
        "path-presentation",
        "radio-scientific-report",
        "paired-scientific-report",
    }
    assert len(planned) == 12
    path_products = sum(
        len(registry.get(key).spec.output_products)
        for key in registry.keys
        if key.startswith("path-")
    )
    aggregate_products = sum(
        len(registry.get(key).spec.output_products)
        for key in ("radio-scientific-report", "paired-scientific-report")
    )
    assert path_products == 11
    assert 4 * path_products + 2 * (aggregate_products - 1) + 1 == 47


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
        (PATH_REPORT_PRODUCT, frozen["products"]["report"]),
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
    pilot_wrapper = next(
        item.wrapper_kind
        for item in STANDARD_SOURCE_BINDING_SPECS
        if item.product_kind == PILOT_SCAN_PRODUCT.kind
    )
    scope = ScopeIdentityV1.receiver_path(
        session_id=_SESSION,
        stream_id="stream-0",
        receiver_id=0,
    )
    reader = MemoryProductReader(
        {(PILOT_SCAN_PRODUCT.kind, 2): documents[PILOT_SCAN_PRODUCT.kind]},
        memberships={
            (PILOT_SCAN_PRODUCT.kind, 2): {
                "standard_source_bindings": {pilot_wrapper: bindings[pilot_wrapper]}
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
        {(PILOT_SCAN_PRODUCT.kind, 2): pilot},
        memberships={
            (PILOT_SCAN_PRODUCT.kind, 2): {
                "standard_source_bindings": {pilot_wrapper: bindings[pilot_wrapper]}
            }
        },
        outcomes={(PILOT_SCAN_PRODUCT.kind, 2): upstream_outcome},
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
    memberships = {}
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
            (PILOT_SCAN_PRODUCT.kind, 2): documents[PILOT_SCAN_PRODUCT.kind],
            (TRAJECTORY_BANK_PRODUCT.kind, 2): documents[TRAJECTORY_BANK_PRODUCT.kind],
        },
        memberships=memberships,
        producer_scope=scope,
    )

    def forbidden_refit(*args, **kwargs):
        del args, kwargs
        raise AssertionError("feedback recomputed the trajectory bank")

    monkeypatch.setattr(standard_analyzers, "fit_pilot_trajectories", forbidden_refit)
    monkeypatch.setattr(standard_analyzers, "replay_pilot_trajectories", lambda *args: ())
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


def _path_binding() -> StandardPathInputBindV2:
    digest = "sha256:" + "1" * 64
    values = {
        "schema_version": 2,
        "algorithm_version": "standard-path-input-bind-v2",
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
    return StandardPathInputBindV2.model_validate(
        {**values, "binding_digest": canonical_digest(values)}
    )
