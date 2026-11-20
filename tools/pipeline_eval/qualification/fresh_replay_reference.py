"""Measure the exact four archived v5 policies on the selected DS29 capture-era input."""

import argparse
import gzip
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic
from uuid import uuid4

from .. import iq_service, whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..scoring import ROLES, validate_result
from ..variants import v5_lean as v5
from . import fresh_replay as trial
from . import original_v5, wide_full_v5
from .full_v5_check import _sha
from .phase_support_results import pack

MODULE = "tools.pipeline_eval.qualification.fresh_replay_reference"
WORK = v5.SOURCE.parents[1] / "fresh-replay-DS29-original-20261119"
REPORT = trial.REPORT
LIMIT, MEMORY = 600, 4 * 1024**3
LANES = {2: (ROLES[0], ROLES[3]), 3: (ROLES[1], ROLES[2])}


def initial(whole, work):
    source = trial.source(whole)
    work.mkdir(parents=True, exist_ok=False)
    (case,) = [c for c in source["cases"].values() if c["id"].startswith("DS29-")]
    for filename, digest in original_v5.RUNNER_DIGESTS.items():
        whole_iq.checked(v5.RUNNER / filename, digest)
    inputs = {}
    for cpu, roles in LANES.items():
        for role in roles:
            recorded = source["original_requests"][role]
            template = whole_iq.read(whole_iq.checked(Path(recorded["path"]), recorded["sha256"]))
            if (
                template["role"] != role
                or template["job"]["evaluation_reference"] is not None
                or template["job"]["identity"]["session_id"] != case["case"]["session_id"]
                or template["job"]["native_input"]["sha256"]
                != "sha256:" + case["capture_native_sha256"]
                or template["causal_snapshots"] != case["orbit_snapshots"]
                or template["job"]["search_center"] != case["tile"]["center"]
            ):
                raise ValueError(
                    "original v5 policy changed capture-era support or truth-free request"
                )
            out = work / role
            out.mkdir()
            template["job"]["output_root"] = str(out / "output")
            path = out / "request.json"
            save_json(path, template)
            inputs[role] = dict(
                request_sha256=_sha(path),
                original_request_sha256=recorded["sha256"],
                policy=template["policy"],
                cpu=cpu,
            )
    plan = dict(
        id=case["id"],
        requests=inputs,
        lanes=LANES,
        case=case,
        original_science_sha256=trial.SCIENCE_SHA,
        original_ds29_plan_sha256=trial.ROOF_SHA,
        source_sha256=_sha(trial.REPORT / "source-lock.json"),
        launcher_sha256=_sha(Path(__file__)),
        runner_sha256=original_v5.RUNNER_DIGESTS,
        deadline_s=LIMIT,
        memory_max=MEMORY,
        swap_max=0,
    )
    save_json(work / "reference-source-lock.json", plan)
    save_json(REPORT / "reference-source-lock.json", plan)
    return plan


def worker(out, cpu):
    if os.sched_getaffinity(0) != {cpu}:
        raise ValueError("original v5 worker left its pinned physical CPU")
    save_json(out / "start.json", wide_full_v5.measure())
    proc = subprocess.run(
        [
            str(v5.PYTHON),
            "-B",
            str(v5.RUNNER / "evaluate_accuracy_repair.py"),
            "worker",
            "--request",
            str(out / "request.json"),
        ],
        check=False,
    )
    save_json(out / "end.json", wide_full_v5.measure())
    return proc.returncode


