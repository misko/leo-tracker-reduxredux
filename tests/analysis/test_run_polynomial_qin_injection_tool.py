from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import zstandard as zstd

from leo.analysis.research.polynomial_injection_protocol import BackgroundSpan, ChunkBinding

ROOT = Path(__file__).parents[2]
TOOL_PATH = ROOT / "tools" / "run_polynomial_qin_injection.py"
SPEC = importlib.util.spec_from_file_location("run_polynomial_qin_injection", TOOL_PATH)
assert SPEC is not None and SPEC.loader is not None
tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tool
SPEC.loader.exec_module(tool)


def _continuity() -> dict[str, object]:
    return {
        "sample_loss_observable": True,
        "gap_count": 0,
        "missing_sample_count": 0,
        "overflow_count": 0,
        "enqueue_failure_count": 0,
        "clipped_sample_count": 0,
        "constant_iq_refill_count": 0,
        "terminal_rejected_gap_count": 0,
        "terminal_rejected_missing_sample_count": 0,
        "terminal_rejected_overflow_count": 0,
        "segment_count": 1,
        "observed_sample_count": 4,
        "device_span_sample_count": 4,
    }


def test_digest_pinned_reader_selects_only_frozen_receiver_span(
    tmp_path: Path, monkeypatch
) -> None:
    capture = tmp_path / "capture"
    chunk_path = capture / "radio" / "iq.ci16.zst"
    chunk_path.parent.mkdir(parents=True)
    cube = np.asarray(
        [
            [[1, 2], [11, 12]],
            [[3, 4], [13, 14]],
            [[5, 6], [15, 16]],
            [[7, 8], [17, 18]],
        ],
        dtype="<i2",
    )
    payload = cube.tobytes(order="C")
    compressed = zstd.ZstdCompressor(level=1).compress(payload)
    chunk_path.write_bytes(compressed)
    manifest = {
        "session_id": "cap-test",
        "streams": [
            {
                "stream_id": "stream-0",
                "state": "complete",
                "captured_sample_count": 4,
                "radio": {"radio_id": "radio-test", "serial": "serial-test"},
                "applied_settings": {"sample_rate_hz": 10, "receiver_ids": [0, 1]},
                "continuity": _continuity(),
                "chunks": [
                    {
                        "chunk_index": 7,
                        "sample_start": 100,
                        "sample_count": 4,
                        "relative_path": "radio/iq.ci16.zst",
                        "compressed_sha256": tool._sha256_bytes(compressed),
                        "uncompressed_sha256": tool._sha256_bytes(payload),
                        "sample_format": "ci16_le",
                        "sample_layout": "sample_receiver_iq",
                        "compressed_bytes": len(compressed),
                        "uncompressed_bytes": len(payload),
                    }
                ],
            }
        ],
    }
    manifest_path = capture / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    analysis_path = tmp_path / "analysis.json"
    analysis_path.write_text("{}", encoding="utf-8")
    binding = BackgroundSpan(
        session_id="cap-test",
        recording_manifest_path=manifest_path,
        recording_manifest_sha256=tool._sha256_file(manifest_path),
        analysis_run_id="capture-test",
        analysis_manifest_path=analysis_path,
        analysis_manifest_sha256=tool._sha256_file(analysis_path),
        stream_id="stream-0",
        radio_id="radio-test",
        radio_serial="serial-test",
        receiver_id=1,
        sample_rate_hz=10,
        sample_start=101,
        sample_count=2,
        chunk=ChunkBinding(
            chunk_index=7,
            sample_start=100,
            sample_count=4,
            relative_path="radio/iq.ci16.zst",
            compressed_sha256=tool._sha256_bytes(compressed),
            uncompressed_sha256=tool._sha256_bytes(payload),
        ),
    )
    monkeypatch.setattr(tool, "authorize_manifest_files", lambda *args, **kwargs: None)

    result = tool._read_verified_background(binding, policy=object())

    np.testing.assert_allclose(
        result.samples,
        np.asarray([13 + 14j, 15 + 16j], dtype=np.complex64) / 32_768.0,
    )
    assert result.span_sha256 == tool._canonical_complex_sha256(result.samples)

    bad = replace(
        binding,
        chunk=replace(binding.chunk, compressed_sha256="sha256:" + "0" * 64),
    )
    try:
        tool._read_verified_background(bad, policy=object())
    except ValueError as error:
        assert "chunk fields differ" in str(error) or "digest differs" in str(error)
    else:
        raise AssertionError("reader accepted a nonmatching frozen digest")


