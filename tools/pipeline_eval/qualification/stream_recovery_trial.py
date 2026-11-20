"""Run and seal the same-input complete-recovery memory comparison."""

import argparse
import gzip
import json
import os
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
from time import perf_counter

from ..__main__ import ROOT, encoded, local_output, references, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from ..variants import (
    compact_finish,
    orbit_projector,
    v5_armijo_aligned_finish,
    v5_armijo_finish,
    v5_armijo_fit,
    v5_core,
    v5_lean,
    v5_stream_recovery,
)
from . import working_memory_trial
from .full_v5_check import _sha
from .prefix_figures import csv_file

REPORT = ROOT / "reports/2026_11_19_receiver_screening/inference/stream-recovery"
RUNS = Path("/srv/bulk/leo-dev/receiver-screening-20261119/stream-recovery")
WORKER = Path(__file__).with_name("stream_recovery_worker.py")
METHODS = {"control": "v5_armijo_aligned_finish", "stream": v5_stream_recovery.METHOD}
PLAN = {
    "DS26-0036": (10, ("control", "stream")),
    "DS29-0082": (11, ("stream", "control")),
}
CAP = 480


def seal():
    modules = (
        v5_stream_recovery,
        v5_armijo_aligned_finish,
        v5_armijo_finish,
        v5_armijo_fit,
        compact_finish,
        orbit_projector,
        v5_lean,
        v5_core,
    )
    frozen = v5_lean.SOURCE / "leo/analysis/localization_v3"
    paths = [
        Path(__file__),
        WORKER,
        orbit_projector.KERNEL,
        WORKER.with_name("working_memory_trial.py"),
        WORKER.with_name("working_memory_worker.py"),
        WORKER.with_name("armijo_finish_phase_retry.py"),
        WORKER.with_name("batched_salvage_eval.py"),
        *(Path(m.__file__) for m in modules),
        *(
            frozen / f"{n}.py"
            for n in (
                "orbits",
                "residual_screen",
                "reassociation_catalogue",
                "reassociation_screen",
                "screen_geometry",
            )
        ),
    ]
    return dict(
        source={p.name: _sha(p) for p in paths},
        frozen=v5_lean.SOURCE_SHA256,
        protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
        whole_iq_lock=_sha(working_memory_trial.PRIOR / "prediction-lock.json"),
        plan={c: [cpu, list(order)] for c, (cpu, order) in PLAN.items()},
        cap_s=CAP,
    )


def run(case, runs, raw, report):
    source = json.loads((report / "source-lock.json").read_bytes())
    if source != seal():
        raise ValueError("source differs from the preregistered lock")
    cpu, order = PLAN[case]
    if os.sched_getaffinity(0) != {cpu}:
        raise ValueError(f"pin the two workers to CPU {cpu}")
    binding, provenance = working_memory_trial.case_binding("ordinary-" + case, raw)
    request_sha = working_memory_trial.canonical_request(Path(binding["request_path"]))
    v5_lean.TIMEOUT_S = CAP
    for mode in order:
        out = runs / case / mode
        row_path = out / "prediction.json"
        if row_path.exists():
            continue
        out.mkdir(parents=True, exist_ok=True)
        lib = out / "orbit_projector.so"
        orbit_projector.compile_kernel(lib)
        before = getrusage(RUSAGE_CHILDREN)
        start = perf_counter()
        result = v5_lean.run_bound_worker(binding, out, WORKER, worker_args=(str(lib), mode))
        wall, after = perf_counter() - start, getrusage(RUSAGE_CHILDREN)
        if working_memory_trial.canonical_request(out / "request.json") != request_sha:
            raise ValueError("replay did not use the original complete ordinary-factor request")
        if result.get("reason") and "exceeded its " in result["reason"]:
            result["status"] = "timed_out"
        validate_result(result)
        if source != seal():
            raise ValueError("sources changed during the execution")
        save_json(
            row_path,
            dict(
                id=case,
                method=METHODS[mode],
                mode="matched-tile",
                tile=binding["regions"][0],
                input_sha256=request_sha,
                request_sha256=_sha(out / "request.json"),
                cpu=cpu,
                worker_wall_s=wall,
                worker_cpu_s=after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime,
                result=result,
                **provenance,
            ),
        )
        print(case, mode, result["status"], round(wall, 2), flush=True)


