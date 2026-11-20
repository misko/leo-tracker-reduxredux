"""Exercise the same complete composed v5 worker with and without a Linux memory cap."""

import argparse
import gzip
import json
import os
import subprocess
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
from time import perf_counter
from uuid import uuid4

from ..__main__ import ROOT, encoded, local_output, references, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from ..variants import (
    orbit_projector,
    v5_composed_memory,
    v5_lean,
    v5_stream_recovery,
    v5_track_projection,
)
from . import solver_memory_trial, working_memory_trial
from .full_v5_check import _sha
from .prefix_figures import csv_file

REPORT = ROOT / "reports/2026_11_19_receiver_screening/recovery/composed-memory"
PRIOR = REPORT.parent / "solver-memory"
RUNS = Path("/srv/bulk/leo-dev/receiver-screening-20261119/composed-memory")
WORKER = Path(__file__).with_name("composed_memory_worker.py")
CASE = "DS29-0082"
CPU = 17
MEMORY = 512 * 1024**2


def seal():
    upstream = solver_memory_trial.source()
    if json.loads((PRIOR / "source-lock.json").read_bytes()) != upstream:
        raise ValueError("the component solver sources differ from their earlier lock")
    paths = (
        Path(__file__),
        WORKER,
        *(Path(m.__file__) for m in (v5_composed_memory, v5_track_projection, v5_stream_recovery)),
    )
    return dict(
        source=dict(upstream["sources"], **{p.name: _sha(p) for p in paths}),
        frozen=v5_lean.SOURCE_SHA256,
        protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
        comparison_lock_sha256=_sha(PRIOR / "prediction-lock.json"),
        native_receipt_lock=upstream["whole_iq_lock"],
        cpu=CPU,
        case=CASE,
        memory_max_bytes=MEMORY,
    )


def locked(report):
    if json.loads((report / "source-lock.json").read_bytes()) != seal():
        raise ValueError("composition source differs from the preregistered lock")


def reference():
    lock = json.loads((PRIOR / "prediction-lock.json").read_bytes())
    path = PRIOR / "tile-positions.jsonl.gz"
    if _sha(path) != lock["files"][path.name]:
        raise ValueError("comparison prediction archive differs")
    return next(
        r
        for r in map(json.loads, gzip.decompress(path.read_bytes()).splitlines())
        if r["id"] == CASE
    )


def same_science(stock, composed):
    for field in ("id", "input_sha256", "native_sha256", "catalog_sha256", "tile", "detector"):
        if stock[field] != composed[field]:
            raise ValueError(f"candidate has a different scientific input field {field}")
    a, b = stock["result"], composed["result"]
    if a["status"] != "ok" or b["status"] != "ok":
        return dict(control_status=a["status"], candidate_status=b["status"])
    s, t = a["metrics"], b["metrics"]
    prepared = s["prep_stream_measurement"]["evidence"]
    earlier = s["early_memory"]["stages"]
    late = s["stream_recovery_measurement"]["banks"]
    measured = t["composed_memory_measurement"]["evidence"]
    banks = [
        {k: v for k, v in row.items() if k != "scratch_bytes"}
        for row in t["bounded_recovery_rows"]["ecef"]
    ]
    same = dict(
        graph=measured["prepare_tracks"] == [prepared["graph"]],
        sky=measured["prepare_initial_sky"]
        == [dict(data=prepared["regional_bank"]["data"], priors=prepared["initial_sky"])],
        history=measured["prepare_phase_history"] == [prepared["phase_history"]],
        forecast=measured["forecast"] == [prepared["phase_forecast"]],
        noise=measured["estimate_noise"] == [prepared["noise"]],
        ranked=measured["ranked_initial_nodes"] == [earlier["ranked_initial"]["decision_sha256"]],
        family=measured["confidence_for"] == [earlier["family_confidence"]["decision_sha256"]],
        salvage=measured["salvage"] == s["solver_memory"]["outcomes"]
        and t["tiled_salvage"]["shortlists"] == s["solver_memory"]["shortlisted"],
        ordered_recovery_states=banks
        == [{k: v for k, v in row.items() if k != "scratch_bytes"} for row in late["ecef_states"]],
        residual=measured["screen_candidates"] == late["screen_candidates"],
        propagation_audit=measured["audit"] == late["audit"],
        reassociation=measured["screen"] == late["screen"],
        endpoints=a["arms"] == b["arms"],
        optimizer_counts=all(
            s["position_optimizer"][k] == t["position_optimizer"][k]
            for k in s["position_optimizer"]
            if k != "wall_s"
        ),
    )
    keys = ("conditional_rms_hz", "frequency_score", "associated_observations")
    same.update(
        {
            f"{arm}_{field}": s.get(f"{arm}_{field}") == t.get(f"{arm}_{field}")
            for arm in ARMS
            for field in keys
        }
    )
    return dict(
        control_status=a["status"],
        candidate_status=b["status"],
        equal=same,
        exact=all(same.values()),
    )


