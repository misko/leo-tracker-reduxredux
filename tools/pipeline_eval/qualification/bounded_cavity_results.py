"""Seal the bounded-cavity receipts, then score the four paired captures."""

import argparse
import gzip
import json
import math
from pathlib import Path

from ..__main__ import local_output, read_predictions, save_json
from ..scoring import ARMS, distance_km, validate_result
from . import bounded_cavity_trial as trial
from .full_receiver_comparison import read, require_fields, roster_matches, seal, sha
from .prefix_figures import csv_file
from .roof_completion import pack
from .short_receiver_figures import _frozen_roof


def validate_attempt(row, plan, lock):
    ident = row["id"]
    require_fields(
        row,
        dict(
            **plan["inputs"][ident],
            cpu=plan["cpu_by_id"][ident],
            source_lock_sha256=lock,
            method=trial.v5_bounded_cavity.METHOD,
        ),
    )
    for key in ("resolved_request_sha256", "scientific_request_sha256"):
        require_fields(row["request_proof"], {key: plan["inputs"][ident][key]})
    result = row["result"]
    validate_result(result)
    samples = row["samples"]
    if not samples or (samples[0]["stage"], samples[0]["event"]) != ("worker", "enter"):
        raise ValueError("missing first kernel observation")
    previous = [-1, -1, -1]
    for sample in samples:
        values = [sample["wall_s"], sample["cpu_s"], sample["peak_bytes"]]
        if (
            sample["cpu"] != row["cpu"]
            or sample["unit"] != row["unit"]
            or sample["swap_bytes"]
            or not 0 < sample["memory_bytes"] <= trial.CAP
            or not sample["memory_bytes"] <= sample["peak_bytes"] <= trial.CAP
            or any(not math.isfinite(x) or x < old for x, old in zip(values, previous, strict=True))
        ):
            raise ValueError("inconsistent worker resource observations")
        previous = values
    if row["returncode"] == 0:
        if (
            row["terminal"] != "success"
            or result["status"] not in ("ok", "withheld")
            or (samples[-1]["stage"], samples[-1]["event"]) != ("worker", "return")
        ):
            raise ValueError("position requires a completed memory-limited worker")
    elif row["terminal"] not in ("oom-kill", "timeout") or result["status"] != (
        "failed" if row["terminal"] == "oom-kill" else "timed_out"
    ):
        raise ValueError("unexpected termination in capped study")


def freeze_attempts(work, output, samples_path=None):
    plan = read(output / "plan.json")["source"]
    lock = sha(output / "plan.json")
    rows = []
    for ident in plan["cases"]:
        path = work / ident
        row = read(path / "attempt.json")
        require_fields(row, dict(id=ident, worker_log_sha256=sha(path / "worker.log")))
        validate_attempt(row, plan, lock)
        rows.append(row)
    name = "capped.jsonl.gz"
    existing = output / "prediction-lock.json"
    files = ["plan.json", name]
    if samples_path:
        ancillary = [json.loads(line) for line in samples_path.read_text().splitlines()]
        units = {r["id"]: r["unit"] + ".service" for r in rows}
        for row in ancillary:
            if (
                row["unit"] != units[row["id"]]
                or int(row["memory_max"]) != trial.CAP
                or int(row["swap_max"])
                or row["swap_current"]
                or not row["pids"]
                or not 0 < row["current"] <= row["peak"] <= trial.CAP
                or any(n < 0 for n in row["stat"].values())
            ):
                raise ValueError("external memory observations differ from the measured workers")
        files.append("memory-stat.jsonl.gz")
    if existing.exists():
        seal(output, existing.name, files)
        if {r["id"]: r for r in rows} != read_predictions(output / name):
            raise ValueError("capped outcomes differ from their original seal")
        if samples_path:
            with gzip.open(output / files[-1], "rt") as recorded:
                if ancillary != [json.loads(line) for line in recorded]:
                    raise ValueError("external memory observations differ from their seal")
        return
    pack(output / name, rows)
    if samples_path:
        pack(output / files[-1], ancillary)
    save_json(existing, {"cases": plan["cases"], "files": {n: sha(output / n) for n in files}})


