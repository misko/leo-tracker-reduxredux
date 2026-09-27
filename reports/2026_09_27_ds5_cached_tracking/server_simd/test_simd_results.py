"""Frozen SIMD component results checks."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_component_result_is_source_locked_and_stopped_at_gate() -> None:
    result = json.loads((HERE / "component_results.json").read_text())
    assert result["fresh_holdout_opened"] is False
    assert result["component_gate_passed"] is False
    assert result["required_cpu_speedup_each_rate"] == 1.10
    assert set(result["results"]) == {"2500000", "5000000"}
    assert all(row["cpu_speedup"] < 1.10 for row in result["results"].values())
    assert result["input_sha256_before"] == result["input_sha256_after"]
    assert result["warmups_per_mode_receiver_rate"] == 1
    assert result["repetitions"] == 11
    for name, expected in result["source_sha256"].items():
        assert digest(HERE / name) == expected


def test_failed_gate_has_no_dataset_result() -> None:
    assert not (HERE / "dataset_results.json").exists()