def replay(runs, report, raw):
    locked(report)
    if os.sched_getaffinity(0) != {CPU}:
        raise ValueError(f"pin this worker to CPU {CPU}")
    binding, native = working_memory_trial.case_binding("ordinary-" + CASE, raw)
    archive = reference()
    request_sha = working_memory_trial.canonical_request(Path(binding["request_path"]))
    if (
        archive["input_sha256"] != request_sha
        or archive["native_sha256"] != native["native_sha256"]
    ):
        raise ValueError("archive and fresh whole-IQ-derived scientific request differ")
    out = runs / "uncapped"
    out.mkdir(parents=True, exist_ok=False)
    lib = out / "orbit_projector.so"
    orbit_projector.compile_kernel(lib)
    v5_lean.TIMEOUT_S = 240
    wall, before = perf_counter(), getrusage(RUSAGE_CHILDREN)
    result = v5_lean.run_bound_worker(binding, out, WORKER, worker_args=(str(lib),))
    elapsed, after = perf_counter() - wall, getrusage(RUSAGE_CHILDREN)
    prepared = out / "request.json"
    if working_memory_trial.canonical_request(prepared) != request_sha:
        raise ValueError("fresh request changed")
    validate_result(result)
    locked(report)
    row = dict(
        id=CASE,
        method=v5_composed_memory.METHOD,
        mode="matched-tile",
        cpu=CPU,
        tile=binding["regions"][0],
        input_sha256=request_sha,
        request_sha256=_sha(prepared),
        worker_wall_s=elapsed,
        worker_cpu_s=after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime,
        result=result,
        **native,
    )
    save_json(out / "prediction.json", row)
    print(json.dumps(same_science(archive, row), indent=2), flush=True)


