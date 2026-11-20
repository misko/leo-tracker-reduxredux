"""Stage the exact DS29-0082 clock and raw bytes for the matched paced receiver."""

import argparse
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, THREAD_ENV, save_json, write
from . import arrival_queue as pace
from . import capture_release
from . import paced_controlled_source as spool
from .full_v5_check import _sha

CASE, COUNT, INVALID = "DS29-0082", 6772, 1904
MAIN, STAGING = 10, 11
SCREEN = ROOT / "reports/2026_11_19_receiver_screening"
ORIGINAL = SCREEN / "antenna-confirmation/capture-whole"
REPORT = SCREEN / "original-support/paced-original"
SOURCE = Path("/dev/shm/leo-paced-original-20261119")
CAPTURE_SEAL = "84f9aa52911b391a8a23c60a57dd0f3e8d4106060ba94fb7e92b40215c829d33"
UNIT = "leo-paced-original-source.service"
MODULE = "tools.pipeline_eval.qualification.paced_original_source"


def clock_events(doc):
    hardware = {r["visit"] for r in doc["provenance"]["excluded_windows"]}
    if len(hardware) != INVALID or doc["provenance"]["window_count"] != COUNT:
        raise ValueError("the original 6,772-visit physical clock changed")
    centers = {}
    for probe in doc["source"]["probes"]:
        f = probe["actual_rf_hz"]
        if int(f) != f or centers.setdefault(probe["visit_index"], int(f)) != f:
            raise ValueError("the two original physical probe slots disagree on RF")
    # The hash field is empty here because staging is source-only.
    statuses = [
        dict(
            visit=i,
            status="invalid_capture" if i in hardware else "processed",
            full_visit_sha256=None,
        )
        for i in range(COUNT)
    ]
    return [
        dict(row, center_hz=centers.get(row["visit"]))
        for row in pace.reference_events(doc, statuses)
    ]


def source_plan():
    from .fresh_replay_results import sealed

    lock = sealed(ORIGINAL, "prediction-lock.json", CAPTURE_SEAL)
    raw = pace.readgz(ORIGINAL / "native.json.gz")
    binding = whole_iq.read(ORIGINAL / "source-lock.json")
    case, _ = whole_iq.binding(CASE)
    capture = dict(capture_release.read_capture(case), case=case)
    if (
        lock["cases"] != [CASE]
        or capture["input_manifest_sha256"] != binding["capture"]["input_manifest_sha256"]
        or case["native"] != binding["original"]["native"]
        or raw["source"]["input_manifest_sha256"] != capture["input_manifest_sha256"]
    ):
        raise ValueError("staging requires the original authenticated receiver, waveform and clock")
    return dict(
        case=CASE,
        capture=capture,
        raw_recording_sha256=raw["source"]["raw_recording_authority_digest"],
        producer=binding["producer"],
        python=binding["python"],
    ), clock_events(raw)


def start():
    spec, events = source_plan()
    SOURCE.mkdir(mode=0o755, exist_ok=False)
    subprocess.run(["setfacl", "-m", "u:leo:rwx", str(SOURCE)], check=True)
    pace.writegz(REPORT / "clock-events.json.gz", events)
    write(SOURCE / "events.json.gz", (REPORT / "clock-events.json.gz").read_bytes())
    (SOURCE / "events.json.gz").chmod(0o444)
    spec["events_sha256"] = _sha(SOURCE / "events.json.gz")
    save_json(SOURCE / "input.json", spec)
    (SOURCE / "input.json").chmod(0o444)
    save_json(
        REPORT / "source-stage-lock.json",
        dict(
            input=spec,
            external_memory_max=spool.CAP,
            external_swap_max=0,
            capture_prediction_sha256=CAPTURE_SEAL,
            source_cpu=STAGING,
            evaluator_sha256=_sha(Path(__file__)),
            source_spool_sha256=_sha(Path(spool.__file__)),
        ),
    )
    command = [
        "systemd-run",
        "--user",
        "--no-block",
        f"--unit={UNIT}",
        f"--working-directory={ROOT}",
        "--property=RuntimeMaxSec=1800s",
        f"--property=MemoryMax={spool.CAP}",
        "--property=MemorySwapMax=0",
        "--property=KillMode=control-group",
        "--property=Nice=10",
        f"--setenv=PYTHONPATH={spec['producer']}:{ROOT}",
        *(f"--setenv={k}={v}" for k, v in THREAD_ENV.items()),
        "taskset",
        "-c",
        str(STAGING),
        sys.executable,
        "-B",
        "-m",
        MODULE,
        "build",
        str(SOURCE),
    ]
    subprocess.run(command, check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "build"))
    parser.add_argument("folder", type=Path, nargs="?", default=SOURCE)
    args = parser.parse_args()
    with patch.multiple(spool, CASE=CASE, COUNT=COUNT, MODULE=MODULE):
        if args.action == "start":
            start()
        else:
            spool.build(args.folder)
