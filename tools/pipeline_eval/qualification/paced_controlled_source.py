"""Authenticate and stage complete IQ in a separately charged read-only tmpfs source."""

import argparse
import os
import pwd
import signal
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, THREAD_ENV, local_output, save_json, write
from . import arrival_queue as pace
from . import equal_pace, recording_to_v5
from .adaptive_arrival_worker import matching_clock
from .full_v5_check import _sha

REPORT = equal_pace.SCREEN / "pilot-influence/paced-controlled"
SOURCE = Path("/dev/shm/leo-paced-controlled-20261119")
OLD_SHA = "1889b1f519a3eb6446dfa079f96cec821e86976c4bdf2804e142ee8f2e95a7c0"
CASE = "DS29-0174"
UNIT = "leo-paced-controlled-source.service"
MODULE = "tools.pipeline_eval.qualification.paced_controlled_source"
SHAPE = (200_000, 2, 2)
WINDOW_BYTES = 1_600_000
COUNT = 6774
CAP = 12 * 1024**3
STAGE_TIME_LIMIT = 1800


def charge(group=None):
    if group is None:
        group = Path("/proc/self/cgroup").read_text().strip().split(":", 2)[2]
    path = Path("/sys/fs/cgroup") / group.lstrip("/")
    values = {
        name: int((path / name).read_text())
        for name in (
            "memory.current",
            "memory.peak",
            "memory.max",
            "memory.swap.current",
            "memory.swap.max",
        )
    }
    for file, fields in (
        ("memory.stat", ("anon", "shmem", "file")),
        ("memory.events", ("oom", "oom_kill")),
        ("cpu.stat", ("usage_usec",)),
    ):
        for line in (path / file).read_text().splitlines():
            name, value = line.split()
            if name in fields:
                values[f"{file}.{name}"] = int(value)
    if values["memory.max"] != CAP or values["memory.swap.max"] or values["memory.swap.current"]:
        raise ValueError("external predecoded source must have its own fixed zero-swap cgroup")
    return dict(values, cgroup=group)


def window_record(frame, expected):
    segment, window, bracket, clock = frame
    matching_clock(frame, expected)
    data = memoryview(window.samples).cast("B")
    digest = sha256(data).hexdigest()
    if (
        len(data) != WINDOW_BYTES
        or window.samples.shape != SHAPE
        or window.samples.dtype.str != "<i2"
        or digest != window.iq_sha256.removeprefix("sha256:")
        or (
            expected["center_hz"] is not None
            and expected["center_hz"] != window.target["rf_center_hz"]
        )
    ):
        raise ValueError("predecoded IQ differs from its sample layout, digest or RF center")
    return data, dict(
        segment=segment,
        sequence=window.sequence,
        iq_sha256=window.iq_sha256,
        acquisition=window.acquisition,
        target=window.target,
        sample_rate_hz=window.sample_rate_hz,
        bracket=bracket,
        clock=clock,
    )


def build(folder):
    if pwd.getpwuid(os.geteuid()).pw_name != "leo":
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
                *(f"{k}={v}" for k, v in THREAD_ENV.items()),
                str(recording_to_v5.ARCHIVE_PYTHON),
                "-B",
                "-m",
                MODULE,
                "build",
                str(folder),
            ],
        )
    spec = whole_iq.read(folder / "input.json")
    checked = pace.readgz(whole_iq.checked(folder / "events.json.gz", spec["events_sha256"]))
    if len(checked) != COUNT or spec["case"] != CASE:
        raise ValueError("source stage requires this complete sealed recording")
    begin = charge()
    capture = spec["capture"]
    staged, verified, digest = [], [], sha256()
    data_file = folder / "samples.ci16"
    with data_file.open("xb", buffering=0) as stream:
        for frame, expected in zip(pace.packets(capture, verified), checked, strict=True):
            data, member = window_record(frame, expected)
            if stream.write(data) != WINDOW_BYTES:
                raise OSError("short predecoded IQ write")
            digest.update(data)
            staged.append(member)
    data_file.chmod(0o444)
    verified_hash = _sha(data_file)
    authority = recording_to_v5.digest(
        [capture["input_manifest_sha256"], [m["iq_sha256"] for m in staged]]
    )
    actual = data_file.stat()
    if (
        len(staged) != COUNT
        or actual.st_size != COUNT * WINDOW_BYTES
        or digest.hexdigest() != verified_hash
        or authority != spec["raw_recording_sha256"]
        or not verified
    ):
        raise ValueError("complete original recording failed its independent tmpfs readback")
    members = folder / "members.json.gz"
    pace.writegz(members, staged)
    members.chmod(0o444)
    ready = folder / "ready.json"
    save_json(
        ready,
        dict(
            case=CASE,
            windows=len(staged),
            bytes=actual.st_size,
            inode=actual.st_ino,
            dev=actual.st_dev,
            mtime_ns=actual.st_mtime_ns,
            full_sha256=verified_hash,
            window_ledger_sha256=_sha(members),
            raw_recording_sha256=authority,
            compressed_chunks=len(verified),
            compressed_bytes=sum(verified),
            start=begin,
            end=charge(),
        ),
    )
    ready.chmod(0o444)
    print("complete authenticated predecoded source", verified_hash, flush=True)
    signal.pause()


