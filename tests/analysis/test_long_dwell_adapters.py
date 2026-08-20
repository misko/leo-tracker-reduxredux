from __future__ import annotations

from collections.abc import Iterator

import numpy as np
from pydantic import JsonValue

from leo.analysis.adapters import (
    LongDwellCoordinator,
    production_long_dwell_configuration,
    production_long_dwell_registry,
)
from leo.analysis.graphs import ComputeTier, long_dwell_stage_specs
from leo.contracts.digests import canonical_digest, canonical_json_bytes, sha256_digest
from leo.contracts.radio import IqBlockMetadataV1, NanosecondIntervalV1
from leo.contracts.states import StarlinkEdge
from leo.domain.iq import IqBlock
from leo.pipeline import (
    AnalysisContext,
    ProductRequirement,
    ProductSpec,
    PublishedProduct,
)


class _Reader:
    sample_rate_hz = 2_500_000
    center_frequency_hz = 1_709_687_500

    def __init__(self) -> None:
        self.samples = np.zeros((2048, 1, 2), dtype="<i2")

    @property
    def sample_count(self) -> int:
        return len(self.samples)

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        return (0,)

    def iter_blocks(self, *, block_samples: int) -> Iterator[IqBlock]:
        interval = NanosecondIntervalV1(lower_ns=0, upper_ns=0)
        for start in range(0, len(self.samples), block_samples):
            values = self.samples[start : start + block_samples]
            yield IqBlock(
                samples=values,
                metadata=IqBlockMetadataV1(
                    radio_id="fixture-radio",
                    receiver_ids=(0,),
                    sample_count=len(values),
                    session_sample_start=start,
                    host_request_utc_ns=interval,
                    host_request_monotonic_ns=interval,
                ),
            )


class _Products:
    def read_subject_binding(self) -> dict[str, JsonValue]:
        digest = "sha256:" + "1" * 64
        values: dict[str, JsonValue] = {
            "schema_version": 3,
            "algorithm_version": "standard-path-input-bind-v3",
            "session_id": "session-1",
            "stream_id": "stream-1",
            "radio_id": "fixture-radio",
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
            "tuned_center_frequency_hz": 1_000_000,
            "sample_rate_hz": 10_000,
            "declared_sample_count": 20_000,
            "starlink_channel": 4,
            "starlink_edge": "lower",
            "starlink_tuning_evidence_source": "capture_profile",
            "timing": {
                "schema_version": 1,
                "first_estimate_utc_ns": 0,
                "first_earliest_utc_ns": 0,
                "first_latest_utc_ns": 0,
                "last_estimate_utc_ns": 2_000_000_000,
                "last_earliest_utc_ns": 2_000_000_000,
                "last_latest_utc_ns": 2_000_000_000,
            },
            "frequency_reference": {
                "schema_version": 1,
                "reference": "uncalibrated_prior",
                "center_frequency_hz": None,
                "uncertainty_hz": None,
                "calibration_digest": None,
            },
        }
        return {**values, "binding_digest": canonical_digest(values)}

    def read_json(self, requirement: ProductRequirement) -> dict[str, JsonValue] | None:
        if requirement.kind == "starlink.pilot-method-detections":
            return {"detections": []}
        if requirement.kind == "starlink.polynomial-trajectories":
            return {"trajectories": []}
        if requirement.kind == "starlink.trajectory-redetection":
            return {"results": []}
        if requirement.kind == "starlink.glrt64-trajectory-table":
            return {"trajectories": []}
        return None


class _Sink:
    def __init__(self) -> None:
        self.documents: dict[str, dict[str, JsonValue]] = {}
        self.payloads: dict[str, bytes] = {}

    def publish_json(
        self,
        product: ProductSpec,
        document: dict[str, JsonValue],
    ) -> PublishedProduct:
        payload = canonical_json_bytes(document)
        self.documents[product.kind] = document
        return PublishedProduct(
            product=product,
            logical_uri=f"memory://{product.kind}.json",
            digest=sha256_digest(payload),
            byte_size=len(payload),
        )

    def publish_bytes(self, product: ProductSpec, payload: bytes) -> PublishedProduct:
        self.payloads[product.kind] = payload
        return PublishedProduct(
            product=product,
            logical_uri=f"memory://{product.kind}.png",
            digest=sha256_digest(payload),
            byte_size=len(payload),
        )


def test_production_registry_executes_every_standard_stage_and_publishes_ui_products() -> None:
    tier = ComputeTier.STANDARD
    registry = production_long_dwell_registry(tier)
    configuration = production_long_dwell_configuration(tier)
    reader = _Reader()
    published: set[str] = set()

    assert registry.keys == tuple(sorted(item.key for item in long_dwell_stage_specs(tier)))
    for analyzer in registry.plan():
        sink = _Sink()
        result = analyzer.analyze(
            AnalysisContext(
                session_id="session-1",
                run_id="run-1",
                pipeline_release="standard-v1",
                scope_key="stream-1",
                stage_config=configuration[analyzer.spec.key],
            ),
            reader,
            _Products(),
            sink,
        )
        assert result.products
        assert set(sink.documents) | set(sink.payloads) == {
            item.kind for item in analyzer.spec.output_products
        }
        published.update(sink.documents)
        published.update(sink.payloads)

    assert {
        "waterfall.presentation",
        "detection.presentation",
        "qam.presentation",
        "doppler.presentation",
        "controls.presentation",
        "overlays.presentation",
        "provenance.presentation",
        "carrier-timing.presentation",
        "qam-timeline.presentation",
        "analysis-stage-timeline.presentation",
        "starlink.glrt64-trajectory-plot",
    } <= published

    assert sink.documents["analysis-stage-timeline.presentation"] == {
        "schema_version": 1,
        "run_id": "run-1",
        "state": "unavailable",
        "stages": [],
        "reason": "the whole-dwell bundle does not contain persisted per-stage signal-time events",
    }


def test_standard_release_configuration_is_complete_and_confidence_free() -> None:
    configuration = production_long_dwell_configuration(ComputeTier.STANDARD)

    assert set(configuration) == {item.key for item in long_dwell_stage_specs(ComputeTier.STANDARD)}
    assert all("confidence" not in values for values in configuration.values())


def test_coordinator_lru_bounds_failed_or_abandoned_run_scope_state() -> None:
    coordinator = LongDwellCoordinator(ComputeTier.STANDARD, maximum_cached_scopes=2)
    reader = _Reader()

    for index in range(7):
        coordinator.compute(
            AnalysisContext(
                session_id=f"session-{index}",
                run_id=f"run-{index}",
                pipeline_release="standard-v1",
                scope_key="stream-1",
            ),
            reader,
            edge=StarlinkEdge.LOWER,
        )
        assert coordinator.cached_scope_count <= 2

    assert coordinator.cached_scope_count == 2
