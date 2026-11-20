"""Replay exact wide control factors through a fused compact discovery pass."""

import argparse
import json
import os
import pstats
import re
import subprocess
import sys
from pathlib import Path
from time import monotonic
from uuid import uuid4

from .. import whole_iq
from ..__main__ import local_output, save_json
from ..scoring import ARMS, validate_result
from ..variants import fit_basis
from . import fit_basis_probe as probe
from . import ranked_fit_trial as installer
from . import wide_full_v5 as earlier
from .direct_cavity_cap import systemd_fields

BASE = Path("/home/mouse9911/.cache/leo-installed-interior-20261119/compatibility/phase-release")
REPORT = earlier.SCREEN / "track-recovery/fit-basis"
CASES = {"DS26-0237": 12, "DS29-0082": 13, "DS29-0127": 13}
DESIGN = ("DS26-0237", "DS29-0082")
STOCK, CANDIDATE, WITNESS = "v5_fit_basis_stock", "v5_fit_basis", "witness"
MEMORY, LIMIT = 512 * 2**20, 210
COMMON = installer.COMMON


def sources():
    return {
        str(p): COMMON.sha(p)
        for p in (
            Path(__file__),
            Path(probe.__file__),
            Path(fit_basis.__file__),
            REPORT / "PROTOCOL.md",
        )
    }


def profile_stats(path):
    raw = pstats.Stats(str(path)).strip_dirs()
    tracked = {"statistics", "augment_phase_statistics", "predictive_residual", "solve"}
    selected = {}
    for (file, _line, function), value in raw.stats.items():
        if function in tracked and file in {
            "discovery.py",
            "shared_orbit_phase_fit.py",
            "predictive_linear.py",
            "_linalg.py",
        }:
            _primitive, calls, own, cumulative, _callers = value
            selected[f"{file}/{function}"] = dict(calls=calls, own_s=own, cumulative_s=cumulative)
    return dict(full_cpu_profile_s=raw.total_tt, moments=selected)


def stage(work):
    inputs = whole_iq.read(work / "inputs.json")
    prior = whole_iq.checked(earlier.REPORT / "prediction-lock.json", inputs["authority_sha256"])
    prediction = whole_iq.read(prior)
    archive = whole_iq.read(
        whole_iq.checked(
            earlier.REPORT / "source-lock.json", prediction["files"]["source-lock.json"]
        )
    )
    if set(inputs["cases"]) != set(CASES) or inputs["protocol_sha256"] != COMMON.sha(
        REPORT / "PROTOCOL.md"
    ):
        raise ValueError("fixed profiling protocol or roster changed")
    for ident, row in inputs["cases"].items():
        original, request = whole_iq.binding(ident)
        prior_case = archive["cases"][ident]["compact"]
        whole_iq.checked(Path(row["native"]), prior_case["native_sha256"])
        job = request["job"]
        binding = dict(
            session=original["session_id"],
            archive=job["tle_root"],
            config=job["track_config"],
            tile=job["search_center"],
            screen=job["screen_center"],
            native_sha256=prior_case["native_sha256"],
        )
        if binding != {key: row[key] for key in binding}:
            raise ValueError("wide factors and original causal settings differ")
    profiles = {ident: profile_stats(work / ident / "stock.prof") for ident in DESIGN}
    stock = dict(
        files=whole_iq.receiver_identity(BASE), compiler_sources=whole_iq.native_sources(BASE)
    )
    candidate = work / "candidate"
    installer.copy_install(BASE, candidate, stock)
    target = candidate / fit_basis.TARGET
    target.write_text(fit_basis.revise(target.read_text()))
    contents = whole_iq.receiver_identity(candidate)
    overlay = {name for name in contents if contents[name] != stock["files"].get(name)}
    if contents.keys() != stock["files"].keys() or overlay != {
        fit_basis.TARGET,
        "native/manifest.json",
    }:
        raise ValueError("candidate contains more than the fused discovery moments")
    files = dict(
        files=contents, compiler_sources=stock["compiler_sources"], changes=sorted(overlay)
    )
    save_json(
        work / "plan.json",
        dict(
            cases=inputs["cases"],
            input_authority_sha256=inputs["authority_sha256"],
            inputs_sha256=COMMON.sha(work / "inputs.json"),
            sources=sources(),
            stock=stock,
            candidate=files,
            profiles=profiles,
            profile_hashes={ident: COMMON.sha(work / ident / "stock.prof") for ident in DESIGN},
            stock_install=str(BASE),
            memory=MEMORY,
            limit_s=LIMIT,
        ),
    )


