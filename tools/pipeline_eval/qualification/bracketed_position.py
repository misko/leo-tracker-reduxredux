"""Run archived wide-factor controls and private edited inputs through phase-release."""

import argparse
import gzip
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic
from uuid import uuid4

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from .full_v5_check import _sha
from .whole_pressure_trial import rows_from

SCREEN = ROOT / "reports/2026_11_19_receiver_screening"
REPORT = SCREEN / "track-recovery/bracketed-position"
PRIOR = SCREEN / "receiver-core/full-stride"
PRIOR_SHA = "42136b7b48d910bf416772d7c7eb9e127dafb0ee5f54089c58d94820a05a9872"
WORK = Path("/home/mouse9911/.cache/leo-bracketed-position-20261119")
MODULE = "tools.pipeline_eval.qualification.bracketed_position"
LIMIT = 210
LANES = {14: ("DS26-0036", "DS26-0162"), 15: ("DS29-0082", "DS29-0519")}


def check_release(lock):
    path = Path(lock["receiver"])
    if (
        whole_iq.receiver_identity(path) != lock["receiver_files"]
        or whole_iq.native_sources(path) != lock["native_sources"]
    ):
        raise ValueError("the phase-release installation changed")


def stage(work, report):
    if work.exists() or (report / "source-lock.json").exists():
        raise FileExistsError("this matched position comparison already has a prospective lock")
    prediction = whole_iq.read(whole_iq.checked(PRIOR / "prediction-lock.json", PRIOR_SHA))
    parent = {
        n: whole_iq.checked(PRIOR / n, prediction["files"][n])
        for n in ("source-lock.json", "positions.jsonl.gz", "resources.json")
    }
    release = whole_iq.read(parent["source-lock.json"])
    check_release(release)
    results = {
        row["id"]: row
        for row in rows_from(parent["positions.jsonl.gz"])
        if row["method"] == "wide-cfo-stride_control"
    }
    resources = whole_iq.read(parent["resources.json"])
    cases = {}
    for cpu, lane in LANES.items():
        for ident in lane:
            case, original = whole_iq.binding(ident)
            job = original["job"]
            baseline, resource = results[ident], resources[ident]["control"]
            native_name = f"native/control/{ident}.json.gz"
            source = whole_iq.checked(PRIOR / native_name, prediction["files"][native_name])
            blob = gzip.decompress(source.read_bytes())
            out = work / ident / "control"
            native = out / "native.json"
            write(native, blob)
            whole_iq.checked(native, baseline["native_sha256"])
            doc = json.loads(blob)
            if (
                baseline["result"]["status"] != "ok"
                or doc["source"]["session_id"] != case["session_id"]
                or doc["source"]["input_manifest_sha256"] != resource["input_manifest_sha256"]
                or doc["provenance"]["detector_sha256"] != "sha256:" + resource["detector_sha256"]
                or baseline["original_request_sha256"] != case["request"]["sha256"]
                or baseline["catalog_sha256"] != case["catalog"]["sha256"]
                or baseline["tile"]["center"] != job["search_center"]
            ):
                raise ValueError(
                    "archived factors and compact result do not bind the original request"
                )
            request = dict(
                native=str(native),
                native_sha256=baseline["native_sha256"],
                session=case["session_id"],
                config=job["track_config"],
                archive=job["tle_root"],
                tile=job["search_center"],
                screen=job["screen_center"],
                install=release["receiver"],
                cpu=cpu,
            )
            save_json(out / "request.json", request)
            cases[ident] = dict(
                archived=baseline,
                cpu=cpu,
                archived_position_wall_s=resource["position_s"],
                native_archive=str(source),
                native_archive_sha256=prediction["files"][native_name],
                original_native_sha256=case["native"]["sha256"],
                original_request_sha256=case["request"]["sha256"],
                causal_snapshots=original["causal_snapshots"],
                detection=doc["provenance"],
                input_manifest_sha256=doc["source"]["input_manifest_sha256"],
                control_request_sha256=_sha(out / "request.json"),
            )
    files = [Path(__file__), report / "PROTOCOL.md", Path(whole_iq.raw.__file__)]
    lock = dict(
        cases=cases,
        paths={str(p): _sha(p) for p in files},
        parent_prediction_sha256=PRIOR_SHA,
        receiver=release["receiver"],
        receiver_files=release["receiver_files"],
        native_sources=release["native_sources"],
        limit_s=LIMIT,
        memory_max=whole_iq.MEMORY,
        swap_max=0,
    )
    save_json(report / "source-lock.json", lock)
    save_json(work / "launch-lock.json", {"source_sha256": _sha(report / "source-lock.json")})
    return lock


