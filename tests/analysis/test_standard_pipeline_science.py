from __future__ import annotations

from collections.abc import Iterator

import numpy as np
import pytest
from pydantic import ValidationError

from leo.analysis.standard import (
    PathReportInputs,
    ReceiverStandardConfig,
    build_probe_schedule,
    reduce_paired_radios,
    reduce_radio,
    run_receiver_standard,
)
from leo.analysis.standard.reports import reusable_trajectory_documents
from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.pilot_methods import PilotMethod, PilotMethodScore, PilotProbeDetection
from leo.analysis.starlink.trajectory_feedback import TrajectoryFeedbackConfig
from leo.analysis.waterfall import WaterfallConfig
from leo.contracts.digests import canonical_digest
from leo.contracts.radio import IqBlockMetadataV1, NanosecondIntervalV1
from leo.contracts.standard_pipeline import (
    AssociationStatus,
    FrequencyReference,
    PairTimingEvidenceV1,
    PathStandardReportV1,
    ReceiverFrequencyReferenceV1,
    StandardScientificStatus,
    StandardTrajectoryV1,
    StreamTimingEvidenceV1,
)
from leo.domain.iq import IqBlock

_SESSION = "production-24h-20260819-01-trial-00000132"
_MANIFEST = "sha256:1712bf9293b684540824ad4adfe0764a3477d01d7da8fdb28398ae465076855d"
_SYNC = canonical_digest({"fixture": "trial-132-sync"})


def test_probe_schedule_is_exact_bounded_and_digest_stable() -> None:
    first = build_probe_schedule(sample_rate_hz=2_500_000, sample_count=150_000_000)
    second = build_probe_schedule(sample_rate_hz=2_500_000, sample_count=150_000_000)

    assert first == second
    assert first.returned_probe_count == 1_200
    assert first.truncated_probe_count == 0
    assert first.probes[0].sample_start == 0
    assert first.probes[0].sample_count == 50_000
    assert first.probes[-1].sample_start == 149_875_000
    assert first.probes[-1].time_s == 59.95
    assert len({item.probe_id for item in first.probes}) == 1_200


def test_uncalibrated_prior_cannot_smuggle_frequency_authority() -> None:
    with pytest.raises(ValidationError, match="cannot carry calibration authority"):
        ReceiverFrequencyReferenceV1(
            reference=FrequencyReference.UNCALIBRATED_PRIOR,
            center_frequency_hz=1_709_687_500.0,
        )


def test_radio_and_pair_reducers_are_deterministic_product_only_and_noncoherent() -> None:
    stream0_start = 1_787_121_029_925_651_245
    stream1_start = 1_787_121_029_924_226_035
    stream0 = (
        _path("stream-0", "radio-0", 0, stream0_start, 253_000.0),
        _path("stream-0", "radio-0", 1, stream0_start, 253_300.0),
    )
    stream1 = (
        _path("stream-1", "radio-1", 0, stream1_start, 253_100.0),
        _path("stream-1", "radio-1", 1, stream1_start, 253_200.0),
    )

    radio0 = reduce_radio(tuple(reversed(stream0)), declared_receiver_ids=(0, 1))
    radio1 = reduce_radio(stream1, declared_receiver_ids=(0, 1))
    timing = PairTimingEvidenceV1(
        synchronization_inventory_digest=_SYNC,
        union_start_utc_ns=stream1_start,
        union_end_utc_ns=stream0_start + 60_000_000_000,
        estimated_overlap_start_utc_ns=stream0_start,
        estimated_overlap_end_utc_ns=stream1_start + 60_000_000_000,
        estimated_start_skew_ns=1_425_210,
        start_skew_uncertainty_ns=301_027_179,
        guaranteed_overlap_ns=0,
        synchronization_grade="degraded",
        phase_coherent=False,
    )
    paired = reduce_paired_radios((radio1, radio0), timing=timing)
    repeated = reduce_paired_radios((radio0, radio1), timing=timing)

    assert radio0.association_status is AssociationStatus.EVALUATED
    assert len(radio0.associations) == 1
    assert paired == repeated
    assert paired.timing.estimated_start_skew_ns == 1_425_210
    assert paired.timing.union_end_utc_ns - paired.timing.union_start_utc_ns == 60_001_425_210
    assert paired.phase_coherent is False
    assert paired.candidate_only is True
    assert paired.specificity_claimed is False
    assert paired.payload_decoded is False
    assert len(paired.radios) == 2
    assert len(tuple(path for radio in paired.radios for path in radio.paths)) == 4


