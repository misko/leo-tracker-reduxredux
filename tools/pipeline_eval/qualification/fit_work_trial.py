"""Same-core capped position comparison on authenticated saved narrow factors."""

import argparse
import os
import re
import subprocess
from pathlib import Path
from time import monotonic, sleep
from uuid import uuid4

from .. import whole_iq
from ..__main__ import local_output, save_json
from . import cavity_pressure_probe as meter
from . import cavity_pressure_trial as pressure
from .direct_cavity_cap import systemd_fields
from .fractional_runtime_whole import verify_request

COMMON = pressure.direct.common
BASE = Path("/srv/bulk/leo-dev/cp-v2")
WHOLE = pressure.ORIGINAL.parent.parent
REPORT = pressure.direct.common.SCREEN / "acquisition-support/fit-work"
CASES = {"DS29-0247": 12, "DS29-0174": 13, "DS26-0237": 13}
STOCK, CANDIDATE = "v5_fit_work_stock", "v5_fit_work"
LIMIT = 185


def binding(ident):
    run = WHOLE / ident / "narrow"
    case, request = whole_iq.binding(ident)
    document = COMMON.read(run / "raw.json")
    native = whole_iq.checked(run / "recording/native.json", document["native_sha256"])
    blind = whole_iq.checked(run / "recording/request.json", document["request_sha256"])
    verify_request(
        COMMON.read(blind),
        request,
        native_path=str(native),
        native_sha256=document["native_sha256"],
    )
    return dict(
        id=ident,
        native=str(native),
        request=str(blind),
        native_sha256=COMMON.sha(native),
        request_sha256=COMMON.sha(blind),
        original_native_sha256=case["native"]["sha256"],
        catalog_sha256=case["catalog"]["sha256"],
        tile=case["regions"][0],
        detector_sha256=COMMON.read(run / "plan.json")["detector_sha256"],
    )


def verify_install(root, manifest):
    if whole_iq.receiver_identity(root) != manifest["files"] or any(
        COMMON.sha(root / f) != h for f, h in manifest["compiler_sources"].items()
    ):
        raise ValueError("standalone package does not match its closed source ledger")


def protocol_source():
    return {
        str(p): COMMON.sha(p)
        for p in (Path(__file__), REPORT / "PROTOCOL.md", Path(meter.__file__))
    }


def lock(work):
    manifest = COMMON.read(BASE / "candidate-lock.json")
    verify_install(BASE / "candidate", manifest)
    work.mkdir(exist_ok=False, parents=True)
    save_json(
        work / "plan.json",
        dict(
            cases={case: binding(case) for case in CASES},
            pins=CASES,
            orders={
                case: [CANDIDATE, STOCK] if case == "DS26-0237" else [STOCK, CANDIDATE]
                for case in CASES
            },
            stock=manifest,
            stock_root=str(BASE / "candidate"),
            memory=536870912,
            swap=0,
            limit_s=LIMIT,
            source=protocol_source(),
        ),
    )


def run(work, ident, method):
    lockfile = work / "plan.json"
    plan = COMMON.read(lockfile)
    cpu, matched = plan["pins"][ident], binding(ident)
    if (
        {cpu} != os.sched_getaffinity(0)
        or os.nice(0) < 10
        or plan["source"] != protocol_source()
        or plan["cases"][ident] != matched
    ):
        raise ValueError("wrong affinity, nice level, preregistration or input")
    if method == STOCK:
        root, manifest = Path(plan["stock_root"]), plan["stock"]
    else:
        root, manifest = work / "candidate", COMMON.read(work / "candidate-lock.json")
    verify_install(root, manifest)
    order = plan["orders"][ident]
    if order[1] == method and not (work / "runs" / ident / order[0] / "attempt.json").is_file():
        raise ValueError("run the frozen first method before its paired second method")
    out = work / "runs" / ident / method
    out.mkdir(exist_ok=False, parents=True)
    unit = "leo-fit-work-" + uuid4().hex[:10]
    cmd = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        f"--unit={unit}",
        f"--working-directory={root}",
        f"--property=MemoryMax={plan['memory']}",
        "--property=MemorySwapMax=0",
        f"--property=RuntimeMaxSec={LIMIT}s",
        "--property=Nice=10",
        "--property=MemoryAccounting=yes",
        "--property=KillMode=control-group",
        f"--setenv=TMPDIR={out}",
        "taskset",
        "-c",
        str(cpu),
        str(pressure.direct.v5_lean.PYTHON),
        "-IB",
        str(root),
        *pressure.command_flags(matched),
    ]
    result_file, log_file = out / "position.json", out / "service.log"
    start, live, group = monotonic(), [], None
    with result_file.open("xb") as output, log_file.open("xb") as logger:
        child = subprocess.Popen(cmd, stdout=output, stderr=logger)
        while child.poll() is None and monotonic() - start < LIMIT + 5:
            group = group or systemd_fields(unit).get("ControlGroup")
            try:
                if group:
                    live.append(meter.kernel(Path("/sys/fs/cgroup") / group.lstrip("/")))
            except FileNotFoundError:
                pass
            sleep(0.25)
        if child.poll() is None:
            subprocess.run(["systemctl", "--user", "stop", unit], check=False, timeout=4)
        child.wait(timeout=4)
    if not live or any(
        s["memory.max"] != plan["memory"] or s["memory.swap.max"] or s["memory.swap.current"]
        for s in live
    ):
        raise ValueError("missing proof of the capped service")
    wall, fields = monotonic() - start, systemd_fields(unit)
    log = log_file.read_text(errors="replace")
    terminal = re.search(r"Finished with result: (\S+)", log)
    status = terminal[1] if terminal else fields["Result"]
    result = (
        COMMON.read(result_file)
        if child.returncode == 0 and status == "success"
        else pressure.direct.v5_lean._no_fix(
            f"Linux capped service {status}",
            status="timed_out" if status == "timeout" else "failed",
        )
    )
    pressure.direct.validate_result(result)
    save_json(
        out / "attempt.json",
        dict(
            matched,
            method=method,
            cpu=cpu,
            order=order.index(method),
            returncode=child.returncode,
            service_result=status,
            kernel=fields,
            samples=live,
            cpu_s=max(s["cpu_s"] for s in live),
            wall_s=wall,
            peak_bytes=max(s["memory.peak"] for s in live),
            plan_sha256=COMMON.sha(lockfile),
            install=manifest,
            log_sha256=COMMON.sha(log_file),
            result=result,
        ),
    )
    print(ident, method, status, round(wall, 2), result["status"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("operation", choices=("lock", "run"))
    parser.add_argument("case", nargs="?", choices=CASES)
    parser.add_argument("method", nargs="?", choices=(STOCK, CANDIDATE))
    p = parser.parse_args()
    folder = local_output(p.work)
    if p.operation == "lock":
        lock(folder)
    else:
        run(folder, p.case, p.method)
