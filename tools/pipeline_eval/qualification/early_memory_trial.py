"""Run same-input early-memory qualification before independent geographic scoring."""

import argparse
import gzip
import json
import os
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
from time import perf_counter

from ..__main__ import ROOT, encoded, local_output, references, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from ..variants import orbit_projector, v5_lean, v5_track_projection
from . import stream_recovery_publish, stream_recovery_trial, working_memory_trial
from .full_v5_check import _sha
from .prefix_figures import csv_file

REPORT = ROOT / "reports/2026_11_19_receiver_screening/factors/early-memory"
RUNS = Path("/srv/bulk/leo-dev/receiver-screening-20261119/early-memory")
WORKER = Path(__file__).with_name("early_memory_worker.py")
METHODS = {"control": "v5_armijo_aligned_finish", "track": v5_track_projection.METHOD}
PLAN = {"DS26-0036": (10, ("control", "track")), "DS29-0082": (11, ("track", "control"))}
CAP = 480
MEASUREMENTS = {
    "compact_projections",
    "original_grid_bytes_at_largest_shape",
    "max_prepared_bytes",
    "early_memory",
}


def source_lock():
    previous = stream_recovery_trial.seal()["source"]
    directory = v5_lean.SOURCE / "leo/analysis/localization_v3"
    files = (
        Path(__file__),
        WORKER,
        Path(v5_track_projection.__file__),
        *(directory / (m + ".py") for m in ("scan", "family_weighting", "discovery")),
    )
    return dict(
        sources=dict(previous, **{p.name: _sha(p) for p in files}),
        frozen=v5_lean.SOURCE_SHA256,
        protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
        whole_iq_lock=_sha(working_memory_trial.PRIOR / "prediction-lock.json"),
        plan={c: [cpu, list(order)] for c, (cpu, order) in PLAN.items()},
        cap_s=CAP,
    )


def replay(case, runs, report, raw):
    seal = json.loads((report / "source-lock.json").read_bytes())
    if seal != source_lock():
        raise ValueError("the code differs from the preregistered source seal")
    cpu, order = PLAN[case]
    if os.sched_getaffinity(0) != {cpu}:
        raise ValueError(f"pin both workers to CPU {cpu}")
    binding, provenance = working_memory_trial.case_binding("ordinary-" + case, raw)
    request_sha = working_memory_trial.canonical_request(Path(binding["request_path"]))
    v5_lean.TIMEOUT_S = CAP
    for mode in order:
        out = runs / case / mode
        path = out / "prediction.json"
        if path.exists():
            continue
        out.mkdir(parents=True, exist_ok=True)
        library = out / "orbit_projector.so"
        orbit_projector.compile_kernel(library)
        begin, before = perf_counter(), getrusage(RUSAGE_CHILDREN)
        value = v5_lean.run_bound_worker(binding, out, WORKER, worker_args=(str(library), mode))
        elapsed, after = perf_counter() - begin, getrusage(RUSAGE_CHILDREN)
        output_request = out / "request.json"
        if (
            working_memory_trial.canonical_request(output_request) != request_sha
            or seal != source_lock()
        ):
            raise ValueError("request or source changed")
        if "exceeded its " in (value.get("reason") or ""):
            value["status"] = "timed_out"
        validate_result(value)
        save_json(
            path,
            dict(
                id=case,
                method=METHODS[mode],
                mode="matched-tile",
                tile=binding["regions"][0],
                input_sha256=request_sha,
                request_sha256=_sha(output_request),
                cpu=cpu,
                worker_wall_s=elapsed,
                worker_cpu_s=after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime,
                result=value,
                **provenance,
            ),
        )
        print(case, mode, value["status"], round(elapsed, 2), flush=True)


def compare(control, candidate):
    comparison = stream_recovery_publish.publication_comparison(
        stream_recovery_trial.compare, control, candidate
    )
    if comparison["status"] != ["ok", "ok"]:
        return comparison
    extra = set(comparison["decision_difference_keys"]) & MEASUREMENTS
    comparison["resource_difference_keys"] += sorted(extra)
    comparison["decision_difference_keys"] = sorted(
        set(comparison["decision_difference_keys"]) - extra
    )
    comparison["decisions_exact"] = not comparison["decision_difference_keys"]
    a, b = [r["result"]["metrics"]["early_memory"]["stages"] for r in (control, candidate)]
    comparison["early_evidence_exact"] = {
        stage: a[stage]["decision_sha256"] == b[stage]["decision_sha256"] for stage in a
    }
    return comparison


def publish(runs, report):
    pairs = {
        case: [
            json.loads((runs / case / role / "prediction.json").read_bytes()) for role in METHODS
        ]
        for case in PLAN
    }
    files = {}
    decisions = {case: compare(*rows) for case, rows in pairs.items()}
    for i, role in enumerate(METHODS):
        name = f"{role}-positions.jsonl.gz"
        archive = gzip.compress(
            b"".join(encoded(pair[i]) + b"\n" for pair in pairs.values()), mtime=0
        )
        write(report / name, archive)
        files[name] = _sha(report / name)
    save_json(report / "comparison.json", decisions)
    files["comparison.json"] = _sha(report / "comparison.json")
    save_json(
        report / "prediction-lock.json",
        dict(cases=list(PLAN), files=files, source_lock_sha256=_sha(report / "source-lock.json")),
    )
    print(json.dumps(decisions, indent=2))


def score(report):
    lock = json.loads((report / "prediction-lock.json").read_bytes())
    if any(_sha(report / n) != expected for n, expected in lock["files"].items()):
        raise ValueError("predictions changed before scoring")
    cases = {
        c: references(panel, [c])[1][0]["truth"]
        for c, panel in zip(PLAN, ("ds26-common127", "roof16"), strict=True)
    }
    rows = []
    for mode in METHODS:
        data = gzip.decompress((report / f"{mode}-positions.jsonl.gz").read_bytes())
        for row in map(json.loads, data.splitlines()):
            result = row["result"]
            for arm in ARMS:
                rows.append(
                    dict(
                        id=row["id"],
                        method=row["method"],
                        arm=arm,
                        status=result["status"],
                        error_km=distance_km(cases[row["id"]], result["arms"][arm]["latlon"]),
                        conditional_rms_hz=result["metrics"].get(arm + "_conditional_rms_hz"),
                        frequency_objective=result["metrics"].get(arm + "_frequency_score"),
                    )
                )
    csv_file(report / "scores.csv", rows)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("seal", "replay", "publish", "score"))
    p.add_argument("--case", choices=PLAN)
    for name, default in (("report", REPORT), ("runs", RUNS), ("raw", working_memory_trial.RAW)):
        p.add_argument("--" + name, type=local_output, default=default)
    args = p.parse_args()
    if args.action == "seal":
        path = args.report / "source-lock.json"
        if path.exists() and json.loads(path.read_bytes()) != source_lock():
            raise ValueError("refuse to replace a source seal")
        if not path.exists():
            save_json(path, source_lock())
    elif args.action == "replay":
        if not args.case:
            p.error("--case required")
        replay(args.case, args.runs, args.report, args.raw)
    elif args.action == "publish":
        publish(args.runs, args.report)
    else:
        score(args.report)


if __name__ == "__main__":
    main()
