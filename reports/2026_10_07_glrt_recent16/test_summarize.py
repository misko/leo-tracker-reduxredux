"""Checks for matched denominators, scan clustering, and evidence-only summaries."""

import copy
import gzip
import json

import numpy as np
import pytest
from summarize import (
    COMMON_REFERENCES,
    PRIMARY_METHODS,
    add_descriptive_strata,
    build_stream_summary,
    build_summary,
    iter_cases,
)


def case(identifier, case_id, difference=0.1):
    baseline = {"candidate_id": "a", "total_cfo_hz": 57000}
    methods = {}
    for method in PRIMARY_METHODS:
        delta = 0 if method == "current_coherent_margin" else difference
        base = {"exact_score": 0.3, "control_score": 0.1, "margin": 0.2}
        winner = {"exact_score": 0.3 + delta, "control_score": 0.1, "margin": 0.2 + delta}
        methods[method] = {
            "winner": (dict(baseline) if delta == 0
                       else {"candidate_id": "b", "total_cfo_hz": 58500}),
            "common_confirmation": {
                reference: {"winner": dict(winner), "baseline": dict(base),
                            "margin_difference": delta}
                for reference in COMMON_REFERENCES
            },
        }
    return {"scan_id": identifier, "case_id": case_id, "receiver": 0,
            "status": "complete", "baseline_winner": baseline, "methods": methods}


def test_equal_scan_weighting_is_not_case_weighting():
    cases = [case("a", f"a{i}", 0.1) for i in range(10)] + [case("b", "b0", -0.1)]
    summary, _ = build_summary([{"scan_id": "a"}, {"scan_id": "b"}], cases, replicates=100)
    value = summary["aggregate"]["segment8"]["common_confirmation"]["gaussian"]
    assert value["equal_scan_mean_margin_difference"] == pytest.approx(0)
    assert value["case_weighted_mean_margin_difference"] == pytest.approx(0.9 / 11)
    assert value["positive_scan_mean_differences"] == value["negative_scan_mean_differences"] == 1


def test_primary_methods_share_complete_case_mask_and_missing_scan_is_retained():
    complete = case("a", "a0")
    incomplete = case("a", "a1")
    del incomplete["methods"]["segment8"]["common_confirmation"]["gaussian"]
    failure = {"scan_id": "b", "case_id": "b0", "status": "raw_unavailable", "reason": "missing IQ"}
    summary, _ = build_summary([{"scan_id": "a"}, {"scan_id": "b"}],
                              [complete, incomplete, failure], replicates=100)
    assert summary["coverage"]["primary_complete_cases"] == 1
    assert summary["coverage"]["primary_excluded_cases"] == 2
    assert summary["coverage"]["scans_without_primary_pairs"] == ["b"]
    for method in PRIMARY_METHODS:
        assert summary["per_scan"][0]["methods"][method]["n_analyzed_pairs"] == 1
        value = summary["aggregate"][method]["common_confirmation"]["gaussian"]
        assert value["scans_with_pairs"] == 1
    assert summary["per_scan"][1]["failures"][0]["reason"] == "missing IQ"


def test_bootstrap_uses_scans_is_deterministic_and_current_delta_is_zero():
    inventory = [{"scan_id": identifier} for identifier in ("a", "b", "c")]
    cases = [case("a", "a0", 0.1), case("b", "b0", -0.2), case("c", "c0", 0.3)]
    left, _ = build_summary(inventory, cases, replicates=200, seed=918)
    right, _ = build_summary(inventory, cases, replicates=200, seed=918)
    assert left == right
    value = left["aggregate"]["current_coherent_margin"]["common_confirmation"]["gaussian"]
    np.testing.assert_array_equal(value["scan_bootstrap_95"], [0, 0])
    assert value["zero_scan_mean_differences"] == 3


def test_cfo_shift_is_absolute_physical_frequency_and_not_wrapped():
    observation = case("a", "a0")
    observation["methods"]["segment8"]["winner"]["total_cfo_hz"] += 1 / 4.4e-6
    summary, rows = build_summary([{"scan_id": "a"}], [observation], replicates=100)
    shifts = summary["aggregate"]["segment8"]["candidate_metrics"]
    assert shifts["equal_scan_cfo_shift_within_1khz_rate"] == 0
    assert shifts["equal_scan_cfo_shift_within_5khz_rate"] == 0
    assert any(row["method"] == "segment8" and row["abs_cfo_shift_hz"] > 200000 for row in rows)


def test_inconsistent_common_margins_and_cohort_contamination_are_rejected():
    observation = case("a", "a0")
    corrupted = copy.deepcopy(observation)
    corrupted["methods"]["segment8"]["common_confirmation"]["gaussian"]["winner"]["margin"] = 999
    with pytest.raises(ValueError, match="Inconsistent"):
        build_summary([{"scan_id": "a"}], [corrupted], replicates=100)
    with pytest.raises(ValueError, match="outside frozen cohort"):
        build_summary([{"scan_id": "b"}], [observation], replicates=100)


def test_streaming_matches_small_reference_and_preserves_group_coverage():
    inventory = [{"scan_id": "a", "sample_rate_hz": 2500000, "edge": "lower"},
                 {"scan_id": "b", "sample_rate_hz": 10000000, "edge": "upper"},
                 {"scan_id": "c", "sample_rate_hz": 2500000, "edge": "lower"}]
    cases = [case("a", "a0", 0.1), case("b", "b0", -0.1),
             {"scan_id": "c", "case_id": "c0", "status": "raw_unavailable"}]
    expected, expected_rows = build_summary(inventory, cases, replicates=100)
    rows = []
    actual = build_stream_summary(inventory, iter(cases), row_sink=rows.append, replicates=100)
    assert actual == expected
    assert sorted(rows, key=str) == sorted(expected_rows, key=str)
    add_descriptive_strata(actual)
    low = actual["descriptive_strata"]["sample_rate_hz"]["2500000"]["coverage"]
    assert low["cohort_scans"] == 2
    assert low["scans_without_primary_pairs"] == ["c"]


def test_jsonl_gzip_reader_yields_explicit_failure_records(tmp_path):
    path = tmp_path / "results.jsonl.gz"
    records = [case("a", "a0"), {"scan_id": "a", "status": "raw_unavailable"}]
    with gzip.open(path, "wt") as stream:
        for record in records:
            stream.write(json.dumps(record) + "\n")
    assert list(iter_cases(path)) == records


def test_streaming_rejects_duplicate_receipts_and_different_common_baselines():
    observation = case("a", "a0")
    with pytest.raises(ValueError, match="unique"):
        build_stream_summary([{"scan_id": "a"}], iter([observation, observation]), replicates=100)
    changed = copy.deepcopy(observation)
    reference = changed["methods"]["segment8"]["common_confirmation"]["gaussian"]
    reference["baseline"]["exact_score"] += 0.03
    reference["baseline"]["margin"] += 0.03
    reference["margin_difference"] -= 0.03
    with pytest.raises(ValueError, match="baseline varies"):
        build_stream_summary([{"scan_id": "a"}], iter([changed]), replicates=100)


def test_directory_reader_streams_sorted_scan_files_without_concatenation(tmp_path):
    records = [case("a", "a0"), case("b", "b0")]
    for label, record in zip(("R02", "R01"), records, strict=True):
        directory = tmp_path / label
        directory.mkdir()
        with gzip.open(directory / "results.jsonl.gz", "wt") as stream:
            stream.write(json.dumps(record) + "\n")
    assert list(iter_cases(tmp_path)) == list(reversed(records))
