"""Frozen evidence checks for the full-response concurrency experiment."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def test_parallel_frozen_results():
    raw = (HERE / "results.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "ac0bcaa26e80125ea569143337c7a86a95c0a268acafdbcf0096795cf70de303"
    result = json.loads(raw)
    assert result["status"] == "complete"
    assert result["error"] is None
    assert len(result["rows"]) == 2
    for row in result["rows"]:
        assert row["exact_full_response"] and row["input_immutable"]
        assert len(row["measurements"]) == 9
        for mode in ("serial", "workers8", "workers22"):
            assert sum(item["mode"] == mode for item in row["measurements"]) == 3
        # Speedup is a wall result: the saved evidence does not claim CPU savings.
        assert row["summary"]["workers22"]["aggregate_cpu_ms"] > row["summary"]["serial"]["aggregate_cpu_ms"]


def test_parallel_sources_unchanged():
    lock = json.loads((HERE / "source_lock.json").read_text())
    for path, expected in lock.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected
