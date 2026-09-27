from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def result():
    return json.loads((HERE / "control_results.json").read_text())


def test_receipt_is_complete_stable_and_scientifically_rejected():
    value = result()
    assert value["status"] == "complete"
    assert value["source_lock_stable"]
    assert value["complete_gate_passed"]
    assert not value["scientific_gate_passed"]
    assert len(value["base_rows"]) == 32
    assert len(value["sequence_rows"]) == 10
    assert not value["real_replay_authorized"]
    assert value["real_replay_not_in_scope"]
    assert not value["holdout_opened"]


def test_all_84_cached_receiver_rows_and_20_all_blind_sequence_rows_are_present():
    value = result()
    cached = sum(len(row["decisions"]) for row in value["base_rows"])
    cached += sum(len(row["cached_decisions"]) for row in value["sequence_rows"])
    blind = sum(len(row["all_blind_decisions"]) for row in value["sequence_rows"])
    assert cached == 84
    assert blind == 20
    assert all(row["input_immutable"] for row in value["base_rows"])
    assert all(row["input_immutable"] for row in value["sequence_rows"])


def test_repeated_pilots_guide_and_wrong_track_fails_open():
    value = result()
    repeated = [row for row in value["sequence_rows"]
                if row["sequence"] in ("pilot-dropout", "changed-pilot")
                and row["step"] == 1]
    assert len(repeated) == 2
    assert all(decision["route"] == "guided" and decision["active"]
               for row in repeated for decision in row["cached_decisions"])
    changed = next(row for row in value["sequence_rows"]
                   if row["sequence"] == "changed-pilot" and row["step"] == 2)
    assert all(decision["route"] == "discovery_guided_failure"
               and decision["active"] for decision in changed["cached_decisions"])
    assert changed["passed"]


def test_six_base_tone_receivers_and_one_sequence_tone_receiver_fail():
    value = result()
    base_failures = [(row["case_id"], gate["receiver"])
                     for row in value["base_rows"] for gate in row["gates"]
                     if not gate["passed"]]
    sequence_failures = [(row["sequence"], row["step"], gate["receiver"])
                         for row in value["sequence_rows"]
                         for gate in row["cached_truth_gates"] if not gate["passed"]]
    assert len(base_failures) == 6
    assert all("tone" in case_id for case_id, _receiver in base_failures)
    assert sequence_failures == [("pilot-dropout", 3, 1)]


def test_timing_is_three_deterministic_repetitions_per_method():
    value = result()
    assert len(value["timing_measurements"]) == 6
    for method in ("cached", "all_blind"):
        rows = [item for item in value["timing_measurements"] if item["method"] == method]
        assert [item["repeat"] for item in rows] == [0, 1, 2]
        assert len({item["output_sha256"] for item in rows}) == 1
        assert value["timing_summary"][method]["median_process_cpu_ms"] > 0


def test_source_lock_remains_exact():
    value = result()
    for name, expected in value["source_lock"]["files"].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == expected

