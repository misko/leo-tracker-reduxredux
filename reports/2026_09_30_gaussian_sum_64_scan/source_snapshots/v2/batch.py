"""Bounded, resumable orchestration for the fixed 64-recording evaluation."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

from launch import launch

HERE = Path(__file__).resolve().parent
ARMS = ("gaussian_sum", "greedy", "prior_only")
PRIOR = "sacramento_uniform"


def digest(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ordered_units(selection):
    """Interleave datasets so every bounded batch spans their time selections."""
    groups = [selection["selected"][name] for name in ("DS9", "DS10", "DS11")]
    units = [group[i]["unit_id"] for i in range(max(map(len, groups)))
             for group in groups if i < len(group)]
    if len(units) != 64 or len(set(units)) != 64:
        raise ValueError("selection must contain exactly 64 unique recordings")
    sessions = [row["session_id"] for group in groups for row in group]
    if len(set(sessions)) != 64:
        raise ValueError("session identities must be distinct")
    return units


def summarize_launch(receipt):
    prediction = Path(receipt["prediction_path"])
    native = json.loads(prediction.read_text()) if prediction.is_file() else {}
    return {
        "unit_id": receipt["unit_id"], "arm": receipt["arm"],
        "launcher_status": receipt["status"],
        "native_status": native.get("status", "missing"),
        "factors": len(native.get("checkpoints", [])),
        "total_factors": native.get("selection", {}).get("retained_tracks"),
        "gate_failures": native.get("gate_failures", []),
        "exception": native.get("exception"),
        "seconds": receipt["wall_seconds"],
        "prediction_path": str(prediction),
    }


def run_unit(unit, output, deadline, launch_fn=launch):
    rows = []
    for arm in ARMS:
        previous = output / f"{unit}-{PRIOR}-{arm}.launch.json"
        if previous.exists():
            receipt = json.loads(previous.read_text())
        elif time.monotonic() + 91 > deadline:
            rows.append({"unit_id": unit, "arm": arm, "native_status": "not_started_batch_budget"})
            continue
        else:
            receipt = launch_fn(unit, arm, PRIOR, output)
        row = summarize_launch(receipt)
        rows.append(row)
        print(json.dumps(row), flush=True)
    return rows


def run_batch(number):
    if not 1 <= number <= 8:
        raise ValueError("batch number must be 1..8")
    selection_path = HERE / "selection.json"
    selection = json.loads(selection_path.read_text())
    units = ordered_units(selection)[(number - 1) * 8:number * 8]
    output = HERE / "runs-v2" / f"batch-{number:02d}"
    output.mkdir(parents=True, exist_ok=True)
    completed = output / "batch.json"
    if completed.exists():
        raise FileExistsError("batch receipt already exists; preserve completed batch")
    # Require preparation of the complete bounded batch before spawning any fit.
    for unit in units:
        for suffix in (".json", "-orbits.json"):
            path = HERE / "evidence" / (unit + suffix)
            if not path.is_file():
                raise FileNotFoundError(path)
    started = time.monotonic()
    rows = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(run_unit, unit, output, started + 900): unit for unit in units}
        for future in as_completed(futures):
            rows.extend(future.result())
    receipt = {"schema": "gaussian-sum-64-batch/v1", "batch": number,
               "selection_sha256": digest(selection_path), "units": units,
               "protocol_sha256": digest(HERE / "PROTOCOL.md"),
               "command": [sys.executable, str(Path(__file__).resolve()), str(number)],
               "finished_utc": datetime.now(timezone.utc).isoformat(),
               "wall_seconds": time.monotonic() - started,
               "rows": sorted(rows, key=lambda r: (r["unit_id"], r["arm"]))}
    with completed.open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
    print(json.dumps({"batch": number, "finished": len(rows), "seconds": receipt["wall_seconds"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("batch", type=int)
    run_batch(parser.parse_args().batch)
