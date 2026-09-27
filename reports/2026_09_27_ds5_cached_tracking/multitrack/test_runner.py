from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(HERE), str(ROOT)]

spec = importlib.util.spec_from_file_location("multitrack_experiment", HERE / "run_experiment.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
summarize = module.summarize


def test_design_is_frozen_to_three_tracks_and_global_discovery() -> None:
    design = json.loads((HERE / "design.json").read_text())
    assert design["stage"] == "frozen_before_detector_outcomes"
    assert design["strategy"]["maximum_tracks_per_key"] == 3
    assert design["strategy"]["global_discovery_interval"] == 32
    assert "switching tracks cannot avoid discovery" in design["strategy"]["global_counter"]
    assert design["strategy"]["scientific_identity_timing_seconds"] == 2e-6
    assert design["strategy"]["cfo_identity_hz"] == 8000


def test_summary_charges_every_check_and_fallback() -> None:
    def row(*, checks, blind, reference_positive, matched, candidate_positive):
        return {
            "reason": "cache_hit" if not blind else "failed_bank",
            "reference_positive": reference_positive,
            "candidate_positive": candidate_positive,
            "matched_reference": matched,
            "cache_check_count": checks,
            "accepted_track_ids": [1, 2] if not blind and checks > 1 else ([1] if not blind else []),
            "used_blind": blind,
            "blind_confirmation_count": 3 if blind else 0,
            "bank_size_after": 3,
            "rate_hz": 2_500_000,
            "baseline_times": [{"cpu_ms": 3.0, "wall_ms": 4.0}] * 3,
            "candidate_times": [{"cpu_ms": 2.0, "wall_ms": 2.5}] * 3,
        }

    summary = summarize([
        row(checks=3, blind=False, reference_positive=True, matched=True,
            candidate_positive=True),
        row(checks=2, blind=True, reference_positive=True, matched=False,
            candidate_positive=False),
    ])["all_visits"]
    assert summary["cache_checks"] == 5
    assert summary["cache_attempt_visits"] == 2
    assert summary["cache_hits"] == 1
    assert summary["ambiguous_cache_hits"] == 1
    assert summary["blind_calls"] == 1
    assert summary["blind_confirmations"] == 3
    assert summary["lost_reference_positives"] == 1
    assert summary["cpu_speedup"] == 1.5


def test_frozen_result_records_full_coverage_rejection() -> None:
    import hashlib

    path = HERE / "results.json"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == (
        "e434f0e6c7ca3894ffde4ef40d2db7051433e42e4e159183656eab11b9f53dff"
    )
    result = json.loads(path.read_text())
    assert result["fresh_holdout_opened"] is False
    assert result["summary"]["all_visits"]["receiver_visits"] == 256
    assert result["summary"]["all_visits"]["matched_reference_positives"] == 118
    assert result["summary"]["all_visits"]["blind_calls"] == 198
    assert result["control_summary"]["decision_changes"] == 0
    assert result["gates"]["full_coverage"] is True
    assert result["gates"]["passed"] is False
