"""Authenticate and stage the complete physical inputs for the parallel acquisition run."""

import argparse
import os
import pwd
import subprocess
from pathlib import Path
from time import monotonic_ns
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, THREAD_ENV, local_output, save_json
from . import arrival_queue as pace
from . import capture_release
from . import paced_controlled_source as spool
from .full_v5_check import _load_case, _sha

SCREEN = ROOT / "reports/2026_11_19_receiver_screening"
REPORT = SCREEN / "receiver-deadline/parallel-acquisition"
STAGE = Path("/dev/shm/leo-parallel-acquisition-20261119")
CPUS = {"DS29-0082": (2, 3, 4), "DS26-0237": (5, 6, 7)}
ORIGINAL = {
    "DS29-0082": (
        SCREEN / "antenna-confirmation/capture-whole",
        "84f9aa52911b391a8a23c60a57dd0f3e8d4106060ba94fb7e92b40215c829d33",
    ),
    "DS26-0237": (
        SCREEN / "original-support/prepared-waveform",
        "edc1e5792841e9d7eb4590e52828cf67b4050a4146d9c209abf9503129cb35ee",
    ),
}
MODULE = "tools.pipeline_eval.qualification.parallel_acquisition_source"
STAGE_LIMIT_S = 900


def original_reference(case_id):
    folder, seal_sha = ORIGINAL[case_id]
    lock = whole_iq.read(whole_iq.checked(folder / "prediction-lock.json", seal_sha))
    if lock["cases"] != [case_id]:
        raise ValueError("original waveform seal identifies a different recording")
    native = whole_iq.checked(folder / "native.json.gz", lock["files"]["native.json.gz"])
    binding = whole_iq.read(
        whole_iq.checked(folder / "source-lock.json", lock["files"]["source-lock.json"])
    )
    return pace.readgz(native), binding


def clock_events(doc):
    invalid = {row["visit"] for row in doc["provenance"]["excluded_windows"]}
    count = doc["provenance"]["window_count"]
    centers = {}
    for probe in doc["source"]["probes"]:
        f = probe["actual_rf_hz"]
        if int(f) != f or centers.setdefault(probe["visit_index"], int(f)) != f:
            raise ValueError("physical probe slots disagree on RF")
    statuses = [
        dict(
            visit=i,
            status="invalid_capture" if i in invalid else "processed",
            full_visit_sha256=None,
        )
        for i in range(count)
    ]
    return [
        dict(row, center_hz=centers.get(row["visit"]))
        for row in pace.reference_events(doc, statuses)
    ]


def service(unit, memory, runtime, cpu, producer, python, module, action, *arguments):
    return [
        "systemd-run",
        "--user",
        "--no-block",
        f"--unit={unit}",
        f"--working-directory={ROOT}",
        f"--property=RuntimeMaxSec={runtime}s",
        f"--property=MemoryMax={memory}",
        "--property=MemorySwapMax=0",
        "--property=KillMode=control-group",
        "--property=Nice=10",
        f"--setenv=PYTHONPATH={producer}:{ROOT}",
        *(f"--setenv={key}={value}" for key, value in THREAD_ENV.items()),
        "taskset",
        "-c",
        str(cpu),
        str(python),
        "-B",
        "-m",
        module,
        action,
        *map(str, arguments),
    ]


def stage(case_id, folder, *, cpu=None, unit=None):
    doc, binding = original_reference(case_id)
    case = _load_case(case_id)
    capture = dict(capture_release.read_capture(case), case=case)
    producer = capture_release.producer(case, capture)
    events = clock_events(doc)
    if (
        capture["input_manifest_sha256"] != binding["capture"]["input_manifest_sha256"]
        or case["native"] != binding["original"]["native"]
        or doc["source"]["input_manifest_sha256"] != capture["input_manifest_sha256"]
        or str(producer.root) != binding["producer"]
        or case["recording"]["window_count"] != len(events)
    ):
        raise ValueError("capture release, original waveform bytes and recorded clock disagree")
    iq_bytes = len(events) * spool.WINDOW_BYTES
    space = os.statvfs(folder.parent)
    if space.f_bavail * space.f_frsize < iq_bytes:
        raise OSError("insufficient local tmpfs for complete physical input")
    folder.mkdir(mode=0o755)
    subprocess.run(["setfacl", "-m", "u:leo:rwx", str(folder)], check=True)
    pace.writegz(folder / "events.json.gz", events)
    if cpu is None:
        cpu = CPUS[case_id][2]
    if unit is None:
        unit = f"leo-parallel-{case_id.lower()}-stage.service"
    spec = dict(
        case=case_id,
        capture=capture,
        producer=str(producer.root),
        python=binding["python"],
        python_sha256=binding["python_sha256"],
        original_seal_sha256=ORIGINAL[case_id][1],
        raw_recording_sha256=doc["source"]["raw_recording_authority_digest"],
        events_sha256=_sha(folder / "events.json.gz"),
        windows=len(events),
        iq_bytes=iq_bytes,
        last_arrival_ns=events[-1]["arrival_ns"],
        cpu=cpu,
        stage_unit=unit,
        stage_memory_max=spool.CAP,
        stage_swap_max=0,
        stage_limit_s=STAGE_LIMIT_S,
        requested_ns=monotonic_ns(),
    )
    save_json(folder / "input.json", spec)
    for path in (folder / "input.json", folder / "events.json.gz"):
        path.chmod(0o444)
    subprocess.run(
        service(
            unit,
            spool.CAP,
            STAGE_LIMIT_S,
            cpu,
            producer.root,
            binding["python"],
            MODULE,
            "build",
            case_id,
            folder,
        ),
        check=True,
    )


def build(case_id, folder):
    spec = whole_iq.read(folder / "input.json")
    if spec["case"] != case_id or os.sched_getaffinity(0) != {spec["cpu"]}:
        raise ValueError("source staging case or dedicated CPU changed")
    read_charge = spool.charge

    def charge():
        return dict(read_charge(), monotonic_ns=monotonic_ns(), cpu=spec["cpu"])

    with patch.multiple(spool, CASE=case_id, COUNT=spec["windows"], MODULE=MODULE, charge=charge):
        # The re-exec under the capture reader must preserve this experiment's case argument.
        if os.geteuid() != pwd.getpwnam("leo").pw_uid:
            os.execv(
                "/usr/bin/sudo",
                [
                    "sudo",
                    "-n",
                    "-u",
                    "leo",
                    "--",
                    "env",
                    f"PYTHONPATH={os.environ['PYTHONPATH']}",
                    *(f"{key}={value}" for key, value in THREAD_ENV.items()),
                    spec["python"],
                    "-B",
                    "-m",
                    MODULE,
                    "build",
                    case_id,
                    str(folder),
                ],
            )
        spool.build(folder)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "build"))
    parser.add_argument("case_id", choices=CPUS)
    parser.add_argument("folder", type=local_output)
    args = parser.parse_args()
    {"stage": stage, "build": build}[args.action](args.case_id, args.folder)
