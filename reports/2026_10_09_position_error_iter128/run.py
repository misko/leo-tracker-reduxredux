"""Original selected-IQ replay. Opening the reader is authorized only after freeze."""

import argparse
import hashlib
import json
import os
import time
from collections import Counter
from dataclasses import fields
from pathlib import Path

from adapter import Window, replay
from evaluate import evaluate

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)


def verify(plan, root=ROOT):
    if plan["schema"] != "iter128-original-iq-v1":
        raise ValueError("unknown protocol")
    for name, expected in plan["source_sha256"].items():
        if digest(root / name) != expected:
            raise ValueError(f"source/input digest mismatch: {name}")
    if plan["scorer"] != "original-python-conditioned-scorer-all-members":
        raise ValueError("unknown scorer")
    if len(plan["members"]) != 12 or len({m["label"] for m in plan["members"]}) != 12:
        raise ValueError("membership differs")


def validate_capture(capture, metadata, chunk_cap):
    geometry = capture.manifest.receipt.plan.geometry
    if capture.manifest_sha256 != metadata["input_manifest_sha256"]:
        raise ValueError("capture identity mismatch")
    if (
        geometry.sample_rate_hz != metadata["sample_rate_hz"]
        or list(geometry.receiver_ids) != metadata["receiver_ids"]
    ):
        raise ValueError("receiver/sample-rate identity mismatch")
    largest = max((c.uncompressed_bytes for c in capture.manifest.chunks), default=0)
    if largest > chunk_cap:
        raise ValueError("reader chunk resource cap")
    return largest


def execute(metadata, plan, *, store, evaluator=evaluate, clock=time.monotonic):
    """Stream rows exactly once; all unfinished original rows survive any exception."""
    started = clock()
    seen = set()
    expected = metadata["window_ids"]
    if len(expected) != len(set(expected)):
        raise ValueError("duplicate authoritative IDs")
    try:
        windows = []
        for row in metadata["windows"]:
            if row["status"] != "metadata-ready":
                raise ValueError("unready original metadata")
            windows.append(Window(**{f.name: row[f.name] for f in fields(Window)}))
        with store.reader(metadata["session_id"]) as reader:
            validate_capture(reader.session, metadata, plan["maximum_chunk_bytes"])

            def read(index):
                if clock() - started >= plan["maximum_case_seconds"]:
                    raise TimeoutError("case soft deadline before visit read")
                visit, raw = reader.read_visit_ci16(index)
                bound = metadata["visits"][str(index)]
                if (
                    visit.event.valid_start_counter != bound["valid_start_counter"]
                    or visit.valid_sample_count != bound["sample_count"]
                ):
                    raise ValueError("visit counter/count identity mismatch")
                return raw

            def score(probe, window, fs):
                if clock() - started >= plan["maximum_case_seconds"]:
                    raise TimeoutError("case soft deadline before original scorer")
                return evaluator(probe, window, fs)

            rows = replay(
                windows,
                expected_ids=expected,
                sample_rate_hz=metadata["sample_rate_hz"],
                receiver_ids=metadata["receiver_ids"],
                visit_sample_counts={
                    int(k): v["sample_count"] for k, v in metadata["visits"].items()
                },
                read_visit=read,
                evaluate=score,
                maximum_visit_bytes=plan["maximum_visit_bytes"],
            )
            for row in rows:
                if row["window_id"] in seen:
                    raise ValueError("duplicate emitted ID")
                if row.get("error", "").startswith("TimeoutError:"):
                    row["status"] = "budget-exhausted"
                seen.add(row["window_id"])
                yield row
    except Exception as exc:
        for window_id in expected:
            if window_id not in seen:
                seen.add(window_id)
                yield {
                    "window_id": window_id,
                    "status": "input-or-replay-failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
    if seen != set(expected):
        raise ValueError("terminal observation coverage mismatch")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    if any(
        os.environ.get(k) != "1"
        for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
    ):
        raise ValueError("single-thread environment required")
    protocol = HERE / "protocol.json"
    plan = json.loads(protocol.read_text())
    verify(plan)
    member = next(m for m in plan["members"] if m["label"] == args.label)
    metadata = json.loads((ROOT / member["metadata_path"]).read_text())
    if digest(ROOT / member["metadata_path"]) != member["metadata_sha256"]:
        raise ValueError("member digest mismatch")
    output = HERE / "results" / args.label
    identity = {
        "label": args.label,
        "protocol_sha256": digest(protocol),
        "metadata_sha256": member["metadata_sha256"],
    }
    write_new(output / "started.json", identity)
    # Import concrete public read-only port only at the application boundary.
    from leo.storage.adaptive_hop import AdaptiveHopIqStore

    start = time.monotonic()
    counts = Counter()
    ids = []
    with (output / "rows.jsonl").open("x") as stream:
        for row in execute(
            metadata, plan, store=AdaptiveHopIqStore(Path(plan["data_root"]), read_only=True)
        ):
            stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
            stream.flush()
            counts[row["status"]] += 1
            ids.append(row["window_id"])
    coverage = len(ids) == len(metadata["window_ids"]) and set(ids) == set(metadata["window_ids"])
    write_new(
        output / "result.json",
        {
            **identity,
            "status": "complete"
            if coverage and counts["complete"] == len(ids)
            else "complete-with-failures",
            "coverage_complete": coverage,
            "expected": len(metadata["window_ids"]),
            "rows": len(ids),
            "counts": dict(counts),
            "elapsed_s": time.monotonic() - start,
            "rows_sha256": digest(output / "rows.jsonl"),
            "position_evaluation": False,
            "peak_memory": "unavailable; reader chunk and visit guards are not an RSS bound",
        },
    )


if __name__ == "__main__":
    main()
