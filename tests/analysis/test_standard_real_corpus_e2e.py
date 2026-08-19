from __future__ import annotations

import hashlib
import json
import math
import os
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from leo.analysis.standard import (
    PathReportInputs,
    ReceiverStandardConfig,
    build_probe_schedule,
    receiver_standard_configuration_digest,
    receiver_standard_implementation_digest,
    reduce_paired_radios,
    reduce_radio,
    run_receiver_standard,
)
from leo.analysis.starlink.corpus import preflight_corpus
from leo.analysis.starlink.trajectory_feedback import TrajectoryFeedbackConfig
from leo.analysis.waterfall import WaterfallConfig
from leo.contracts.digests import canonical_digest, canonical_json_bytes
from leo.contracts.standard_pipeline import (
    FrequencyReference,
    PairTimingEvidenceV1,
    ReceiverFrequencyReferenceV1,
    StandardPairInputBindV2,
    StandardPathInputBindV2,
    StreamTimingEvidenceV1,
)
from leo.domain.iq import IqBlock
from leo.pipeline import synchronization_inventory_document
from leo.storage import RecordingStore

_CORPUS_MANIFEST = Path("corpus/manifest.json").resolve()
_GOLDEN = Path("corpus/goldens/trial-132-standard-v2-summary.json").resolve()
_FULL_REVIEW_RECEIPT = Path(
    "corpus/goldens/trial-132-standard-v2-full-review-receipt.json"
).resolve()
_FULL_GOLDEN_SHA256 = "0b13a4c0b09cda17fc971e66396b5673c6b89eb8cef9fcef3ddcf8bc87309daa"
_FULL_REVIEW_RECEIPT_SHA256 = "c7e354b9edd4989673cdc860d9ea61610f4d96bccdb6163e35ac5977150d1105"
_ONE_SECOND_FROZEN = Path("corpus/goldens/trial-132-standard-v2-one-second-frozen.json").resolve()
_ONE_SECOND_FROZEN_SHA256 = "e26bc5b5fc8c5573713e9e8f730361f1081e9720baecdbfe24c9af68feaf47b9"
_CORPUS_ROOT = Path(os.environ.get("LEO_REAL_CORPUS_ROOT", "/srv/bulk/leo/test-corpus"))
_FIXTURE_ID = "trial-132-four-path-v1"
_SESSION_ID = "production-24h-20260819-01-trial-00000132"


def test_pair_timing_is_derived_from_exact_child_report_bounds() -> None:
    left = StreamTimingEvidenceV1(
        first_estimate_utc_ns=1_000,
        first_earliest_utc_ns=900,
        first_latest_utc_ns=1_100,
        last_estimate_utc_ns=11_000,
        last_earliest_utc_ns=10_900,
        last_latest_utc_ns=11_100,
    )
    right = StreamTimingEvidenceV1(
        first_estimate_utc_ns=1_250,
        first_earliest_utc_ns=1_100,
        first_latest_utc_ns=1_400,
        last_estimate_utc_ns=10_750,
        last_earliest_utc_ns=10_600,
        last_latest_utc_ns=10_900,
    )
    timing = _exact_pair_timing(
        "sha256:" + "a" * 64,
        (left, right),
        start_skew_uncertainty_ns=75,
        guaranteed_overlap_ns=9_000,
        synchronization_grade="degraded",
    )
    assert (
        timing.union_start_utc_ns,
        timing.union_end_utc_ns,
        timing.estimated_overlap_start_utc_ns,
        timing.estimated_overlap_end_utc_ns,
        timing.estimated_start_skew_ns,
    ) == (1_000, 11_000, 1_250, 10_750, 250)


def test_artifact_reload_compares_normalized_documents(tmp_path: Path) -> None:
    first_root = tmp_path / "run-a"
    second_root = tmp_path / "run-b"
    first_root.mkdir()
    second_root.mkdir()
    document = {
        "values": (1, 2),
        "reference": FrequencyReference.UNCALIBRATED_PRIOR,
    }
    payload = canonical_json_bytes(document)
    (first_root / "scientific-output.json").write_bytes(payload)
    (second_root / "scientific-output.json").write_bytes(payload)

    first, second = _reload_identical_artifacts(first_root, second_root, document, document.copy())

    assert (
        first
        == second
        == {
            "reference": "uncalibrated_prior",
            "values": [1, 2],
        }
    )


