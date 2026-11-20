"""Launch and account for full ordinary whole-IQ compact replay in one cgroup."""

import argparse
import gzip
import json
import os
import subprocess
import sys
from pathlib import Path
from time import perf_counter, sleep
from uuid import uuid4

from ..__main__ import ROOT, encoded, local_output, references, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from . import recovery_reads_trial, working_memory_trial
from . import whole_memory_chain_worker as chain
from .full_v5_check import NATIVE_LIBRARY, PRODUCERS, _load_case, _sha
from .prefix_figures import csv_file

REPORT = ROOT / "reports/2026_11_19_receiver_screening/integration/whole-memory-chain"
RUNS = Path("/srv/bulk/leo-dev/receiver-screening-20261119/whole-memory-chain")
CASES = ("DS29-0082", "DS26-0036")
PRIOR = working_memory_trial.PRIOR
CONTROLS = {
    "DS29-0082": (recovery_reads_trial.REPORT, "capped-positions.jsonl.gz", "v5_recovery_reads"),
    "DS26-0036": (
        ROOT / "reports/2026_11_19_receiver_screening/recovery/solver-memory",
        "tile-positions.jsonl.gz",
        "v5_tiled_salvage",
    ),
}


def sealed(directory, filename):
    lock = json.loads((directory / "prediction-lock.json").read_bytes())
    path = directory / filename
    if _sha(path) != lock["files"][filename]:
        raise ValueError(f"prior sealed artifact changed: {filename}")
    return path


def control(ident):
    directory, name, method = CONTROLS[ident]
    path = sealed(directory, name)
    return next(
        r
        for r in map(json.loads, gzip.decompress(path.read_bytes()).splitlines())
        if r["id"] == ident and r["method"] == method
    )


def plan():
    stage = sealed(PRIOR, "stage-receipts.json")
    receipts = json.loads(stage.read_bytes())
    row_major = recovery_reads_trial.REPORT / "source-lock.json"
    if json.loads(row_major.read_bytes()) != recovery_reads_trial.source():
        raise ValueError("row-major solver source differs from the qualification lock")
    inputs = {}
    for ident in CASES:
        row = receipts[ident]
        native = row["raw_replay"]
        request = working_memory_trial.RAW / ident / "secant" / "request.json"
        expected = _load_case(ident)
        archived = control(ident)
        if (
            not row["same_factors_as_prior_whole_iq"]
            or native["detector_sha256"] != "sha256:" + _sha(NATIVE_LIBRARY)
            or _sha(request) != row["paired_request_sha256"]["secant"]
            or native["recording_windows"] != expected["recording"]["window_count"]
            or archived["native_sha256"] != native["native_sha256"]
        ):
            raise ValueError("no matched ordinary replay authority")
        inputs[ident] = dict(
            native_sha256=native["native_sha256"],
            prior_request_path=str(request),
            prior_request_sha256=_sha(request),
            recording=expected["recording"],
            capture_era_native_sha256=expected["native"]["sha256"],
            control_method=archived["method"],
            control_sha256=_sha(sealed(*CONTROLS[ident][:2])),
        )
    sources = [
        Path(__file__),
        Path(chain.__file__),
        REPORT / "PROTOCOL.md",
        NATIVE_LIBRARY,
        stage,
        row_major,
    ]
    sources += [p.root / "leo/storage/short_window.py" for p in PRODUCERS.values()]
    sources += [
        ROOT / f"tools/pipeline_eval/qualification/{n}.py"
        for n in ("recording_to_v5", "capture_release", "recovery_reads_worker")
    ]
    return dict(
        inputs=inputs,
        sources={str(p): _sha(p) for p in sources},
        cpus=list(chain.CPUS),
        memory_bytes=chain.MEMORY,
        swap_bytes=0,
        nice=10,
        runtime_max_s=chain.LIMIT,
    )


