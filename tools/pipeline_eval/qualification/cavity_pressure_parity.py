"""One larger-cap original receiver run for scientific parity on the reserve."""

import argparse
import os
import re
import subprocess
from pathlib import Path
from time import monotonic, sleep
from uuid import uuid4

from .. import whole_iq
from ..__main__ import local_output, save_json
from . import cavity_pressure_trial as trial
from .cavity_pressure_results import scientific_payload
from .direct_cavity_cap import systemd_fields

CASE, CAP, LIMIT = "DS29-0247", 896 * 2**20, 180
COMMON = trial.direct.common


def parity(work, out):
    planfile = work / "plan.json"
    plan = COMMON.read(planfile)
    case = trial.bindings()[CASE]
    release = Path(plan["runtime"])
    cpu = plan["pins"][CASE]
    fixed_path = work / "runs" / CASE / trial.CANDIDATE / "attempt.json"
    fixed = COMMON.read(fixed_path)
    if (
        plan["source"] != trial.sources()
        or case != plan["bindings"][CASE]
        or whole_iq.receiver_identity(release) != plan["files"]
        or fixed["result"]["status"] != "ok"
        or os.sched_getaffinity(0) != {cpu}
        or os.nice(0) < 10
    ):
        raise ValueError("reserve parity must bind the original package and completed capped pair")
    out.mkdir(exist_ok=False, parents=True)
    build = out / "plan.json"
    save_json(
        build,
        dict(
            case=case,
            cpu=cpu,
            limit_s=LIMIT,
            memory=CAP,
            original_files=plan["files"],
            larger_cap_source_sha256=COMMON.sha(Path(__file__)),
            capped_plan_sha256=COMMON.sha(planfile),
            candidate_receipt_sha256=COMMON.sha(fixed_path),
        ),
    )
    unit = "leo-pressure-parity-" + uuid4().hex[:10]
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        f"--unit={unit}",
        f"--working-directory={release}",
        f"--property=MemoryMax={CAP}",
        "--property=MemorySwapMax=0",
        f"--property=RuntimeMaxSec={LIMIT}s",
        "--property=Nice=10",
        "--property=MemoryAccounting=yes",
        "--property=KillMode=control-group",
        f"--setenv=TMPDIR={out}",
        "taskset",
        "-c",
        str(cpu),
        str(trial.direct.v5_lean.PYTHON),
        "-IB",
        str(release),
        *trial.command_flags(case),
    ]
    started, live, group = monotonic(), [], None
    result_path, log_path = out / "result.json", out / "service.log"
    with result_path.open("xb") as output, log_path.open("xb") as log:
        proc = subprocess.Popen(command, stdout=output, stderr=log)
        while proc.poll() is None and monotonic() - started < LIMIT + 5:
            group = group or systemd_fields(unit).get("ControlGroup")
            try:
                if group:
                    live.append(trial.probe.kernel(Path("/sys/fs/cgroup") / group.lstrip("/")))
            except FileNotFoundError:
                pass
            sleep(0.25)
        if proc.poll() is None:
            subprocess.run(["systemctl", "--user", "stop", unit], check=False, timeout=4)
        proc.wait(timeout=4)
    if not live or any(
        s["memory.max"] != CAP or s["memory.swap.max"] or s["memory.swap.current"] for s in live
    ):
        raise ValueError("no proof of the declared larger-cap trial")
    wall = monotonic() - started
    kernel = systemd_fields(unit)
    terminal = re.search(r"Finished with result: (\S+)", log_path.read_text())
    status = terminal[1] if terminal else kernel["Result"]
    stock = COMMON.read(result_path) if status == "success" and proc.returncode == 0 else None
    if stock:
        trial.direct.validate_result(stock)
    same = None
    if stock and stock["status"] == "ok":
        same = scientific_payload(stock) == scientific_payload(fixed["result"])
    save_json(
        out / "parity.json",
        dict(
            case=CASE,
            cpu=cpu,
            larger_cap_service_result=status,
            larger_cap_wall_s=wall,
            charged_peak_bytes=max(s["memory.peak"] for s in live),
            cpu_s=max(s["cpu_s"] for s in live),
            stock=stock,
            candidate=fixed["result"],
            exact_scientific_payload=same,
            kernel=kernel,
            live=live,
            log_sha256=COMMON.sha(log_path),
            plan_sha256=COMMON.sha(build),
        ),
    )
    print(CASE, status, same, wall, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    parity(args.work, local_output(args.out))
