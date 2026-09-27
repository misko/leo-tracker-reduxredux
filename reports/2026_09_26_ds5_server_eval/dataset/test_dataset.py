from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RATES = {2_500_000, 5_000_000, 7_500_000, 10_000_000}
SPLITS = {"dev", "validation", "holdout"}


def load_cases() -> dict:
    return json.loads((HERE / "cases.json").read_text())


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_case_hashes_and_array_geometry() -> None:
    payload = load_cases()
    for case in payload["cases"]:
        path = HERE / case["raw_npy"]["path"]
        assert path.is_relative_to(HERE / "iq")
        assert digest(path) == case["raw_npy"]["sha256"]
        values = np.load(path, allow_pickle=False, mmap_mode="r")
        assert values.dtype.str == "<i2"
        assert list(values.shape) == case["raw_npy"]["shape"]
        assert values.shape == (case["rate_hz"] * case["dwell_ms"] // 1000, 2, 2)
        if case["origin"] == "real_ds5":
            assert (
                "sha256:" + hashlib.sha256(values).hexdigest()
                == case["source"]["uncompressed_sha256"]
            )


def test_real_split_is_session_disjoint_and_balanced() -> None:
    cases = [case for case in load_cases()["cases"] if case["origin"] == "real_ds5"]
    assert len(cases) == 96
    sessions = {
        split: {case["session_id"] for case in cases if case["split"] == split} for split in SPLITS
    }
    assert all(len(value) == 4 for value in sessions.values())
    assert not sessions["dev"] & sessions["validation"]
    assert not sessions["dev"] & sessions["holdout"]
    assert not sessions["validation"] & sessions["holdout"]
    assert not sessions["holdout"] & {
        "scan-fw-03f629ba67a8af0b",
        "scan-fw-3159ec54906a6800",
    }
    for split in SPLITS:
        selected = [case for case in cases if case["split"] == split]
        assert {case["rate_hz"] for case in selected} == RATES
        assert {case["edge"] for case in selected} == {"lower", "upper"}
        assert len(selected) == 32


def test_real_blocks_are_contiguous_and_source_aligned() -> None:
    cases = [case for case in load_cases()["cases"] if case["origin"] == "real_ds5"]
    sessions = {case["session_id"] for case in cases}
    for session_id in sessions:
        block = sorted(
            (case for case in cases if case["session_id"] == session_id),
            key=lambda case: case["visit_index"],
        )
        assert len(block) == 8
        assert [case["visit_index"] for case in block] == list(
            range(block[0]["visit_index"], block[0]["visit_index"] + 8)
        )
        assert {case["channel"] for case in block} == {1, 2, 3, 4}
        for case in block:
            samples = case["rate_hz"] * case["dwell_ms"] // 1000
            assert case["source_end_counter_exclusive"] - case["source_start_counter"] == samples
            assert case["source"]["sample_count"] == samples
            assert case["source"]["uncompressed_sha256"].startswith("sha256:")
            assert case["source"]["compressed_sha256"].startswith("sha256:")


def test_truth_and_outcome_boundaries_are_explicit() -> None:
    payload = load_cases()
    assert payload["truth_contract"]["detector_outcomes_included"] is False
    assert payload["truth_contract"]["holdout_outcomes_included"] is False
    real = [case for case in payload["cases"] if case["origin"] == "real_ds5"]
    controls = [case for case in payload["cases"] if case["origin"] == "synthetic_control"]
    assert all(case["truth_status"] == "unknown" and "truth" not in case for case in real)
    assert len(controls) == 24
    assert {case["truth"]["kind"] for case in controls} == {"pilot", "noise", "tone"}
    assert {case["edge"] for case in controls} == {"lower", "upper"}
    assert {case["rate_hz"] for case in controls} == RATES
    assert all(case["truth"]["expected_detector_decision"] is None for case in controls)
    assert all(case["source"]["seeds"] for case in controls)
    seeds = [seed for case in controls for seed in case["source"]["seeds"]]
    assert len(seeds) == len(set(seeds))


def test_coverage_audit_discloses_uncrossed_rate_edges() -> None:
    audit = load_cases()["coverage_audit"]
    assert "not fully crossed" in audit["limitation"]
    for split in SPLITS:
        row = audit["by_split"][split]
        assert row["rates_hz"] == sorted(RATES)
        assert row["edges"] == ["lower", "upper"]
        assert row["channels"] == [1, 2, 3, 4]
        assert row["receivers"] == ["RX0", "RX1"]
        assert len(row["observed_rate_edge_pairs"]) == 4
        assert len(row["missing_rate_edge_pairs"]) == 4
