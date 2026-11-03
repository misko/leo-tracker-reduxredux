#!/usr/bin/env python3
"""Verify the bounded saved-IQ queue-four acceptance artifacts."""

import argparse
import hashlib
import json
import math
from pathlib import Path

EXPECTED_RELEASE_HASHES = {
    "libleo-adaptive-detector.so": (
        "6951287cd82009ad79e76bb6293ac18f5f3c4bb4c16bfa865131e5629b114e44"
    ),
    "leo-paced": "b949a5f78c5b32f398a8a8967784c15b9e81ae99b0a07b64e73ebd322ec669cf",
    "leo-native-adaptive-replay": (
        "1834dec42eec29edade7bbc8a035b60993d819aa9d67891d758a432f231a9fb0"
    ),
    "leo-location": "2a6bdb8f6c4e7d81dc03f10dc4af7cbdde2acc504fd2524ff4bfc107a9d48a5e",
}


def reject_constant(value):
    raise ValueError(f"non-finite JSON number: {value}")


def reject_duplicate(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_loads(text, source):
    try:
        value = json.loads(text, object_pairs_hook=reject_duplicate, parse_constant=reject_constant)
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid strict JSON in {source}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON record is not an object: {source}")
    return value


def jsonl(path):
    rows = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line:
            raise ValueError(f"blank JSONL line: {path}:{number}")
        rows.append(strict_loads(line, f"{path}:{number}"))
    return rows


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def nearest_rank(values, probability):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(1, math.ceil(probability * len(ordered))) - 1]


def verify_release(path):
    document = strict_loads(path.read_text(), path)
    manifest = document.get("manifest", document)
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("release manifest has no files mapping")
    actual = {name: files.get(name) for name in EXPECTED_RELEASE_HASHES}
    if actual != EXPECTED_RELEASE_HASHES:
        raise ValueError(f"release detector/benchmark hashes differ: {actual}")
    return {
        "release_id": manifest.get("release_id"),
        "artifact_sha256": actual,
        "exact_qualified_detector_library": True,
    }


def verify_paced(path):
    rows = jsonl(path)
    arrivals = [row for row in rows if row.get("kind") == "arrival"]
    summaries = [row for row in rows if row.get("kind") == "summary"]
    if len(summaries) != 1 or len(arrivals) != 80:
        raise ValueError("paced output must contain 80 arrivals and one summary")
    for sequence, row in enumerate(arrivals):
        if (
            row.get("sequence") != sequence
            or row.get("input_index") != sequence % 8
            or row.get("accepted") is not True
            or row.get("status") != 0
        ):
            raise ValueError(f"paced arrival differs at sequence {sequence}")
    summary = summaries[0]
    expected = {
        "period_ms": 120,
        "arrivals": 80,
        "completed": 80,
        "failed": 0,
        "rejected": 0,
    }
    if any(summary.get(key) != value for key, value in expected.items()):
        raise ValueError(f"paced summary differs: {summary}")
    high_water = summary.get("queue_high_water")
    if type(high_water) is not int or not 0 <= high_water <= 4:
        raise ValueError("paced queue high-water exceeds four entries")
    finishes = [float(row["due_to_finish_ms"]) for row in arrivals]
    queues = [float(row["queue_ms"]) for row in arrivals]
    return {
        "path": str(path),
        "sha256": sha256(path),
        "invocation_contract": {
            "period_ms": 120,
            "rounds": 10,
            "queue_capacity": 4,
            "fractional_mode": 1,
            "detector_workers": 1,
        },
        "arrivals": 80,
        "completed": 80,
        "rejected": 0,
        "failed": 0,
        "queue_high_water": high_water,
        "maximum_queue_ms": max(queues),
        "p95_due_to_finish_ms_nearest_rank": nearest_rank(finishes, 0.95),
        "maximum_due_to_finish_ms": max(finishes),
        "due_to_finish_over_120ms": sum(value > 120.0 for value in finishes),
    }


def replay_science(path):
    calls = []
    for row in jsonl(path):
        result = row.get("result")
        if not isinstance(result, dict) or result.get("kind") != "call":
            continue
        calls.append(
            {
                "sequence": result.get("sequence"),
                "rate_hz": result.get("rate_hz"),
                "dwell_ms": result.get("dwell_ms"),
                "stride_ms": result.get("stride_ms"),
                "metadata": result.get("metadata"),
                "rows": [
                    {
                        "receiver_id": item.get("receiver_id"),
                        "probe_index": item.get("probe_index"),
                        "probe_start_ms": item.get("probe_start_ms"),
                        "candidates": item.get("candidates"),
                    }
                    for item in result.get("rows", [])
                ],
            }
        )
    return calls


def verify_replay(observed, reference):
    actual = replay_science(observed)
    expected = replay_science(reference)
    if len(actual) != 80 or actual != expected:
        raise ValueError("replay candidate fields differ from the 80-call reference")
    candidate_count = sum(len(row["candidates"]) for call in actual for row in call["rows"])
    return {
        "observed_path": str(observed),
        "observed_sha256": sha256(observed),
        "reference_path": str(reference),
        "reference_sha256": sha256(reference),
        "calls": len(actual),
        "candidates": candidate_count,
        "all_candidate_fields_exact": True,
    }


def verify_location(observed, reference):
    actual = strict_loads(observed.read_text(), observed)
    expected = strict_loads(reference.read_text(), reference)
    if actual != expected:
        raise ValueError("location output differs from the saved reference")
    return {
        "observed_path": str(observed),
        "observed_sha256": sha256(observed),
        "reference_path": str(reference),
        "reference_sha256": sha256(reference),
        "parsed_json_exact": True,
        "workers": 1,
        "required_nice": 19,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--paced", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--reference-replay", type=Path, required=True)
    parser.add_argument("--location", type=Path, required=True)
    parser.add_argument("--reference-location", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = {
        "schema": "org.leo.native-adaptive-saved-pacing-4slot/v1",
        "scope": (
            "saved DS9 IQ pacing and saved-track location; no RF; CLI invocation "
            "is recorded separately and required to bind nice and queue arguments"
        ),
        "release": verify_release(args.release),
        "paced": verify_paced(args.paced),
        "replay_science": verify_replay(args.replay, args.reference_replay),
        "location": verify_location(args.location, args.reference_location),
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "status": "pass"}))


if __name__ == "__main__":
    main()
