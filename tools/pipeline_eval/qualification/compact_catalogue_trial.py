"""Run fresh same-core compact receiver pairs with the regional catalogue overlay."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic
from uuid import uuid4

from .. import cavity_runtime, whole_iq
from ..__main__ import ROOT, local_output, save_json
from ..scoring import ARMS
from . import cavity_payload_trial as apparatus
from . import cavity_reuse_observe as observer
from . import cavity_reuse_trial as prior
from . import compact_catalogue_build as build
from .full_receiver_comparison import sha

REPORT = prior.REPORT.parents[1] / "antenna-confirmation/compact-cost"
MODES = ("stock", "regional")
SCHEDULE = {
    "DS26-0036": ("ordinary", 20, MODES),
    "DS29-0127": ("capture-era", 21, MODES[::-1]),
    "DS26-0112": ("capture-era", 20, MODES[::-1]),
    "DS29-0082": ("ordinary", 21, MODES),
}
LIMIT = 170
METHODS = dict(stock="v5_phase_release_control", regional="v5_regional_catalogue")


def source_lock(work):
    work.mkdir()
    releases = {mode: build.install(work / mode, candidate=mode == "regional") for mode in MODES}
    libraries = {name: releases["stock"][name] for name in prior.LIBRARIES}
    if any(releases["regional"][name] != digest for name, digest in libraries.items()):
        raise ValueError("the candidate must preserve both compiled numerical backends")
    bindings = {
        ident: prior.qualify_input(ident, specification[0])[2]
        for ident, specification in SCHEDULE.items()
    }
    files = (
        Path(__file__),
        Path(build.__file__),
        Path(observer.__file__),
        Path(apparatus.__file__),
        REPORT / "PROTOCOL.md",
        cavity_runtime.RELEASE / "prediction-lock.json",
    )
    lock = dict(
        cases=list(SCHEDULE),
        schedule=SCHEDULE,
        bindings=bindings,
        releases=releases,
        sources={str(p.relative_to(ROOT)): sha(p) for p in files},
        memory_bytes=whole_iq.MEMORY,
        swap_bytes=0,
        nice=10,
        limit_s=LIMIT,
    )
    save_json(REPORT / "source-lock.json", lock)
    return lock


def work_case(work, lock, ident):
    cohort, cpu, order = SCHEDULE[ident]
    case, job, actual = prior.qualify_input(ident, cohort)
    if actual != lock["bindings"][ident]:
        raise ValueError("receiver received a different native, causal catalogue or tile authority")
    for mode in order:
        install = work / mode
        for name, digest in lock["releases"][mode].items():
            whole_iq.checked(install / name, digest)
        workdir = work / ident / mode
        workdir.mkdir(parents=True)
        unit = f"leo-catalogue-{ident.lower()}-{uuid4().hex[:8]}"
        command = [
            "systemd-run",
            "--user",
            "--wait",
            "--pipe",
            f"--unit={unit}",
            f"--working-directory={install}",
            f"--setenv=TMPDIR={workdir}",
            f"--property=MemoryMax={lock['memory_bytes']}",
            "--property=MemorySwapMax=0",
            f"--property=RuntimeMaxSec={LIMIT}s",
            "--property=Nice=10",
            "--property=KillMode=control-group",
            *(f"--setenv={v}=1" for v in apparatus.THREADS),
            "/usr/bin/taskset",
            "-c",
            str(cpu),
            str(prior.direct.v5_lean.PYTHON),
            "-IB",
            str(Path(observer.__file__)),
            unit,
            str(cpu),
            str(install),
            *prior.flags_for(case, job, install),
        ]
        start = monotonic()
        code, failure = apparatus.supervise(command, unit, workdir)
        wall = monotonic() - start
        result, resources, code = apparatus.service_result(workdir, code, failure)
        result.setdefault("arms", {arm: {"latlon": None} for arm in ARMS})
        lines = (workdir / "stderr").read_text().splitlines()
        witness = [
            line.removeprefix("catalogue-work ")
            for line in lines
            if line.startswith("catalogue-work ")
        ]
        if len(witness) == 1:
            import json

            witness = json.loads(witness[0])
        elif not witness:
            witness = None
        else:
            raise ValueError("the public entry prepared a single catalogue more than once")
        save_json(
            workdir / "attempt.json",
            dict(
                actual,
                id=ident,
                cohort=cohort,
                method=METHODS[mode],
                mode="matched-tile",
                cpu=cpu,
                wall_s=wall,
                result=result,
                measurements=resources,
                exit_code=code,
                unit=unit,
                log_sha256=sha(workdir / "stderr"),
                source_lock_sha256=sha(REPORT / "source-lock.json"),
                catalogue=witness,
            ),
        )
        print(ident, mode, result["status"], round(wall, 1), result.get("reason", ""), flush=True)


def run(work):
    lock = source_lock(work)
    print("locked", sha(REPORT / "source-lock.json"), flush=True)

    def lane(cpu):
        for ident, (_, pin, _) in SCHEDULE.items():
            if pin == cpu:
                work_case(work, lock, ident)

    with ThreadPoolExecutor(2) as pool:
        list(pool.map(lane, (20, 21)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    run(parser.parse_args().work)
