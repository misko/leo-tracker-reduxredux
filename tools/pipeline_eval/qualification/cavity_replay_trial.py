"""Freeze and run a bounded stock cavity hint on measured merged IQ factors."""

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic
from uuid import uuid4

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from . import locked_assignments_trial as locked
from . import rescue_attribution, support_cross_trial
from .cavity_pressure_trial import command_flags
from .fractional_runtime_whole import verify_request
from .full_v5_check import _sha

REPORT = locked.REPORT.with_name("cavity-replay")
REPLICATION = "DS26-0237"
PINS = locked.PINS | {REPLICATION: 15}
LIMIT = 200
WORKER = Path(__file__).with_name("cavity_replay_worker.py")
CROSS = Path.home() / ".cache/leo-support-cross-replay-20261119"


def sources():
    paths = (
        Path(__file__),
        WORKER,
        REPORT / "PROTOCOL.md",
        *(ROOT / name for name in locked.sources()),
    )
    return {str(p.relative_to(ROOT)): _sha(p) for p in paths}


def stage(work, crossed):
    work.mkdir(exist_ok=False)
    if (REPORT / "plan.json").exists():
        raise FileExistsError("already froze cavity replay")
    sealed = rescue_attribution.sealed
    primary = whole_iq.read(sealed(locked.REPORT, "prediction-lock.json", "plan.json"))
    study = support_cross_trial.REPORT
    replication = whole_iq.read(sealed(study, "prediction-lock.json", "plan.json"))
    cases = {
        ident: a
        | dict(
            inputs=dict(stock=a["inputs"]["stock"], merged=a["inputs"]["union"]),
            receiver=primary["receiver"],
            receiver_files=primary["receiver_files"],
            cohort="negative-rescue",
        )
        for ident, a in primary["cases"].items()
    }
    specs = [r for r in replication["schedule"] if r["id"] == REPLICATION]
    stock, merged = (
        next(row for row in specs if row["condition"] == r) for r in ("wide", "restore")
    )
    cases[REPLICATION] = dict(
        inputs={
            role: dict(
                native=str(crossed / REPLICATION / spec["condition"] / "recording/native.json"),
                request=str(crossed / REPLICATION / spec["condition"] / "recording/request.json"),
                native_sha256=spec["native_sha256"],
                request_sha256=spec["prepared_request_sha256"],
            )
            for role, spec in (("stock", stock), ("merged", merged))
        },
        catalogue=stock["catalog_sha256"],
        tile=stock["tile"],
        original_request_sha256=stock["original_request_sha256"],
        receiver=replication["receiver"],
        receiver_files=replication["receiver_files"],
        cohort="restore-only replication",
    )
    for ident, case in cases.items():
        _, request = whole_iq.binding(ident)
        if whole_iq.receiver_identity(Path(case["receiver"])) != case["receiver_files"]:
            raise ValueError("installed receiver changed from parent")
        for item in case["inputs"].values():
            native = whole_iq.checked(Path(item["native"]), item["native_sha256"])
            fresh = whole_iq.checked(Path(item["request"]), item["request_sha256"])
            verify_request(
                whole_iq.read(fresh),
                request,
                native_path=native,
                native_sha256=item["native_sha256"],
            )
    save_json(
        REPORT / "plan.json",
        dict(
            cases=cases,
            pins=PINS,
            sources=sources(),
            limit_s=LIMIT,
            memory=whole_iq.MEMORY,
            swap=0,
            parents={
                str(name.relative_to(ROOT)): _sha(name)
                for name in (
                    locked.REPORT / "prediction-lock.json",
                    rescue_attribution.parent.REPORT / "figure-lock.json",
                    study / "prediction-lock.json",
                )
            },
        ),
    )
    print("Cavity replay plan locked", _sha(REPORT / "plan.json"), flush=True)


def service(work, ident, case, role):
    path = work / ident / role
    path.mkdir(parents=True)
    source = path.parent / "stock/outcome.json"
    item = case["inputs"][role]
    for field in ("native", "request"):
        whole_iq.checked(Path(item[field]), item[f"{field}_sha256"])
    unit = "leo-cavity-replay-" + uuid4().hex[:12]
    cpu = PINS[ident]
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        "--collect",
        f"--unit={unit}",
        f"--working-directory={case['receiver']}",
        "-p",
        f"MemoryMax={whole_iq.MEMORY}",
        "-p",
        "MemorySwapMax=0",
        "-p",
        "Nice=10",
        "-p",
        f"RuntimeMaxSec={LIMIT}s",
        f"--setenv=TMPDIR={path}",
        "taskset",
        "-c",
        str(cpu),
        sys.executable,
        "-IB",
        str(WORKER),
        case["receiver"],
        str(path),
        str(cpu),
        role,
        str(source),
        *command_flags(item),
    ]
    log = path / "service.log"
    began = monotonic()
    with log.open("xb") as file:
        code = subprocess.run(
            command, stdout=file, stderr=subprocess.STDOUT, check=False
        ).returncode
    report = path / "outcome.json"
    result = dict(
        id=ident,
        role=role,
        cpu=cpu,
        returncode=code,
        supervisor_wall_s=monotonic() - began,
        log_sha256=_sha(log),
        result_sha256=_sha(report) if report.is_file() else None,
        stock_prior_sha256=_sha(source) if role == "merged" and source.is_file() else None,
        plan_sha256=_sha(REPORT / "plan.json"),
        terminal=[
            line.strip()
            for line in log.read_text(errors="replace").splitlines()
            if line.strip().startswith(("Finished with result:", "Memory peak:"))
        ],
    )
    save_json(path / "attempt.json", result)
    print(ident, role, code, round(result["supervisor_wall_s"], 2), flush=True)
    return result


def run(work):
    plan = whole_iq.read(REPORT / "plan.json")
    if plan["sources"] != sources():
        raise ValueError("frozen candidate source changed")

    def lane(cases):
        return [
            service(work, ident, plan["cases"][ident], role)
            for ident in cases
            for role in ("stock", "merged")
        ]

    with ThreadPoolExecutor(2) as pool:
        outcomes = [
            r for lane in pool.map(lane, (("DS26-0168",), ("DS29-0604", REPLICATION))) for r in lane
        ]
    save_json(REPORT / "attempts.json", outcomes)
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
    parser.add_argument("--crossed", type=Path, default=CROSS)
    args = parser.parse_args()
    stage(args.work, args.crossed)
    run(args.work)
