from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return "sha256:" + result.hexdigest()


def manifest() -> dict:
    return json.loads((HERE / "cases.json").read_text())


def test_manifest_role_inventory_and_frozen_sources() -> None:
    payload = manifest()
    plan = json.loads((HERE / "selection_plan.json").read_text())
    cases = payload["cases"]
    assert payload["evaluation_role"] == "newdevelopment"
    assert payload["is_holdout"] is False
    assert payload["frozen_as_of_utc"] == "2026-09-27T04:34:59Z"
    assert payload["selection_plan_sha256"] == digest(HERE / "selection_plan.json")
    assert payload["builder_sha256"] == digest(HERE / "build_dataset.py")
    assert payload["counts"]["by_split"] == {"dev": 128}
    assert payload["counts"]["materialized_npy_bytes"] <= 512_000_000
    assert len(cases) == len({case["case_id"] for case in cases}) == 128
    assert {case["session_id"] for case in cases} == {
        block["session_id"] for block in plan["blocks"]
    }
    assert all(
        case["split"] == "dev"
        and case["cohort"] == "newdevelopment"
        and case["evaluation_role"] == "newdevelopment"
        and case["is_holdout"] is False
        and case["truth_status"] == "unknown"
        for case in cases
    )
    assert payload["truth_contract"]["detector_outcomes_included"] is False
    assert payload["truth_contract"]["holdout_outcomes_included"] is False


def test_local_iq_hashes_geometry_and_source_alignment() -> None:
    for case in manifest()["cases"]:
        path = HERE / case["raw_npy"]["path"]
        assert path.is_relative_to(HERE / "iq" / "dev")
        assert digest(path) == case["raw_npy"]["sha256"]
        values = np.load(path, allow_pickle=False, mmap_mode="r")
        sample_count = case["rate_hz"] * 120 // 1000
        assert values.dtype == np.dtype("<i2")
        assert values.shape == (sample_count, 2, 2)
        assert hashlib.sha256(values).hexdigest() == case["source"][
            "uncompressed_sha256"
        ].removeprefix("sha256:")
        assert case["source_end_counter_exclusive"] - case["source_start_counter"] == (sample_count)
        assert case["source"]["sample_count"] == sample_count


def test_blocks_are_contiguous_causal_and_cover_every_channel() -> None:
    cases = manifest()["cases"]
    for block_id in {case["block_id"] for case in cases}:
        block = sorted(
            (case for case in cases if case["block_id"] == block_id),
            key=lambda case: case["block_offset"],
        )
        assert len(block) == 64
        assert [case["block_offset"] for case in block] == list(range(64))
        assert [case["visit_index"] for case in block] == list(range(1077, 1141))
        assert all(
            left["source_start_counter"] < right["source_start_counter"]
            for left, right in zip(block, block[1:], strict=False)
        )
        counts = Counter(case["channel"] for case in block)
        assert all(counts[channel] >= 8 for channel in (1, 2, 3, 4))
        assert len({case["edge"] for case in block}) == 1
        assert len({case["rate_hz"] for case in block}) == 1


def test_no_detector_results_or_labels_are_persisted() -> None:
    forbidden = {"outcome", "positive", "reference", "detected", "power_dbfs"}
    for case in manifest()["cases"]:
        assert not forbidden.intersection(case)
        assert not forbidden.intersection(case["source"])
