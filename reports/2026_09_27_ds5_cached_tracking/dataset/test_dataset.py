from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SPLITS = ("dev", "holdout")


def manifest() -> dict:
    return json.loads((HERE / "cases.json").read_text())


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return "sha256:" + result.hexdigest()


def test_local_hashes_geometry_and_source_payload_alignment() -> None:
    for case in manifest()["cases"]:
        path = HERE / case["raw_npy"]["path"]
        assert path.is_relative_to(HERE / "iq")
        assert digest(path) == case["raw_npy"]["sha256"]
        values = np.load(path, allow_pickle=False, mmap_mode="r")
        assert values.dtype.str == "<i2"
        assert values.shape == (case["rate_hz"] * 120 // 1000, 2, 2)
        assert (
            "sha256:" + hashlib.sha256(values).hexdigest() == case["source"]["uncompressed_sha256"]
        )


def test_split_and_fresh_holdout_session_discipline() -> None:
    payload = manifest()
    cases = payload["cases"]
    assert payload["counts"]["by_split"] == {"dev": 128, "holdout": 128}
    assert len({case["case_id"] for case in cases}) == len(cases)
    assert len({case["raw_npy"]["path"] for case in cases}) == len(cases)
    assert len({(case["session_id"], case["visit_index"]) for case in cases}) == len(cases)
    assert len({case["source"]["uncompressed_sha256"] for case in cases}) == len(cases)
    sessions = {
        split: {case["session_id"] for case in cases if case["split"] == split} for split in SPLITS
    }
    assert len(sessions["dev"]) == 2
    assert len(sessions["holdout"]) == 2
    assert not sessions["dev"] & sessions["holdout"]
    forbidden = set(
        json.loads((HERE / "selection_plan.json").read_text())[
            "sessions_forbidden_in_fresh_holdout"
        ]
    )
    assert not sessions["holdout"] & forbidden


def test_blocks_are_contiguous_causal_and_channel_repetitive() -> None:
    cases = manifest()["cases"]
    for block_id in {case["block_id"] for case in cases}:
        block = sorted(
            (case for case in cases if case["block_id"] == block_id),
            key=lambda case: case["block_offset"],
        )
        assert len(block) == 64
        assert [case["block_offset"] for case in block] == list(range(64))
        assert [case["visit_index"] for case in block] == list(
            range(block[0]["visit_index"], block[0]["visit_index"] + 64)
        )
        assert all(
            left["source_start_counter"] < right["source_start_counter"]
            for left, right in zip(block[:-1], block[1:], strict=True)
        )
        counts = Counter(case["channel"] for case in block)
        assert all(counts[channel] >= 8 for channel in (1, 2, 3, 4))
        for case in block:
            expected = case["rate_hz"] * 120 // 1000
            assert case["source_end_counter_exclusive"] - case["source_start_counter"] == expected
            assert case["source"]["sample_count"] == expected


def test_outcome_boundary_and_stress_recipe_are_frozen() -> None:
    payload = manifest()
    assert payload["truth_contract"]["detector_outcomes_included"] is False
    assert payload["truth_contract"]["holdout_outcomes_included"] is False
    assert all(
        case["truth_status"] == "unknown" and "truth" not in case for case in payload["cases"]
    )
    stress = payload["stress_protocol"]
    assert stress["raw_iq_is_never_modified"] is True
    assert stress["variants_are_independent"] is True
    assert stress["forced_state_drop"]["before_block_offsets"] == [16, 32, 48]
    assert stress["processing_outage"]["block_offset_ranges_end_exclusive"] == [[24, 28]]
    assert stress["wrong_cache"]["block_offset_ranges_end_exclusive"] == [[40, 48]]
    assert stress["primary_max_state_age_ms"] == 2000
    assert stress["short_age_stress"]["max_state_age_ms"] == 500
