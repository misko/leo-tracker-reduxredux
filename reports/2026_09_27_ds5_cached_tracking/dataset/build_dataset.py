"""Build bounded, causal DS5 blocks for cached-tracking evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import time
from collections import Counter
from pathlib import Path

import numpy as np
import zstandard

HERE = Path(__file__).resolve().parent
RATES = (2_500_000, 5_000_000)
SPLITS = ("dev", "holdout")
DWELL_MS = 120
BLOCK_VISITS = 64
MAX_DATASET_BYTES = 1_200_000_000


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

    def remaining(self) -> float:
        remaining = self.end - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("dataset build exceeded its bounded deadline")
        return remaining

    def read_archive(self, path: Path) -> bytes:
        return subprocess.run(
            ["sudo", "-n", "cat", str(path)],
            check=True,
            capture_output=True,
            timeout=min(30.0, self.remaining()),
        ).stdout


def save_npy(path: Path, values: np.ndarray) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as stream:
        np.save(stream, values, allow_pickle=False)
    expected = digest_file(temporary)
    if path.exists():
        if digest_file(path) != expected:
            temporary.unlink()
            raise ValueError(f"existing generated file differs: {path}")
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


def load_inventory(source_bytes: bytes) -> dict[str, dict]:
    payload = json.loads(source_bytes)
    included = [case for case in payload["captures"] if case["admission_status"] == "included"]
    by_id = {case["session_id"]: case for case in included}
    if len(by_id) != 42:
        raise ValueError("unexpected frozen DS5 inventory")
    return by_id


def extract_cases(plan: dict, inventory: dict[str, dict], deadline: Deadline) -> list[dict]:
    cases = []
    total_bytes = 0
    for block in plan["blocks"]:
        source = inventory[block["session_id"]]
        manifest_path = Path(source["recording_manifest_path"])
        manifest_bytes = deadline.read_archive(manifest_path)
        if digest_bytes(manifest_bytes) != source["recording_manifest_file_sha256"]:
            raise ValueError(f"recording manifest hash mismatch: {block['session_id']}")
        manifest = json.loads(manifest_bytes)["manifest"]
        if (
            manifest["session_id"] != block["session_id"]
            or source["sample_rate_hz"] != block["rate_hz"]
            or manifest["sample_format"] != "ci16_le"
            or manifest["sample_layout"] != "sample_receiver_iq"
        ):
            raise ValueError(f"source identity mismatch: {block['session_id']}")
        chunks = {item["first_visit_index"]: item for item in manifest["chunks"]}
        events = {item["visit_index"]: item for item in manifest["receipt"]["events"]}
        indices = range(
            block["first_visit_index"],
            block["first_visit_index"] + block["visit_count"],
        )
        selected = [events[index] for index in indices]
        channels = Counter(event["target"]["channel"] for event in selected)
        if (
            block["visit_count"] != BLOCK_VISITS
            or {event["target"]["edge"] for event in selected} != {block["edge"]}
            or any(channels[channel] < 8 for channel in (1, 2, 3, 4))
        ):
            raise ValueError(f"selected block geometry changed: {block['block_id']}")
        for block_offset, event in enumerate(selected):
            visit_index = event["visit_index"]
            chunk = chunks[visit_index]
            sample_count = block["rate_hz"] * DWELL_MS // 1000
            if (
                chunk["visit_count"] != 1
                or chunk["sample_count"] != sample_count
                or event["valid_end_counter_exclusive"] - event["valid_start_counter"]
                != sample_count
            ):
                raise ValueError(f"visit/source mismatch: {block['block_id']}:{visit_index}")
            compressed_path = manifest_path.parent / chunk["relative_path"]
            compressed = deadline.read_archive(compressed_path)
            if (
                len(compressed) != chunk["compressed_bytes"]
                or digest_bytes(compressed) != chunk["compressed_sha256"]
            ):
                raise ValueError(f"compressed chunk mismatch: {compressed_path}")
            raw = zstandard.ZstdDecompressor().decompress(
                compressed,
                max_output_size=chunk["uncompressed_bytes"],
            )
            if (
                len(raw) != chunk["uncompressed_bytes"]
                or digest_bytes(raw) != chunk["uncompressed_sha256"]
            ):
                raise ValueError(f"uncompressed chunk mismatch: {compressed_path}")
            iq = np.frombuffer(raw, dtype="<i2").reshape(sample_count, 2, 2)
            case_id = (
                f"seq-{block['split']}-r{block['rate_hz']}-{block['session_id']}-v{visit_index:06d}"
            )
            raw_npy = save_npy(HERE / "iq" / block["split"] / f"{case_id}.npy", iq)
            total_bytes += raw_npy["bytes"]
            if total_bytes > MAX_DATASET_BYTES:
                raise ValueError("materialized IQ exceeds the frozen 1.2 GB hard cap")
            cases.append(
                {
                    "case_id": case_id,
                    "origin": "real_ds5",
                    "split": block["split"],
                    "cohort": block["cohort"],
                    "block_id": block["block_id"],
                    "block_offset": block_offset,
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
                        "recording_manifest_file_sha256": source["recording_manifest_file_sha256"],
                        "recording_manifest_content_sha256": source[
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


def validate_cases(cases: list[dict], plan: dict) -> None:
    if len(cases) != 256 or len({case["case_id"] for case in cases}) != 256:
        raise ValueError("unexpected case inventory")
    sessions = {
        split: {case["session_id"] for case in cases if case["split"] == split} for split in SPLITS
    }
    if sessions["dev"] & sessions["holdout"]:
        raise ValueError("session leakage across splits")
    if sessions["holdout"] & set(plan["sessions_forbidden_in_fresh_holdout"]):
        raise ValueError("previously exposed session leaked into fresh holdout")


def coverage(cases: list[dict]) -> dict:
    result = {}
    for split in SPLITS:
        selected = [case for case in cases if case["split"] == split]
        result[split] = {
            "visits": len(selected),
            "sessions": sorted({case["session_id"] for case in selected}),
            "rates_hz": sorted({case["rate_hz"] for case in selected}),
            "edges": sorted({case["edge"] for case in selected}),
            "channels": {
                str(channel): sum(case["channel"] == channel for case in selected)
                for channel in (1, 2, 3, 4)
            },
            "receivers": ["RX0", "RX1"],
        }
    return result


def write_manifest(cases: list[dict], plan: dict) -> None:
    payload = {
        "schema": "org.leo.research.ds5-cached-tracking-cases.v1",
        "dataset": "DS5 causal cached-tracking sequences",
        "source_dataset_manifest_sha256": plan["source_dataset_manifest_sha256"],
        "prior_suite_manifest_sha256": plan["prior_suite_manifest_sha256"],
        "selection_plan_sha256": digest_file(HERE / "selection_plan.json"),
        "builder_sha256": digest_file(Path(__file__)),
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
            "by_split": {split: sum(case["split"] == split for case in cases) for split in SPLITS},
            "materialized_npy_bytes": sum(case["raw_npy"]["bytes"] for case in cases),
        },
        "coverage_audit": {
            "by_split": coverage(cases),
            "limitation": (
                "Development and fresh holdout each cover both native rates and both edges, but "
                "each rate appears on only one edge. The suite is not a crossed rate-by-edge "
                "qualification and its 7.68-second blocks cannot establish rare-event rates or "
                "long-duration drift."
            ),
        },
        "cases": cases,
    }
    temporary = HERE / "cases.json.tmp"
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    os.replace(temporary, HERE / "cases.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deadline-seconds", type=int, default=180)
    args = parser.parse_args()
    signal.alarm(args.deadline_seconds)
    deadline = Deadline(args.deadline_seconds)
    plan = json.loads((HERE / "selection_plan.json").read_text())
    source_path = Path(plan["source_dataset_manifest"])
    source_bytes = source_path.read_bytes()
    if digest_bytes(source_bytes) != plan["source_dataset_manifest_sha256"]:
        raise ValueError("frozen DS5 source manifest hash mismatch")
    inventory = load_inventory(source_bytes)
    cases = extract_cases(plan, inventory, deadline)
    validate_cases(cases, plan)
    write_manifest(cases, plan)
    print(
        json.dumps(
            {
                "cases": len(cases),
                "bytes": sum(case["raw_npy"]["bytes"] for case in cases),
                "cases_path": str(HERE / "cases.json"),
            }
        )
    )


if __name__ == "__main__":
    main()