def _scenario_metric(
    scenario_id: str,
    *,
    error: float | None,
    background: str,
) -> dict[str, object]:
    count = 0 if error is None else 1
    values = tool._metric(
        np.asarray([] if error is None else [error], dtype=float),
        np.asarray([] if error is None else [True], dtype=bool),
        np.asarray([] if error is None else [False], dtype=bool),
    )
    row: dict[str, object] = {
        "scenario_id": scenario_id,
        "estimator": "fixed_500ms_linear",
        "scope": "all_complete",
        "estimator_no_result": error is None,
        "background_session_id": background,
        "seed": 1,
        "truth_rate_hz_s": 0.0,
        "truth_acceleration_hz_s2": 0.0,
        "truth_jerk_hz_s3": 0.0,
        "snr_db": -24.0,
        "frame_occupancy": 1.0,
        "alias_change_hz": 0.0,
        "cfo_step_hz": 0.0,
        "sample_clock_offset_ppm": 0.0,
    }
    for coordinate in ("receiver", "physical"):
        row.update({f"{coordinate}_{key}": value for key, value in values.items()})
        row[f"{coordinate}_count"] = count
    return row


def test_aggregate_is_scenario_equal_and_retains_no_results() -> None:
    rows = [
        _scenario_metric("P1", error=0.0, background="A"),
        _scenario_metric("P2", error=10.0, background="B"),
        _scenario_metric("P3", error=None, background="C"),
    ]

    aggregate = tool._aggregate_scenario_metrics(
        rows,
        selector=lambda row: True,
        scope_name="test",
    )[0]

    assert aggregate["scenario_count"] == 3
    assert aggregate["evaluable_scenario_count"] == 2
    assert aggregate["no_result_scenario_count"] == 1
    assert aggregate["no_result_scenario_rate"] == 1 / 3
    assert np.isclose(aggregate["receiver_rmse"], np.sqrt(50.0))


def test_step_aggregate_is_scenario_equal() -> None:
    rows = []
    for scenario_id, mse, count in (("P1", 1.0, 100), ("P2", 100.0, 1)):
        rows.append(
            {
                "scenario_id": scenario_id,
                "estimator": "fixed_500ms_linear",
                "scope": "transition",
                "cfo_step_hz": 300.0,
                "receiver_count": count,
                "receiver_mse": mse,
                "receiver_median_absolute_error": np.sqrt(mse),
            }
        )
    for estimator in ("causal_20ms_linear", "fixed_125ms_linear"):
        for row in list(rows):
            if row["estimator"] == "fixed_500ms_linear":
                rows.append({**row, "estimator": estimator})
    for estimator in (
        "causal_20ms_linear",
        "fixed_125ms_linear",
        "fixed_500ms_linear",
    ):
        for phase in ("pre_step", "post_history"):
            rows.append(
                {
                    "scenario_id": "P1",
                    "estimator": estimator,
                    "scope": phase,
                    "cfo_step_hz": 300.0,
                    "receiver_count": 0,
                    "receiver_mse": None,
                    "receiver_median_absolute_error": None,
                }
            )

    aggregate = tool._aggregate_step_scenario_metrics(rows)
    fixed_transition = next(
        row
        for row in aggregate
        if row["estimator"] == "fixed_500ms_linear" and row["phase"] == "transition"
    )

    assert fixed_transition["endpoint_count"] == 101
    assert fixed_transition["scenario_count"] == 2
    assert fixed_transition["evaluable_scenario_count"] == 2
    assert np.isclose(fixed_transition["receiver_rmse"], np.sqrt(50.5))


def test_promotion_requires_cubic_evidence_from_all_backgrounds() -> None:
    config = json.loads(
        (ROOT / "config/analysis/polynomial-phase-injection-protocol-v1.json").read_text(
            encoding="utf-8"
        )
    )
    rate = [
        {
            "scope": "promotion",
            "estimator": "fixed_500ms_linear",
            "evaluable_background_count": 3,
            "receiver_rmse": 100.0,
            "receiver_failure_rate": 0.0,
            "receiver_coverage_95": 0.9,
        }
    ]
    cubic = [
        {
            "scope": "promotion",
            "coordinate": "receiver",
            "derivative": derivative,
            "evaluable_background_count": 2,
            "rmse": 10.0,
        }
        for derivative in ("acceleration", "jerk")
    ]

    promotion = tool._promotion(rate, cubic, config)

    assert promotion["checks"]["all_three_backgrounds"] is False
    assert promotion["status"] == "fail"


def test_postprocess_receipt_preserves_execution_hashes() -> None:
    result = {
        "repository_head_at_execution": "execution-head",
        "implementation": {
            "tool_sha256": "sha256:" + "1" * 64,
            "kernel_sha256": "sha256:" + "2" * 64,
            "protocol_loader_sha256": "sha256:" + "3" * 64,
        },
    }
    execution = dict(result["implementation"])

    tool._attach_postprocess_receipt(result, ROOT)

    assert result["implementation"] == execution
    assert result["postprocess_implementation"]["tool_sha256"] == tool._sha256_file(TOOL_PATH)
