"""Freeze an outcome-blind, capture-balanced DS7 cohort and extract it read-only."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import signal
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools"))
import ds7_eval

PRIOR_INPUTS = REPO / "reports/2026_09_28_ds7_glrt_benchmark/inputs.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def selected_indices(visits: int, excluded: set[int]) -> list[int]:
    """Return eight deterministic midpoint-octile indices, avoiding prior exposure."""
    selected = []
    for position in range(8):
        candidate = ((2 * position + 1) * visits) // 16
        while candidate in excluded or candidate in selected:
            candidate += 1
        if candidate >= visits:
            raise ValueError("cannot select unique in-range visit")
        selected.append(candidate)
    return selected


def make_plan() -> dict:
    manifest, _ = ds7_eval.load_dataset()
    prior = json.loads(PRIOR_INPUTS.read_text())
    excluded: dict[str, set[int]] = {}
    for row in prior["rows"]:
        excluded.setdefault(row["session_id"], set()).add(row["visit_index"])
    captures = []
    for capture in manifest["captures"]:
        indices = selected_indices(capture["visits"], excluded.get(capture["session_id"], set()))
        captures.append(
            {k: capture[k] for k in (
                "session_id", "manifest_sha256", "sample_rate_hz", "receiver_ids", "visits"
            )}
            | {"visit_indices": indices}
        )
    return {
        "schema": "ds7-large-arm-plan/v1",
        "dataset_sha256": ds7_eval.DS7_SHA256,
        "selection": (
            "all 88 DS7 captures; midpoint of each of eight equal chronological strata; "
            "increment only to avoid the prior 28-visit smoke cohort; detector outcomes unused"
        ),
        "scope": "exposed development evaluation cohort, not an independent holdout",
        "captures": captures,
        "expected_captures": 88,
        "visits_per_capture": 8,
        "expected_visits": 704,
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
        "prior_input_manifest_sha256": sha(PRIOR_INPUTS),
    }


def write_plan(output: Path) -> None:
    plan = make_plan()
    with output.open("x") as stream:
        json.dump(plan, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"output": str(output), "captures": 88, "visits": 704}))


def validate_plan(plan: dict) -> None:
    expected = make_plan()
    if plan != expected:
        raise ValueError("plan differs from deterministic metadata-only selection")
    pairs = [(c["session_id"], i) for c in plan["captures"] for i in c["visit_indices"]]
    if len(pairs) != plan["expected_visits"] or len(set(pairs)) != len(pairs):
        raise ValueError("planned visit accounting")


def extract(plan_path: Path, output: Path) -> None:
    import numpy as np
    from leo.storage.adaptive_hop import AdaptiveHopIqStore

    signal.alarm(1800)
    plan = json.loads(plan_path.read_text())
    validate_plan(plan)
    manifest, _ = ds7_eval.load_dataset()
    allowed = {c["session_id"]: c for c in manifest["captures"]}
    output.mkdir(parents=True, exist_ok=False)
    (output / "batches").mkdir()
    rows = []
    total = 0
    store = AdaptiveHopIqStore("/srv/bulk/leo", read_only=True)
    try:
        for capture in plan["captures"]:
            published = ds7_eval.load_recording(allowed[capture["session_id"]], store)
            if published.manifest_sha256 != capture["manifest_sha256"]:
                raise ValueError("source binding")
            reader = store.reader(capture["session_id"], expected=published)
            try:
                capture_rows = []
                for index in capture["visit_indices"]:
                    started = time.perf_counter()
                    visit, iq = reader.read_visit_ci16(index)
                    read_wall = time.perf_counter() - started
                    event = visit.event
                    duration_ms = iq.shape[0] * 1000 / capture["sample_rate_hz"]
                    if event.visit_index != index or tuple(iq.shape[1:]) != (2, 2):
                        raise ValueError("visit geometry")
                    if duration_ms != plan["expected_dwell_ms"]:
                        raise ValueError("selected visit is not a 120 ms dwell")
                    total += iq.nbytes
                    if total > plan["maximum_uncompressed_iq_bytes"]:
                        raise ValueError("IQ budget exceeded")
                    filename = f'{capture["session_id"]}-{index}.npy'
                    np.save(output / filename, iq, allow_pickle=False)
                    row = {
                        "ordinal": len(rows), "session_id": capture["session_id"],
                        "visit_index": index, "manifest_sha256": capture["manifest_sha256"],
                        "sample_start_counter": event.valid_start_counter,
                        "sample_end_counter": visit.valid_end_counter_exclusive,
                        "rate_hz": capture["sample_rate_hz"], "target_index": event.target_index,
                        "target": event.target.model_dump(mode="json"),
                        "actual_lo_frequency_hz": event.actual_lo_frequency_hz,
                        "actual_if_offset_hz": event.actual_if_offset_hz,
                        "shape": list(iq.shape), "dtype": str(iq.dtype), "file": filename,
                        "sha256": sha(output / filename), "iq_bytes": iq.nbytes,
                        "read_decode_wall_s": read_wall,
                    }
                    rows.append(row)
                    capture_rows.append(row)
                batch = {
                    "schema": "ds7-large-arm-input-batch/v1", "plan_sha256": sha(plan_path),
                    "dataset_sha256": plan["dataset_sha256"], "complete": True,
                    "session_id": capture["session_id"], "manifest_sha256": capture["manifest_sha256"],
                    "expected_rows": 8, "rows": capture_rows,
                }
                batch_path = output / "batches" / f'{capture["session_id"]}.json'
                with batch_path.open("x") as stream:
                    json.dump(batch, stream, indent=2)
                    stream.write("\n")
                partial = {
                    "schema": "ds7-large-arm-inputs/v1", "plan_sha256": sha(plan_path),
                    "dataset_sha256": plan["dataset_sha256"], "complete": False,
                    "expected_rows": 704, "ready_captures": len(rows) // 8, "rows": rows,
                    "iq_bytes": total,
                }
                temporary = output / "inputs-partial.json.tmp"
                temporary.write_text(json.dumps(partial, indent=2) + "\n")
                temporary.replace(output / "inputs-partial.json")
                print(json.dumps({"ready_session": capture["session_id"],
                                  "ready_captures": len(rows) // 8, "ready_rows": len(rows)}), flush=True)
            finally:
                reader.close()
    finally:
        store.close()
    target_counts: dict[str, int] = {}
    edge_counts: dict[str, int] = {}
    rate_counts: dict[str, int] = {}
    for row in rows:
        key = str(row["target_index"])
        target_counts[key] = target_counts.get(key, 0) + 1
        edge = str(row["target"]["edge"])
        edge_counts[edge] = edge_counts.get(edge, 0) + 1
        rate = str(row["rate_hz"])
        rate_counts[rate] = rate_counts.get(rate, 0) + 1
    receipt = {
        "schema": "ds7-large-arm-inputs/v1", "plan_sha256": sha(plan_path),
        "dataset_sha256": plan["dataset_sha256"], "complete": len(rows) == 704,
        "expected_rows": 704, "rows": rows, "target_index_counts": target_counts,
        "target_edge_counts": edge_counts, "sample_rate_counts": rate_counts,
        "iq_bytes": total,
        "integrity": (
            "source manifests verified; public reader checks selected chunk payloads; "
            "each extracted payload SHA-256 bound; no full-corpus IQ hash claim"
        ),
    }
    with (output / "inputs.json").open("x") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"visits": len(rows), "iq_bytes": total, "targets": target_counts}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("plan", "extract"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plan", type=Path)
    args = parser.parse_args()
    if args.command == "plan":
        write_plan(args.output)
    elif args.plan is None:
        parser.error("extract requires --plan")
    else:
        extract(args.plan, args.output)
