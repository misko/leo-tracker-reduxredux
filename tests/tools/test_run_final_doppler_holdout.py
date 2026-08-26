from __future__ import annotations

import json
import re
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.research.doppler_holdout_odd_adapter import (
    AuthorizedOddChunk,
    OddQinFrameReadRequest,
)
from leo.analysis.research.doppler_holdout_pre_response import (
    DEFAULT_STRICT_PAST_CONFIGS,
    DopplerHoldoutPredictionLedgerV1,
    ForecastTargetKeyV1,
    OddQinTargetAuthorityV1,
)
from leo.contracts.digests import canonical_digest
from tools import run_final_doppler_holdout as runner

DIGEST = "sha256:" + "1" * 64


def _authority(*, stream_id: str = "stream-0") -> OddQinTargetAuthorityV1:
    return OddQinTargetAuthorityV1(
        target=ForecastTargetKeyV1(
            session_id="capture-a",
            episode_id=DIGEST,
            target_mask_digest=DIGEST,
            frame_start_sample=101,
            reference_sample=102.0,
            continuity_segment_id=0,
        ),
        scope_key=DIGEST,
        stream_id=stream_id,
        radio_id="radio-a",
        receiver_id=0,
        edge="lower",
        source_id=DIGEST,
        branch_id=DIGEST,
        trajectory_id=DIGEST,
        acquisition_absolute_cfo_hz=100_000.0,
    )


def _chunk(*, stream_id: str = "stream-0", start: int = 0) -> AuthorizedOddChunk:
    return AuthorizedOddChunk(
        session_id="capture-a",
        stream_id=stream_id,
        relative_path=f"{stream_id}/iq-{start}.ci16.zst",
        sample_start=start,
        sample_count=10_000,
        compressed_sha256=DIGEST,
    )


class _FakeReader:
    def __init__(self, stream_id: str, calls: list[tuple[str, int, int]]) -> None:
        self.stream_id = stream_id
        self.sample_rate_hz = 2_500_000
        self._calls = calls

    def read(
        self,
        start: int,
        count: int,
        *,
        receiver_ids: tuple[int, ...],
    ) -> np.ndarray:
        self._calls.append((self.stream_id, start, count))
        marker = 1 if self.stream_id == "stream-0" else 2
        return np.full((count, len(receiver_ids), 2), marker, dtype=np.int16)


class _FakeStore:
    def __init__(self, chunks: tuple[AuthorizedOddChunk, ...]) -> None:
        self.calls: list[tuple[str, int, int]] = []
        streams = []
        for stream_id in tuple(dict.fromkeys(item.stream_id for item in chunks)):
            manifest_chunks = tuple(
                SimpleNamespace(
                    relative_path=item.relative_path,
                    sample_start=item.sample_start,
                    sample_count=item.sample_count,
                    compressed_sha256=item.compressed_sha256,
                )
                for item in chunks
                if item.stream_id == stream_id
            )
            streams.append(SimpleNamespace(stream_id=stream_id, chunks=manifest_chunks))
        self.bundle = SimpleNamespace(
            manifest_sha256=DIGEST,
            manifest=SimpleNamespace(streams=tuple(streams)),
        )

    def inspect(self, session_id: str) -> object:
        assert session_id == "capture-a"
        return self.bundle

    def reader(self, bundle: object, stream_id: str, *, verify: bool) -> _FakeReader:
        assert bundle is self.bundle
        assert verify is True
        return _FakeReader(stream_id, self.calls)


def _request(
    authority: OddQinTargetAuthorityV1, chunk: AuthorizedOddChunk
) -> OddQinFrameReadRequest:
    return OddQinFrameReadRequest(
        authority=authority,
        sample_rate_hz=2_500_000,
        recording_manifest_sha256=DIGEST,
        chunks=(chunk,),
    )


