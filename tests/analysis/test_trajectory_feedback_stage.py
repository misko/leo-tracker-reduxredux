from __future__ import annotations

from collections.abc import Iterator

import numpy as np
import pytest
from pydantic import JsonValue

from leo.analysis.graphs import LONG_DWELL_STAGE_SPECS
from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.pilot_methods import PilotMethod, PilotMethodScore, PilotProbeDetection
from leo.analysis.starlink.trajectory_feedback import (
    TrajectoryFeedbackAnalyzer,
    TrajectoryFeedbackConfig,
)
from leo.contracts.digests import canonical_digest, canonical_json_bytes, sha256_digest
from leo.contracts.radio import IqBlockMetadataV1, NanosecondIntervalV1
from leo.domain.iq import IqBlock
from leo.pipeline import AnalysisContext, ProductRequirement, ProductSpec, PublishedProduct
from leo.pipeline.scopes import ScopeIdentityV1


class _Reader:
    sample_rate_hz = 1_000
    center_frequency_hz = 1_000_000
    receiver_ids = (0,)
    sample_count = 4_000

    def iter_blocks(self, *, block_samples: int) -> Iterator[IqBlock]:
        interval = NanosecondIntervalV1(lower_ns=0, upper_ns=0)
        for start in range(0, self.sample_count, block_samples):
            count = min(block_samples, self.sample_count - start)
            yield IqBlock(
                samples=np.zeros((count, 1, 2), dtype="<i2"),
                metadata=IqBlockMetadataV1(
                    radio_id="radio",
                    receiver_ids=(0,),
                    sample_count=count,
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
            "session_id": "session",
            "stream_id": "stream",
            "radio_id": "radio",
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
            "sample_rate_hz": 1_000,
            "declared_sample_count": 4_000,
            "starlink_channel": 4,
            "starlink_edge": "lower",
            "starlink_tuning_evidence_source": "capture_profile",
            "timing": {
                "schema_version": 1,
                "first_estimate_utc_ns": 0,
                "first_earliest_utc_ns": 0,
                "first_latest_utc_ns": 0,
                "last_estimate_utc_ns": 4_000_000_000,
                "last_earliest_utc_ns": 4_000_000_000,
                "last_latest_utc_ns": 4_000_000_000,
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

    def read_json(self, _requirement: ProductRequirement) -> dict[str, JsonValue] | None:
        return None


class _Sink:
    def __init__(self) -> None:
        self.documents: dict[str, dict[str, JsonValue]] = {}

    def publish_json(
        self, product: ProductSpec, document: dict[str, JsonValue]
    ) -> PublishedProduct:
        self.documents[product.kind] = document
        payload = canonical_json_bytes(document)
        return PublishedProduct(
            product=product,
            logical_uri=f"memory://{product.kind}",
            digest=sha256_digest(payload),
            byte_size=len(payload),
        )


def _context(*, stream_id: str = "stream") -> AnalysisContext:
    return AnalysisContext(
        session_id="session",
        run_id="run",
        pipeline_release="release",
        scope_key="stream",
        scope=ScopeIdentityV1.receiver_path(
            session_id="session", stream_id=stream_id, receiver_id=0
        ),
        stage_config={"starlink_edge": "lower"},
    )


def test_standard_feedback_stage_runs_every_method_degree_and_replay(monkeypatch) -> None:
    def fake_detect(
        _samples,
        sample_rate_hz,
        *,
        sample_start,
        calibration,
        acquisition_config,
        maximum_scored_candidates=4,
        edge,
    ) -> PilotProbeDetection:
        del calibration, acquisition_config, maximum_scored_candidates
        assert edge.value == "lower"
        time_s = sample_start / sample_rate_hz
        negative = (sample_start // 50) % 10 == 0
        scores = tuple(
            PilotMethodScore(
                method,
                0.0 if negative else 0.9,
                0.1 if method is not PilotMethod.QAM_ACCURACY else None,
                (-0.1 if negative else 0.8),
                0.0,
                250_000.0 - 2_000.0 * time_s + 20.0 * time_s**2,
            )
            for method in PilotMethod
        )
        return PilotProbeDetection(
            NumericalStatus.COMPLETE,
            sample_start,
            time_s,
            0,
            scores[0].tracking_cfo_hz,
            scores,
            0.9,
            0.1,
            "fixture",
        )

    monkeypatch.setattr(
        "leo.analysis.starlink.trajectory_feedback.detect_pilot_methods", fake_detect
    )
    spec = next(item for item in LONG_DWELL_STAGE_SPECS if item.key == "trajectory-feedback")
    analyzer = TrajectoryFeedbackAnalyzer(
        spec,
        TrajectoryFeedbackConfig(maximum_outer_windows=4, maximum_replayed_families=16),
    )
    sink = _Sink()

    result = analyzer.analyze(
        _context(),
        _Reader(),
        _Products(),
        sink,
    )

    trajectory_document = sink.documents["starlink.polynomial-trajectories"]
    assert result.outcome.value == "complete"
    trajectories = trajectory_document["trajectories"]
    assert isinstance(trajectories, list)
    assert {item["method"] for item in trajectories} == {item.value for item in PilotMethod}
    assert {item["polynomial_degree"] for item in trajectories} == {1, 2, 3}
    assert sink.documents["starlink.trajectory-redetection"]["results"]
    table = sink.documents["starlink.glrt64-trajectory-table"]["trajectories"]
    assert isinstance(table, list)
    assert {item["model"] for item in table} == {"linear", "quadratic", "cubic"}
    assert all("coefficients_hz" in item for item in table)
    pilot_document = sink.documents["starlink.pilot-method-detections"]
    assert "frequency_reference" not in pilot_document
    assert "maximum_scored_candidates_per_probe" not in pilot_document
    assert set(pilot_document["detections"][0]) == {
        "status",
        "sample_start",
        "time_s",
        "local_epoch_sample",
        "acquired_cfo_hz",
        "scores",
        "qam_accuracy",
        "qam_evm",
        "reason",
    }


def test_feedback_rejects_subject_binding_for_different_scope_before_science() -> None:
    spec = next(item for item in LONG_DWELL_STAGE_SPECS if item.key == "trajectory-feedback")
    analyzer = TrajectoryFeedbackAnalyzer(spec)

    with pytest.raises(ValueError, match="exact analyzer scope"):
        analyzer.analyze(_context(stream_id="other-stream"), _Reader(), _Products(), _Sink())


def test_feedback_rejects_iq_geometry_for_different_subject_before_science() -> None:
    class WrongCenterReader(_Reader):
        center_frequency_hz = 2_000_000

    spec = next(item for item in LONG_DWELL_STAGE_SPECS if item.key == "trajectory-feedback")
    analyzer = TrajectoryFeedbackAnalyzer(spec)

    with pytest.raises(ValueError, match="exact path input binding"):
        analyzer.analyze(_context(), WrongCenterReader(), _Products(), _Sink())
