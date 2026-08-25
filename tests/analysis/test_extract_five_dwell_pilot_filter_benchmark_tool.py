from __future__ import annotations

import copy
import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest
import zstandard as zstd


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "extract_five_dwell_pilot_filter_benchmark.py"
    spec = importlib.util.spec_from_file_location("five_dwell_filter_extractor_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _candidate(
    *,
    margin: float,
    exact: float = 0.5,
    rank: int = 0,
    tracking_cfo_hz: float = 1_000.0,
    epoch: int = 3,
) -> dict[str, object]:
    return {
        "rank": rank,
        "local_epoch_sample": epoch,
        "acquired_cfo_hz": tracking_cfo_hz - 10.0,
        "scores": [
            {
                "method": "glrt64",
                "tracking_cfo_hz": tracking_cfo_hz,
                "residual_cfo_hz": 10.0,
                "exact_score": exact,
                "control_score": exact - margin,
                "margin": margin,
            }
        ],
    }


def _detection(start: int, *candidates: dict[str, object]) -> dict[str, object]:
    return {
        "sample_start": start,
        "time_s": start / 1_000.0,
        "source_candidate_count": len(candidates),
        "candidates": list(candidates),
    }


def test_frozen_cohort_is_the_five_nondevelopment_siblings() -> None:
    tool = _tool()
    assert [spec.label for spec in tool.DWELLS] == ["D1", "D2", "D4", "D5", "D6"]
    assert len({spec.session_id for spec in tool.DWELLS}) == 5
    assert len({spec.run_id for spec in tool.DWELLS}) == 5
    assert all(spec.run_id.startswith("capture-") for spec in tool.DWELLS)
    assert all(spec.scope_digest.startswith("sha256:") for spec in tool.DWELLS)
    assert all(len(spec.recording_manifest_sha256) == 64 for spec in tool.DWELLS)
    assert all(len(spec.analysis_manifest_sha256) == 64 for spec in tool.DWELLS)
    assert all(len(spec.pilot_scan_sha256) == 64 for spec in tool.DWELLS)
    assert not any("192531" in spec.session_id for spec in tool.DWELLS)
    assert [(spec.channel, spec.edge.value) for spec in tool.DWELLS] == [
        (2, "lower"),
        (3, "upper"),
        (3, "lower"),
        (2, "lower"),
        (3, "lower"),
    ]


def test_seed_selection_is_sample_binned_deterministic_and_keeps_misses() -> None:
    tool = _tool()
    scan = {
        "probe_samples": 20,
        "detections": [
            _detection(0, _candidate(margin=0.5, exact=0.6, rank=2)),
            _detection(50, _candidate(margin=0.5, exact=0.6, rank=1)),
            _detection(80, _candidate(margin=0.5, exact=0.6, rank=1)),
            _detection(100, _candidate(margin=0.2)),
            _detection(300, _candidate(margin=0.3)),
            _detection(400, _candidate(margin=0.4)),
            # This candidate cannot seed a complete 100 ms replay.
            _detection(450, _candidate(margin=0.9)),
        ],
    }
    bins = tool.select_seed_bins(
        scan,
        sample_rate_hz=1_000,
        sample_count=500,
        replay_window_samples=100,
    )

    assert len(bins) == 5
    assert bins[0]["seed"]["sample_start"] == 50
    assert bins[0]["seed"]["candidate_rank"] == 1
    assert bins[2]["status"] == "missing"
    assert bins[2]["seed"] is None
    assert bins[2]["missing_reason"]
    assert bins[4]["seed"]["sample_start"] == 400
    assert [row["raw_disjoint"] for row in bins] == [True, False, True, False, True]