def test_full_path_golden_contains_four_explicit_reviewed_summaries() -> None:
    golden_bytes = _GOLDEN.read_bytes()
    receipt_bytes = _FULL_REVIEW_RECEIPT.read_bytes()
    assert hashlib.sha256(golden_bytes).hexdigest() == _FULL_GOLDEN_SHA256
    assert hashlib.sha256(receipt_bytes).hexdigest() == _FULL_REVIEW_RECEIPT_SHA256
    golden = json.loads(golden_bytes)
    receipt = json.loads(receipt_bytes)
    assert receipt["golden_summary_sha256"] == _FULL_GOLDEN_SHA256
    assert receipt["review_status"] == "reviewed_corrected_full_run"
    assert receipt["review_inputs"] == {
        "run_a": (
            "/srv/bulk/leo/test-output/standard-v2-corrected-review-c/"
            "test_trial132_full_four_path_t0/run-a/scientific-output.json"
        ),
        "run_b": (
            "/srv/bulk/leo/test-output/standard-v2-corrected-review-c/"
            "test_trial132_full_four_path_t0/run-b/scientific-output.json"
        ),
        "bytes_each": 93_713_940,
        "sha256_each": "cae4c4e44f72749211ccd65a3f0af776adfb82031eb0250cdedaf15fb93a9886",
        "byte_identical": True,
        "elapsed_seconds": 692,
    }
    verification = receipt["post_freeze_verification"]
    assert verification["result"] == "1 passed"
    assert verification["elapsed_seconds"] == 687.16
    assert verification["run_a_bytes"] == verification["run_b_bytes"] == 93_713_940
    assert (
        verification["run_a_sha256"]
        == verification["run_b_sha256"]
        == receipt["review_inputs"]["sha256_each"]
    )
    summaries = golden["expected_full_path_summaries"]
    assert [(item["stream_id"], item["receiver_id"]) for item in summaries] == [
        ("stream-0", 0),
        ("stream-0", 1),
        ("stream-1", 0),
        ("stream-1", 1),
    ]
    assert [item["trajectory_count"] for item in summaries] == [6, 6, 9, 6]
    required_detail = {
        "family_count",
        "source_candidate_count",
        "returned_candidate_count",
        "truncated_candidate_count",
        "control_score_count",
        "positive_control_margin_count",
        "representative_count",
        "replay_result_count",
        "trajectory_models",
    }
    for item in summaries:
        assert item["probe_count"] == 1_200
        assert required_detail < set(item)
        assert item["review_status"] == "reviewed_corrected_full_run"
        assert all(item[field] is not None for field in required_detail)
        assert len(item["trajectory_models"]) == item["trajectory_count"]
    assert receipt["path_inventory"] == golden["path_inventory"]
    assert receipt["path_scalar_facts"] == [
        {
            "path": f"{item['stream_id']}/RX{item['receiver_id']}",
            "probes": item["probe_count"],
            "trajectories": item["trajectory_count"],
            "families": item["family_count"],
            "source_candidates": item["source_candidate_count"],
            "returned_candidates": item["returned_candidate_count"],
            "truncated_candidates": item["truncated_candidate_count"],
            "controls": item["control_score_count"],
            "positive_control_margins": item["positive_control_margin_count"],
            "representatives": item["representative_count"],
            "replay_rows": item["replay_result_count"],
        }
        for item in summaries
    ]
    assert receipt["verified_invariants"] == {
        "all_numbers_finite": True,
        "polynomial_degrees_per_path": [1, 2, 3],
        "trajectory_ids_unique": True,
        "selected_trajectories_equal_replayed_representatives": True,
        "glrt64_feedback_recomputed_exactly": True,
        "candidate_only": golden["candidate_only"],
        "specificity_claimed": golden["specificity_claimed"],
        "payload_decoded": golden["payload_decoded"],
        "phase_coherent": golden["phase_coherent"],
    }


def test_path_summary_reads_raw_v2_pilot_score_inventory() -> None:
    frozen = json.loads(_ONE_SECOND_FROZEN.read_bytes())

    summary = _path_summary(
        {
            "stream_id": "stream-0",
            "receiver_id": 0,
            "documents": frozen["documents"],
            "report": frozen["products"]["report"],
            "pilot_certificates": frozen["products"]["pilot_certificates"],
        }
    )

    assert summary["probe_count"] == 20
    assert summary["returned_candidate_count"] > 0
    assert summary["control_score_count"] > 0


