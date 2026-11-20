"""Re-run the exact wide original-v5 numerical request without evidence PNG generation."""

import argparse
import os
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path
from time import monotonic, time_ns
from uuid import uuid4

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from ..scoring import validate_result
from . import wide_full_v5 as bound
from .full_v5_check import _sha

REPORT = bound.REPORT.with_name("wide-reference-recovery")
CASES = ("DS26-0122", "DS29-0082")
CPU, LIMIT = 3, 420
MODULE = "tools.pipeline_eval.qualification.wide_reference_recovery"


def relocated(original, folder):
    request = deepcopy(original)
    job = request["job"]
    job["native_input"]["path"] = str(folder / "native.json")
    job["track_config"]["path"] = str(folder / "track-config.json")
    job["tle_root"] = str(folder / "tle")
    job["output_root"] = str(folder / "lean-output")
    return request


def copy_bound(source, destination, digest):
    shutil.copyfile(whole_iq.checked(source, digest), destination)
    whole_iq.checked(destination, digest)


def prepare(work):
    work.mkdir(exist_ok=False)
    parent = whole_iq.checked(
        bound.REPORT / "source-lock.json",
        whole_iq.read(bound.WORK / "launch-lock.json")["source_sha256"],
    )
    inputs = whole_iq.read(parent)["cases"]
    cases = {}
    for ident in CASES:
        out = work / ident
        out.mkdir()
        pin = inputs[ident]
        source = bound.WORK / ident
        parent_request = whole_iq.checked(source / "request.json", pin["rebound_request_sha256"])
        original = whole_iq.read(parent_request)
        job = original["job"]
        if (
            original["role"] != "baseline"
            or job["evaluation_reference"] is not None
            or original["source"]["sha256"] != bound.v5.SOURCE_SHA256
        ):
            raise ValueError("expected the exact blind original-v5 request")
        native = job["native_input"]
        copy_bound(Path(native["path"]), out / "native.json", native["sha256"])
        config = job["track_config"]
        copy_bound(Path(config["path"]), out / "track-config.json", config["sha256"])
        tle = out / "tle"
        tle.mkdir()
        original_root = Path(job["tle_root"])
        snapshots = list(original_root.rglob("*.tle"))
        if len(snapshots) != len(original["causal_snapshots"]) or {
            path.name for path in snapshots
        } != set(original["causal_snapshots"]):
            raise ValueError("parent causal history membership differs")
        for path in snapshots:
            local = tle / path.relative_to(original_root)
            local.parent.mkdir(parents=True, exist_ok=True)
            copy_bound(path, local, original["causal_snapshots"][path.name])
        req = out / "request.json"
        save_json(req, relocated(original, out))
        cases[ident] = dict(
            request_sha256=_sha(req),
            original_request_sha256=_sha(parent_request),
            capture_native_sha256=pin["original_native_sha256"],
            native_sha256=native["sha256"].removeprefix("sha256:"),
            track_config_sha256=config["sha256"],
            causal_snapshots=original["causal_snapshots"],
            catalog_sha256=pin["compact"]["catalog_sha256"],
            tile=pin["compact"]["tile"],
        )
    for file, digest in bound.original_v5.RUNNER_DIGESTS.items():
        whole_iq.checked(bound.v5.RUNNER / file, digest)
    save_json(
        REPORT / "source-lock.json",
        dict(
            cases=cases,
            order=CASES,
            frozen_ns=time_ns(),
            cpu=CPU,
            cap_s=LIMIT,
            nice=10,
            memory_bytes=bound.MEMORY,
            swap_bytes=0,
            parent_source_lock_sha256=_sha(parent),
            protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
            launcher_sha256=_sha(Path(__file__)),
            original_source_sha256=bound.v5.SOURCE_SHA256,
            lean_source_sha256=_sha(Path(bound.v5.__file__)),
            original_runner_sha256=bound.original_v5.RUNNER_DIGESTS,
        ),
    )
    (work / "study.sha256").write_text(_sha(REPORT / "source-lock.json") + "\n")


def worker(out):
    if os.sched_getaffinity(0) != {CPU} or os.nice(0) != 10:
        raise ValueError("run the original science on the single predeclared low-priority core")
    save_json(out / "start.json", bound.measure())
    (out / "lean-output").mkdir()
    env = dict(
        os.environ,
        **bound.THREADS,
        PYTHONPATH=f"{bound.v5.SOURCE}:{bound.v5.RUNNER}",
        PYTHONSAFEPATH="1",
        MPLCONFIGDIR=str(out / "matplotlib"),
    )
    result = subprocess.run(
        [
            str(bound.v5.PYTHON),
            "-B",
            str(Path(bound.v5.__file__)),
            str(out / "request.json"),
            str(out / "position.json"),
        ],
        cwd=ROOT,
        env=env,
        check=False,
    )
    save_json(out / "end.json", dict(bound.measure(), worker_exit_code=result.returncode))
    return result.returncode


def attempt(work, ident, plan):
    out = work / ident
    pin = plan["cases"][ident]
    whole_iq.checked(out / "request.json", pin["request_sha256"])
    whole_iq.checked(out / "native.json", pin["native_sha256"])
    unit = "leo-wide-recovery-" + uuid4().hex[:12]
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        f"--unit={unit}",
        f"--working-directory={ROOT}",
        f"--property=MemoryMax={bound.MEMORY}",
        "--property=MemorySwapMax=0",
        f"--property=RuntimeMaxSec={LIMIT}s",
        "--property=TimeoutStopSec=5s",
        "--property=KillMode=control-group",
        "--property=Nice=10",
        f"--setenv=TMPDIR={out}",
        "taskset",
        "-c",
        str(CPU),
        str(bound.v5.PYTHON),
        "-B",
        "-m",
        MODULE,
        "worker",
        str(out),
    ]
    began = monotonic()
    with (out / "service.log").open("xb") as log:
        code = subprocess.run(
            command, stdout=log, stderr=subprocess.STDOUT, timeout=LIMIT + 25, check=False
        ).returncode
    status = subprocess.run(
        [
            "systemctl",
            "--user",
            "show",
            unit,
            "--property=Result,CPUUsageNSec,MemoryPeak,MemorySwapPeak,MainPID,ControlPID,ActiveState,ActiveEnterTimestampMonotonic,InactiveEnterTimestampMonotonic",
        ],
        capture_output=True,
        text=True,
        timeout=6,
        check=False,
    )
    state = dict(line.split("=", 1) for line in status.stdout.splitlines() if "=" in line)
    if state.get("MainPID") != "0" or state.get("ControlPID") != "0":
        raise RuntimeError("the repeat service still owns active processes")
    save_json(
        out / "service.json",
        dict(
            exit_code=code,
            supervisor_s=monotonic() - began,
            unit=unit,
            systemd=state,
            log_sha256=_sha(out / "service.log"),
        ),
    )
    if code == 0:
        validate_result(whole_iq.read(out / "position.json"))
    print(ident, state.get("Result"), code, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "run", "worker"))
    parser.add_argument("work", type=local_output)
    args = parser.parse_args()
    if args.action == "worker":
        raise SystemExit(worker(args.work))
    if args.action == "seal":
        prepare(args.work)
        return
    plan = whole_iq.read(
        whole_iq.checked(
            REPORT / "source-lock.json",
            (args.work / "study.sha256").read_text().strip(),
        )
    )
    whole_iq.checked(Path(__file__), plan["launcher_sha256"])
    whole_iq.checked(Path(bound.v5.__file__), plan["lean_source_sha256"])
    for ident in plan["order"]:
        attempt(args.work, ident, plan)


if __name__ == "__main__":
    main()