def _synthetic_prediction() -> DopplerHoldoutPredictionLedgerV1:
    target = ForecastTargetKeyV1(
        session_id="capture-a",
        episode_id=DIGEST,
        target_mask_digest=DIGEST,
        frame_start_sample=101,
        reference_sample=102.0,
        continuity_segment_id=0,
    )
    forecasts = []
    for config in DEFAULT_STRICT_PAST_CONFIGS:
        forecasts.append(
            {
                "method": config.name,
                "history_s": config.history_s,
                "polynomial_degree": config.polynomial_degree,
                "status": "complete",
                "rejection_reasons": [],
                "history_frame_count": config.minimum_frames,
                "effective_history_frame_count": float(config.minimum_effective_frames),
                "history_span_ms": config.history_s * 900.0,
                "history_to_target_span_ms": config.history_s * 950.0,
                "maximum_gap_ms": 1.4,
                "earliest_history_reference_sample": 1.0,
                "latest_history_reference_sample": 100.0,
                "history_digest": DIGEST,
                "predicted_cfo_hz": 10.0,
                "rate_hz_s": -3.0,
                "acceleration_hz_s2": 0.0 if config.polynomial_degree == 1 else 0.25,
                "weighted_rms_hz": 5.0,
                "converged": True,
            }
        )
    document = {
        "schema": "org.leo.research.doppler-holdout-prediction-ledger/v1",
        "phase": "pre_response_prediction_freeze",
        "source_v2_file_sha256": DIGEST,
        "source_v2_manifest_digest": DIGEST,
        "forecast_implementation_sha256": DIGEST,
        "forecast_configuration_digest": DIGEST,
        "future_odd_qin_outcomes_opened": False,
        "target_even_numeric_cfo_consumed": False,
        "target_count": 1,
        "rows": [
            {
                "target": target.model_dump(mode="json"),
                "target_even_status_used_for_membership": True,
                "target_even_numeric_cfo_consumed": False,
                "forecasts": forecasts,
            }
        ],
    }
    document["ledger_digest"] = canonical_digest(document)
    return DopplerHoldoutPredictionLedgerV1.model_validate(document)


def test_odd_source_rejects_gap_and_manifest_drift_before_read() -> None:
    first = _chunk(start=0)
    second = _chunk(start=20_000)
    with pytest.raises(ValueError, match="contiguous"):
        runner._PinnedRecordingOddSource(_FakeStore((first, second)), (first, second))

    store = _FakeStore((first,))
    store.bundle.manifest.streams[0].chunks[0].sample_count = 9_999
    source = runner._PinnedRecordingOddSource(store, (first,))
    with pytest.raises(ValueError, match="manifest chunk"):
        source.read_guarded_odd_qin_frame(_request(_authority(), first))
    assert store.calls == []


def test_odd_source_cache_is_bound_to_stream_even_for_same_receiver() -> None:
    stream_zero = _chunk(stream_id="stream-0")
    stream_one = _chunk(stream_id="stream-1")
    store = _FakeStore((stream_zero, stream_one))
    source = runner._PinnedRecordingOddSource(store, (stream_zero, stream_one))

    zero = source.read_guarded_odd_qin_frame(_request(_authority(), stream_zero))
    one = source.read_guarded_odd_qin_frame(_request(_authority(stream_id="stream-1"), stream_one))

    assert len(store.calls) == 2
    assert store.calls[0][0] == "stream-0"
    assert store.calls[1][0] == "stream-1"
    assert np.real(zero.samples[0]) == 1
    assert np.real(one.samples[0]) == 2


