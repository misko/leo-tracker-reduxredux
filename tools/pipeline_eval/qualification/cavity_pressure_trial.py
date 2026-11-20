"""Replay exact stored factors under the deployment cap with stage pressure receipts."""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from time import monotonic, sleep, time_ns
from uuid import uuid4

from .. import whole_iq
from ..__main__ import local_output, save_json
from . import cavity_pressure_probe as probe
from . import direct_cavity_trial as direct
from .fractional_runtime_whole import verify_request

REPORT = direct.common.SCREEN / "detector-origins/pressure"
ORIGINAL = Path("/srv/bulk/leo-dev/whole-band-BCw8KqMY/DS29-0247/narrow")
PINS, LIMIT = {"DS29-0247": 12, "DS29-0082": 13}, 165
CONTROL, CANDIDATE = "v5_cavity_pressure_stock", "v5_cavity_pressure"


def bindings():
    prior = direct.common.read(ORIGINAL / "raw.json")
    receipt = direct.common.read(ORIGINAL / "service.json")
    log = ORIGINAL / "service.log"
    if (
        receipt["log_sha256"] != direct.common.sha(log)
        or receipt["systemd"]["Result"] != "oom-kill"
    ):
        raise ValueError("original whole-IQ failure is not the declared verified OOM")
    native, bound = (ORIGINAL / "recording" / name for name in ("native.json", "request.json"))
    if prior["native_sha256"] != "sha256:" + direct.common.sha(native) or prior[
        "request_sha256"
    ] != direct.common.sha(bound):
        raise ValueError("full recording output no longer binds the reserve request")
    case, original = whole_iq.binding("DS29-0247")
    verify_request(
        direct.common.read(bound),
        original,
        native_path=str(native),
        native_sha256=prior["native_sha256"],
    )
    reserve = dict(
        id=case["id"],
        native=str(native),
        request=str(bound),
        native_sha256=prior["native_sha256"].removeprefix("sha256:"),
        request_sha256=prior["request_sha256"],
        catalog_sha256=case["catalog"]["sha256"],
        tile=case["regions"][0],
        original_failure={"service": receipt, "position_start": prior["position_start"]},
    )
    ordinary, _, bound = direct.input_case("ordinary-DS29-0082")
    control = dict(
        bound,
        native=ordinary["native_path"],
        request=ordinary["request_path"],
        request_sha256=direct.common.sha(Path(ordinary["request_path"])),
    )
    return {d["id"]: d for d in (reserve, control)}


def sources():
    src = (Path(__file__).resolve(), Path(probe.__file__).resolve(), REPORT / "PROTOCOL.md")
    return {str(path): direct.common.sha(path) for path in src}


def lock(work):
    work.mkdir(exist_ok=False, parents=True)
    old = direct.common.read(ORIGINAL / "plan.json")
    runtime = Path(old["receiver"])
    if whole_iq.receiver_identity(runtime) != old["receiver_files"]:
        raise ValueError("actual failed whole receiver no longer matches its sealed install")
    save_json(
        work / "plan.json",
        dict(
            bindings=bindings(),
            source=sources(),
            runtime=str(runtime),
            files=old["receiver_files"],
            pins=PINS,
            memory=probe.MEMORY,
            swap=0,
            limit_s=LIMIT,
            frozen_ns=time_ns(),
        ),
    )


def command_flags(binding):
    job = direct.common.read(Path(binding["request"]))["job"]
    if job["evaluation_reference"] is not None:
        raise ValueError("truth found in pressure trial")
    return [
        "--native",
        binding["native"],
        "--native-sha256",
        binding["native_sha256"],
        "--session",
        job["identity"]["session_id"],
        "--track-config",
        job["track_config"]["path"],
        "--config-sha256",
        job["track_config"]["sha256"],
        "--archive",
        job["tle_root"],
        "--tile",
        *map(str, job["search_center"]),
        "--screen-center",
        *map(str, job["screen_center"]),
    ]