def worker(out):
    row = whole_iq.read(out / "request.json")
    if os.sched_getaffinity(0) != {row["cpu"]}:
        raise ValueError("the receiver left the scheduled CPU")
    save_json(out / "start.json", whole_iq.raw.mark("factor-only compact enter"))
    command = [
        sys.executable,
        "-IB",
        row["install"],
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
    with (out / "position.json").open("xb") as stream:
        subprocess.run(command, cwd=out, stdout=stream, check=True)
    save_json(out / "end.json", whole_iq.raw.mark("both compact arms returned"))


def launch_case(out, cpu):
    unit = "leo-bracketed-position-" + uuid4().hex[:12]
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        f"--unit={unit}",
        f"--working-directory={ROOT}",
        f"--property=MemoryMax={whole_iq.MEMORY}",
        "--property=MemorySwapMax=0",
        f"--property=RuntimeMaxSec={LIMIT}s",
        "--property=TimeoutStopSec=8s",
        "--property=KillMode=control-group",
        "--property=Nice=10",
        f"--setenv=TMPDIR={out}",
        "taskset",
        "-c",
        str(cpu),
        sys.executable,
        "-B",
        "-m",
        MODULE,
        "worker",
        str(out),
    ]
    tick = monotonic()
    with (out / "service.log").open("xb") as log:
        code = subprocess.run(
            command, stdout=log, stderr=subprocess.STDOUT, timeout=LIMIT + 40
        ).returncode
    info = subprocess.run(
        [
            "systemctl",
            "--user",
            "show",
            unit,
            "--property=MainPID,ControlPID,Result,ExecMainStatus,CPUUsageNSec,MemoryPeak,MemorySwapPeak,ActiveEnterTimestampMonotonic,InactiveEnterTimestampMonotonic",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=6,
    )
    state = dict(line.split("=", 1) for line in info.stdout.splitlines() if "=" in line)
    if any(state.get(key) != "0" for key in ("MainPID", "ControlPID")):
        raise RuntimeError("prior unit must release its CPU before the next invocation")
    save_json(
        out / "service.json",
        dict(
            unit=unit,
            state=state,
            exit_code=code,
            supervisor_s=monotonic() - tick,
            log_sha256=_sha(out / "service.log"),
        ),
    )
    print(out.parent.name, out.name, state.get("Result"), code, flush=True)


def controls(work, report):
    lock = stage(work, report)

    def lane(cpu):
        for ident in LANES[cpu]:
            directory = work / ident / "control"
            whole_iq.checked(
                directory / "request.json", lock["cases"][ident]["control_request_sha256"]
            )
            launch_case(directory, cpu)

    with ThreadPoolExecutor(max_workers=2) as workers:
        list(workers.map(lane, LANES))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    run = commands.add_parser("controls")
    run.add_argument("--work", type=local_output, default=WORK)
    run.add_argument("--out", type=local_output, default=REPORT)
    commands.add_parser("worker").add_argument("path", type=local_output)
    args = parser.parse_args()
    if args.action == "worker":
        worker(args.path)
    else:
        controls(args.work, args.out)


if __name__ == "__main__":
    main()
