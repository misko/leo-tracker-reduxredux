"""Freeze a DS8+DS9 outcome-blind cohort, then extract it read-only."""

from __future__ import annotations

import argparse
import hashlib
import json
import signal
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATASETS = {
    "DS8": REPO / "reports/2026_09_28_ds8_post_ds7/manifest.json",
    "DS9": REPO / "reports/2026_09_28_ds9_post_ds8/manifest.json",
}
DS7_MANIFEST = REPO / "reports/2026_09_27_ds7_post_ds6/manifest.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def selected_indices(visits: int) -> list[int]:
    """Return the midpoint of each chronological quartile."""
    if visits < 4:
        raise ValueError("capture has fewer than four visits")
    result = [((2 * position + 1) * visits) // 8 for position in range(4)]
    if len(set(result)) != 4 or result[-1] >= visits:
        raise ValueError("cannot select four unique in-range visits")
    return result


def _load_manifests() -> tuple[dict[str, dict], dict[str, str], str]:
    manifests = {name: json.loads(path.read_text()) for name, path in DATASETS.items()}
    digests = {name: sha(path) for name, path in DATASETS.items()}
    for name, path in DATASETS.items():
        sums = path.with_name("SHA256SUMS").read_text().splitlines()
        sealed = next(
            (line.split()[0] for line in sums if line.split()[-1] == "manifest.json"), None
        )
        if sealed != digests[name]:
            raise ValueError(f"{name} manifest differs from SHA256SUMS")
    session_sets = {
        "DS7": {row["session_id"] for row in json.loads(DS7_MANIFEST.read_text())["captures"]},
        **{name: {row["session_id"] for row in doc["captures"]}
           for name, doc in manifests.items()},
    }
    manifest_sets = {
        "DS7": {row["manifest_sha256"] for row in json.loads(DS7_MANIFEST.read_text())["captures"]},
        **{name: {row["manifest_sha256"] for row in doc["captures"]}
           for name, doc in manifests.items()},
    }
    for left, right in (("DS7", "DS8"), ("DS7", "DS9"), ("DS8", "DS9")):
        if session_sets[left] & session_sets[right] or manifest_sets[left] & manifest_sets[right]:
            raise ValueError(f"{left}/{right} source membership overlaps")
    binding = hashlib.sha256(
        b"".join(name.encode() + b"\0" + DATASETS[name].read_bytes() for name in sorted(DATASETS))
    ).hexdigest()
    return manifests, digests, "sha256:" + binding


def make_plan() -> dict:
    manifests, digests, composite = _load_manifests()
    captures = []
    for dataset in ("DS8", "DS9"):
        for capture in manifests[dataset]["captures"]:
            captures.append(
                {k: capture[k] for k in (
                    "session_id", "manifest_sha256", "sample_rate_hz", "receiver_ids", "visits"
                )}
                | {"dataset_id": dataset, "visit_indices": selected_indices(capture["visits"])}
            )
    expected_captures = sum(len(manifests[name]["captures"]) for name in manifests)
    return {
        # Deliberately retains the large-arm plan schema so its runner can consume this view.
        "schema": "ds7-large-arm-plan/v1",
        "dataset_sha256": composite,
        "dataset_manifests": {
            name: {"path": str(DATASETS[name].relative_to(REPO)), "sha256": digests[name]}
            for name in ("DS8", "DS9")
        },
        "selection": (
            "all frozen DS8 and DS9 captures; midpoint of each of four equal chronological "
            "strata; detector and production-analysis outcomes unused"
        ),
        "scope": "post-DS7 validation cohort; DS8 and DS9 remain separately identified",
        "captures": captures,
        "expected_captures": expected_captures,
        "dataset_capture_counts": {
            name: len(manifests[name]["captures"]) for name in ("DS8", "DS9")
        },
        "visits_per_capture": 4,
        "expected_visits": expected_captures * 4,
        "expected_dwell_ms": 120,
        "expected_receiver_ids": [0, 1],
        "probe_ms": 20,
        "probe_stride_ms": 10,
        "expected_probe_windows": 11,
        "maximum_acquisition_candidates": 8,
        "method": "original",
        "repetitions": 1,
        "maximum_uncompressed_iq_bytes": 8 * 1024**3,
        "runner_wall_limit_s": 1800,
    }


def write_plan(output: Path) -> None:
    plan = make_plan()
    with output.open("x") as stream:
        json.dump(plan, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"output": str(output), "captures": plan["expected_captures"],
                      "visits": plan["expected_visits"]}))


def validate_plan(plan: dict) -> None:
    if plan != make_plan():
        raise ValueError("plan differs from deterministic metadata-only selection")
    keys = [(c["dataset_id"], c["session_id"], i)
            for c in plan["captures"] for i in c["visit_indices"]]
    if len(keys) != plan["expected_visits"] or len(set(keys)) != len(keys):
        raise ValueError("planned visit accounting")


