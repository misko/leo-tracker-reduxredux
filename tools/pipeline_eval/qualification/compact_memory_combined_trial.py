"""Qualify the composed sparse discovery and sampled family-width receiver."""

import argparse
import gzip
import json
import os
from pathlib import Path
from unittest.mock import patch

from ..__main__ import ROOT, encoded, local_output, references, save_json, write
from ..scoring import ARMS, distance_km
from ..variants import v5_compact_memory_combined as combined
from ..variants import v5_composed_memory, v5_lean
from . import composed_memory_trial as control
from . import discovery_memory_trial as early
from . import working_memory_trial
from .full_v5_check import _sha
from .prefix_figures import csv_file

REPORT = early.REPORT.with_name("compact-memory-combined")
RUNS = early.RUNS.with_name("compact-memory-combined")
FAMILY = early.REPORT.with_name("family-memory")
WORKER = Path(__file__).with_name("compact_memory_combined_worker.py")


def source():
    early_paths = ("source-lock.json", "prediction-lock.json")
    if early.source() != json.loads((early.REPORT / early_paths[0]).read_bytes()):
        raise ValueError("sparse-only control sources differ from the original lock")
    plan = FAMILY / "plan.json"
    family = json.loads(plan.read_bytes())["source"]
    frozen = v5_lean.SOURCE / "leo/analysis/localization_v3"
    actual = {path: _sha(ROOT / path) for path in family["files"]}
    actual_frozen = {name: _sha(frozen / f"{name}.py") for name in family["frozen"]}
    if actual != family["files"] or actual_frozen != family["frozen"]:
        raise ValueError("family-width sources differ from their original plan")
    paths = (Path(__file__), WORKER, Path(combined.__file__), REPORT / "PROTOCOL.md")
    return dict(
        source={str(p.relative_to(ROOT)): _sha(p) for p in paths},
        sparse={name: _sha(early.REPORT / name) for name in early_paths},
        family_plan_sha256=_sha(plan),
        family=family,
        composed_predictions_sha256=_sha(control.REPORT / "prediction-lock.json"),
        case=control.CASE,
        cpu=control.CPU,
        nice=early.NICE,
        memory_max_bytes=control.MEMORY,
    )


def reference():
    lock = json.loads((early.REPORT / "prediction-lock.json").read_bytes())
    path = early.REPORT / "uncapped-positions.jsonl.gz"
    if (
        lock["cases"] != [control.CASE]
        or _sha(path) != lock["files"][path.name]
        or _sha(early.REPORT / "source-lock.json") != lock["source_lock_sha256"]
    ):
        raise ValueError("sparse-only control archive differs from its lock")
    row = json.loads(gzip.decompress(path.read_bytes()))
    plan = json.loads((FAMILY / "plan.json").read_bytes())["inputs"][control.CASE]
    if row["input_sha256"] != plan["request_sha256"] or any(
        row[field] != value for field, value in plan["native"].items()
    ):
        raise ValueError("family and discovery controls bind a different scientific request")
    return row


def same_science(sparse, candidate):
    only = early.same_science(sparse, candidate)
    composed = early.same_science(early.reference(), candidate)
    return dict(
        sparse=only,
        composed=composed,
        exact=only.get("exact", False) and composed.get("exact", False),
    )


def publish(runs, report):
    control.locked(report)
    stock, sparse = early.reference(), reference()
    free, capped = (
        json.loads((runs / mode / "prediction.json").read_bytes())
        for mode in ("uncapped", "capped")
    )
    rows = dict(control=stock, sparse=sparse, uncapped=free, capped=capped)
    files = {}
    for name, row in rows.items():
        path = report / f"{name}-positions.jsonl.gz"
        write(path, gzip.compress(encoded(row) + b"\n", mtime=0))
        files[path.name] = _sha(path)
    comparison = dict(unrestricted=same_science(sparse, free), capped=same_science(sparse, capped))
    save_json(report / "comparison.json", comparison)
    for name in ("memory-cap.json", "comparison.json"):
        files[name] = _sha(report / name)
    save_json(
        report / "prediction-lock.json",
        dict(
            cases=[control.CASE], files=files, source_lock_sha256=_sha(report / "source-lock.json")
        ),
    )
    truth = references("roof16", [control.CASE])[1][0]["truth"]
    scores = []
    for row in rows.values():
        r = row["result"]
        for arm in ARMS:
            scores.append(
                dict(
                    id=control.CASE,
                    method=row["method"],
                    mode=row["mode"],
                    arm=arm,
                    status=r["status"],
                    error_km=distance_km(truth, r["arms"][arm]["latlon"]),
                    conditional_rms_hz=r["metrics"].get(arm + "_conditional_rms_hz"),
                    objective=r["metrics"].get(arm + "_frequency_score"),
                )
            )
    csv_file(report / "scores.csv", scores)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "replay", "cap", "publish"))
    for name, default in (("report", REPORT), ("runs", RUNS), ("raw", working_memory_trial.RAW)):
        parser.add_argument("--" + name, type=local_output, default=default)
    args = parser.parse_args()
    if args.action == "seal":
        path, candidate = args.report / "source-lock.json", source()
        if path.exists() and json.loads(path.read_bytes()) != candidate:
            raise ValueError("refuse to replace a previous source seal")
        if not path.exists():
            save_json(path, candidate)
        return
    with (
        patch.multiple(
            control, WORKER=WORKER, seal=source, reference=reference, same_science=same_science
        ),
        patch.multiple(v5_composed_memory, METHOD=combined.METHOD, BOUNDARY=combined.BOUNDARY),
    ):
        if args.action == "replay":
            if os.getpriority(os.PRIO_PROCESS, 0) != early.NICE:
                raise ValueError(f"start the unrestricted worker with nice -n {early.NICE}")
            control.replay(args.runs, args.report, args.raw)
        elif args.action == "cap":
            early.cap(args.runs, args.report)
        else:
            publish(args.runs, args.report)


if __name__ == "__main__":
    main()
