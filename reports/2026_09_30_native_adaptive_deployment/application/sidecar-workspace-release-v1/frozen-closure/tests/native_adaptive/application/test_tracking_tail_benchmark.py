#!/usr/bin/env python3
import json
import pathlib
import sys


if len(sys.argv) != 3:
    raise SystemExit("usage: test_tracking_tail_benchmark.py WORKER1.json WORKER2.json")

one = json.loads(pathlib.Path(sys.argv[1]).read_text())
two = json.loads(pathlib.Path(sys.argv[2]).read_text())

for expected_workers, result in ((1, one), (2, two)):
    assert result["schema"] == "leo-application-tracking-tail-prefix/v1"
    assert result["analysis_workers"] == expected_workers
    assert result["input_candidates"] == 11_747
    assert result["available_prefixes"] == 60
    assert result["seed_prefix_index_zero_based"] == 58
    assert result["warm_prefix_index_zero_based"] == 59
    assert result["seed_candidates"] < result["final_candidates"]
    assert result["bit_exact_prefixes"] == 2
    assert result["final_tracks"] == 64
    assert result["warm_cached_lanes"] == 8
    assert result["warm_reused_lanes"] + result["warm_extended_lanes"] == 8
    assert result["warm_bin_cells_computed"] > 0
    assert result["cold_starts"] == 1
    assert result["prefix_invalidations"] == 0
    assert result["config_invalidations"] == 0
    assert result["capacity_fallbacks"] == 0
    assert result["warm_resident_cache_bytes"] <= result["cache_budget_bytes"]
    assert result["maximum_rss_kib"] > 0

assert one["seed_result_sha256"] == two["seed_result_sha256"]
assert one["final_result_sha256"] == two["final_result_sha256"]
assert one["seed_cutoff_utc_ns"] == two["seed_cutoff_utc_ns"]
assert one["warm_cutoff_utc_ns"] == two["warm_cutoff_utc_ns"]
assert one["seed_candidates"] == two["seed_candidates"]
assert one["warm_resident_cache_bytes"] == two["warm_resident_cache_bytes"]
assert one["warm_bin_cells_computed"] == two["warm_bin_cells_computed"]