def publish(output):
    filename = "capped.jsonl.gz"
    proof = seal(output, "prediction-lock.json", ("plan.json", filename))
    cases = proof["cases"]
    plan = read(output / "plan.json")["source"]
    rows = read_predictions(output / filename)
    roster_matches(rows, cases, "bounded compact receiver")
    for row in rows.values():
        validate_attempt(row, plan, sha(output / "plan.json"))
    _, controls = trial.row_memory_replay.controls()
    full_source = trial.row_memory_replay.REPORT
    other_file = "capped-positions.jsonl.gz"
    seal(full_source, "prediction-lock.json", (other_file,))
    extended = read_predictions(full_source / other_file)
    archive = trial.row_memory_replay.baseline.REPORT
    if sha(archive / "roof-lock.json") != plan["original_timing_lock"]:
        raise ValueError("historical timing and coordinates changed")
    compact = controls[trial.row_memory_replay.baseline.COMPACT]
    original = controls[trial.row_memory_replay.baseline.ORIGINAL]
    refs, _ = _frozen_roof()
    scores = []
    for ident in cases:
        measurements = dict(
            capped=rows[ident],
            compact=compact[ident],
            original=original[ident],
            capped_extended=extended[ident],
        )
        for name, method in measurements.items():
            require_fields(
                method,
                {k: plan["inputs"][ident][k] for k in trial.row_memory_replay.baseline.MATCH},
            )
            for arm in ARMS:
                data = method["result"]["arms"][arm]
                reference = compact[ident]["result"]["arms"][arm]
                scores.append(
                    dict(
                        id=ident,
                        method=name,
                        arm=arm,
                        status=method["result"]["status"],
                        error_km=distance_km(data.get("latlon"), refs[ident]["truth"]),
                        delta_to_compact_km=distance_km(data.get("latlon"), reference["latlon"]),
                        rf_rms_hz=data.get("rf_rms_hz"),
                        returned=bool(data.get("latlon")),
                        wall_s=method.get("worker_wall_s") or method["resources"]["wall_s"],
                    )
                )
    csv_file(output / "scores.csv", scores)
    views = [("one", "Cavity at 512 MiB", trial.v5_bounded_cavity.METHOD, filename)]
    for key, label, records in (
        ("stock", "Unrestricted compact cavity", compact),
        ("all_visits", "Final recovery at 512 MiB", extended),
    ):
        name = key + ".jsonl.gz"
        pack(output / name, [records[ident] for ident in cases])
        views.append((key, label, records[cases[0]]["method"], name))
    members = ("prediction-lock.json", "scores.csv", "plan.json", *(v[3] for v in views))
    save_json(
        output / "figure-lock.json",
        dict(
            cases=cases,
            files={f: sha(output / f) for f in members},
            compact_archive=sha(archive / "roof-lock.json"),
            capped_extended=sha(full_source / "prediction-lock.json"),
        ),
    )
    save_json(
        output / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id="v5_bounded_cavity-roof4",
                    method=trial.v5_bounded_cavity.METHOD,
                    scope="roof",
                    cases=cases,
                    title="The compact cavity decision under 512 MiB",
                    caption=(
                        "Both capped workers used zero swap. The four recordings ran on their "
                        "original host cores. Linux memory kills count in the denominator."
                    ),
                    provenance=["prediction-lock.json", "plan.json", "scores.csv"],
                    seal="figure-lock.json",
                    series=[
                        dict(
                            key=k,
                            label=label,
                            value=method,
                            file=f,
                            match=list(trial.row_memory_replay.baseline.MATCH),
                        )
                        for k, label, method, f in views
                    ],
                )
            ],
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--memory-stat", type=Path)
    parser.add_argument("--out", type=Path, default=trial.REPORT)
    args = parser.parse_args()
    output = local_output(args.out)
    if args.work is not None:
        freeze_attempts(local_output(args.work), output, args.memory_stat)
    publish(output)