def memory_cap(runs, report):
    locked(report)
    uncapped = runs / "uncapped"
    row = json.loads((uncapped / "prediction.json").read_bytes())
    if not same_science(reference(), row).get("exact"):
        raise ValueError("exact unrestricted replay required before imposing the cap")
    request, lib = uncapped / "request.json", uncapped / "orbit_projector.so"
    if _sha(request) != row["request_sha256"]:
        raise ValueError("unrestricted request changed")
    out = runs / "capped"
    out.mkdir(parents=True, exist_ok=False)
    raw = json.loads(request.read_bytes())
    raw["job"]["output_root"] = str(out)
    bound, output = out / "request.json", out / "result.json"
    save_json(bound, raw)
    if working_memory_trial.canonical_request(bound) != row["input_sha256"]:
        raise ValueError("memory cap would use a different request")
    unit = f"leo-compose-512m-{uuid4().hex[:12]}"
    properties = (
        f"MemoryMax={MEMORY}",
        "MemorySwapMax=0",
        "RuntimeMaxSec=180s",
        "MemoryAccounting=yes",
        "KillMode=control-group",
    )
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        "--unit",
        unit,
        f"--working-directory={ROOT}",
        *(f"--property={p}" for p in properties),
        f"--setenv=PYTHONPATH={v5_lean.SOURCE}:{v5_lean.RUNNER}:{ROOT}",
        "--setenv=OPENBLAS_NUM_THREADS=1",
        "--setenv=OMP_NUM_THREADS=1",
        "--setenv=MKL_NUM_THREADS=1",
        "/usr/bin/taskset",
        "-c",
        str(CPU),
        str(v5_lean.PYTHON),
        "-B",
        str(WORKER),
        str(bound),
        str(output),
        str(lib),
    ]
    started = perf_counter()
    finished = subprocess.run(command, text=True, capture_output=True, timeout=195, check=False)
    elapsed = perf_counter() - started
    wanted = (
        "Result",
        "ExecMainCode",
        "ExecMainStatus",
        "MemoryPeak",
        "MemoryMax",
        "MemorySwapMax",
        "CPUUsageNSec",
        "ActiveState",
    )
    status = subprocess.run(
        ["systemctl", "--user", "show", unit, *("-p" + k for k in wanted)],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    systemd = dict(line.split("=", 1) for line in status.stdout.splitlines() if "=" in line)
    trace = [line for line in finished.stdout.splitlines() if line.startswith("stage: ")]
    receipt = dict(
        id=CASE,
        source_lock_sha256=_sha(report / "source-lock.json"),
        worker_sha256=_sha(WORKER),
        native_sha256=row["native_sha256"],
        scientific_request_sha256=row["input_sha256"],
        unit=unit,
        controls=list(properties),
        cpu=CPU,
        systemd=systemd,
        completed_result=output.is_file(),
        exit_code=finished.returncode,
        stage_trace=trace,
        service_log=finished.stderr[-3000:],
    )
    save_json(report / "memory-cap.json", receipt)
    result = (
        json.loads(output.read_bytes())
        if output.is_file()
        else dict(
            status="timed_out" if systemd.get("Result") == "timeout" else "failed",
            reason=systemd.get("Result", "memory-cap launch failed"),
            boundary=v5_composed_memory.BOUNDARY,
            metrics=dict(
                position_attempted=bool(trace),
                last_stage=trace[-1] if trace else None,
                memory_max_bytes=MEMORY,
            ),
            arms={a: {"latlon": None} for a in ARMS},
        )
    )
    validate_result(result)
    save_json(
        out / "prediction.json",
        dict(
            row,
            mode="memory-cap",
            request_sha256=_sha(bound),
            worker_wall_s=elapsed,
            worker_cpu_s=float(systemd["CPUUsageNSec"]) / 1e9
            if systemd.get("CPUUsageNSec", "").isdigit()
            else None,
            result=result,
        ),
    )
    print(json.dumps(receipt, indent=2), flush=True)


def publish(runs, report):
    locked(report)
    base = reference()
    free, capped = (
        json.loads((runs / mode / "prediction.json").read_bytes())
        for mode in ("uncapped", "capped")
    )
    files = {}
    for name, row in (("control", base), ("uncapped", free), ("capped", capped)):
        path = report / f"{name}-positions.jsonl.gz"
        write(path, gzip.compress(encoded(row) + b"\n", mtime=0))
        files[path.name] = _sha(path)
    save_json(report / "comparison.json", same_science(base, free))
    for artifact in ("memory-cap.json", "comparison.json"):
        files[artifact] = _sha(report / artifact)
    save_json(
        report / "prediction-lock.json",
        dict(cases=[CASE], files=files, source_lock_sha256=_sha(report / "source-lock.json")),
    )
    truth = references("roof16", [CASE])[1][0]["truth"]
    scores = []
    for row in (base, free, capped):
        r = row["result"]
        for arm in ARMS:
            scores.append(
                dict(
                    id=CASE,
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
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("seal", "replay", "cap", "publish"))
    for name, default in (("report", REPORT), ("runs", RUNS), ("raw", working_memory_trial.RAW)):
        p.add_argument("--" + name, type=local_output, default=default)
    args = p.parse_args()
    if args.action == "seal":
        path = args.report / "source-lock.json"
        if path.exists() and json.loads(path.read_bytes()) != seal():
            raise ValueError("refuse to replace a previous source seal")
        if not path.exists():
            save_json(path, seal())
    elif args.action == "replay":
        replay(args.runs, args.report, args.raw)
    elif args.action == "cap":
        memory_cap(args.runs, args.report)
    else:
        publish(args.runs, args.report)


if __name__ == "__main__":
    main()
