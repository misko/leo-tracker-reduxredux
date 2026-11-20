import json

import pytest

from tools.pipeline_eval.qualification import batched_waveform as trial
from tools.pipeline_eval.qualification import batched_waveform_results as results


def test_weighted_partition_preserves_source_chunks_and_exclusions():
    chunks = [(i // 10, i % 10 * 64, (i % 10 + 1) * 64, i // 10 * 640) for i in range(80)]
    excluded = set(range(0, 5120, 7))
    workers = trial.partition(chunks, excluded)
    assert [cpu for cpu, _, _ in workers] == list(trial.CPUS)
    assert sorted(chunk for _, _, items in workers for chunk in items) == sorted(chunks)
    assert sum(valid for _, valid, _ in workers) == 5120 - len(excluded)
    fastest = min(n for cpu, n, _ in workers if cpu <= 7)
    slowest = max(n for cpu, n, _ in workers if cpu >= 8)
    assert fastest > slowest


def test_prefix_does_not_hide_a_gap_and_tails_keep_rf_visits():
    assert results.prefix_count({0, 2, 3, 4}, 5) == 1
    assert results.prefix_count(set(range(5)), 5) == 5
    rows = [
        dict(
            visit=v,
            channel=c,
            rf_ordinal=n,
            segment=0,
            sequence=v,
            cpu_ms=ms,
            wall_ms=ms * 2,
            status=status,
        )
        for v, c, n, ms, status in (
            (1, 1, 0, 400, "processed"),
            (2, 1, 1, 700, "processed"),
            (3, 2, 0, 200, "processed"),
            (4, 1, 2, 900, "invalid_capture"),
        )
    ]
    tails = results.ordinal_tails(rows)
    assert tails[1]["cpu_ms"][0]["rf_ordinal"] == 1
    assert tails[1]["wall_ms"][0]["visit"] == 2
    assert tails[2]["wall_ms"][0]["visit"] == 3


def test_partial_telemetry_requires_authenticated_chunk_close(tmp_path):
    cpu = 0
    rows = [dict(kind="visit", visit=v, status="processed", grid_calls=2) for v in (0, 1)]
    (tmp_path / "cpu-0.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    trace = []
    for ordinal in (0, 1, 2):
        coarse = dict(
            ordinal=ordinal, calls=2, cache_hits=1, cold_builds=1, filter_ffts=1, input_ffts=1
        )
        fine = dict(ordinal=ordinal, calls=16, fallbacks=0, frames=224, bins=71904)
        trace += [
            results.prepared_trial.TRACE + json.dumps(coarse) + "\n",
            trial.TRACE + json.dumps(fine) + "\n",
        ]
    (tmp_path / "cpu-0.log").write_text("".join(trace))
    lock = {"workers": [(cpu, 2, [])]}
    shard = {(0, 0): ({}, rows[:1])}
    grid, fine = results.trace(tmp_path, lock, shard, {"0": {"terminal": None}})
    assert [r["visit"] for r in grid] == [0]
    assert [r["calls"] for r in fine] == [16]
    with pytest.raises(ValueError, match="completed worker lost"):
        results.trace(tmp_path, lock, shard, {"0": {"terminal": {"successful": True}}})