@pytest.mark.real_corpus
def test_trial132_one_path_one_coarse_window_benchmark_smoke() -> None:
    """Measured real-IQ component smoke; deliberately not a full-dwell claim."""

    store, bundle, raw_attestation_digest = _open_verified_fixture()
    try:
        stream = bundle.manifest.streams[0]
        source = _PrefixReader(store.reader(bundle, stream.stream_id), 2_500_000)
        timing = _prefix_timing(stream, 1.0)
        config = ReceiverStandardConfig(
            waterfall=WaterfallConfig(
                fft_samples=1_024,
                frequency_bins=128,
                maximum_time_bins=20,
                block_samples=262_144,
            ),
            feedback=TrajectoryFeedbackConfig(
                maximum_outer_windows=1,
                maximum_replayed_families=16,
                maximum_scored_candidates_per_probe=4,
                maximum_workers=2,
            ),
        )
        inputs = _path_inputs(
            bundle,
            stream,
            0,
            timing,
            source.sample_count,
            config,
            raw_attestation_digest=raw_attestation_digest,
        )
        planner_sync_digest = canonical_digest(synchronization_inventory_document(bundle.manifest))
        legacy_sync_digest = canonical_digest(
            bundle.manifest.synchronization.model_dump(mode="json")
        )
        assert inputs.synchronization_inventory_digest == planner_sync_digest
        assert inputs.synchronization_inventory_digest != legacy_sync_digest

        started = time.perf_counter()
        result = run_receiver_standard(source, inputs, config=config)
        elapsed = time.perf_counter() - started

        assert len(result.products.pilot_certificates) == 20
        assert result.documents["quality.summary"]["observed_sample_count"] == 2_500_000
        assert len(result.documents["standard.power-timeline"]["timeline"]) == 1
        assert result.documents["standard.numerical-waterfall"]["schema_version"] == 2
        assert result.documents["standard.pilot-scan"]["schema_version"] == 2
        frozen_bytes = _ONE_SECOND_FROZEN.read_bytes()
        assert hashlib.sha256(frozen_bytes).hexdigest() == _ONE_SECOND_FROZEN_SHA256
        current = json.loads(
            canonical_json_bytes(
                {
                    "products": {
                        "report": result.products.report.model_dump(mode="json"),
                        "pilot_certificates": [
                            item.model_dump(mode="json")
                            for item in result.products.pilot_certificates
                        ],
                    },
                    "documents": result.documents,
                }
            )
        )
        tolerances = json.loads(_GOLDEN.read_bytes())["floating_tolerances"]
        _assert_frozen_equivalent(
            json.loads(frozen_bytes),
            current,
            absolute=float(tolerances["absolute"]),
            relative=float(tolerances["relative"]),
        )
        assert elapsed > 0
        print(
            json.dumps(
                {
                    "fixture_id": _FIXTURE_ID,
                    "path": f"{stream.stream_id}/RX0",
                    "coarse_windows": 1,
                    "probes": 20,
                    "maximum_scored_candidates_per_probe": 4,
                    "wall_seconds": elapsed,
                    "naive_full_twice_extrapolation_seconds": elapsed * 60 * 4 * 2,
                    "note": "extrapolation is diagnostic, not a runtime promise",
                },
                sort_keys=True,
            )
        )
    finally:
        store.close()