def test_invalid_pre_response_receipt_fails_before_storage_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text("{}")
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps({"schema": "wrong"}))
    monkeypatch.setattr(
        runner,
        "load_and_validate_final_protocol",
        lambda *_args, **_kwargs: {
            "selector_v2": {"path": "selector.json"},
            "captures": [],
        },
    )
    monkeypatch.setattr(runner, "_load_manifest", lambda *_args, **_kwargs: object())

    def forbidden_pin(_path: Path) -> object:
        raise AssertionError("storage must not open before receipt validation")

    monkeypatch.setattr(runner, "PinnedLocalRoot", forbidden_pin)
    arguments = Namespace(
        protocol=str(protocol_path),
        prediction_ledger=str(tmp_path / "prediction.json"),
        association_bins=str(tmp_path / "bins.json"),
        rankings=str(tmp_path / "rankings.json"),
        pre_response_receipt=str(receipt_path),
        bulk_root=str(tmp_path / "bulk"),
        output=str(tmp_path / "attachment.json"),
    )

    with pytest.raises(ValueError, match="receipt schema"):
        runner._attach_odd(arguments)


@pytest.mark.parametrize(
    ("poison", "message"),
    (
        ("prediction_digest", "prediction ledger semantic"),
        ("prediction_sha", "prediction ledger bytes"),
        ("bins_digest", "association-bin digest"),
        ("bins_sha", "association-bin bytes"),
    ),
)
def test_response_free_replay_artifact_expectations_fail_closed(
    poison: str,
    message: str,
    tmp_path: Path,
) -> None:
    prediction = _synthetic_prediction()
    prediction_path = tmp_path / "prediction.json"
    prediction_path.write_text(prediction.model_dump_json(indent=2) + "\n")
    bins_document = {
        "schema": "org.leo.research.final-holdout-association-bins/v1",
        "prediction_ledger_digest": prediction.ledger_digest,
        "response_accessed": False,
        "inventories": [],
    }
    bins_document["bins_digest"] = canonical_digest(bins_document)
    bins_path = tmp_path / "bins.json"
    runner._write_json(bins_path, bins_document)
    correction = {
        "expected_prediction_ledger_digest": prediction.ledger_digest,
        "expected_prediction_ledger_sha256": "sha256:" + runner._sha256(prediction_path),
        "expected_corrected_bins_digest": bins_document["bins_digest"],
        "expected_corrected_bins_sha256": "sha256:" + runner._sha256(bins_path),
    }
    protocol_document = {"supersession": {"response_free_correction": correction}}
    runner._validate_pre_response_replay_artifacts(
        protocol_document,
        prediction=prediction,
        prediction_path=prediction_path,
        bins_document=bins_document,
        bins_path=bins_path,
    )
    field = {
        "prediction_digest": "expected_prediction_ledger_digest",
        "prediction_sha": "expected_prediction_ledger_sha256",
        "bins_digest": "expected_corrected_bins_digest",
        "bins_sha": "expected_corrected_bins_sha256",
    }[poison]
    correction[field] = "sha256:" + "0" * 64

    with pytest.raises(ValueError, match=message):
        runner._validate_pre_response_replay_artifacts(
            protocol_document,
            prediction=prediction,
            prediction_path=prediction_path,
            bins_document=bins_document,
            bins_path=bins_path,
        )


