from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from leo.analysis.standard import (
    PathReportInputs,
    ReceiverStandardConfig,
    build_probe_schedule,
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
    StreamTimingEvidenceV1,
)
from leo.domain.iq import IqBlock
from leo.storage import RecordingStore

_CORPUS_MANIFEST = Path("corpus/manifest.json").resolve()
_GOLDEN = Path("corpus/goldens/trial-132-standard-v2-summary.json").resolve()
_CORPUS_ROOT = Path(os.environ.get("LEO_REAL_CORPUS_ROOT", "/srv/bulk/leo/test-corpus"))
_FIXTURE_ID = "trial-132-four-path-v1"
_SESSION_ID = "production-24h-20260819-01-trial-00000132"


@pytest.mark.real_corpus
def test_trial132_one_path_one_coarse_window_benchmark_smoke() -> None:
    """Measured real-IQ component smoke; deliberately not a full-dwell claim."""

    store, bundle = _open_verified_fixture()
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
        inputs = _path_inputs(bundle, stream, 0, timing, source.sample_count, config)

        started = time.perf_counter()
        result = run_receiver_standard(source, inputs, config=config)
        elapsed = time.perf_counter() - started

        assert len(result.products.pilot_certificates) == 20
        assert result.documents["quality.summary"]["observed_sample_count"] == 2_500_000
        assert len(result.documents["power.summary"]["timeline"]) == 1
        assert result.documents["standard.pilot-scan"]["schema_version"] == 2
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

    first = _run_full_chain(first_root)
    second = _run_full_chain(second_root)

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
        degree
        for item in first["path_summaries"]
        for degree in item["polynomial_degrees"]
    } == set(golden["required_polynomial_degrees"])


def _run_full_chain(output_root: Path) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=False)
    store, bundle = _open_verified_fixture()
    try:
        config = ReceiverStandardConfig()
        synchronization = bundle.manifest.synchronization
        assert synchronization is not None and synchronization.phase_coherent is False
        sync_digest = canonical_digest(synchronization.model_dump(mode="json"))
        path_results = []
        reports = []
        for stream in sorted(bundle.manifest.streams, key=lambda item: item.stream_id):
            settings = stream.applied_settings or stream.requested_settings
            assert stream.timing is not None
            timing = _stream_timing(stream)
            source = store.reader(bundle, stream.stream_id)
            for receiver_id in settings.receiver_ids:
                inputs = _path_inputs(
                    bundle,
                    stream,
                    receiver_id,
                    timing,
                    stream.captured_sample_count,
                    config,
                    synchronization_inventory_digest=sync_digest,
                )
                result = run_receiver_standard(source, inputs, config=config)
                reports.append(result.products.report)
                path_results.append(
                    {
                        "stream_id": stream.stream_id,
                        "receiver_id": receiver_id,
                        "report": result.products.report.model_dump(mode="json"),
                        "pilot_certificates": [
                            item.model_dump(mode="json")
                            for item in result.products.pilot_certificates
                        ],
                        "documents": result.documents,
                    }
                )
        radio_reports = tuple(
            reduce_radio(
                tuple(item for item in reports if item.stream_id == stream.stream_id),
                declared_receiver_ids=tuple(
                    (stream.applied_settings or stream.requested_settings).receiver_ids
                ),
            )
            for stream in sorted(bundle.manifest.streams, key=lambda item: item.stream_id)
        )
        pair_timing = PairTimingEvidenceV1(
            synchronization_inventory_digest=sync_digest,
            union_start_utc_ns=min(
                item.paths[0].timing.first_estimate_utc_ns for item in radio_reports
            ),
            union_end_utc_ns=max(
                item.paths[0].timing.last_estimate_utc_ns for item in radio_reports
            ),
            estimated_overlap_start_utc_ns=synchronization.estimated_overlap_start_utc_ns,
            estimated_overlap_end_utc_ns=synchronization.estimated_overlap_end_utc_ns,
            estimated_start_skew_ns=synchronization.estimated_start_skew_ns,
            start_skew_uncertainty_ns=synchronization.start_skew_uncertainty_ns,
            guaranteed_overlap_ns=synchronization.guaranteed_overlap_ns,
            synchronization_grade=synchronization.grade.value,
            phase_coherent=False,
        )
        paired = reduce_paired_radios(radio_reports, timing=pair_timing)
        result_document = {
            "fixture_id": _FIXTURE_ID,
            "manifest_digest": bundle.manifest_sha256,
            "path_inventory": [
                [item["stream_id"], item["receiver_id"]] for item in path_results
            ],
            "path_summaries": [
                {
                    "stream_id": item["stream_id"],
                    "receiver_id": item["receiver_id"],
                    "probe_count": len(item["pilot_certificates"]),
                    "trajectory_count": len(item["report"]["trajectories"]),
                    "polynomial_degrees": sorted(
                        {value["polynomial_degree"] for value in item["report"]["trajectories"]}
                    ),
                    "report_digest": item["report"]["report_digest"],
                }
                for item in path_results
            ],
            "paths": path_results,
            "radio_reports": [item.model_dump(mode="json") for item in radio_reports],
            "paired_report": paired.model_dump(mode="json"),
        }
        (output_root / "scientific-output.json").write_bytes(
            canonical_json_bytes(result_document)
        )
        return result_document
    finally:
        store.close()


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
    return store, bundle


def _path_inputs(
    bundle,
    stream,
    receiver_id: int,
    timing: StreamTimingEvidenceV1,
    sample_count: int,
    config: ReceiverStandardConfig,
    *,
    synchronization_inventory_digest: str | None = None,
) -> PathReportInputs:
    schedule = build_probe_schedule(
        sample_rate_hz=(stream.applied_settings or stream.requested_settings).sample_rate_hz,
        sample_count=sample_count,
        subwindow_ms=config.feedback.subwindow_ms,
        probe_ms=config.feedback.probe_ms,
        maximum_coarse_windows=config.feedback.maximum_outer_windows,
    )
    synchronization = bundle.manifest.synchronization
    assert synchronization is not None
    return PathReportInputs(
        session_id=bundle.session_id,
        stream_id=stream.stream_id,
        radio_id=stream.radio.radio_id,
        receiver_id=receiver_id,
        manifest_digest=bundle.manifest_sha256,
        synchronization_inventory_digest=(
            synchronization_inventory_digest
            or canonical_digest(synchronization.model_dump(mode="json"))
        ),
        sample_rate_hz=schedule.sample_rate_hz,
        declared_sample_count=sample_count,
        timing=timing,
        frequency_reference=ReceiverFrequencyReferenceV1(
            reference=FrequencyReference.UNCALIBRATED_PRIOR
        ),
        schedule=schedule,
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