@pytest.mark.real_corpus
def test_trial132_full_four_path_twice_is_numerically_identical(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """Full raw-IQ gate; run explicitly with ``pytest -m real_corpus``.

    The expensive twice-run gate is intentionally excluded from an unfiltered
    developer suite until component optimization makes it practical. When the
    real-corpus lane is explicitly selected, a missing or corrupt fixture is a
    hard failure rather than a skip.
    """

    if "real_corpus" not in request.config.option.markexpr:
        pytest.skip("full twice-run gate requires explicit `pytest -m real_corpus`")
    golden = json.loads(_GOLDEN.read_bytes())
    tolerances = golden["floating_tolerances"]
    first_root = tmp_path / "run-a"
    second_root = tmp_path / "run-b"

    with ProcessPoolExecutor(max_workers=2) as executor:
        first, second = tuple(executor.map(_run_full_chain, (first_root, second_root)))

    first, second = _reload_identical_artifacts(first_root, second_root, first, second)

    _assert_numerically_equal(
        first,
        second,
        absolute=float(tolerances["absolute"]),
        relative=float(tolerances["relative"]),
    )
    assert canonical_digest(first) == canonical_digest(second)
    assert first["paired_report"]["report_digest"] == second["paired_report"]["report_digest"]
    assert first["paired_report"]["phase_coherent"] is False
    assert first["paired_report"]["specificity_claimed"] is False
    assert first["paired_report"]["payload_decoded"] is False
    assert first["path_inventory"] == golden["path_inventory"]
    assert all(
        item["probe_count"] == golden["scheduled_probe_count_per_path"]
        for item in first["path_summaries"]
    )
    assert {
        degree for item in first["path_summaries"] for degree in item["polynomial_degrees"]
    } == set(golden["required_polynomial_degrees"])
    _assert_reviewed_path_summaries(
        golden["expected_full_path_summaries"],
        first["path_summaries"],
        tolerances,
    )


def _run_full_chain(output_root: Path) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=False)
    store, bundle, raw_attestation_digest = _open_verified_fixture()
    try:
        config = ReceiverStandardConfig(feedback=TrajectoryFeedbackConfig(maximum_workers=1))
        synchronization = bundle.manifest.synchronization
        assert synchronization.phase_coherent is False
        sync_digest = canonical_digest(synchronization_inventory_document(bundle.manifest))
        jobs = []
        for stream in sorted(bundle.manifest.streams, key=lambda item: item.stream_id):
            settings = stream.applied_settings or stream.requested_settings
            assert stream.timing is not None
            timing = _stream_timing(stream)
            for receiver_id in settings.receiver_ids:
                jobs.append((stream, receiver_id, timing))

        def analyze_path(job):
            stream, receiver_id, timing = job
            source = store.reader(bundle, stream.stream_id)
            inputs = _path_inputs(
                bundle,
                stream,
                receiver_id,
                timing,
                stream.captured_sample_count,
                config,
                raw_attestation_digest=raw_attestation_digest,
                synchronization_inventory_digest=sync_digest,
            )
            result = run_receiver_standard(source, inputs, config=config)
            return result.products.report, {
                "stream_id": stream.stream_id,
                "receiver_id": receiver_id,
                "report": result.products.report.model_dump(mode="json"),
                "pilot_certificates": [
                    item.model_dump(mode="json") for item in result.products.pilot_certificates
                ],
                "documents": result.documents,
            }

        with ThreadPoolExecutor(max_workers=4) as executor:
            analyzed = tuple(executor.map(analyze_path, jobs))
        reports = [report for report, _ in analyzed]
        path_results = [document for _, document in analyzed]
        radio_reports = tuple(
            reduce_radio(
                tuple(item for item in reports if item.stream_id == stream.stream_id),
                declared_receiver_ids=tuple(
                    (stream.applied_settings or stream.requested_settings).receiver_ids
                ),
            )
            for stream in sorted(bundle.manifest.streams, key=lambda item: item.stream_id)
        )
        child_timings = tuple(item.paths[0].timing for item in radio_reports)
        pair_timing = _exact_pair_timing(
            sync_digest,
            child_timings,
            start_skew_uncertainty_ns=synchronization.start_skew_uncertainty_ns,
            guaranteed_overlap_ns=synchronization.guaranteed_overlap_ns,
            synchronization_grade=synchronization.grade.value,
        )
        pair_values = {
            "schema_version": 2,
            "algorithm_version": "standard-pair-input-bind-v2",
            "session_id": bundle.session_id,
            "manifest_digest": bundle.manifest_sha256,
            "synchronization_inventory_digest": sync_digest,
            "raw_integrity_attestation_digests": [raw_attestation_digest],
            "timing": pair_timing.model_dump(mode="json"),
        }
        pair_binding = StandardPairInputBindV2(
            **pair_values,
            binding_digest=canonical_digest(pair_values),
        )
        paired = reduce_paired_radios(radio_reports, binding=pair_binding)
        result_document = {
            "fixture_id": _FIXTURE_ID,
            "manifest_digest": bundle.manifest_sha256,
            "path_inventory": [[item["stream_id"], item["receiver_id"]] for item in path_results],
            "path_summaries": [_path_summary(item) for item in path_results],
            "paths": path_results,
            "radio_reports": [item.model_dump(mode="json") for item in radio_reports],
            "paired_report": paired.model_dump(mode="json"),
        }
        with (output_root / "scientific-output.json").open("xb") as artifact:
            artifact.write(canonical_json_bytes(result_document))
        return result_document
    finally:
        store.close()