def test_even_bin_lane_is_raw_window_disjoint_at_worst_case_offsets() -> None:
    tool = _tool()
    scan = {
        "probe_samples": 20,
        "detections": [
            _detection(90, _candidate(margin=0.5)),
            _detection(200, _candidate(margin=0.5)),
            _detection(290, _candidate(margin=0.6)),
            _detection(400, _candidate(margin=0.5)),
        ],
    }
    bins = tool.select_seed_bins(
        scan,
        sample_rate_hz=1_000,
        sample_count=500,
        replay_window_samples=100,
    )
    even_starts = [
        int(row["seed"]["sample_start"])
        for row in bins
        if row["raw_disjoint"] and row["seed"] is not None
    ]
    assert even_starts == [90, 290, 400]
    assert all(
        right - left >= 100 for left, right in zip(even_starts, even_starts[1:], strict=False)
    )


def test_tuning_parser_uses_one_exact_stream_tag_and_rejects_ambiguity() -> None:
    tool = _tool()
    manifest = {
        "tags": [
            "RANDOM_TUNING",
            "tuning:stream-0:ch4:lower",
            "tuning:stream-1:ch3:upper",
        ]
    }
    assert tool._tuning_from_manifest(manifest, "stream-1") == (
        3,
        tool.StarlinkEdge.UPPER,
    )
    manifest["tags"].append("tuning:stream-1:ch2:lower")
    with pytest.raises(ValueError, match="one tuning tag"):
        tool._tuning_from_manifest(manifest, "stream-1")


def test_continuity_validation_fails_closed_on_a_gap() -> None:
    tool = _tool()
    continuity = {
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
        "device_span_sample_count": 8,
        "observed_sample_count": 8,
        "segment_count": 1,
    }
    stream = {"captured_sample_count": 8, "continuity": continuity}
    assert tool._validate_continuity(stream) == continuity
    stream["continuity"]["gap_count"] = 1
    with pytest.raises(ValueError, match="gap-free"):
        tool._validate_continuity(stream)


def _chunk(
    root: Path,
    *,
    index: int,
    sample_start: int,
    values: np.ndarray,
) -> dict[str, object]:
    payload = np.asarray(values, dtype="<i2").tobytes()
    compressed = zstd.ZstdCompressor(level=1).compress(payload)
    relative = Path("radio-test") / f"iq-{index:06d}.ci16.zst"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(compressed)
    return {
        "chunk_index": index,
        "sample_start": sample_start,
        "sample_count": len(values),
        "compressed_bytes": len(compressed),
        "compressed_sha256": f"sha256:{hashlib.sha256(compressed).hexdigest()}",
        "uncompressed_bytes": len(payload),
        "uncompressed_sha256": f"sha256:{hashlib.sha256(payload).hexdigest()}",
        "relative_path": str(relative),
        "sample_format": "ci16_le",
        "sample_layout": "sample_receiver_iq",
        "segment_index": 0,
    }


def test_v2_reader_verifies_chunks_and_reads_one_receiver_across_boundary(
    tmp_path: Path,
) -> None:
    tool = _tool()
    first = np.arange(16, dtype=np.int16).reshape(4, 2, 2)
    second = np.arange(100, 116, dtype=np.int16).reshape(4, 2, 2)
    chunks = [
        _chunk(tmp_path, index=0, sample_start=0, values=first),
        _chunk(tmp_path, index=1, sample_start=4, values=second),
    ]
    stream = {
        "captured_sample_count": 8,
        "applied_settings": {"receiver_ids": [0, 1]},
        "chunks": chunks,
    }
    reader = tool.VerifiedCi16Reader(tmp_path, stream)
    observed = reader.read_complex(2, 4, 1)
    selected = np.concatenate((first[2:, 1, :], second[:2, 1, :]))
    expected = (selected[:, 0].astype(float) + 1j * selected[:, 1].astype(float)) / 32_768
    np.testing.assert_array_equal(observed, expected)

    corrupted = copy.deepcopy(stream)
    corrupted["chunks"][0]["compressed_sha256"] = f"sha256:{'0' * 64}"
    with pytest.raises(ValueError, match="compressed chunk digest"):
        tool.VerifiedCi16Reader(tmp_path, corrupted).read_complex(0, 1, 1)


