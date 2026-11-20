"""Measure the composed worker before and after the sampled family prior lookup."""

import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
from time import perf_counter, time_ns
from unittest.mock import patch

from ..__main__ import ROOT, local_output, save_json
from ..scoring import validate_result
from ..variants import orbit_projector, v5_lean
from ..variants import v5_family_memory as fast
from . import composed_memory_trial as archive
from . import working_memory_trial as inputs
from .family_memory_worker import FROZEN
from .phase_confirmation import _read, digest
from .secant_full import _verify_files

REPORT = ROOT / "reports/2026_11_19_receiver_screening/redesign/family-memory"
WORKER = Path(__file__).with_name("family_memory_worker.py")
MODES = (fast.METHOD, archive.v5_composed_memory.METHOD)
DS29 = "DS29-0082"
DS26 = "DS26-0036"
CPUS = (7, 18)
LIMIT = 435


def sources():
    archive.locked(archive.REPORT)
    loc = v5_lean.SOURCE / "leo/analysis/localization_v3"
    if {name: digest(loc / f"{name}.py") for name in FROZEN} != FROZEN:
        raise ValueError("the frozen family confidence source changed")
    paths = (WORKER, Path(__file__), Path(fast.__file__), REPORT / "PROTOCOL.md")
    return dict(
        files={str(p.relative_to(ROOT)): digest(p) for p in paths},
        frozen=FROZEN,
        composed_source_lock_sha256=digest(archive.REPORT / "source-lock.json"),
        same_input_archive_sha256=digest(archive.REPORT / "prediction-lock.json"),
    )


def _cpu():
    value = getrusage(RUSAGE_CHILDREN)
    return value.ru_utime + value.ru_stime


def execute(work, ident, mode, cpu):
    plan = _read(work / "plan.json")
    if plan["source"] != sources() or os.sched_getaffinity(0) != {cpu}:
        raise ValueError("the family memory sources or core changed")
    case, native = inputs.case_binding("ordinary-" + ident, inputs.RAW)
    request_sha = inputs.canonical_request(Path(case["request_path"]))
    if (
        request_sha != plan["inputs"][ident]["request_sha256"]
        or native != plan["inputs"][ident]["native"]
    ):
        raise ValueError("the fresh native request differs from the plan")
    out = work / ident / mode
    out.mkdir(parents=True, exist_ok=False)
    library = out / "orbit_projector.so"
    wall, cpu_start = perf_counter(), _cpu()
    remaining = (plan["deadline_ns"] - time_ns()) // 10**9
    if remaining > 5:
        orbit_projector.compile_kernel(library)
        with patch.object(v5_lean, "TIMEOUT_S", min(230, remaining - 4)):
            result = v5_lean.run_bound_worker(case, out, WORKER, worker_args=(str(library), mode))
    else:
        result = v5_lean._no_fix("common deadline before launch", status="missing")
    if "exceeded its " in (result.get("reason") or ""):
        result["status"] = "timed_out"
    if (out / "request.json").exists() and inputs.canonical_request(
        out / "request.json"
    ) != request_sha:
        raise ValueError("the receiver consumed a different scientific request")
    validate_result(result)
    record = dict(
        id=ident,
        method=mode,
        mode="matched-tile",
        cpu=cpu,
        tile=case["regions"][0],
        input_sha256=request_sha,
        result=result,
        worker_cpu_s=_cpu() - cpu_start,
        worker_wall_s=perf_counter() - wall,
        **native,
    )
    save_json(work / f"{ident}-{mode}.json", record)
    print(ident, mode, result["status"], round(record["worker_wall_s"], 2), flush=True)


def run(work):
    work = local_output(work)
    work.mkdir(parents=True, exist_ok=False)
    started = time_ns()
    ref = archive.REPORT
    _verify_files(ref, _read(ref / "prediction-lock.json")["files"])
    bound = {}
    for ident in (DS29, DS26):
        case, native = inputs.case_binding("ordinary-" + ident, inputs.RAW)
        bound[ident] = dict(
            request_sha256=inputs.canonical_request(Path(case["request_path"])), native=native
        )
    plan = dict(
        primary=DS29,
        reserve=DS26,
        cpus=CPUS,
        source=sources(),
        inputs=bound,
        deadline_ns=started + LIMIT * 10**9,
    )
    save_json(work / "plan.json", plan)
    save_json(REPORT / "plan.json", plan)

    def lane(cpu, mode):
        def launch(ident):
            subprocess.run(
                [
                    "nice",
                    "-n",
                    "3",
                    "taskset",
                    "-c",
                    str(cpu),
                    sys.executable,
                    "-m",
                    "tools.pipeline_eval.qualification.family_memory_trial",
                    "execute",
                    str(work),
                    ident,
                    mode,
                    str(cpu),
                ],
                check=True,
            )

        launch(DS29)

    with ThreadPoolExecutor(2) as pool:
        jobs = [pool.submit(lane, cpu, mode) for cpu, mode in zip(CPUS, MODES, strict=True)]
        for job in jobs:
            job.result()
    if (plan["deadline_ns"] - time_ns()) / 1e9 > 180:
        with ThreadPoolExecutor(2) as pool:
            steps = [
                pool.submit(
                    subprocess.run,
                    [
                        "nice",
                        "-n",
                        "3",
                        "taskset",
                        "-c",
                        str(cpu),
                        sys.executable,
                        "-m",
                        "tools.pipeline_eval.qualification.family_memory_trial",
                        "execute",
                        str(work),
                        DS26,
                        mode,
                        str(cpu),
                    ],
                    check=True,
                )
                for cpu, mode in zip(CPUS, MODES, strict=True)
            ]
            for step in steps:
                step.result()


if __name__ == "__main__":
    if len(sys.argv) == 6 and sys.argv[1] == "execute":
        _, _, work, ident, mode, cpu = sys.argv
        execute(Path(work), ident, mode, int(cpu))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--work", required=True, type=Path)
        run(parser.parse_args().work)
