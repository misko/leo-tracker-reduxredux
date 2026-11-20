"""Qualify row-major late screening on the original ordinary DS29-0082 inputs."""

import argparse
import json
import os
from pathlib import Path
from unittest.mock import patch

from ..__main__ import local_output, read_predictions, save_json
from ..variants import v5_composed_memory
from ..variants import v5_recovery_reads as tiled
from . import composed_memory_trial as apparatus
from . import discovery_memory_trial as discovery
from . import nomination_memory_trial as nomination
from . import recovery_cache_memory_trial as previous
from . import working_memory_trial
from .full_receiver_comparison import seal as verify
from .full_v5_check import _sha

REPORT = previous.REPORT.with_name("recovery-reads")
RUNS = previous.RUNS.with_name("recovery-reads")
WORKER = Path(__file__).with_name("recovery_reads_worker.py")
CPU = 14


def source():
    prior = previous.REPORT / "source-lock.json"
    with patch.object(apparatus, "CPU", nomination.CPU):
        reciprocal = previous.source()
    if json.loads(prior.read_bytes()) != reciprocal:
        raise ValueError("the bounded scratch control differs from its sealed source")
    paths = (Path(__file__), WORKER, Path(tiled.__file__), REPORT / "PROTOCOL.md")
    return dict(
        sources={p.name: _sha(p) for p in paths},
        late_donors=tiled.DONORS,
        bounded_scratch_source_sha256=_sha(prior),
        bounded_scratch_predictions_sha256=_sha(previous.REPORT / "prediction-lock.json"),
        case=apparatus.CASE,
        cpu=CPU,
        nice=discovery.NICE,
        memory_max_bytes=apparatus.MEMORY,
        swap_max_bytes=0,
    )


def reference():
    name = "uncapped-positions.jsonl.gz"
    lock = verify(previous.REPORT, "prediction-lock.json", (name,))
    if lock["cases"] != [apparatus.CASE]:
        raise ValueError("bounded scratch prediction changed its roster")
    return read_predictions(previous.REPORT / name)[apparatus.CASE]


def same_science(stock, candidate):
    check = discovery.same_science(stock, candidate)
    if "equal" not in check:
        return check
    a, b = (row["result"]["metrics"] for row in (stock, candidate))
    check["equal"]["recovery_rows"] = all(
        a["bounded_recovery_rows"][key] == b["bounded_recovery_rows"][key]
        for key in ("ecef", "audit")
    )
    checks = nomination.nomination_parity(stock, candidate)["checks"]
    for key in ("ordered_coarse", "complete_nominations"):
        check["equal"][key] = checks[key]
    check["exact"] = all(check["equal"].values())
    return check


def figures(report):
    capped = read_predictions(report / "capped-positions.jsonl.gz")[apparatus.CASE]
    outcome = capped["result"]["status"]
    roles = (
        ("one", "Row-major screens", "uncapped", tiled.METHOD, "matched-tile"),
        ("stock", "Bounded cache control", "control", "v5_recovery_cache_memory", "matched-tile"),
        ("all_visits", "512 MiB cap", "capped", tiled.METHOD, "memory-cap"),
    )
    series = [
        dict(
            key=key,
            label=label,
            file=f"{file}-positions.jsonl.gz",
            value=value,
            native_authority="ordinary",
            where=dict(mode=mode),
            match=["input_sha256", "tile"],
        )
        for key, label, file, value, mode in roles
    ]
    result = {"ok": "returned both positions", "timed_out": "timed out"}.get(outcome, outcome)
    save_json(
        report / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id=tiled.METHOD,
                    method=tiled.METHOD,
                    scope="roof",
                    title="Row-major orbit recovery",
                    caption=f"Ordinary DS29-0082. The 512 MiB zero-swap service {result}. "
                    "Original v5 options use capture-era factors.",
                    cases=[apparatus.CASE],
                    seal="prediction-lock.json",
                    series=series,
                    provenance=["memory-cap.json", "comparison.json", "io-summary.json"],
                    source_lock=dict(file="source-lock.json", digest_key="source_lock_sha256"),
                )
            ],
        ),
    )


def publish(runs, report):
    apparatus.publish(runs, report)
    free, capped = (
        json.loads((runs / mode / "prediction.json").read_bytes())
        for mode in ("uncapped", "capped")
    )
    stats = {}
    for name, row in (("archived_control", reference()), ("uncapped", free), ("capped", capped)):
        metrics = row["result"]["metrics"]
        stats[name] = dict(
            status=row["result"]["status"],
            cpu_s=row["worker_cpu_s"],
            wall_s=row["worker_wall_s"],
            cpu=row["cpu"],
            position_rss=metrics.get("composed_memory_measurement", {}).get("after"),
            bank_writes=metrics.get("bounded_recovery_rows"),
            row_major_reads=metrics.get("recovery_reads"),
        )
    stats["archived_control_cap"] = json.loads((previous.REPORT / "memory-cap.json").read_bytes())
    stats["parity_of_capped_candidate"] = same_science(reference(), capped)
    path = report / "io-summary.json"
    save_json(path, stats)
    lock = report / "prediction-lock.json"
    value = json.loads(lock.read_bytes())
    value["files"][path.name] = _sha(path)
    save_json(lock, value)
    figures(report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "replay", "cap", "publish"))
    for name, default in (("report", REPORT), ("runs", RUNS), ("raw", working_memory_trial.RAW)):
        parser.add_argument(f"--{name}", type=local_output, default=default)
    args = parser.parse_args()
    if args.action == "seal":
        path = args.report / "source-lock.json"
        if path.exists() and json.loads(path.read_bytes()) != source():
            raise ValueError("the preregistered source changed")
        if not path.exists():
            save_json(path, source())
        return
    with (
        patch.multiple(
            apparatus,
            CPU=CPU,
            WORKER=WORKER,
            seal=source,
            reference=reference,
            same_science=same_science,
        ),
        patch.multiple(v5_composed_memory, METHOD=tiled.METHOD, BOUNDARY=tiled.BOUNDARY),
    ):
        if args.action == "replay":
            if os.getpriority(os.PRIO_PROCESS, 0) < discovery.NICE:
                raise ValueError("use nice +10 or lower priority")
            apparatus.replay(args.runs, args.report, args.raw)
        elif args.action == "cap":
            discovery.cap(args.runs, args.report)
        else:
            publish(args.runs, args.report)


if __name__ == "__main__":
    main()