def test_npz_keeps_d3_fields_and_explicit_bin_lane(tmp_path: Path) -> None:
    tool = _tool()
    frame = SimpleNamespace(
        frame_index=7,
        frame_start_sample=12,
        time_s=0.002,
        measurement_supported=True,
        exact_coherence=0.8,
        control_coherence=0.1,
        coherence_margin=0.7,
        absolute_cfo_measurement_hz=12_345.0,
        frequency_sigma_hz=0.5,
        frequency_innovation_hz=10.0,
        tracked_absolute_cfo_hz=12_340.0,
        tracked_doppler_rate_hz_s=-3_000.0,
        doppler_rate_sigma_hz_s=100.0,
        phase_innovation_modulo_pi_rad=0.2,
        phase_sigma_rad=0.03,
        phase_update_applied=True,
        frequency_update_applied=True,
        timing_update_applied=False,
        reacquired=False,
    )
    result = SimpleNamespace(frames=(frame,))
    bin_row = {
        "bin_index": 4,
        "raw_disjoint": True,
        "seed": {
            "sample_start": 400,
            "center_time_s": 0.41,
            "glrt_margin": 0.4,
        },
    }
    arrays = tool.empty_frame_arrays()
    tool.append_exact_frames(
        arrays,
        bin_row=bin_row,
        result=result,
        sample_rate_hz=1_000,
    )
    output = tmp_path / "rows.npz"
    tool._atomic_npz(output, arrays)
    with np.load(output, allow_pickle=False) as saved:
        assert set(saved.files) == set(tool.FRAME_KEYS)
        assert saved["window_index"].tolist() == [4]
        assert saved["bin_index"].tolist() == [4]
        assert saved["window_raw_disjoint"].tolist() == [True]
        assert saved["seed_present"].tolist() == [True]
        assert saved["frame_start_sample"].tolist() == [412]
        assert saved["measurement_sigma_hz"].tolist() == [1.0]
        assert saved["window_index"].dtype == np.dtype("int64")
        assert saved["measurement_supported"].dtype == np.dtype("bool")


def test_missing_window_rows_remain_explicit_in_both_summary_lanes() -> None:
    tool = _tool()
    bin_row = {
        "bin_index": 2,
        "bin_center_time_s": 0.25,
        "raw_disjoint": True,
        "missing_reason": "no seed",
        "seed": None,
    }
    row = tool._missing_window_row(bin_row)
    assert row == {
        "window_index": 2,
        "bin_index": 2,
        "center_time_s": 0.25,
        "sample_start": None,
        "raw_disjoint": True,
        "missing": True,
        "skip_reason": "no seed",
        "qualified": False,
        "supported": 0,
        "phase_updates": 0,
        "reacquisitions": 0,
        "phase_rms_rad": None,
    }


def test_replay_snapshot_covers_loaded_pnt_sources() -> None:
    tool = _tool()
    snapshot = tool.capture_replay_source_snapshot()
    names = {row.logical_name for row in snapshot.files}

    assert {
        "leo.analysis.qam.pilot_pnt_kalman",
        "leo.analysis.qam.pilot",
        "leo.analysis.starlink.acquisition",
        "leo.analysis.starlink.templates",
        "tools.extract_five_dwell_pilot_filter_benchmark",
    } <= names
    assert snapshot.file("leo.analysis.qam.pilot_pnt_kalman").sha256
    tool.verify_replay_source_snapshot(snapshot)


def test_mid_run_source_tamper_blocks_summary_commit(tmp_path: Path) -> None:
    tool = _tool()
    source = tmp_path / "pilot_pnt_kalman.py"
    source.write_text("version = 1\n", encoding="utf-8")
    snapshot = tool.capture_replay_source_snapshot((("leo.analysis.qam.pilot_pnt_kalman", source),))
    tool.verify_replay_source_snapshot(snapshot)
    summary = {
        "replay_source_inventory_sha256": snapshot.inventory_sha256,
        "replay_source_snapshot": snapshot.document(),
    }

    source.write_text("version = 2\n", encoding="utf-8")
    destination = tmp_path / "summary.json"
    with pytest.raises(RuntimeError, match="replay source mutation detected"):
        tool._commit_summary(destination, summary, snapshot)

    assert not destination.exists()