def _path_summary(item: dict[str, Any]) -> dict[str, Any]:
    documents = item["documents"]
    pilot = documents["standard.pilot-scan"]
    bank = documents["standard.trajectory-bank"]
    feedback = documents["standard.trajectory-feedback"]
    trajectories = item["report"]["trajectories"]
    candidates = [
        candidate for detection in pilot["detections"] for candidate in detection["candidates"]
    ]
    method_scores = [score for candidate in candidates for score in candidate["scores"]]
    return {
        "stream_id": item["stream_id"],
        "receiver_id": item["receiver_id"],
        "probe_count": len(item["pilot_certificates"]),
        "trajectory_count": len(trajectories),
        "polynomial_degrees": sorted({value["polynomial_degree"] for value in trajectories}),
        "family_count": len(bank["families"]),
        "source_candidate_count": sum(
            detection["source_candidate_count"] for detection in pilot["detections"]
        ),
        "returned_candidate_count": len(candidates),
        "truncated_candidate_count": sum(
            detection["truncated_candidate_count"] for detection in pilot["detections"]
        ),
        "control_score_count": sum(score["control_score"] is not None for score in method_scores),
        "positive_control_margin_count": sum(
            score["control_score"] is not None and score["margin"] > 0 for score in method_scores
        ),
        "representative_count": len(bank["replayed_representatives"]),
        "replay_result_count": len(feedback["results"]),
        "trajectory_models": [
            {
                "trajectory_id": value["trajectory_id"],
                "family_id": value["family_id"],
                "polynomial_degree": value["polynomial_degree"],
                "reference_time_s": value["reference_time_s"],
                "coefficients_hz": value["coefficients_hz"],
                "residual_rms_hz": value["residual_rms_hz"],
                "selected_for_correction": value["selected_for_correction"],
                "corrected_glrt64_probe_count": value["corrected_glrt64_probe_count"],
                "median_glrt64_margin_delta": value["median_glrt64_margin_delta"],
            }
            for value in trajectories
        ],
        "report_digest": item["report"]["report_digest"],
    }


def _assert_reviewed_path_summaries(
    expected: list[dict[str, Any]],
    actual: list[dict[str, Any]],
    tolerances: dict[str, float],
) -> None:
    pending = [
        f"{item['stream_id']}/RX{item['receiver_id']}"
        for item in expected
        if item["review_status"] != "reviewed_corrected_full_run"
    ]
    if pending:
        raise AssertionError(
            "corrected full-run detailed golden is explicitly pending review for "
            + ", ".join(pending)
        )
    by_path = {(item["stream_id"], item["receiver_id"]): item for item in actual}
    for reviewed in expected:
        identity = (reviewed["stream_id"], reviewed["receiver_id"])
        observed = by_path[identity]
        expected_values = {
            key: value
            for key, value in reviewed.items()
            if key not in {"review_status", "trajectory_models"}
        }
        actual_values = {key: observed[key] for key in expected_values}
        _assert_numerically_equal(
            expected_values,
            actual_values,
            absolute=float(tolerances["absolute"]),
            relative=float(tolerances["relative"]),
        )
        expected_models = reviewed["trajectory_models"]
        actual_models = observed["trajectory_models"]
        assert len(expected_models) == len(actual_models)
        for expected_model, actual_model in zip(
            expected_models,
            actual_models,
            strict=True,
        ):
            for field in (
                "trajectory_id",
                "family_id",
                "polynomial_degree",
                "selected_for_correction",
                "corrected_glrt64_probe_count",
            ):
                assert expected_model[field] == actual_model[field]
            assert math.isclose(
                expected_model["reference_time_s"],
                actual_model["reference_time_s"],
                abs_tol=float(tolerances["absolute"]),
                rel_tol=float(tolerances["relative"]),
            )
            for left, right in zip(
                expected_model["coefficients_hz"],
                actual_model["coefficients_hz"],
                strict=True,
            ):
                assert math.isclose(
                    left,
                    right,
                    abs_tol=float(tolerances["trajectory_coefficient_absolute_hz"]),
                    rel_tol=float(tolerances["relative"]),
                )
            assert math.isclose(
                expected_model["residual_rms_hz"],
                actual_model["residual_rms_hz"],
                abs_tol=float(tolerances["trajectory_rms_absolute_hz"]),
                rel_tol=float(tolerances["relative"]),
            )
            expected_margin = expected_model["median_glrt64_margin_delta"]
            actual_margin = actual_model["median_glrt64_margin_delta"]
            if expected_margin is None:
                assert actual_margin is None
            else:
                assert actual_margin is not None and math.isclose(
                    expected_margin,
                    actual_margin,
                    abs_tol=float(tolerances["glrt_margin_absolute"]),
                    rel_tol=float(tolerances["relative"]),
                )


