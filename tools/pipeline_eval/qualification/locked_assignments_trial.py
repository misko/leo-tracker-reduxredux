"""Freeze and run the two matched-support assignments on the authentic receiver."""

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic
from uuid import uuid4

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from . import cavity_pressure_trial, rescue_attribution
from .fractional_runtime_whole import verify_request
from .full_v5_check import _sha

REPORT = rescue_attribution.REPORT.parent.parent / "support-preserving/locked-assignments"
PINS = {"DS26-0168": 14, "DS29-0604": 15}
LIMIT = 250
HERE = Path(__file__).parent
WORKER = HERE / "locked_assignments_worker.py"


def sources():
    paths = (
        Path(__file__),
        WORKER,
        HERE / "locked_assignments.py",
        HERE / "ranked_fit_probe.py",
        REPORT / "PROTOCOL.md",
        Path(cavity_pressure_trial.__file__),
    )
    return {str(p.relative_to(ROOT)): _sha(p) for p in paths}


def stage(work, raw, union):
    work.mkdir(exist_ok=False)
    if (REPORT / "plan.json").exists():
        raise FileExistsError("matched-assignment panel is already sealed")
    parent = rescue_attribution.parent
    parent_lock = parent.REPORT / "figure-lock.json"
    parent_plan = whole_iq.read(
        rescue_attribution.sealed(parent.REPORT, "prediction-lock.json", "plan.json")
    )
    if whole_iq.receiver_identity(Path(parent_plan["receiver"])) != parent_plan["receiver_files"]:
        raise ValueError("installed numerical release differs from the measured parent")
    bindings = {}
    for spec in parent_plan["scheduled"]:
        ident = spec["id"]
        _, request = whole_iq.binding(ident)
        cells = {}
        for role, directory, native_sha, prepared_sha in (
            (
                "stock",
                raw / ident / "control",
                spec["stock_native_sha256"],
                spec["raw_parents"]["control"]["files"]["recording/request.json"],
            ),
            (
                "union",
                union / ident / "rescue",
                spec["native_sha256"],
                spec["prepared_request_sha256"],
            ),
        ):
            native = whole_iq.checked(directory / "recording/native.json", native_sha)
            native_request = whole_iq.checked(directory / "recording/request.json", prepared_sha)
            verify_request(
                whole_iq.read(native_request), request, native_path=native, native_sha256=native_sha
            )
            cells[role] = dict(
                native=str(native),
                native_sha256=native_sha,
                request=str(native_request),
                request_sha256=prepared_sha,
            )
        bindings[ident] = dict(
            inputs=cells,
            catalogue=spec["catalog_sha256"],
            tile=spec["tile"],
            original_request_sha256=spec["original_request_sha256"],
        )
    if bindings.keys() != PINS.keys():
        raise ValueError("same two parent recordings required")
    save_json(
        REPORT / "plan.json",
        dict(
            cases=bindings,
            sources=sources(),
            receiver=parent_plan["receiver"],
            receiver_files=parent_plan["receiver_files"],
            parent_sha256=_sha(parent_lock),
            pins=PINS,
            limit_s=LIMIT,
            memory_bytes=whole_iq.MEMORY,
            swap_bytes=0,
        ),
    )
    print("Frozen matched assignment plan", _sha(REPORT / "plan.json"), flush=True)


def service(work, ident, role, plan):
    bound = plan["cases"][ident]["inputs"][role]
    for field in ("native", "request"):
        whole_iq.checked(Path(bound[field]), bound[f"{field}_sha256"])
    planfile = REPORT / "plan.json"
    path = work / ident / role
    path.mkdir(parents=True, exist_ok=False)
    union = path.parent / "union" / "capture.json"
    unit = "leo-locked-assignment-" + uuid4().hex[:10]
    cpu = PINS[ident]
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        "--collect",
        f"--unit={unit}",
        f"--working-directory={plan['receiver']}",
        f"--property=MemoryMax={whole_iq.MEMORY}",
        "--property=MemorySwapMax=0",
        "--property=Nice=10",
        "--property=KillMode=control-group",
        f"--property=RuntimeMaxSec={LIMIT}s",
        f"--setenv=TMPDIR={path}",
        "taskset",
        "-c",
        str(cpu),
        sys.executable,
        "-IB",
        str(WORKER),
        plan["receiver"],
        str(path),
        str(cpu),
        role,
        str(union),
        *cavity_pressure_trial.command_flags(bound),
    ]
    log = path / "service.log"
    start = monotonic()
    with log.open("xb") as stream:
        status = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=False)
    receipt = [
        line.strip()
        for line in log.read_text(errors="replace").splitlines()
        if line.strip().startswith(("Finished with result:", "Memory peak:", "CPU time consumed:"))
    ]
    files = ("service.log", "capture.json", "refits.json", "resources.json")
    result = dict(
        id=ident,
        role=role,
        status=status.returncode,
        cpu=cpu,
        service=receipt,
        source_plan_sha256=_sha(planfile),
        input=bound,
        supervisor_wall_s=monotonic() - start,
        files={n: _sha(path / n) for n in files if (path / n).is_file()},
    )
    if role == "stock" and union.is_file():
        result["union_assignment_sha256"] = _sha(union)
    save_json(path / "attempt.json", result)
    print(ident, role, status.returncode, round(result["supervisor_wall_s"], 1), flush=True)
    return result


def run(work):
    plan = whole_iq.read(REPORT / "plan.json")
    if (
        sources() != plan["sources"]
        or whole_iq.receiver_identity(Path(plan["receiver"])) != plan["receiver_files"]
    ):
        raise ValueError("prespecified sources or authentic solver changed")

    def lane(ident):
        union = service(work, ident, "union", plan)
        return [union, service(work, ident, "stock", plan)]

    with ThreadPoolExecutor(2) as threads:
        attempts = [row for lane in threads.map(lane, PINS) for row in lane]
    save_json(REPORT / "attempts.json", attempts)
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=list(PINS),
            files={name: _sha(REPORT / name) for name in ("plan.json", "attempts.json")},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--raw", type=Path, default=rescue_attribution.parent.DEFAULT_RAW)
    parser.add_argument("--union", type=Path, default=rescue_attribution.PARENT_WORK)
    arguments = parser.parse_args()
    stage(arguments.work, arguments.raw, arguments.union)
    run(arguments.work)
