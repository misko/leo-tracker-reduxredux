#!/usr/bin/env python3
"""Materialize the frozen bounded new-development saved-IQ blocks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from collections import Counter
from pathlib import Path

import numpy as np
import zstandard

HERE = Path(__file__).resolve().parent
BLOCK_VISITS = 64
DWELL_MS = 120


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return "sha256:" + result.hexdigest()


class Deadline:
    def __init__(self, seconds: int) -> None:
        if type(seconds) is not int or not 1 <= seconds <= 180:
            raise ValueError("deadline must be an integer from 1 through 180 seconds")
        self.end = time.monotonic() + seconds

    def read(self, path: Path) -> bytes:
        remaining = self.end - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("new-development extraction exceeded its deadline")
        return subprocess.run(
            ["sudo", "-n", "cat", str(path)],
            check=True,
            capture_output=True,
            timeout=min(30.0, remaining),
        ).stdout


def save_npy(path: Path, values: np.ndarray) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".npy.tmp")
    with temporary.open("wb") as stream:
        np.save(stream, values, allow_pickle=False)
    expected = digest_file(temporary)
    if path.exists():
        if digest_file(path) != expected:
            temporary.unlink()
            raise ValueError(f"existing IQ differs: {path}")
        temporary.unlink()
    else:
        os.replace(temporary, path)
    return {
        "path": path.relative_to(HERE).as_posix(),
        "dtype": values.dtype.str,
        "shape": list(values.shape),
        "sha256": expected,
        "bytes": path.stat().st_size,
    }


def extract(plan: dict, deadline: Deadline) -> list[dict]:
    cases = []
    total_bytes = 0
    maximum = plan["limits"]["materialized_bytes_max"]
    for block in plan["blocks"]:
        summary_path = Path(block["source_summary_path"])
        if digest_bytes(deadline.read(summary_path)) != block["source_summary_sha256"]:
            raise ValueError(f"source summary changed: {block['session_id']}")
        manifest_path = Path(block["recording_manifest_path"])
        manifest_bytes = deadline.read(manifest_path)
        if digest_bytes(manifest_bytes) != block["recording_manifest_file_sha256"]:
            raise ValueError(f"recording manifest changed: {block['session_id']}")
        wrapped = json.loads(manifest_bytes)
        if wrapped.get("sha256") != block["recording_manifest_content_sha256"]:
            raise ValueError(f"recording manifest content changed: {block['session_id']}")
        manifest = wrapped["manifest"]
        if (
            manifest["session_id"] != block["session_id"]
            or manifest["sample_format"] != "ci16_le"
            or manifest["sample_layout"] != "sample_receiver_iq"
            or manifest["receipt"]["terminal"]["state"] != "completed"
            or manifest["receipt"]["terminal"]["reason"] != "complete"
            or manifest["receipt"]["plan"]["geometry"]["sample_rate_hz"] != block["rate_hz"]
        ):
            raise ValueError(f"source identity or completion changed: {block['session_id']}")
        chunks = {item["first_visit_index"]: item for item in manifest["chunks"]}
        events = {item["visit_index"]: item for item in manifest["receipt"]["events"]}
        indices = range(block["first_visit_index"], block["first_visit_index"] + BLOCK_VISITS)
        selected = [events[index] for index in indices]
        channel_counts = Counter(event["target"]["channel"] for event in selected)
        if (
            block["visit_count"] != BLOCK_VISITS
            or dict(sorted(channel_counts.items()))
            != {int(key): value for key, value in block["channel_counts"].items()}
            or {event["target"]["edge"] for event in selected} != {block["edge"]}
            or any(channel_counts[channel] < 8 for channel in (1, 2, 3, 4))
        ):
            raise ValueError(f"frozen block geometry changed: {block['block_id']}")
        for offset, event in enumerate(selected):
            visit_index = event["visit_index"]
            chunk = chunks[visit_index]
            sample_count = block["rate_hz"] * DWELL_MS // 1000
            if (
                chunk["first_visit_index"] != visit_index
                or chunk["visit_count"] != 1
                or chunk["sample_count"] != sample_count
                or event["valid_end_counter_exclusive"] - event["valid_start_counter"]
                != sample_count
            ):
                raise ValueError(f"visit geometry changed: {block['block_id']}:{visit_index}")
            compressed_path = manifest_path.parent / chunk["relative_path"]
            compressed = deadline.read(compressed_path)
            if (
                len(compressed) != chunk["compressed_bytes"]
                or digest_bytes(compressed) != chunk["compressed_sha256"]
            ):
                raise ValueError(f"compressed source changed: {compressed_path}")
            raw = zstandard.ZstdDecompressor().decompress(
                compressed, max_output_size=chunk["uncompressed_bytes"]
            )
            if (
                len(raw) != chunk["uncompressed_bytes"]
                or digest_bytes(raw) != chunk["uncompressed_sha256"]
            ):
                raise ValueError(f"uncompressed source changed: {compressed_path}")
            iq = np.frombuffer(raw, dtype="<i2").reshape(sample_count, 2, 2)
            case_id = f"newdev-r{block['rate_hz']}-{block['session_id']}-v{visit_index:06d}"
            raw_npy = save_npy(HERE / "iq" / "dev" / f"{case_id}.npy", iq)
            total_bytes += raw_npy["bytes"]
            if total_bytes > maximum:
                raise ValueError("materialized IQ exceeds the frozen 512 MB limit")
            cases.append(
                {
                    "case_id": case_id,
                    "origin": "real_ds5_new",
                    "split": "dev",
                    "cohort": "newdevelopment",
                    "evaluation_role": "newdevelopment",
                    "is_holdout": False,
                    "block_id": block["block_id"],
                    "block_offset": offset,
                    "rate_hz": block["rate_hz"],
                    "dwell_ms": DWELL_MS,
                    "edge": event["target"]["edge"],
                    "channel": event["target"]["channel"],
                    "session_id": block["session_id"],
                    "visit_index": visit_index,
                    "source_start_counter": event["valid_start_counter"],
                    "source_end_counter_exclusive": event["valid_end_counter_exclusive"],
                    "truth_status": "unknown",
                    "raw_npy": raw_npy,
                    "source": {
                        "source_summary_sha256": block["source_summary_sha256"],
                        "recording_manifest_file_sha256": block["recording_manifest_file_sha256"],
                        "recording_manifest_content_sha256": block[
                            "recording_manifest_content_sha256"
                        ],
                        "relative_path": chunk["relative_path"],
                        "compressed_sha256": chunk["compressed_sha256"],
                        "uncompressed_sha256": chunk["uncompressed_sha256"],
                        "sample_start": chunk["sample_start"],
                        "sample_count": chunk["sample_count"],
                    },
                }
            )
    return cases


def build_payload(cases: list[dict], plan: dict, elapsed_seconds: float) -> dict:
    return {
        "schema": "org.leo.research.ds5-cached-tracking-cases.v1",
        "dataset": "DS5 new-development causal cached-tracking sequences",
        "selection_plan_sha256": digest_file(HERE / "selection_plan.json"),
        "builder_sha256": digest_file(Path(__file__)),
        "frozen_as_of_utc": plan["frozen_as_of_utc"],
        "evaluation_role": "newdevelopment",
        "is_holdout": False,
        "array_contract": {
            "loader": "numpy.load(dataset_directory / raw_npy.path, allow_pickle=False)",
            "dtype": "<i2",
            "axes": ["sample", "receiver", "component"],
            "receiver_axis": ["RX0", "RX1"],
            "component_axis": ["I", "Q"],
            "shape": ["rate_hz * dwell_ms // 1000", 2, 2],
        },
        "truth_contract": {
            "real_cases": (
                "unknown: baseline positives are reference-relative evidence; misses are not "
                "negatives"
            ),
            "detector_outcomes_included": False,
            "holdout_outcomes_included": False,
            "source_summary_outcomes_ignored_for_selection": True,
        },
        "sequence_contract": {
            "block_visits": BLOCK_VISITS,
            "block_order": "strictly increasing block_offset, visit_index, and source counter",
            "state_scope": ["session_id", "receiver", "channel", "edge", "rate_hz"],
            "state_reset": "before block_offset 0 of every block",
            "both_receivers_grouped": True,
            "selection_independent_of_detector_outcomes": True,
        },
        "stress_protocol": {
            "variants_are_independent": True,
            "raw_iq_is_never_modified": True,
            "primary": "process every visit causally without injected disruption",
            "forced_state_drop": {
                "before_block_offsets": [16, 32, 48],
                "action": "clear every cache in the block before processing this visit",
            },
            "processing_outage": {
                "block_offset_ranges_end_exclusive": [[24, 28]],
                "action": (
                    "mark visits unprocessed and forbid detector output or state update; resume "
                    "at the next retained visit"
                ),
            },
            "wrong_cache": {
                "block_offset_ranges_end_exclusive": [[40, 48]],
                "channel_remap": {"1": 4, "4": 1, "2": 3, "3": 2},
                "action": (
                    "lookup only the remapped channel cache for the same receiver/edge/rate; "
                    "the innovation gate must reject inconsistency and invoke blind fallback"
                ),
            },
            "primary_max_state_age_ms": 2000,
            "short_age_stress": {
                "max_state_age_ms": 500,
                "scope": "independent sensitivity scenario, not the primary state policy",
            },
        },
        "counts": {
            "real_cases": len(cases),
            "by_split": {"dev": len(cases)},
            "materialized_npy_bytes": sum(case["raw_npy"]["bytes"] for case in cases),
        },
        "coverage_audit": {
            "visits": len(cases),
            "sessions": sorted({case["session_id"] for case in cases}),
            "rates_hz": sorted({case["rate_hz"] for case in cases}),
            "edges": sorted({case["edge"] for case in cases}),
            "channels": {
                str(channel): sum(case["channel"] == channel for case in cases)
                for channel in (1, 2, 3, 4)
            },
            "receivers": ["RX0", "RX1"],
        },
        "build_elapsed_seconds": elapsed_seconds,
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deadline-seconds", type=int, default=180)
    args = parser.parse_args()
    output = HERE / "cases.json"
    if output.exists():
        raise FileExistsError(output)
    plan = json.loads((HERE / "selection_plan.json").read_text())
    started = time.monotonic()
    cases = extract(plan, Deadline(args.deadline_seconds))
    if len(cases) != 128 or len({case["case_id"] for case in cases}) != 128:
        raise ValueError("new-development case inventory differs")
    payload = build_payload(cases, plan, time.monotonic() - started)
    with output.open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