def flags(row):
    return [
        "--native",
        row["native"],
        "--native-sha256",
        row["native_sha256"],
        "--session",
        row["session"],
        "--track-config",
        row["config"]["path"],
        "--config-sha256",
        row["config"]["sha256"],
        "--archive",
        row["archive"],
        "--tile",
        *map(str, row["tile"]),
        "--screen-center",
        *map(str, row["screen"]),
    ]


def run(work, ident, method):
    planfile = work / "plan.json"
    plan = whole_iq.read(planfile)
    row, cpu = plan["cases"][ident], CASES[ident]
    if os.sched_getaffinity(0) != {cpu} or os.nice(0) < 10 or plan["sources"] != sources():
        raise ValueError("profile, CPU pin, or priority departed from its source seal")
    whole_iq.checked(Path(row["native"]), row["native_sha256"])
    candidate = work / "candidate"
    installer.shared.verify_install(candidate, plan["candidate"])
    root = BASE if method != CANDIDATE else candidate
    if method != CANDIDATE:
        installer.shared.verify_install(BASE, plan["stock"])
    if method != WITNESS:
        for design in DESIGN:
            evidence = whole_iq.read(work / design / WITNESS / "receipt.json")
            if (
                evidence["plan_sha256"] != COMMON.sha(planfile)
                or len(evidence["marks"]["witness"]) != 3
                or evidence["service_result"] != "success"
            ):
                raise ValueError("three exact candidate inventories required per design recording")
        first = STOCK if ident in DESIGN else CANDIDATE
        if method != first and not (work / ident / first / "receipt.json").exists():
            raise ValueError("fixed same-core method order changed")
    out = work / ident / method
    out.mkdir(exist_ok=False)
    unit = "leo-fit-basis-" + uuid4().hex[:10]
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        f"--unit={unit}",
        f"--working-directory={root}",
        f"--property=MemoryMax={MEMORY}",
        "--property=MemorySwapMax=0",
        "--property=MemoryAccounting=yes",
        f"--property=RuntimeMaxSec={LIMIT}s",
        "--property=Nice=10",
        f"--setenv=TMPDIR={out}",
        "taskset",
        "-c",
        str(cpu),
        sys.executable,
        "-IB",
        str(Path(probe.__file__)),
        str(root),
        str(cpu),
        "witness" if method == WITNESS else "measure",
        str(candidate),
        *flags(row),
    ]
    result_path, log = out / "result.json", out / "service.log"
    began = monotonic()
    with result_path.open("xb") as stdout, log.open("xb") as stderr:
        try:
            exitcode = subprocess.run(
                command, stdout=stdout, stderr=stderr, timeout=LIMIT + 9, check=False
            ).returncode
        except subprocess.TimeoutExpired:
            exitcode = 124
    wall, kernel = monotonic() - began, systemd_fields(unit)
    lines = log.read_text(errors="replace")
    terminal = re.search(r"Finished with result: (\S+)", lines)
    status = terminal[1] if terminal else kernel["Result"]
    marks = {}
    for line in lines.splitlines():
        name, _, data = line.partition(" ")
        if name in {"ready", "finish", "statistics", "witness"}:
            marks[name] = json.loads(data)
    result = None
    if method != WITNESS:
        if exitcode == 0 and status == "success":
            result = whole_iq.read(result_path)
        else:
            result = dict(
                status="timed_out" if status == "timeout" else "failed",
                reason=f"Linux capped service {status}",
                boundary="Stored wide factors through compact position",
                metrics={},
                arms={arm: {"latlon": None} for arm in ARMS},
            )
        validate_result(result)
    save_json(
        out / "receipt.json",
        dict(
            case=ident,
            method=method,
            cpu=cpu,
            service_result=status,
            returncode=exitcode,
            kernel=kernel,
            wall_s=wall,
            marks=marks,
            result=result,
            plan_sha256=COMMON.sha(planfile),
            log_sha256=COMMON.sha(log),
            native_sha256=row["native_sha256"],
        ),
    )
    print(
        ident,
        method,
        status,
        round(wall, 2),
        marks.get(method if method == WITNESS else "statistics"),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("operation", choices=("stage", "run"))
    parser.add_argument("case", nargs="?", choices=CASES)
    parser.add_argument("method", nargs="?", choices=(WITNESS, STOCK, CANDIDATE))
    args = parser.parse_args()
    work = local_output(args.work)
    if args.operation == "stage":
        stage(work)
    else:
        run(work, args.case, args.method)