def start(folder):
    old_path = whole_iq.checked(equal_pace.REPORT / "source-lock.json", OLD_SHA)
    old = whole_iq.read(old_path)
    if old["case"] != CASE:
        raise ValueError("controlled source case changed")
    spec = old["cases"][CASE]
    bound = spec["modes"][equal_pace.FOUR]
    events = whole_iq.checked(equal_pace.REPORT / bound["events"], bound["sha256"])
    capture_bytes = COUNT * WINDOW_BYTES
    if os.statvfs(folder.parent).f_bavail * os.statvfs(folder.parent).f_frsize < capture_bytes:
        raise ValueError("insufficient local predecoded source capacity")
    folder.mkdir(mode=0o755, exist_ok=False)
    subprocess.run(["setfacl", "-m", "u:leo:rwx", str(folder)], check=True)
    source_input = dict(
        case=CASE,
        capture=spec["capture"],
        events_sha256=bound["sha256"],
        raw_recording_sha256=spec["raw_recording_sha256"],
    )
    save_json(folder / "input.json", source_input)
    write(folder / "events.json.gz", events.read_bytes())
    for path in (folder / "input.json", folder / "events.json.gz"):
        path.chmod(0o444)
    save_json(
        REPORT / "source-stage-lock.json",
        dict(
            input=source_input,
            equal_source_sha256=OLD_SHA,
            source_cap_bytes=CAP,
            source_swap_max=0,
            source_limit_s=STAGE_TIME_LIMIT,
            iq_bytes=capture_bytes,
            sources={str(Path(__file__).relative_to(ROOT)): _sha(Path(__file__))},
            source_service=UNIT,
        ),
    )
    command = [
        "systemd-run",
        "--user",
        "--no-block",
        f"--unit={UNIT}",
        f"--working-directory={ROOT}",
        f"--property=RuntimeMaxSec={STAGE_TIME_LIMIT}s",
        f"--property=MemoryMax={CAP}",
        "--property=MemorySwapMax=0",
        "--property=KillMode=control-group",
        "--property=Nice=10",
        f"--setenv=PYTHONPATH={spec['producer']}:{ROOT}",
        *(f"--setenv={k}={v}" for k, v in THREAD_ENV.items()),
        "taskset",
        "-c",
        str(equal_pace.MAIN),
        sys.executable,
        "-B",
        "-m",
        MODULE,
        "build",
        str(folder),
    ]
    subprocess.run(command, check=True)


def packets(folder):
    """A bounded read supplies one immutable original window at a time."""
    import numpy as np

    from leo.scanner.fast_scan_analysis import VerifiedFastWindow

    ready = whole_iq.read(folder / "ready.json")
    members = pace.readgz(
        whole_iq.checked(folder / "members.json.gz", ready["window_ledger_sha256"])
    )
    with (folder / "samples.ci16").open("rb", buffering=0) as stream:
        stat = os.fstat(stream.fileno())
        if (
            len(members) != ready["windows"]
            or ready["windows"] != COUNT
            or (stat.st_size, stat.st_ino, stat.st_dev, stat.st_mtime_ns)
            != (ready["bytes"], ready["inode"], ready["dev"], ready["mtime_ns"])
        ):
            raise ValueError("staged IQ inode, size, timestamp or visit count changed")
        for item in members:
            payload = stream.read(WINDOW_BYTES)
            if len(payload) != WINDOW_BYTES:
                raise ValueError("staged IQ ended before its exact physical window count")
            w = VerifiedFastWindow(
                item["sequence"],
                item["iq_sha256"],
                item["acquisition"],
                item["target"],
                np.frombuffer(payload, dtype="<i2").reshape(SHAPE),
                sample_rate_hz=item["sample_rate_hz"],
            )
            yield item["segment"], w, item["bracket"], item["clock"]
        if stream.read(1):
            raise ValueError("staged IQ exceeds the authenticated capture inventory")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "build"))
    parser.add_argument("folder", type=local_output, nargs="?", default=SOURCE)
    args = parser.parse_args()
    {"stage": start, "build": build}[args.action](args.folder)