def run(ident, runs):
    if json.loads((runs / "plan.json").read_bytes()) != plan():
        raise ValueError("saved-IQ chain differs from its source and input lock")
    unit = f"leo-whole-memory-{ident.lower()}-{uuid4().hex[:8]}"
    output = runs / ident
    if output.exists() or (runs / f"{ident}-systemd.log").exists():
        raise FileExistsError("use a fresh attempt path")
    command = [
        "systemd-run",
        "--user",
        "--pipe",
        "--wait",
        "--unit",
        unit,
        f"--working-directory={ROOT}",
        f"--property=MemoryMax={chain.MEMORY}",
        "--property=MemorySwapMax=0",
        "--property=Nice=10",
        f"--property=RuntimeMaxSec={chain.LIMIT}s",
        "--property=MemoryAccounting=yes",
        "--property=KillMode=control-group",
        "--setenv=OPENBLAS_NUM_THREADS=1",
        "--setenv=OMP_NUM_THREADS=1",
        "--setenv=MKL_NUM_THREADS=1",
        "/usr/bin/taskset",
        "-c",
        ",".join(map(str, chain.CPUS)),
        sys.executable,
        "-B",
        "-m",
        chain.__name__,
        "chain",
        ident,
        str(output),
    ]
    begin, samples = perf_counter(), []
    with (runs / f"{ident}-systemd.log").open("x") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        while process.poll() is None:
            try:
                group = (
                    Path("/sys/fs/cgroup/user.slice")
                    / f"user-{os.getuid()}.slice"
                    / f"user@{os.getuid()}.service"
                    / "app.slice"
                    / f"{unit}.service"
                )
                sample = {
                    k: int((group / k).read_text())
                    for k in (
                        "memory.max",
                        "memory.peak",
                        "memory.current",
                        "memory.swap.max",
                        "memory.swap.current",
                    )
                }
                if sample["memory.max"] == chain.MEMORY and sample["memory.swap.max"] == 0:
                    for k in ("cgroup.procs", "cpu.stat", "memory.events"):
                        sample[k] = (group / k).read_text().splitlines()
                    samples.append(dict(elapsed_s=perf_counter() - begin, **sample))
            except FileNotFoundError:
                pass
            sleep(1)
    elapsed = perf_counter() - begin
    status = subprocess.run(
        [
            "systemctl",
            "--user",
            "show",
            unit,
            "-pResult",
            "-pMemoryPeak",
            "-pCPUUsageNSec",
            "-pExecMainStatus",
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    save_json(
        runs / f"{ident}-service.json",
        dict(
            command=command,
            unit=unit,
            elapsed_s=elapsed,
            code=process.returncode,
            systemd=dict(s.split("=", 1) for s in status.stdout.splitlines() if "=" in s),
            samples=samples,
            log_sha256=_sha(runs / f"{ident}-systemd.log"),
        ),
    )
    print(ident, "service exit", process.returncode, round(elapsed, 2), flush=True)


def scientific_values(result):
    fields = ("conditional_rms_hz", "frequency_score", "associated_observations")
    return result["arms"], {
        f"{a}_{k}": result["metrics"].get(f"{a}_{k}") for a in ARMS for k in fields
    }


def summarize(runs, ident):
    service = json.loads((runs / f"{ident}-service.json").read_bytes())
    begin = json.loads((runs / f"{ident}-begin.json").read_bytes())["start"]
    folder = runs / ident
    raw_path, position_path = folder / "raw-stages.json", folder / "position-stages.json"
    raw = json.loads(raw_path.read_bytes()) if raw_path.is_file() else None
    position = json.loads(position_path.read_bytes()) if position_path.is_file() else None
    original = control(ident)
    if position is not None:
        result = json.loads((folder / "position/result.json").read_bytes())
        result["boundary"] = chain.BOUNDARY
        exact = scientific_values(result) == scientific_values(original["result"])
        if (
            not service["samples"]
            or any(
                x["cgroup"] != begin["cgroup"] or x["pid"] != begin["pid"]
                for x in position.values()
            )
            or position["start"]["cpus"] != [chain.CPUS[0]]
        ):
            raise ValueError(
                "position did not replace the raw supervisor in the same capped cgroup"
            )
    else:
        exact = False
        result = dict(
            status="failed",
            reason=service["systemd"].get("Result", "worker did not finish"),
            boundary=chain.BOUNDARY,
            arms={a: {"latlon": None} for a in ARMS},
            metrics={"position_attempted": (folder / "position/request.json").is_file()},
        )
    validate_result(result)
    visits = (
        []
        if raw is None
        else sorted(t for lane in raw["raw_lanes"] for t in lane["native_timings_s"])
    )
    timing = {}
    if visits:
        timing = dict(
            visit_count=len(visits),
            wall_median_ms=1000 * visits[len(visits) // 2][0],
            wall_p95_ms=1000 * visits[int(0.95 * (len(visits) - 1))][0],
            wall_at_most_20ms=sum(w <= 0.020 for w, c in visits),
            median_native_cpu_ms=1000 * sorted(c for w, c in visits)[len(visits) // 2],
        )
    case = _load_case(ident)
    actual = (
        position["end"]["monotonic_s"] - begin["monotonic_s"] if position else service["elapsed_s"]
    )
    row = dict(
        id=ident,
        method=chain.METHOD,
        mode="matched-tile",
        detector="ordinary",
        native_sha256=raw["native_sha256"] if raw else case["native"]["sha256"],
        input_sha256=original["input_sha256"],
        catalog_sha256=case["catalog"]["sha256"],
        tile=case["regions"][0],
        result=result,
        worker_wall_s=actual,
    )
    return row, dict(
        service=service,
        start=begin,
        raw=raw,
        position=position,
        visit_timing=timing,
        control_method=original["method"],
        exact_endpoints_and_radio=exact,
        capture_era_native_sha256=case["native"]["sha256"],
        service_log=(runs / f"{ident}-systemd.log").read_text(),
    )


def publish(runs, report):
    pins = json.loads((runs / "plan.json").read_bytes())
    if pins != plan():
        raise ValueError("source and complete input lock changed")
    ids = [ident for ident in CASES if (runs / f"{ident}-service.json").is_file()]
    if not ids:
        raise ValueError("no completed service receipts to publish")
    rows, evidence = [], {}
    for ident in ids:
        row, evidence[ident] = summarize(runs, ident)
        rows.append(row)
    save_json(report / "source-lock.json", pins)
    write(
        report / "positions.jsonl.gz",
        gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0),
    )
    write(report / "stages.json.gz", gzip.compress(encoded(evidence), mtime=0))
    files = ("positions.jsonl.gz", "stages.json.gz")
    save_json(
        report / "prediction-lock.json",
        dict(
            cases=ids,
            files={f: _sha(report / f) for f in files},
            source_lock_sha256=_sha(report / "source-lock.json"),
        ),
    )
    truth = {r["id"]: r["truth"] for r in references("roof16", ids)[1]}
    scores = []
    for r in rows:
        result = r["result"]
        for arm in ARMS:
            scores.append(
                dict(
                    id=r["id"],
                    arm=arm,
                    status=result["status"],
                    error_km=distance_km(truth[r["id"]], result["arms"][arm]["latlon"]),
                    conditional_rms_hz=result["metrics"].get(f"{arm}_conditional_rms_hz"),
                )
            )
    csv_file(report / "scores.csv", scores)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("seal", "run", "publish"))
    p.add_argument("--case", choices=CASES)
    p.add_argument("--runs", type=local_output, default=RUNS)
    args = p.parse_args()
    if args.action == "seal":
        args.runs.mkdir(parents=True, exist_ok=False)
        save_json(args.runs / "plan.json", plan())
    elif args.action == "run":
        if args.case is None:
            p.error("use --case for run")
        run(args.case, args.runs)
    else:
        publish(args.runs, REPORT)


if __name__ == "__main__":
    main()