def test_uncalibrated_prior_preserves_tracks_but_disables_association() -> None:
    start = 1_787_121_029_925_651_245
    paths = (
        _path("stream-0", "radio-0", 0, start, 253_000.0, calibrated=False),
        _path("stream-0", "radio-0", 1, start, 253_300.0, calibrated=False),
    )

    radio = reduce_radio(paths, declared_receiver_ids=(0, 1))

    assert radio.association_status is AssociationStatus.UNAVAILABLE_UNCALIBRATED_PRIOR
    assert radio.associations == ()
    assert len(radio.unmatched_trajectory_ids) == 2
    assert all(path.trajectories for path in radio.paths)


def test_reducers_reject_foreign_or_missing_children() -> None:
    start = 1_787_121_029_925_651_245
    one = _path("stream-0", "radio-0", 0, start, 253_000.0)
    foreign = _path("stream-1", "radio-1", 1, start, 253_000.0)

    with pytest.raises(ValueError, match="exactly match declared"):
        reduce_radio((one,), declared_receiver_ids=(0, 1))
    with pytest.raises(ValueError, match="stream_id"):
        reduce_radio((one, foreign), declared_receiver_ids=(0, 1))


def test_complete_receiver_runner_is_exact_repeatable_and_keeps_uncalibrated_prior(
    monkeypatch,
) -> None:
    def fake_detect(
        _samples,
        sample_rate_hz,
        *,
        sample_start,
        calibration,
        acquisition_config,
        maximum_scored_candidates=4,
    ) -> PilotProbeDetection:
        del calibration, acquisition_config, maximum_scored_candidates
        time_s = sample_start / sample_rate_hz
        negative = (sample_start // 50) % 10 == 0
        scores = tuple(
            PilotMethodScore(
                method,
                0.0 if negative else 0.9,
                0.1 if method is not PilotMethod.QAM_ACCURACY else None,
                -0.1 if negative else 0.8,
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
            "synthetic multi-method candidate",
        )

    monkeypatch.setattr(
        "leo.analysis.starlink.trajectory_feedback.detect_pilot_methods", fake_detect
    )
    monkeypatch.setattr(
        "leo.analysis.starlink.trajectory_feedback.detect_pilot_method_candidates",
        fake_detect,
    )
    schedule = build_probe_schedule(
        sample_rate_hz=1_000,
        sample_count=4_000,
        maximum_coarse_windows=4,
    )
    inputs = PathReportInputs(
        session_id="synthetic-session",
        stream_id="stream-0",
        radio_id="radio-0",
        receiver_id=1,
        manifest_digest=canonical_digest({"manifest": "synthetic"}),
        synchronization_inventory_digest=canonical_digest({"sync": "synthetic"}),
        sample_rate_hz=1_000,
        declared_sample_count=4_000,
        timing=_timing(10_000_000_000),
        frequency_reference=ReceiverFrequencyReferenceV1(
            reference=FrequencyReference.UNCALIBRATED_PRIOR
        ),
        schedule=schedule,
    )
    config = ReceiverStandardConfig(
        quality_block_samples=333,
        power_block_samples=271,
        waterfall=WaterfallConfig(
            fft_samples=20,
            frequency_bins=10,
            maximum_time_bins=8,
            block_samples=257,
        ),
        feedback=TrajectoryFeedbackConfig(
            maximum_outer_windows=4,
            maximum_replayed_families=16,
            maximum_workers=2,
        ),
    )

    first = run_receiver_standard(_DualReader(), inputs, config=config)
    second = run_receiver_standard(_DualReader(), inputs, config=config)

    assert first == second
    assert first.products.report.status is StandardScientificStatus.COMPLETE
    assert len(first.products.pilot_certificates) == 80
    assert {item.polynomial_degree for item in first.products.report.trajectories} == {1, 2, 3}
    assert len(first.documents["power.summary"]["timeline"]) == 4
    serialized = repr(first.documents) + first.products.report.model_dump_json()
    assert "standard-exploratory-zero-baseband-prior" not in serialized
    assert "calibration_sha256" not in serialized
    assert (
        first.products.report.frequency_reference.reference
        is FrequencyReference.UNCALIBRATED_PRIOR
    )
    assert first.products.report.frequency_reference.calibration_digest is None


def test_reusable_trajectory_bytes_do_not_depend_on_run_membership() -> None:
    base = {
        "schema_version": 1,
        "scope_key": "stream-0.rx-0",
        "candidate_only": True,
        "frequency_coordinate": "baseband_cfo_hz",
        "frequency_reference": "uncalibrated_prior",
    }
    documents_a = {
        "starlink.pilot-method-detections": {
            **base,
            "run_id": "run-a",
            "methods": [],
            "detections": [],
        },
        "starlink.polynomial-trajectories": {
            **base,
            "run_id": "run-a",
            "trajectories": [],
            "families": [],
        },
        "starlink.trajectory-redetection": {**base, "run_id": "run-a", "results": []},
        "starlink.glrt64-trajectory-table": {
            **base,
            "run_id": "run-a",
            "trajectories": [],
        },
    }
    documents_b = {
        kind: {**document, "run_id": "run-b", "scope_key": "another-membership-key"}
        for kind, document in documents_a.items()
    }

    stable_a = reusable_trajectory_documents(documents_a)
    stable_b = reusable_trajectory_documents(documents_b)

    assert stable_a == stable_b
    assert canonical_digest(stable_a) == canonical_digest(stable_b)
    assert "run-a" not in repr(stable_a) and "run-b" not in repr(stable_b)


def _path(
    stream_id: str,
    radio_id: str,
    receiver_id: int,
    start_utc_ns: int,
    cfo_hz: float,
    *,
    calibrated: bool = True,
) -> PathStandardReportV1:
    trajectory_values = {
        "schema_version": 1,
        "trajectory_id": canonical_digest(
            {"stream": stream_id, "receiver": receiver_id, "cfo": cfo_hz}
        ),
        "family_id": canonical_digest({"stream": stream_id, "family": receiver_id}),
        "method": "glrt64",
        "polynomial_degree": 2,
        "reference_time_s": 30.0,
        "coefficients_hz": [20.0, -2_000.0, cfo_hz],
        "start_s": 6.2,
        "end_s": 39.0,
        "point_count": 120,
        "residual_rms_hz": 400.0,
        "bic": 100.0,
        "em_iterations": 3,
        "fit_matches_well": True,
        "selected_for_correction": True,
        "corrected_glrt64_probe_count": 656,
        "median_glrt64_margin_delta": 0.12,
    }
    trajectory = StandardTrajectoryV1.model_validate(trajectory_values)
    timing = _timing(start_utc_ns)
    frequency = (
        ReceiverFrequencyReferenceV1(
            reference=FrequencyReference.CALIBRATED,
            center_frequency_hz=1_709_687_500.0,
            uncertainty_hz=100.0,
            calibration_digest=canonical_digest(
                {"stream": stream_id, "receiver": receiver_id, "calibration": "fixture"}
            ),
        )
        if calibrated
        else ReceiverFrequencyReferenceV1(reference=FrequencyReference.UNCALIBRATED_PRIOR)
    )
    values = {
        "schema_version": 1,
        "session_id": _SESSION,
        "stream_id": stream_id,
        "radio_id": radio_id,
        "receiver_id": receiver_id,
        "manifest_digest": _MANIFEST,
        "synchronization_inventory_digest": _SYNC,
        "pipeline_family": "standard-glrt64-v2",
        "status": StandardScientificStatus.COMPLETE,
        "reason": "synthetic complete candidate-only path",
        "sample_rate_hz": 2_500_000,
        "declared_sample_count": 150_000_000,
        "observed_sample_count": 150_000_000,
        "coverage_fraction": 1.0,
        "timing": timing.model_dump(mode="json"),
        "frequency_reference": frequency.model_dump(mode="json"),
        "probe_schedule_digest": canonical_digest({"schedule": "fixture"}),
        "method_names": ["glrt64"],
        "initial_glrt64": [],
        "trajectories": [trajectory.model_dump(mode="json")],
        "products": [],
        "truncated_candidate_count": 0,
        "truncated_trajectory_count": 0,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    return PathStandardReportV1(**values, report_digest=canonical_digest(values))


def _timing(start_utc_ns: int) -> StreamTimingEvidenceV1:
    return StreamTimingEvidenceV1(
        first_estimate_utc_ns=start_utc_ns,
        first_earliest_utc_ns=start_utc_ns - 100_000,
        first_latest_utc_ns=start_utc_ns + 100_000,
        last_estimate_utc_ns=start_utc_ns + 60_000_000_000,
        last_earliest_utc_ns=start_utc_ns + 59_999_900_000,
        last_latest_utc_ns=start_utc_ns + 60_000_100_000,
    )


class _DualReader:
    sample_rate_hz = 1_000
    center_frequency_hz = 1_000_000
    receiver_ids = (0, 1)
    sample_count = 4_000

    def iter_blocks(self, *, block_samples: int) -> Iterator[IqBlock]:
        interval = NanosecondIntervalV1(lower_ns=0, upper_ns=0)
        for start in range(0, self.sample_count, block_samples):
            count = min(block_samples, self.sample_count - start)
            samples = np.empty((count, 2, 2), dtype="<i2")
            samples[:, 0, 0] = 100
            samples[:, 0, 1] = -50
            samples[:, 1, 0] = 1_000
            samples[:, 1, 1] = -500
            yield IqBlock(
                samples=np.ascontiguousarray(samples),
                metadata=IqBlockMetadataV1(
                    radio_id="radio-0",
                    receiver_ids=(0, 1),
                    sample_count=count,
                    session_sample_start=start,
                    host_request_utc_ns=interval,
                    host_request_monotonic_ns=interval,
                ),
            )