def service(work, role, plan):
    out, entry = work / role, plan["requests"][role]
    whole_iq.checked(out / "request.json", entry["request_sha256"])
    unit = "leo-fresh-v5-" + uuid4().hex[:12] + ".service"
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        f"--unit={unit}",
        f"--working-directory={ROOT}",
        f"--property=MemoryMax={MEMORY}",
        "--property=MemorySwapMax=0",
        "--property=Nice=10",
        "--property=KillMode=control-group",
        f"--property=RuntimeMaxSec={LIMIT}s",
        "--property=TimeoutStopSec=5s",
        f"--setenv=YTHONPATH={v5.SOURCE}:{v5.RUNNER}:{ROOT}",
        f"--setenv=TMPDIR={out}",
        f"--setenv=MPLCONFIGDIR={out / 'matplotlib'}",
        *(f"--setenv={key}={value}" for key, value in wide_full_v5.THREADS.items()),
        "taskset",
        "-c",
        str(entry["cpu"]),
        "bwrap",
        "--unshare-net",
        "--die-with-parent",
        "--ro-bind",
        "/",
        "/",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--bind",
        str(out),
        str(out),
        "--tmpfs",
        str(ROOT / "reports"),
        *(
            arg
            for name in ("evaluation-references.json", "site-audit.json", "site-authority.json")
            for arg in ("--ro-bind", "/dev/null", str(trial.DS29 / name))
        ),
        str(v5.PYTHON),
        "-B",
        "-m",
        MODULE,
        "worker",
        str(out),
        str(entry["cpu"]),
    ]
    print(role, "start", flush=True)
    print_path = out / "service.log"
    began = monotonic()
    with print_path.open("xb") as log:
        try:
            code = subprocess.run(
                command,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=LIMIT + 20,
                check=False,
            ).returncode
        except subprocess.TimeoutExpired:
            code = None
    elapsed = monotonic() - began
    state = iq_service._show(unit)
    if state.get("MainPID") != "0" or state.get("ControlPID") != "0":
        raise RuntimeError(f"terminal reference service still has a PID: {unit}")
    cgroup = iq_service._empty_cgroup(iq_service._cgroup(unit))
    marker = out / "end.json"
    result_path = out / "output/worker-result.json"
    if (
        code == 0
        and state.get("Result") in (None, "success")
        and marker.is_file()
        and result_path.is_file()
    ):
        observed = whole_iq.read(result_path)
        frozen = whole_iq.read(out / "request.json")
        if (
            observed["role"] != role
            or observed["policy"] != entry["policy"]
            or observed["source_sha256"] != frozen["source"]["sha256"]
            or observed["status"] != "complete"
        ):
            raise ValueError("original worker result does not bind the frozen implementation")
        whole_iq.checked(Path(observed["artifact"]["path"]), observed["artifact"]["sha256"])
        result = original_v5._result(observed, elapsed)
        payload = gzip.compress(result_path.read_bytes(), mtime=0)
        write(REPORT / "original-v5" / f"{role}.worker-result.json.gz", payload)
    else:
        reason = state.get("Result") or "original v5 failed"
        log = print_path.read_text(errors="replace")
        status = (
            "timed_out"
            if reason == "timeout" or "result: timeout" in log
            else "withheld"
            if "no_active_curvature" in log
            else "failed"
        )
        result = original_v5._no_fix(role, status, reason, elapsed)
    validate_result(result)
    measured = {
        name: whole_iq.read(out / f"{name}.json")
        for name in ("start", "end")
        if (out / f"{name}.json").is_file()
    }
    service = dict(
        unit=unit,
        exit_code=code,
        systemd=state,
        command=command,
        terminal_cgroup=cgroup,
        supervisor_s=elapsed,
        measures=measured,
        log_sha256=_sha(print_path),
    )
    row = dict(
        id=plan["id"],
        method=role,
        result=result,
        service=service,
        native_sha256=plan["case"]["capture_native_sha256"],
        paired_capture_sha256=plan["case"]["capture_native_sha256"],
        original_request_sha256=plan["case"]["request_sha256"],
        catalog_sha256=plan["case"]["catalog_sha256"],
        tile=plan["case"]["tile"],
    )
    save_json(out / "receipt.json", row)
    write(REPORT / "original-v5" / f"{role}.service.log", print_path.read_bytes())
    print(role, result["status"], round(elapsed, 2), flush=True)
    return row


def run(whole, work):
    plan = initial(whole, work)

    def run_lane(roles):
        return [service(work, role, plan) for role in roles]

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = {
            row["method"]: row for lane in pool.map(run_lane, LANES.values()) for row in lane
        }
    pack(REPORT / "fresh-v5.jsonl.gz", [outcomes[role] for role in ROLES])
    names = ["reference-source-lock.json", "fresh-v5.jsonl.gz"]
    names.extend(str(path.relative_to(REPORT)) for path in (REPORT / "original-v5").iterdir())
    save_json(
        REPORT / "reference-prediction-lock.json",
        dict(
            cases=[plan["id"]],
            files={name: _sha(REPORT / name) for name in names},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    run_args = modes.add_parser("run")
    run_args.add_argument("--work", type=local_output, default=WORK)
    run_args.add_argument("--whole", type=local_output, default=trial.WORK)
    stage = modes.add_parser("worker")
    stage.add_argument("out", type=local_output)
    stage.add_argument("cpu", type=int)
    args = parser.parse_args()
    if args.mode == "worker":
        raise SystemExit(worker(args.out, args.cpu))
    run(args.whole, args.work)