def extract(plan_path: Path, output: Path, bulk_root: Path) -> None:
    import numpy as np
    from leo.storage.adaptive_hop import AdaptiveHopIqStore

    signal.alarm(1800)
    plan = json.loads(plan_path.read_text())
    validate_plan(plan)
    manifests, _, _ = _load_manifests()
    allowed = {
        (dataset, capture["session_id"]): capture
        for dataset, manifest in manifests.items() for capture in manifest["captures"]
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / "batches").mkdir()
    rows: list[dict] = []
    total = 0
    store = AdaptiveHopIqStore(bulk_root, read_only=True)
    try:
        for capture in plan["captures"]:
            source = allowed[(capture["dataset_id"], capture["session_id"])]
            published = store.inspect(capture["session_id"])
            if published.manifest_sha256 != source["manifest_sha256"]:
                raise ValueError("source manifest changed")
            reader = store.reader(capture["session_id"], expected=published)
            try:
                capture_rows = []
                for index in capture["visit_indices"]:
                    started = time.perf_counter()
                    visit, iq = reader.read_visit_ci16(index)
                    elapsed = time.perf_counter() - started
                    event = visit.event
                    if event.visit_index != index or tuple(iq.shape[1:]) != (2, 2):
                        raise ValueError("visit geometry")
                    if iq.shape[0] * 1000 / capture["sample_rate_hz"] != plan["expected_dwell_ms"]:
                        raise ValueError("selected visit is not a 120 ms dwell")
                    total += iq.nbytes
                    if total > plan["maximum_uncompressed_iq_bytes"]:
                        raise ValueError("IQ budget exceeded")
                    prefix = capture["dataset_id"].lower()
                    filename = f'{prefix}-{capture["session_id"]}-{index}.npy'
                    np.save(output / filename, iq, allow_pickle=False)
                    row = {
                        "ordinal": len(rows), "dataset_id": capture["dataset_id"],
                        "session_id": capture["session_id"], "visit_index": index,
                        "manifest_sha256": capture["manifest_sha256"],
                        "sample_start_counter": event.valid_start_counter,
                        "sample_end_counter": visit.valid_end_counter_exclusive,
                        "rate_hz": capture["sample_rate_hz"], "target_index": event.target_index,
                        "target": event.target.model_dump(mode="json"),
                        "actual_lo_frequency_hz": event.actual_lo_frequency_hz,
                        "actual_if_offset_hz": event.actual_if_offset_hz,
                        "shape": list(iq.shape), "dtype": str(iq.dtype), "file": filename,
                        "sha256": sha(output / filename), "iq_bytes": iq.nbytes,
                        "read_decode_wall_s": elapsed,
                    }
                    rows.append(row)
                    capture_rows.append(row)
                batch = {
                    "schema": "ds7-large-arm-input-batch/v1", "plan_sha256": sha(plan_path),
                    "dataset_sha256": plan["dataset_sha256"],
                    "dataset_id": capture["dataset_id"],
                    "complete": True, "session_id": capture["session_id"],
                    "manifest_sha256": capture["manifest_sha256"], "expected_rows": 4,
                    "rows": capture_rows,
                }
                batch_name = f'{capture["dataset_id"].lower()}-{capture["session_id"]}.json'
                batch_path = output / "batches" / batch_name
                with batch_path.open("x") as stream:
                    json.dump(batch, stream, indent=2)
                    stream.write("\n")
                partial = _receipt(plan, plan_path, rows, total, complete=False)
                temporary = output / "inputs-partial.json.tmp"
                temporary.write_text(json.dumps(partial, indent=2) + "\n")
                temporary.replace(output / "inputs-partial.json")
                print(json.dumps({"ready_dataset": capture["dataset_id"],
                                  "ready_session": capture["session_id"],
                                  "ready_captures": len(rows) // 4,
                                  "ready_rows": len(rows)}), flush=True)
            finally:
                reader.close()
    finally:
        store.close()
        signal.alarm(0)
    receipt = _receipt(plan, plan_path, rows, total, complete=len(rows) == plan["expected_visits"])
    with (output / "inputs.json").open("x") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"visits": len(rows), "iq_bytes": total}))


def _receipt(plan: dict, plan_path: Path, rows: list[dict], total: int, *, complete: bool) -> dict:
    def counts(field: str) -> dict[str, int]:
        result: dict[str, int] = {}
        for row in rows:
            key = str(row[field])
            result[key] = result.get(key, 0) + 1
        return result

    return {
        # Legacy schema is intentional: ds7_large_arm/run_baseline.py accepts dynamic counts.
        "schema": "ds7-large-arm-inputs/v1", "plan_sha256": sha(plan_path),
        "dataset_sha256": plan["dataset_sha256"], "complete": complete,
        "expected_rows": plan["expected_visits"], "ready_captures": len(rows) // 4,
        "rows": rows, "dataset_counts": counts("dataset_id"),
        "sample_rate_counts": counts("rate_hz"), "iq_bytes": total,
        "integrity": (
            "source manifests verified; public reader checks selected chunk payloads; "
            "each extracted payload SHA-256 bound; no full-corpus IQ hash claim"
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("plan", "extract"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    args = parser.parse_args()
    if args.command == "plan":
        write_plan(args.output)
    elif args.plan is None:
        parser.error("extract requires --plan")
    else:
        extract(args.plan, args.output, args.bulk_root)