def run(work, ident, mode):
    from .direct_cavity_cap import systemd_fields

    lock = work / "plan.json"
    plan = direct.common.read(lock)
    cpu = plan["pins"][ident]
    if os.sched_getaffinity(0) != {cpu} or os.nice(0) < 10 or plan["source"] != sources():
        raise ValueError("pressure trial no longer matches its intended pin or source")
    binding = bindings()[ident]
    if binding != plan["bindings"][ident]:
        raise ValueError("recorded factor authority changed")
    if mode == CONTROL:
        root, manifest = Path(plan["runtime"]), plan["files"]
    else:
        published = direct.common.read(work / "candidate-lock.json")
        root, manifest = work / "candidate", published["files"]
    if whole_iq.receiver_identity(root) != manifest:
        raise ValueError("pressure receiver changed after seal")
    out = work / "runs" / ident / mode
    out.mkdir(exist_ok=False, parents=True)
    unit = "leo-pressure-" + uuid4().hex[:10]
    flags = command_flags(binding)
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        f"--unit={unit}",
        f"--working-directory={root}",
        f"--property=MemoryMax={probe.MEMORY}",
        "--property=MemorySwapMax=0",
        f"--property=RuntimeMaxSec={LIMIT}s",
        "--property=Nice=10",
        "--property=MemoryAccounting=yes",
        "--property=KillMode=control-group",
        f"--setenv=TMPDIR={out}",
        *(
            f"--setenv={k}=1"
            for k in (
                "OPENBLAS_NUM_THREADS",
                "OMP_NUM_THREADS",
                "MKL_NUM_THREADS",
                "BLIS_NUM_THREADS",
            )
        ),
        "taskset",
        "-c",
        str(cpu),
        str(direct.v5_lean.PYTHON),
        "-IB",
        str(Path(probe.__file__)),
        "observe",
        str(root),
        str(cpu),
        *flags,
    ]
    start, live, group = monotonic(), [], None
    result_file, service_log = out / "result.json", out / "service.log"
    with result_file.open("xb") as stdout, service_log.open("xb") as log:
        proc = subprocess.Popen(command, stdout=stdout, stderr=log)
        while proc.poll() is None and monotonic() - start < LIMIT + 5:
            group = group or systemd_fields(unit).get("ControlGroup")
            try:
                if group:
                    snap = probe.kernel(Path("/sys/fs/cgroup") / group.lstrip("/"))
                    live.append(dict(snap, monotonic_s=monotonic()))
            except FileNotFoundError:
                pass
            sleep(0.25)
        if proc.poll() is None:
            subprocess.run(["systemctl", "--user", "stop", unit], timeout=4, check=False)
        proc.wait(timeout=4)
    elapsed, kernel = monotonic() - start, systemd_fields(unit)
    text = service_log.read_text(errors="replace")
    terminal = re.search(r"Finished with result: (\S+)", text)
    status = terminal[1] if terminal else kernel.get("Result")
    stages = {k: [] for k in ("observer", "stage", "finish", "observer-end")}
    for line in text.splitlines():
        key, _, value = line.partition(" ")
        if key in stages:
            stages[key].append(json.loads(value))
    result = (
        direct.common.read(result_file)
        if proc.returncode == 0 and status == "success"
        else direct.v5_lean._no_fix(
            f"Linux capped service {status}",
            status="timed_out" if status == "timeout" else "failed",
        )
    )
    direct.validate_result(result)
    save_json(
        out / "attempt.json",
        dict(
            binding,
            method=mode,
            result=result,
            wall_s=elapsed,
            cpu=cpu,
            kernel=kernel,
            service_result=status,
            measurements=stages,
            live=live,
            bundle_files=manifest,
            plan_sha256=direct.common.sha(lock),
            log_sha256=direct.common.sha(service_log),
            returncode=proc.returncode,
        ),
    )
    print(ident, mode, result["status"], status, round(elapsed, 2), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=Path)
    p.add_argument("operation", choices=("lock", "run"))
    p.add_argument("case", nargs="?", choices=PINS)
    p.add_argument("method", nargs="?", choices=(CONTROL, CANDIDATE))
    a = p.parse_args()
    target = local_output(a.work)
    if a.operation == "lock":
        lock(target)
    else:
        run(target, a.case, a.method)
