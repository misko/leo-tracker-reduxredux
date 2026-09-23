"""Check exact loader equality and measure complete first-TRAIN preparation."""

import json
import time
from pathlib import Path

import numpy as np
from benchmark import digest, load


def main():
    here = Path(__file__).resolve().parent
    single_path = here.parent / "2026_09_23_long_training_search/search.py"
    multi_path = here.parent / "2026_09_23_long_training_search_multi/search.py"
    single = load("loader_benchmark_single", single_path)
    multi = load("loader_benchmark_multi", multi_path)
    fast = load("loader_benchmark_fast", here / "loader.py")
    manifest_path = here.parent / "2026_09_23_long_inventory_complete/manifest.json"
    sid = json.loads(manifest_path.read_text())["partitions"]["train"]["session_ids"][0]
    directory = Path("/tmp/leo-long-training-cache-first16") / sid
    started = time.perf_counter()
    before = multi.load_session(single, directory, sid)
    before_s = time.perf_counter() - started
    started = time.perf_counter()
    after = fast.load_session(single, directory, sid)
    after_s = time.perf_counter() - started
    assert before.keys() == after.keys()
    for key in before:
        if key == "prepared":
            continue
        np.testing.assert_array_equal(before[key], after[key])
    for left, right in zip(before["prepared"], after["prepared"], strict=True):
        assert left.keys() == right.keys()
        for key in left:
            np.testing.assert_array_equal(left[key], right[key])
    result = {
        "session_id": sid,
        "tracks": len(after["prepared"]),
        "all_arrays_and_metadata_exactly_equal": True,
        "runtime_s": {
            "repeated_npz_reads": before_s,
            "materialized_once": after_s,
            "speed_ratio": before_s / after_s,
        },
        "bindings": {
            str(p): digest(p)
            for p in (
                Path(__file__),
                here / "loader.py",
                single_path,
                multi_path,
                manifest_path,
                directory / "cache_receipt.json",
                directory / "state_cache.npz",
            )
        },
    }
    (here / "loader_results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["runtime_s"]))


if __name__ == "__main__":
    main()
