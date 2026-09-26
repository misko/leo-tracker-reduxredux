"""Build the metadata-only frozen cohort from the source manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SEED = 20260926
TARGETS = (4, 5, 6, 7)
BIN_COUNT = 8
PER_BIN = 4


def _rank(event: dict[str, object], bin_index: int) -> str:
    identity = (
        f"{SEED}:{event['target_index']}:{bin_index}:"
        f"{event['visit_index']}:{event['valid_start_counter']}"
    )
    return hashlib.sha256(identity.encode()).hexdigest()


def build(document: dict[str, object], manifest_sha256: str) -> dict[str, object]:
    manifest = document["manifest"]
    receipt = manifest["receipt"]
    events = [receipt["events"][i] for i in receipt["retained_visit_indices"]]
    stored_starts: dict[int, int] = {}
    for chunk in manifest["chunks"]:
        offset = chunk["sample_start"]
        for visit_index in range(
            chunk["first_visit_index"], chunk["first_visit_index"] + chunk["visit_count"]
        ):
            event = events[visit_index]
            stored_starts[visit_index] = offset
            offset += event["valid_end_counter_exclusive"] - event["valid_start_counter"]
        if offset != chunk["sample_start"] + chunk["sample_count"]:
            raise ValueError("chunk visit mapping disagrees with stored sample extent")
    selected: list[dict[str, object]] = []
    session_first = receipt["terminal"]["first_counter"]
    session_stop = receipt["terminal"]["final_counter"]
    session_span = session_stop - session_first
    for target in TARGETS:
        population = [e for e in events if e["target_index"] == target]
        for bin_index in range(BIN_COUNT):
            lower = session_first + session_span * bin_index // BIN_COUNT
            upper = session_first + session_span * (bin_index + 1) // BIN_COUNT
            eligible = [
                e
                for e in population
                if lower <= e["valid_start_counter"] and e["valid_end_counter_exclusive"] <= upper
            ]
            ranked = sorted(eligible, key=lambda e: (_rank(e, bin_index), e["visit_index"]))
            if len(ranked) < PER_BIN:
                raise ValueError(f"target {target} bin {bin_index} has only {len(ranked)} visits")
            for event in ranked[:PER_BIN]:
                selected.append(
                    {
                        "visit_index": event["visit_index"],
                        "target_index": target,
                        "channel": event["target"]["channel"],
                        "edge": event["target"]["edge"],
                        "valid_start_counter": event["valid_start_counter"],
                        "valid_end_counter_exclusive": event["valid_end_counter_exclusive"],
                        "stored_sample_start": stored_starts[event["visit_index"]],
                        "time_bin": bin_index,
                        "split": "development" if bin_index < 2 else "evaluation",
                        "rank_sha256": "sha256:" + _rank(event, bin_index),
                    }
                )
    selected.sort(key=lambda row: (row["target_index"], row["time_bin"], row["rank_sha256"]))
    development = [r for r in selected if r["split"] == "development"]
    start4 = [
        next(r["visit_index"] for r in development if r["target_index"] == target)
        for target in TARGETS
    ]
    smoke8 = [
        r["visit_index"]
        for target in TARGETS
        for r in [item for item in development if item["target_index"] == target][:2]
    ]
    return {
        "schema": "scan-phase-replay-selection/v1",
        "recording_id": manifest["session_id"],
        "input_manifest_sha256": manifest_sha256,
        "selection_policy": {
            "inputs": "manifest metadata only; no IQ, GLRT, phase, or outcome values",
            "seed": SEED,
            "targets": list(TARGETS),
            "device_time_bins_per_target": BIN_COUNT,
            "visits_per_target_bin": PER_BIN,
            "device_counter_range": [session_first, session_stop],
            "binning": (
                "eight equal half-open bins over the shared terminal "
                "first_counter/final_counter device-time range"
            ),
            "boundary_policy": (
                "a selected visit's complete 120 ms support must lie inside one bin; "
                "visits crossing a bin or development/evaluation boundary are ineligible"
            ),
            "ranking": "ascending SHA-256 of seed:target:bin:visit_index:valid_start_counter",
            "split": "bins 0-1 development; bins 2-7 locked evaluation",
        },
        "counts": {
            "selected": len(selected),
            "development": len(development),
            "evaluation": len(selected) - len(development),
        },
        "probe_schedule": {
            "sample_rate_hz": 10_000_000,
            "visit_samples": 1_200_000,
            "probe_start_samples": [0, 200_000, 400_000, 600_000, 800_000, 1_000_000],
            "probe_samples": 200_000,
            "receiver_ids": [0, 1],
        },
        "development_start4_visit_indices": start4,
        "smoke8_visit_indices": smoke8,
        "visits": selected,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    raw = args.manifest.read_bytes()
    document = json.loads(raw)
    declared = document.get("sha256")
    # The envelope's declared digest is the public manifest identity.  Hashing
    # the envelope itself would include that digest and is a different object.
    if not isinstance(declared, str) or not declared.startswith("sha256:"):
        raise ValueError("manifest envelope has no declared SHA-256 identity")
    result = build(document, declared)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