def _exact_pair_timing(
    synchronization_inventory_digest: str,
    child_timings: tuple[StreamTimingEvidenceV1, StreamTimingEvidenceV1],
    *,
    start_skew_uncertainty_ns: int,
    guaranteed_overlap_ns: int,
    synchronization_grade: str,
) -> PairTimingEvidenceV1:
    return PairTimingEvidenceV1(
        synchronization_inventory_digest=synchronization_inventory_digest,
        union_start_utc_ns=min(item.first_estimate_utc_ns for item in child_timings),
        union_end_utc_ns=max(item.last_estimate_utc_ns for item in child_timings),
        estimated_overlap_start_utc_ns=max(item.first_estimate_utc_ns for item in child_timings),
        estimated_overlap_end_utc_ns=min(item.last_estimate_utc_ns for item in child_timings),
        estimated_start_skew_ns=abs(
            child_timings[0].first_estimate_utc_ns - child_timings[1].first_estimate_utc_ns
        ),
        start_skew_uncertainty_ns=start_skew_uncertainty_ns,
        guaranteed_overlap_ns=guaranteed_overlap_ns,
        synchronization_grade=synchronization_grade,
        phase_coherent=False,
    )


def _reload_identical_artifacts(
    first_root: Path,
    second_root: Path,
    first: dict[str, Any],
    second: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    first_bytes = (first_root / "scientific-output.json").read_bytes()
    second_bytes = (second_root / "scientific-output.json").read_bytes()
    assert first_bytes == canonical_json_bytes(first)
    assert second_bytes == canonical_json_bytes(second)
    assert first_bytes == second_bytes
    first_normalized = json.loads(first_bytes)
    second_normalized = json.loads(second_bytes)
    assert isinstance(first_normalized, dict)
    assert isinstance(second_normalized, dict)
    assert first_normalized == second_normalized
    return first_normalized, second_normalized


def _open_verified_fixture():
    report = preflight_corpus(_CORPUS_MANIFEST, local_corpus_root=_CORPUS_ROOT)
    fixture = report.by_id(_FIXTURE_ID)
    store = RecordingStore.open_read_only(fixture.directory)
    bundle = store.inspect(_SESSION_ID)
    verification = store.verify(bundle)
    assert bundle.manifest_sha256 == (
        "sha256:1712bf9293b684540824ad4adfe0764a3477d01d7da8fdb28398ae465076855d"
    )
    assert verification.chunk_count == 18
    assert verification.compressed_bytes == 1_179_238_949
    assert verification.uncompressed_bytes == 2_400_000_000
    assert verification.timeline_count == 2
    attestation_document = {
        "schema_version": 1,
        "algorithm_version": "recording-store-full-byte-verification-v1",
        "session_id": bundle.session_id,
        "manifest_digest": bundle.manifest_sha256,
        "chunk_count": verification.chunk_count,
        "compressed_bytes": verification.compressed_bytes,
        "uncompressed_bytes": verification.uncompressed_bytes,
        "timeline_count": verification.timeline_count,
        "streams": [
            {
                "stream_id": stream.stream_id,
                "chunk_count": len(stream.chunks),
                "compressed_chunk_closure_digest": _chunk_closure_digest(
                    stream,
                    digest_field="compressed_sha256",
                ),
                "uncompressed_chunk_closure_digest": _chunk_closure_digest(
                    stream,
                    digest_field="uncompressed_sha256",
                ),
                "timeline_digest": stream.timeline_sha256,
            }
            for stream in sorted(bundle.manifest.streams, key=lambda item: item.stream_id)
        ],
    }
    return store, bundle, canonical_digest(attestation_document)


def _path_inputs(
    bundle,
    stream,
    receiver_id: int,
    timing: StreamTimingEvidenceV1,
    sample_count: int,
    config: ReceiverStandardConfig,
    *,
    raw_attestation_digest: str,
    synchronization_inventory_digest: str | None = None,
) -> PathReportInputs:
    schedule = build_probe_schedule(
        sample_rate_hz=(stream.applied_settings or stream.requested_settings).sample_rate_hz,
        sample_count=sample_count,
        subwindow_ms=config.feedback.subwindow_ms,
        probe_ms=config.feedback.probe_ms,
        maximum_coarse_windows=config.feedback.maximum_outer_windows,
    )
    settings = stream.applied_settings or stream.requested_settings
    planner_sync_digest = canonical_digest(synchronization_inventory_document(bundle.manifest))
    sync_digest = synchronization_inventory_digest or planner_sync_digest
    if sync_digest != planner_sync_digest:
        raise ValueError("path binding synchronization inventory is not planner authoritative")
    bind_values = {
        "schema_version": 2,
        "algorithm_version": "standard-path-input-bind-v2",
        "session_id": bundle.session_id,
        "stream_id": stream.stream_id,
        "radio_id": stream.radio.radio_id,
        "receiver_id": receiver_id,
        "manifest_digest": bundle.manifest_sha256,
        "raw_integrity_attestation_digest": raw_attestation_digest,
        "selected_stream_digest": canonical_digest(stream.model_dump(mode="json")),
        "compressed_chunk_closure_digest": _chunk_closure_digest(
            stream,
            digest_field="compressed_sha256",
        ),
        "uncompressed_chunk_closure_digest": _chunk_closure_digest(
            stream,
            digest_field="uncompressed_sha256",
        ),
        "synchronization_inventory_digest": sync_digest,
        "profile_revision_digest": bundle.manifest.capture_plan.profile_revision.revision_digest,
        "capture_plan_digest": bundle.manifest.capture_plan.plan_digest,
        "receiver_settings_digest": canonical_digest(settings.model_dump(mode="json")),
        "science_configuration_digest": receiver_standard_configuration_digest(config),
        "science_implementation_digest": receiver_standard_implementation_digest(),
        "capture_lineage_resolution": "legacy_unresolved",
        "physical_receiver_id": None,
        "hardware_epoch_id": None,
        "tuned_center_frequency_hz": settings.center_frequency_hz,
        "sample_rate_hz": schedule.sample_rate_hz,
        "declared_sample_count": sample_count,
        "timing": timing.model_dump(mode="json"),
        "frequency_reference": ReceiverFrequencyReferenceV1(
            reference=FrequencyReference.UNCALIBRATED_PRIOR
        ).model_dump(mode="json"),
    }
    return PathReportInputs(
        input_bind=StandardPathInputBindV2(
            **bind_values,
            binding_digest=canonical_digest(bind_values),
        ),
        schedule=schedule,
        quality_clipping_abs_threshold=32_767,
        power_window_samples=config.power_window_samples or schedule.sample_rate_hz,
        waterfall_config_digest=config.waterfall.digest,
        maximum_scored_candidates_per_probe=(config.feedback.maximum_scored_candidates_per_probe),
        maximum_replayed_families=config.feedback.maximum_replayed_families,
    )


def _chunk_closure_digest(stream, *, digest_field: str) -> str:
    return canonical_digest(
        [
            {
                "chunk_index": chunk.chunk_index,
                "segment_index": chunk.segment_index,
                "sample_start": chunk.sample_start,
                "sample_count": chunk.sample_count,
                "digest": getattr(chunk, digest_field),
            }
            for chunk in stream.chunks
        ]
    )


def _stream_timing(stream) -> StreamTimingEvidenceV1:
    assert stream.timing is not None
    first = stream.timing.first_sample
    last = stream.timing.last_sample
    return StreamTimingEvidenceV1(
        first_estimate_utc_ns=first.estimate_utc_ns,
        first_earliest_utc_ns=first.earliest_utc_ns,
        first_latest_utc_ns=first.latest_utc_ns,
        last_estimate_utc_ns=last.estimate_utc_ns,
        last_earliest_utc_ns=last.earliest_utc_ns,
        last_latest_utc_ns=last.latest_utc_ns,
    )


def _prefix_timing(stream, duration_s: float) -> StreamTimingEvidenceV1:
    full = _stream_timing(stream)
    end = full.first_estimate_utc_ns + round(duration_s * 1e9)
    return StreamTimingEvidenceV1(
        first_estimate_utc_ns=full.first_estimate_utc_ns,
        first_earliest_utc_ns=full.first_earliest_utc_ns,
        first_latest_utc_ns=full.first_latest_utc_ns,
        last_estimate_utc_ns=end,
        last_earliest_utc_ns=end,
        last_latest_utc_ns=end,
    )


@dataclass(frozen=True, slots=True)
class _PrefixReader:
    source: Any
    sample_count: int

    @property
    def sample_rate_hz(self) -> int:
        return self.source.sample_rate_hz

    @property
    def center_frequency_hz(self) -> int:
        return self.source.center_frequency_hz

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        return self.source.receiver_ids

    def iter_blocks(self, *, block_samples: int):
        for block in self.source.iter_blocks(block_samples=block_samples):
            start = block.metadata.session_sample_start
            if start >= self.sample_count:
                return
            count = min(block.metadata.sample_count, self.sample_count - start)
            yield IqBlock(
                samples=block.samples[:count].copy(),
                metadata=block.metadata.model_copy(update={"sample_count": count}),
            )
            if start + count >= self.sample_count:
                return


def _assert_numerically_equal(
    left: Any,
    right: Any,
    *,
    absolute: float,
    relative: float,
    path: str = "$",
) -> None:
    if isinstance(left, bool) or left is None or isinstance(left, (str, int)):
        assert left == right, path
        return
    if isinstance(left, float):
        assert isinstance(right, (int, float)) and not isinstance(right, bool), path
        assert math.isfinite(left) and math.isfinite(float(right)), path
        assert math.isclose(left, float(right), abs_tol=absolute, rel_tol=relative), path
        return
    if isinstance(left, list):
        assert isinstance(right, list) and len(left) == len(right), path
        for index, (left_item, right_item) in enumerate(zip(left, right, strict=True)):
            _assert_numerically_equal(
                left_item,
                right_item,
                absolute=absolute,
                relative=relative,
                path=f"{path}[{index}]",
            )
        return
    if isinstance(left, dict):
        assert isinstance(right, dict) and set(left) == set(right), path
        for key in sorted(left):
            _assert_numerically_equal(
                left[key],
                right[key],
                absolute=absolute,
                relative=relative,
                path=f"{path}.{key}",
            )
        return
    raise AssertionError(f"unsupported comparison type at {path}: {type(left).__name__}")


def _assert_frozen_equivalent(
    frozen: Any,
    current: Any,
    *,
    absolute: float,
    relative: float,
    path: str = "$",
) -> None:
    """Compare every frozen field while allowing derived digests to rebind."""

    if isinstance(frozen, dict):
        assert isinstance(current, dict), path
        assert frozen.keys() == current.keys(), path
        for key in frozen:
            child = f"{path}.{key}"
            if key in {"content_digest", "report_digest"}:
                value = current[key]
                assert isinstance(value, str) and value.startswith("sha256:"), child
                assert len(value) == 71, child
                continue
            _assert_frozen_equivalent(
                frozen[key],
                current[key],
                absolute=absolute,
                relative=relative,
                path=child,
            )
        return
    if isinstance(frozen, list):
        assert isinstance(current, list) and len(frozen) == len(current), path
        for index, (left, right) in enumerate(zip(frozen, current, strict=True)):
            _assert_frozen_equivalent(
                left,
                right,
                absolute=absolute,
                relative=relative,
                path=f"{path}[{index}]",
            )
        return
    if isinstance(frozen, float):
        assert isinstance(current, (int, float)) and not isinstance(current, bool), path
        assert math.isclose(frozen, float(current), rel_tol=relative, abs_tol=absolute), path
        return
    assert frozen == current, path