def compare(control, stream):
    keys = ("id", "tile", "detector", "input_sha256", "native_sha256", "catalog_sha256", "cpu")
    if any(control[k] != stream[k] for k in keys):
        raise ValueError("inference inputs differ in a paired receipt")
    results = [r["result"] for r in (control, stream)]
    pair = dict(status=[r["status"] for r in results])
    if pair["status"] != ["ok", "ok"]:
        return pair
    metrics = [r["metrics"] for r in results]
    measurements = [m["stream_recovery_measurement"] for m in metrics]
    banks = [m["banks"] for m in measurements]

    def states(blobs):
        return [{k: v for k, v in b.items() if k != "scratch_bytes"} for b in blobs]

    skip = {"stage_s", "candidate_s", "stream_recovery_measurement", "position_optimizer"}
    numbers = [{k: v for k, v in m.items() if k not in skip} for m in metrics]
    pair.update(
        endpoints_exact=results[0]["arms"] == results[1]["arms"],
        decisions_exact=numbers[0] == numbers[1],
        decision_difference_keys=sorted(
            k
            for k in numbers[0].keys() | numbers[1].keys()
            if numbers[0].get(k) != numbers[1].get(k)
        ),
        ordered_eligible_states_exact=states(banks[0]["ecef_states"])
        == states(banks[1]["ecef_states"]),
        propagation_audit_exact=banks[0].get("audit") == banks[1].get("audit"),
        residual_shortlists_exact=banks[0].get("screen_candidates")
        == banks[1].get("screen_candidates"),
        reassociation_nomination_exact=banks[0].get("screen") == banks[1].get("screen"),
        conditional_rms_exact={
            a: numbers[0].get(a + "_conditional_rms_hz")
            == numbers[1].get(a + "_conditional_rms_hz")
            for a in ARMS
        },
    )
    return pair


def publish(runs, report):
    pairs = {
        case: [
            json.loads((runs / case / mode / "prediction.json").read_bytes()) for mode in METHODS
        ]
        for case in PLAN
    }
    decisions = {case: compare(*rows) for case, rows in pairs.items()}
    files = {}
    for i, mode in enumerate(METHODS):
        name = f"{mode}-positions.jsonl.gz"
        write(
            report / name,
            gzip.compress(b"".join(encoded(r[i]) + b"\n" for r in pairs.values()), mtime=0),
        )
        files[name] = _sha(report / name)
    save_json(report / "comparison.json", decisions)
    files["comparison.json"] = _sha(report / "comparison.json")
    save_json(
        report / "prediction-lock.json",
        dict(cases=list(PLAN), files=files, source_lock_sha256=_sha(report / "source-lock.json")),
    )
    return decisions


def score(report):
    lock = json.loads((report / "prediction-lock.json").read_bytes())
    if any(_sha(report / n) != expected for n, expected in lock["files"].items()):
        raise ValueError("predictions changed before scoring")
    truth = {
        c: references(panel, [c])[1][0]["truth"]
        for c, panel in zip(PLAN, ("ds26-common127", "roof16"), strict=True)
    }
    rows = []
    for mode in METHODS:
        pool = gzip.decompress((report / f"{mode}-positions.jsonl.gz").read_bytes()).splitlines()
        for row in map(json.loads, pool):
            r = row["result"]
            for a in ARMS:
                rows.append(
                    dict(
                        id=row["id"],
                        method=row["method"],
                        arm=a,
                        status=r["status"],
                        error_km=distance_km(truth[row["id"]], r["arms"][a]["latlon"]),
                        conditional_rms_hz=r["metrics"].get(a + "_conditional_rms_hz"),
                        objective=r["metrics"].get(a + "_frequency_score"),
                    )
                )
    csv_file(report / "scores.csv", rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "replay", "publish", "score"))
    parser.add_argument("--case", choices=PLAN)
    for name, default in (("runs", RUNS), ("report", REPORT), ("raw", working_memory_trial.RAW)):
        parser.add_argument("--" + name, type=local_output, default=default)
    args = parser.parse_args()
    if args.action == "seal":
        path = args.report / "source-lock.json"
        if path.exists() and json.loads(path.read_bytes()) != seal():
            raise ValueError("refuse to replace scientific source lock")
        if not path.exists():
            save_json(path, seal())
    elif args.action == "replay":
        if not args.case:
            parser.error("--case is required")
        run(args.case, args.runs, args.raw, args.report)
    elif args.action == "publish":
        print(json.dumps(publish(args.runs, args.report), indent=2))
    else:
        score(args.report)


if __name__ == "__main__":
    main()