def test_predict_replay_mismatch_precedes_tle_and_candidate_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prediction = _synthetic_prediction()
    inventory = runner.FrozenCaptureBinInventory(
        session_id="capture-a",
        prediction_ledger_digest=prediction.ledger_digest,
        bins=tuple(
            runner.FrozenAssociationBin(
                session_id="capture-a",
                bin_id=index,
                center_utc_ns=100 + index,
                target_count=1,
                target_frame_start_samples=(index,),
                primary_cfo_hz=float(index),
                baseline_cfo_hz=float(index),
                split="training" if index <= 6 else "evaluation",
            )
            for index in range(1, 11)
        ),
        evaluable=True,
        failure_reasons=(),
    )
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text("{}")
    protocol_document = {
        "selector_v2": {"path": "selector.json"},
        "association": {"maximum_pre_response_compute_seconds": 3600.0},
        "captures": [
            {
                "session_id": "capture-a",
                "first_sample_estimate_utc_ns": 1,
                "sample_rate_hz": 1,
            }
        ],
        "supersession": {
            "response_free_correction": {
                "expected_prediction_ledger_digest": "sha256:" + "0" * 64,
                "expected_prediction_ledger_sha256": "sha256:" + "0" * 64,
                "expected_corrected_bins_digest": "sha256:" + "0" * 64,
                "expected_corrected_bins_sha256": "sha256:" + "0" * 64,
            }
        },
    }
    monkeypatch.setattr(
        runner,
        "load_and_validate_final_protocol",
        lambda *_args, **_kwargs: protocol_document,
    )
    monkeypatch.setattr(runner, "_load_manifest", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(runner, "build_prediction_ledger", lambda *_args, **_kwargs: prediction)
    monkeypatch.setattr(runner, "freeze_association_bins", lambda *_args, **_kwargs: (inventory,))
    monkeypatch.setattr(runner, "TARGET_COUNT", 1)
    forbidden_calls: list[str] = []

    def forbidden(name: str):
        def fail(*_args: object, **_kwargs: object) -> object:
            forbidden_calls.append(name)
            raise AssertionError(f"{name} must not run after a replay mismatch")

        return fail

    monkeypatch.setattr(runner, "LegacyTleSnapshotReader", forbidden("tle-reader"))
    monkeypatch.setattr(
        runner,
        "visible_starlink_candidates_at_site",
        forbidden("candidate-propagation"),
    )
    monkeypatch.setattr(runner, "_freeze_population_ranking", forbidden("candidate-ranking"))

    with pytest.raises(ValueError, match="prediction ledger semantic"):
        runner._predict(
            Namespace(protocol=str(protocol_path), output_dir=str(tmp_path / "attempt"))
        )

    assert forbidden_calls == []


def test_predict_preflights_every_rolling_origin_before_tle_or_candidate_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prediction = _synthetic_prediction()
    inventory = runner.FrozenCaptureBinInventory(
        session_id="capture-a",
        prediction_ledger_digest=prediction.ledger_digest,
        bins=tuple(
            runner.FrozenAssociationBin(
                session_id="capture-a",
                bin_id=index,
                center_utc_ns=100 + index,
                target_count=1,
                target_frame_start_samples=(index,),
                primary_cfo_hz=float(index),
                baseline_cfo_hz=float(index),
                split="training" if index <= 6 else "evaluation",
            )
            for index in range(1, 11)
        ),
        evaluable=True,
        failure_reasons=(),
    )
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text("{}")
    protocol_document = {
        "selector_v2": {"path": "selector.json"},
        "association": {"maximum_pre_response_compute_seconds": 3600.0},
        "captures": [
            {
                "session_id": "capture-a",
                "first_sample_estimate_utc_ns": 1,
                "sample_rate_hz": 1,
            }
        ],
    }
    monkeypatch.setattr(
        runner,
        "load_and_validate_final_protocol",
        lambda *_args, **_kwargs: protocol_document,
    )
    monkeypatch.setattr(runner, "_load_manifest", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(runner, "build_prediction_ledger", lambda *_args, **_kwargs: prediction)
    monkeypatch.setattr(runner, "freeze_association_bins", lambda *_args, **_kwargs: (inventory,))
    monkeypatch.setattr(
        runner,
        "_validate_pre_response_replay_artifacts",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(runner, "_target_span_utc_ns", lambda *_args, **_kwargs: (100, 109))
    monkeypatch.setattr(runner, "TARGET_COUNT", 1)
    forbidden_calls: list[str] = []

    def forbidden(name: str):
        def fail(*_args: object, **_kwargs: object) -> object:
            forbidden_calls.append(name)
            raise AssertionError(f"{name} must not run before rolling preflight")

        return fail

    monkeypatch.setattr(runner, "LegacyTleSnapshotReader", forbidden("tle-reader"))
    monkeypatch.setattr(
        runner,
        "visible_starlink_candidates_at_site",
        forbidden("candidate-propagation"),
    )
    monkeypatch.setattr(runner, "_freeze_population_ranking", forbidden("candidate-ranking"))
    output = tmp_path / "attempt"

    with pytest.raises(ValueError, match="outside the full target UTC span"):
        runner._predict(Namespace(protocol=str(protocol_path), output_dir=str(output)))

    assert forbidden_calls == []
    assert (output / "prediction-ledger.json").is_file()
    assert (output / "association-bin-inventory.json").is_file()
    assert not (output / "pre-response-rankings.json").exists()
    status = json.loads((output / "pre-response-failure-status.json").read_text())
    assert status["status"] == "failed_closed"
    assert status["candidate_propagation_or_ranking_may_have_started"] is False
    assert status["odd_iq_accessed"] is False
    assert status["odd_responses_accessed"] is False
    assert status["status_digest"] == canonical_digest(
        {key: value for key, value in status.items() if key != "status_digest"}
    )
    assert set(status["partial_artifacts"]) == {
        "prediction-ledger.json",
        "association-bin-inventory.json",
    }


def test_failure_status_never_mutates_a_preexisting_output_directory(tmp_path: Path) -> None:
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text("{}\n")
    output = tmp_path / "preexisting-attempt"
    output.mkdir()
    sentinel = output / "keep-exactly.bin"
    sentinel.write_bytes(b"preexisting bytes\x00\xff")
    before = {path.name: path.read_bytes() for path in output.iterdir()}
    arguments = Namespace(
        protocol=str(protocol_path),
        output_dir=str(output),
        _output_dir_created_by_run=False,
        _candidate_work_started=False,
    )

    runner._write_predict_failure_status(
        arguments,
        started_time_ns=123,
        error=FileExistsError(str(output)),
        traceback_text="preexisting output directory",
    )

    assert {path.name: path.read_bytes() for path in output.iterdir()} == before
    assert not (output / "pre-response-failure-status.json").exists()


def test_report_figure_links_resolve_from_markdown_directory(tmp_path: Path) -> None:
    report_dir = tmp_path / "reports"
    figure_dir = tmp_path / "artifacts" / "figures"
    report_dir.mkdir()
    score_path = tmp_path / "artifacts" / "score.json"
    protocol_path = tmp_path / "config" / "protocol.json"
    score = {
        "scores": [
            {
                "method": runner.BASELINE_ASSOCIATION_METHOD,
                "equal_capture_rms_hz": 10.0,
                "captures": [{"session_id": "cap-a", "rms_hz": 10.0}],
            },
            {
                "method": runner.PRIMARY_ASSOCIATION_METHOD,
                "equal_capture_rms_hz": 8.0,
                "captures": [{"session_id": "cap-a", "rms_hz": 8.0}],
            },
        ],
        "association": [{"session_id": "cap-a", "evaluable": False}],
        "association_thresholds": {
            "maximum_claim_rank_one_heldout_odd_rms_hz": 100.0,
        },
        "response_status_denominator": {
            "target_count": 1,
            "measured_nonmissing": 1,
            "accuracy_eligible": 1,
            "boundary": 0,
            "no_support": 0,
            "missing": 0,
            "common_accuracy": 1,
            "captures": [
                {
                    "session_id": "cap-a",
                    "target_count": 1,
                    "accuracy_eligible": 1,
                    "boundary": 0,
                    "no_support": 0,
                    "missing": 0,
                    "common_accuracy": 1,
                }
            ],
        },
        "quadratic_promotion_gate": {
            "passed": True,
            "ratio": 0.8,
            "capture_wins": 10,
            "capture_comparisons": 10,
            "failed_conditions": [],
        },
        "score_digest": DIGEST,
        "prediction_ledger_digest": DIGEST,
        "attachment_digest": DIGEST,
    }
    markdown_path = report_dir / "final.md"
    runner._write_report_artifacts(
        score,
        figure_dir=figure_dir,
        markdown_path=markdown_path,
        score_path=score_path,
        protocol_path=protocol_path,
    )

    links = re.findall(r"!\[[^]]*\]\(([^)]+)\)", markdown_path.read_text())
    assert len(links) == 3
    assert all((markdown_path.parent / link).resolve().is_file() for link in links)


@pytest.mark.parametrize(
    "poison",
    (
        "source_sha",
        "configuration_digest",
        "target_reference",
        "target_frame",
        "predicted_cfo",
        "history_digest",
        "forecast_status",
    ),
)
def test_resigned_prediction_poison_fails_exact_recomputation_before_bins(
    poison: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _synthetic_prediction()
    document = expected.model_dump(mode="json", exclude={"ledger_digest"})
    if poison == "source_sha":
        document["source_v2_file_sha256"] = "sha256:" + "2" * 64
    elif poison == "configuration_digest":
        document["forecast_configuration_digest"] = "sha256:" + "2" * 64
    elif poison == "target_reference":
        document["rows"][0]["target"]["reference_sample"] += 1.0
    elif poison == "target_frame":
        document["rows"][0]["target"]["frame_start_sample"] += 1
    elif poison == "predicted_cfo":
        document["rows"][0]["forecasts"][0]["predicted_cfo_hz"] += 1.0
    elif poison == "history_digest":
        document["rows"][0]["forecasts"][0]["history_digest"] = "sha256:" + "2" * 64
    else:
        forecast = document["rows"][0]["forecasts"][0]
        forecast["status"] = "no_result"
        forecast["rejection_reasons"] = ["poisoned"]
        for key in (
            "predicted_cfo_hz",
            "rate_hz_s",
            "acceleration_hz_s2",
            "weighted_rms_hz",
            "converged",
        ):
            forecast[key] = None
    document["ledger_digest"] = canonical_digest(document)
    poisoned = DopplerHoldoutPredictionLedgerV1.model_validate(document)

    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text("{}")
    prediction_path = tmp_path / "prediction.json"
    prediction_path.write_text(poisoned.model_dump_json(indent=2))
    bins_path = tmp_path / "bins.json"
    bins_path.write_text("{}")
    rankings_path = tmp_path / "rankings.json"
    rankings_path.write_text("{}")
    protocol_document = {
        "protocol_digest": DIGEST,
        "selector_v2": {"path": "selector.json"},
        "association": {"maximum_pre_response_compute_seconds": 3600.0},
        "captures": [],
    }
    receipt = {
        "schema": "org.leo.research.final-holdout-pre-response-receipt/v1",
        "protocol_sha256": "sha256:" + runner._sha256(protocol_path),
        "protocol_digest": DIGEST,
        "prediction_ledger_digest": poisoned.ledger_digest,
        "target_count": 1,
        "satellites_propagated_or_ranked_before_protocol_freeze": False,
        "odd_iq_accessed": False,
        "odd_responses_accessed": False,
        "runtime_seconds": 1.0,
        "maximum_pre_response_compute_seconds": 3600.0,
        "artifacts": {
            "prediction_ledger": {
                "basename": prediction_path.name,
                "sha256": "sha256:" + runner._sha256(prediction_path),
                "semantic_digest": poisoned.ledger_digest,
            },
            "association_bins": {
                "basename": bins_path.name,
                "sha256": "sha256:" + runner._sha256(bins_path),
                "semantic_digest": DIGEST,
            },
            "rankings_and_controls": {
                "basename": rankings_path.name,
                "sha256": "sha256:" + runner._sha256(rankings_path),
                "semantic_digest": DIGEST,
            },
        },
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt))

    monkeypatch.setattr(runner, "TARGET_COUNT", 1)
    monkeypatch.setattr(runner, "CAPTURE_IDS", ("capture-a",))
    monkeypatch.setattr(runner, "_load_manifest", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        runner,
        "build_prediction_ledger",
        lambda *_args, **_kwargs: expected,
    )
    with pytest.raises(ValueError, match="exact selector recomputation"):
        runner._load_pre_response_authority(
            protocol_path=protocol_path,
            protocol=protocol_document,
            prediction_path=prediction_path,
            bins_path=bins_path,
            rankings_path=rankings_path,
            receipt_path=receipt_path,
        )
