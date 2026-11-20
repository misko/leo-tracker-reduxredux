"""Run the original full v5 worker on the sealed complete wide four-start factors."""

import argparse
import gzip
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from time import monotonic
from uuid import uuid4

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..variants import v5_lean as v5
from . import original_v5
from .full_v5_check import _sha
from .whole_pressure_trial import rows_from

SCREEN = ROOT / "reports/2026_11_19_receiver_screening"
REPORT = SCREEN / "receiver-core/wide-full-v5"
WORK = v5.SOURCE.parents[1] / "wide-full-v5-20261119"
PRIMARY = SCREEN / "acquisition-support/scout-full"
REPEAT = PRIMARY.with_name("deadline-repeat")
PIN = {
    PRIMARY: "42d5e21eacaed581df00d9fd3be33035c707479b59bbc24eec72a6756c3b81fc",
    REPEAT: "376087bb676ed73004f86069293390c8e01e0f781e2d42be0ae418c176140a85",
}
ANCHORS = ("DS26-0122", "DS29-0082")
LIMIT, MEMORY = 600, 4 * 1024**3
MODULE = "tools.pipeline_eval.qualification.wide_full_v5"
THREADS = dict.fromkeys(
    (
        "OPENBLAS_NUM_THREADS",
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "BLIS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ),
    "1",
)


def digest(value):
    return (
        "sha256:"
        + sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
    )


def ranking(rows):
    eligible = sorted(
        (row["native_sha256"], ident) for ident, row in rows.items() if ident not in ANCHORS
    )
    return [*ANCHORS, *(ident for _, ident in eligible[:2])]


def _run_id(request, ident, native):
    return (
        "experiment-"
        + digest(
            dict(
                case=ident,
                repetition=0,
                role="baseline",
                source=request["source"]["sha256"],
                native=request["native_manifest"],
                input=native,
            )
        )[7:47]
    )


def bind(original, case, wide, blob, out):
    job = original["job"]
    native = "sha256:" + sha256(blob).hexdigest()
    if (
        original["role"] != "baseline"
        or original["policy"] != "fast-v5-zero-recovery-control-v1"
        or job["evaluation_reference"] is not None
        or job["identity"]["session_id"] != case["session_id"]
        or job["native_input"]["sha256"] != "sha256:" + case["native"]["sha256"]
        or job["identity"]["input_sha256"] != job["native_input"]["sha256"]
        or job["identity"]["run_id"] != _run_id(original, case["id"], job["native_input"]["sha256"])
        or wide["native_sha256"] != native[7:]
        or wide["original_request_sha256"] != case["request"]["sha256"]
        or wide["catalog_sha256"] != case["catalog"]["sha256"]
        or wide["tile"] != case["regions"][0]
    ):
        raise ValueError("wide replay and original no-repair request do not use the same recording")
    request = deepcopy(original)
    request["job"]["native_input"] = dict(path=str(out / "native.json"), sha256=native)
    request["job"]["identity"].update(
        input_sha256=native, run_id=_run_id(original, case["id"], native)
    )
    request["job"]["output_root"] = str(out / "original-output")
    return request


def past_controls():
    plans = {}
    all_rows = {}
    for folder, method in (
        (PRIMARY, "scout-centers_control"),
        (REPEAT, "scout-deadline-repeat_control"),
    ):
        lock = whole_iq.read(whole_iq.checked(folder / "prediction-lock.json", PIN[folder]))
        paths = {
            name: whole_iq.checked(folder / name, lock["files"][name])
            for name in ("positions.jsonl.gz", "resources.json", "source-lock.json")
        }
        all_rows[folder] = {
            r["id"]: r for r in rows_from(paths["positions.jsonl.gz"]) if r["method"] == method
        }
        plans[folder] = (lock, whole_iq.read(paths["resources.json"]))
    selected = ranking(all_rows[PRIMARY])
    if len(all_rows[PRIMARY]) != 8 or len(set(selected)) != 4:
        raise ValueError("the eight archived four-start controls changed")
    for ident in selected:
        primary = all_rows[PRIMARY][ident]
        folder = PRIMARY if primary["result"]["status"] == "ok" else REPEAT
        compact = all_rows[folder][ident]
        if (
            compact["result"]["status"] != "ok"
            or compact["native_sha256"] != primary["native_sha256"]
        ):
            raise ValueError(
                "no successful phase-release compact prediction on identical wide factors"
            )
        native = f"native/control/{ident}.json.gz"
        archive = whole_iq.checked(PRIMARY / native, plans[PRIMARY][0]["files"][native])
        yield ident, compact, folder, plans[folder][1][ident]["control"], archive


def prepare(work, report):
    if work.exists() or (report / "source-lock.json").exists():
        raise FileExistsError("the four original v5 services are already planned")
    for name, digest_value in original_v5.RUNNER_DIGESTS.items():
        whole_iq.checked(v5.RUNNER / name, digest_value)
    schedule, inputs = {20: [], 21: []}, {}
    for ident, compact, folder, compact_resources, archive in past_controls():
        cpu = 20 if ident.startswith("DS26") else 21
        out = work / ident
        case, historical = whole_iq.binding(ident)
        blob = gzip.decompress(archive.read_bytes())
        document = json.loads(blob)
        if (
            document["source"]["session_id"] != case["session_id"]
            or document["source"]["input_manifest_sha256"]
            != compact_resources["input_manifest_sha256"]
            or document["provenance"]["detector_sha256"]
            != "sha256:" + compact_resources["detector_sha256"]
        ):
            raise ValueError("native archive differs from the compact service lineage")
        request = bind(historical, case, compact, blob, out)
        write(out / "native.json", blob)
        save_json(out / "request.json", request)
        schedule[cpu].append(ident)
        inputs[ident] = dict(
            cpu=cpu,
            compact=compact,
            compact_source=str(folder.relative_to(SCREEN)),
            compact_resources=compact_resources,
            native_archive=str(archive),
            native_archive_sha256=_sha(archive),
            rebound_request_sha256=_sha(out / "request.json"),
            original_native_sha256=case["native"]["sha256"],
            original_request_sha256=case["request"]["sha256"],
        )
    pins = dict(
        cases=inputs,
        schedule=schedule,
        deadline_s=LIMIT,
        memory_max=MEMORY,
        swap_max=0,
        protocol_sha256=_sha(report / "PROTOCOL.md"),
        launcher_sha256=_sha(Path(__file__)),
        runner_sha256=original_v5.RUNNER_DIGESTS,
        source_sha256=v5.SOURCE_SHA256,
        parents={str(path.relative_to(SCREEN)): value for path, value in PIN.items()},
    )
    save_json(report / "source-lock.json", pins)
    save_json(work / "launch-lock.json", {"source_sha256": _sha(report / "source-lock.json")})
    return pins


def measure():
    group = Path("/sys/fs/cgroup") / Path("/proc/self/cgroup").read_text().strip().split(":")[
        2
    ].lstrip("/")
    values = {
        name: int((group / name).read_text())
        for name in (
            "memory.max",
            "memory.peak",
            "memory.swap.max",
            "memory.swap.current",
        )
    }
    usage = dict(line.split() for line in (group / "cpu.stat").read_text().splitlines())
    events = dict(line.split() for line in (group / "memory.events").read_text().splitlines())
    if values["memory.max"] != MEMORY or values["memory.swap.max"] != 0:
        raise ValueError("original v5 process could not verify its resource cap")
    return dict(
        values,
        cgroup=str(group),
        cpu_usec=int(usage["usage_usec"]),
        oom_kill=int(events["oom_kill"]),
        monotonic_s=monotonic(),
    )


def worker(out, cpu):
    if os.sched_getaffinity(0) != {cpu}:
        raise ValueError("original v5 process left its assigned CPU")
    save_json(out / "start.json", measure())
    env = dict(
        os.environ,
        **THREADS,
        PYTHONPATH=f"{v5.SOURCE}:{v5.RUNNER}",
        PYTHONSAFEPATH="1",
        MPLCONFIGDIR=str(out / "matplotlib"),
    )
    (out / "original-output").mkdir()
    run = subprocess.run(
        [
            str(v5.PYTHON),
            "-B",
            str(v5.RUNNER / "evaluate_accuracy_repair.py"),
            "worker",
            "--request",
            str(out / "request.json"),
        ],
        cwd=ROOT,
        env=env,
        check=False,
    )
    save_json(out / "end.json", dict(measure(), worker_exit_code=run.returncode))
    return run.returncode


def launch_case(work, pins, ident):
    out = work / ident
    row = pins["cases"][ident]
    whole_iq.checked(out / "request.json", row["rebound_request_sha256"])
    whole_iq.checked(out / "native.json", row["compact"]["native_sha256"])
    unit = "leo-wide-full-v5-" + uuid4().hex[:12]
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        f"--unit={unit}",
        f"--working-directory={ROOT}",
        f"--property=MemoryMax={MEMORY}",
        "--property=MemorySwapMax=0",
        f"--property=RuntimeMaxSec={LIMIT}s",
        "--property=TimeoutStopSec=8s",
        "--property=KillMode=control-group",
        "--property=Nice=10",
        "taskset",
        "-c",
        str(row["cpu"]),
        str(v5.PYTHON),
        "-B",
        "-m",
        MODULE,
        "worker",
        str(out),
        "--cpu",
        str(row["cpu"]),
    ]
    print(ident, "starting original full v5", flush=True)
    started = monotonic()
    with (out / "service.log").open("xb") as log:
        code = subprocess.run(
            command, stdout=log, stderr=subprocess.STDOUT, timeout=LIMIT + 40
        ).returncode
    status = subprocess.run(
        [
            "systemctl",
            "--user",
            "show",
            unit,
            "--property=Result,CPUUsageNSec,MemoryPeak,MemorySwapPeak,ExecMainStatus,MainPID,ControlPID,ActiveState,ActiveEnterTimestampMonotonic,InactiveEnterTimestampMonotonic",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=6,
    )
    state = dict(line.split("=", 1) for line in status.stdout.splitlines() if "=" in line)
    if state.get("MainPID") != "0" or state.get("ControlPID") != "0":
        raise RuntimeError(f"{ident} service has no confirmed terminal PID receipt")
    save_json(
        out / "service.json",
        dict(
            exit_code=code,
            supervisor_s=monotonic() - started,
            unit=unit,
            systemd=state,
            log_sha256=_sha(out / "service.log"),
        ),
    )
    print(ident, state.get("Result"), code, flush=True)


def launch(work, report):
    pins = prepare(work, report)

    def lane(ids):
        for ident in ids:
            launch_case(work, pins, ident)

    with ThreadPoolExecutor(max_workers=2) as workers:
        list(workers.map(lane, pins["schedule"].values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    run = commands.add_parser("run")
    run.add_argument("--work", type=local_output, default=WORK)
    run.add_argument("--out", type=local_output, default=REPORT)
    child = commands.add_parser("worker")
    child.add_argument("path", type=local_output)
    child.add_argument("--cpu", type=int, required=True)
    args = parser.parse_args()
    if args.action == "worker":
        raise SystemExit(worker(args.path, args.cpu))
    launch(args.work, args.out)


if __name__ == "__main__":
    main()
