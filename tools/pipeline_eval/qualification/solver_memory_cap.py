"""Run one source-bound tiled worker in an isolated 512 MiB host memory cgroup."""

import argparse
import json
import subprocess
from pathlib import Path
from uuid import uuid4

from ..__main__ import ROOT, local_output, save_json
from ..variants import v5_lean
from .full_v5_check import _sha
from .solver_memory_trial import REPORT, RUNS, WORKER, source
from .working_memory_trial import canonical_request


def probe(work, report, runs, *, trace=False):
    source_path = report / "source-lock.json"
    if json.loads(source_path.read_bytes()) != source():
        raise ValueError("bounded replay source differs from scientific seal")
    reference = runs / "DS29-0082/tile"
    row = json.loads((reference / "prediction.json").read_bytes())
    request = reference / "request.json"
    lib = reference / "orbit_projector.so"
    if row["request_sha256"] != _sha(request) or row["input_sha256"] != canonical_request(request):
        raise ValueError("the matching ordinary request differs")
    work.mkdir(parents=True, exist_ok=False)
    raw = json.loads(request.read_bytes())
    raw["job"]["output_root"] = str(work)
    bound, output = work / "request.json", work / "result.json"
    save_json(bound, raw)
    if canonical_request(bound) != row["input_sha256"]:
        raise ValueError("capped worker has a different scientific request")

    unit = f"leo-salvage-512m-{uuid4().hex[:12]}"
    properties = (
        "MemoryMax=536870912",
        "MemorySwapMax=0",
        "RuntimeMaxSec=90s",
        "MemoryAccounting=yes",
        "CPUAccounting=yes",
        "KillMode=control-group",
    )
    script = WORKER.with_name("solver_memory_cap_trace.py") if trace else WORKER
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        "--unit",
        unit,
        f"--working-directory={ROOT}",
        *(f"--property={key}" for key in properties),
        f"--setenv=PYTHONPATH={v5_lean.SOURCE}:{v5_lean.RUNNER}:{ROOT}",
        "--setenv=OPENBLAS_NUM_THREADS=1",
        "--setenv=OMP_NUM_THREADS=1",
        "--setenv=MKL_NUM_THREADS=1",
        "/usr/bin/taskset",
        "-c",
        "5",
        str(v5_lean.PYTHON),
        "-B",
        str(script),
        str(bound),
        str(output),
        str(lib),
        "tile",
    ]
    result = subprocess.run(command, capture_output=True, check=False, text=True, timeout=105)
    fields = (
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
        ["systemctl", "--user", "show", unit, *("-p" + key for key in fields)],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    measured = dict(line.split("=", 1) for line in status.stdout.splitlines() if "=" in line)
    item = dict(
        id=row["id"],
        native_sha256=row["native_sha256"],
        scientific_request_sha256=row["input_sha256"],
        source_lock_sha256=_sha(source_path),
        probe_sha256=_sha(Path(__file__)),
        worker_sha256=_sha(script),
        host_cgroup=True,
        cpu=5,
        unit=unit,
        controls=list(properties),
        exit_code=result.returncode,
        completed_result=output.is_file(),
        systemd=measured,
        service_log=(result.stdout + result.stderr)[-3500:],
    )
    save_json(report / ("memory-cap-trace.json" if trace else "memory-cap.json"), item)
    print(json.dumps(item, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", type=local_output, required=True)
    p.add_argument("--report", type=local_output, default=REPORT)
    p.add_argument("--runs", type=local_output, default=RUNS)
    p.add_argument("--trace", action="store_true")
    args = p.parse_args()
    probe(args.work, args.report, args.runs, trace=args.trace)


if __name__ == "__main__":
    main()
