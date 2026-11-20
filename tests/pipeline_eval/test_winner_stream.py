import hashlib
import io
import json

import pytest

from tools.pipeline_eval.qualification import winner_stream_results as results
from tools.pipeline_eval.variants import winner_stream as stream


def peak(frequency, margin, rank, *, gate=True, epoch=0):
    return dict(
        fractional_tracking_cfo_hz=frequency,
        fractional_margin=margin,
        candidate_rank=rank,
        passed_fractional_margin_gate=gate,
        integer_epoch_sample=epoch,
        fractional_epoch_offset_samples=0,
    )


def probe(candidates, start=100, *, receiver=0, visit=7):
    return dict(
        receiver_id=receiver,
        actual_rf_hz=11.5e9,
        channel=1,
        valid_start_counter=start,
        visit_index=visit,
        probe_index=0,
        candidates=candidates,
    )


def native(probes):
    clk = dict(monotonic_ns=100, realtime_ns=1000)
    return dict(
        source=dict(sample_rate_hz=100, probe_ms=20, session_id="run", probes=probes),
        clock_anchor=dict(before=clk, after=clk, sample_counter=100),
        delivery_clocks=[clk],
        last_sample_counter=300,
        schema_version=2,
        provenance={"excluded_windows": [{"visit": 8, "reason": "fixture"}]},
    )


def test_probe_ties_follow_gate_rank_then_source_order_and_keep_duplicate_count():
    record = probe(
        [
            peak(10.0, 5.0, 2),
            peak(30.0, 5.0, 1),
            peak(20.0, 5.0, 1),
            peak(50.0, 9.0, 0, gate=False),
            peak(30.5, 3.0, 0, gate=1),
        ]
    )
    row = stream.project(record)
    assert row[6:] == (5, 4, (30.0, 5.0))
    record["candidates"][3]["integer_epoch_sample"] = float("nan")
    with pytest.raises(ValueError, match="nonfinite"):
        stream.project(record)


def test_private_stream_authenticates_and_preserves_clock_gap_and_negative_support(tmp_path):
    document = native(
        [
            probe([peak(5, 0.3, 0)], start=100),
            probe([], start=102, visit=9),
            probe([peak(-3, 0.1, 0)], start=200, visit=12),
        ]
    )
    raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    origin = hashlib.sha256(raw).hexdigest()
    output = io.BytesIO()
    digest, size = stream.convert(io.BytesIO(raw), output, origin)
    path = tmp_path / "capture.stream"
    path.write_bytes(output.getvalue())
    assert size == path.stat().st_size
    value = stream.read(path, digest, origin)
    assert [item["time_s"] for item in value.rows] == [0.01, 1.01]
    assert value.counts == dict(probes=3, winners=2, deliveries=1, excluded=1)
    assert value.metadata["empty_factors"] == 1
    assert value.metadata["distinct_candidates"] == 2
    assert value.metadata["excluded_windows"] == document["provenance"]["excluded_windows"]
    with pytest.raises(ValueError, match="originating"):
        stream.read(path, digest, "0" * 64)
    with pytest.raises(ValueError, match="SHA-256"):
        stream.read(path, "0" * 64, origin)
    path.write_bytes(output.getvalue()[:-3])
    with pytest.raises(ValueError, match="truncated"):
        stream.read(path, digest, origin)


def test_invalid_zero_winner_probe_and_clock_step_still_rejected():
    rows = [stream.project(probe([peak(5, 0.3, 0)])), stream.project(probe([], start=101))]
    document = native([])
    with pytest.raises(ValueError, match="overlapping"):
        stream.observations(rows, document)
    document["delivery_clocks"][0] = dict(monotonic_ns=0, realtime_ns=3_000_000_000)
    with pytest.raises(ValueError, match="clock step"):
        stream.observations(rows[:1], document)


def test_incremental_live_writer_matches_readback_without_original_candidate_objects(tmp_path):
    path = tmp_path / "private.winners"
    document = native([probe([peak(5, 0.3, 0)]), probe([], start=106)])
    probes = document["source"].pop("probes")
    with path.open("xb") as handle:
        writer = stream.Writer(handle)
        for item in probes:
            writer.probe(item)
        assert writer.count == 2
        digest, _ = writer.finish(document, "a" * 64)
        with pytest.raises(ValueError, match="open record budget"):
            writer.probe(probes[0])
    result = stream.read(path, digest, "a" * 64)
    assert result.rows[0]["measured_cfo_hz"] == 5


def test_published_wide_measurements_rescore_without_native_archives(tmp_path):
    source = results.trial.REPORT
    score = results.score(source, tmp_path)
    assert set(score) == {"DS26-0036", "DS29-0082", "DS29-0247"}
    assert all(row == dict(graph_exact=True, solver_exact=True) for row in score.values())
    for name in ("scores.csv", "resources.csv", "parity.json"):
        assert (tmp_path / name).read_bytes() == (source / name).read_bytes()
