"""Explicit full-member successor: only event-ID to reader-ordinal translation changes."""

import importlib.util
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

from mapping import visit_ordinals

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = HERE.parent / "2026_10_09_position_error_iter128"
sys.path.insert(0, str(OLD))
spec = importlib.util.spec_from_file_location("frozen128_run", OLD / "run.py")
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)


class EventReader:
    def __init__(self, reader, metadata):
        self.reader, self.metadata = reader, metadata

    def __enter__(self):
        self.reader.__enter__()
        try:
            self.session = self.reader.session
            self.ordinals = visit_ordinals(self.session.manifest.receipt.visits, self.metadata)
            return self
        except Exception:
            self.reader.__exit__(*sys.exc_info())
            raise

    def __exit__(self, *args):
        return self.reader.__exit__(*args)

    def read_visit_ci16(self, event_id):
        visit, values = self.reader.read_visit_ci16(self.ordinals[event_id])
        if visit.event.visit_index != event_id:
            raise ValueError("reader returned wrong event ID")
        return visit, values


class EventStore:
    def __init__(self, store, metadata):
        self.store, self.metadata = store, metadata

    def reader(self, session_id):
        if session_id != self.metadata["session_id"]:
            raise ValueError("session identity differs")
        return EventReader(self.store.reader(session_id), self.metadata)


def main():
    if any(
        os.environ.get(k) != "1"
        for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
    ):
        raise ValueError("single-thread environment required")
    protocol = HERE / "protocol.json"
    plan = json.loads(protocol.read_text())
    for name, expected in plan["source_sha256"].items():
        if original.digest(ROOT / name) != expected:
            raise ValueError(f"source/input changed: {name}")
    old_plan = json.loads((OLD / "protocol.json").read_text())
    original.verify(old_plan)
    metadata = json.loads((ROOT / plan["member"]["metadata_path"]).read_text())
    if plan["member"]["label"] != "DS18-029":
        raise ValueError("unfrozen successor member")
    output = HERE / "results"
    identity = {
        "label": plan["member"]["label"],
        "protocol_sha256": original.digest(protocol),
        "metadata_sha256": plan["member"]["metadata_sha256"],
        "supersedes_operational_rows_only": "iter128 DS18-029; original failure preserved",
    }
    original.write_new(output / "started.json", identity)
    from leo.storage.adaptive_hop import AdaptiveHopIqStore

    store = EventStore(AdaptiveHopIqStore(Path(old_plan["data_root"]), read_only=True), metadata)
    started = time.monotonic()
    counts, ids = Counter(), []
    with (output / "rows.jsonl").open("x") as stream:
        for row in original.execute(metadata, old_plan, store=store):
            stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
            stream.flush()
            counts[row["status"]] += 1
            ids.append(row["window_id"])
    coverage = len(ids) == len(metadata["window_ids"]) and set(ids) == set(metadata["window_ids"])
    original.write_new(
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
            "elapsed_s": time.monotonic() - started,
            "rows_sha256": original.digest(output / "rows.jsonl"),
            "position_evaluation": False,
        },
    )


if __name__ == "__main__":
    main()
