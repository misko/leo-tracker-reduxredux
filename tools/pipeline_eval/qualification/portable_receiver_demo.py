"""Seal one relocated whole-recording run against its established stock control."""

import argparse
import shutil
import subprocess
from pathlib import Path
from time import monotonic
from uuid import uuid4

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from . import adaptive_arrival_position as authority
from . import portable_receiver_build
from .full_v5_check import BULK, _sha

CASE = "DS26-0197"
CPUS = (10, 11)
REPORT = authority.REPORT.parents[1] / "latency-and-support/portable-receiver"
MANIFEST = "recording-input.json"
PLAN = "source-lock.json"
LIMIT = 450


def stage(bundle, python, scratch):
    if (REPORT / PLAN).exists():
        raise FileExistsError("a portable receipt is already registered")
    scratch.mkdir(exist_ok=False)
    case, request = whole_iq.binding(CASE)
    job = request["job"]
    archive = Path(job["tle_root"])
    snapshots = {
        str(path.relative_to(archive)): request["causal_snapshots"][path.name].removeprefix(
            "sha256:"
        )
        for path in archive.rglob("*.tle")
    }
    spec = dict(
        schema="leo-portable-receiver-input/v1",
        segments=[
            dict(path=str(BULK / row["path"]), sha256=row["sha256"])
            for row in case["recording"]["segments"]
        ],
        tle=dict(path=str(archive), snapshots=snapshots),
        track_config=dict(
            path=job["track_config"]["path"],
            sha256=job["track_config"]["sha256"].removeprefix("sha256:"),
        ),
        offer=dict(center=job["search_center"], width_km=25),
        screen_center=job["screen_center"],
    )
    save_json(scratch / MANIFEST, spec)
    # The already deployed archive account can read the historical chunks. This
    # ACL affects only new local scratch and is never needed by the product.
    (scratch / MANIFEST).chmod(0o644)
    subprocess.run(["setfacl", "-m", "u:leo:rwx", str(scratch)], check=True)
    write(REPORT / MANIFEST, (scratch / MANIFEST).read_bytes())
    files = whole_iq.read(bundle / "files.json")
    if files["files"]["stock-wide.so"] != portable_receiver_build.STOCK:
        raise ValueError("portable package lacks the exact qualified stock detector")
    datasets = (
        authority.parent_member(
            "source-lock.json",
            whole_iq.read(
                whole_iq.checked(authority.PARENT / "prediction-lock.json", authority.PARENT_PIN)
            ),
        ),
    )
    previous = whole_iq.read(datasets[0])
    legacy = previous["cases"][CASE]
    if (
        legacy["request_sha256"] != case["request"]["sha256"]
        or legacy["capture_native_sha256"] != case["native"]["sha256"]
        or legacy["catalog_sha256"] != case["catalog"]["sha256"]
        or legacy["tile"] != case["regions"][0]
    ):
        raise ValueError("the demo no longer binds the exact archived stock input authority")
    isolation = [
        "sudo",
        "-n",
        "-u",
        "leo",
        "--",
        "bwrap",
        "--unshare-user",
        "--unshare-pid",
        "--unshare-net",
        "--unshare-ipc",
        "--unshare-uts",
        "--die-with-parent",
        "--ro-bind",
        "/",
        "/",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--tmpfs",
        str(ROOT),
        "--tmpfs",
        "/opt",
        "--bind",
        str(scratch),
        str(scratch),
        "--chdir",
        str(scratch),
        "--clearenv",
        "--setenv",
        "PATH",
        "/usr/bin:/bin",
        "--setenv",
        "TMPDIR",
        str(scratch),
    ]
    command = [
        *isolation,
        str(python),
        "-IB",
        str(bundle / "receive.py"),
        str(scratch / MANIFEST),
        "--out",
        str(scratch / "run"),
        "--cpus",
        *map(str, CPUS),
    ]
    lock = dict(
        id=CASE,
        native_sha256=case["native"]["sha256"],
        catalogue_sha256=case["catalog"]["sha256"],
        original_request_sha256=case["request"]["sha256"],
        tile=case["regions"][0],
        stock_prediction_sha256=authority.PARENT_PIN,
        protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
        detector_sha256=portable_receiver_build.STOCK,
        manifest_sha256=_sha(scratch / MANIFEST),
        package_sha256=_sha(bundle / "files.json"),
        command=command,
        cgroup=dict(cpu=CPUS, nice=10, memory_max=whole_iq.MEMORY, swap_max=0, limit_s=LIMIT),
        installed_files=len(files["files"]),
        installed_component_bytes=sum((bundle / name).stat().st_size for name in files["files"]),
        programs={str(Path(__file__).relative_to(ROOT)): _sha(Path(__file__))},
    )
    save_json(REPORT / PLAN, lock)
    write(scratch / PLAN, (REPORT / PLAN).read_bytes())
    print("sealed explicit recording request and relocated application", flush=True)


def run(bundle, python, scratch):
    stage(bundle, python, scratch)
    lock = whole_iq.read(scratch / PLAN)
    unit = "leo-portable-receiver-" + uuid4().hex[:12]
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        "--unit=" + unit,
        "--property=MemoryMax=" + str(whole_iq.MEMORY),
        "--property=MemorySwapMax=0",
        "--property=Nice=10",
        "--property=KillMode=control-group",
        "--property=RuntimeMaxSec=" + str(LIMIT) + "s",
        "taskset",
        "-c",
        ",".join(map(str, CPUS)),
        *lock["command"],
    ]
    before = monotonic()
    with (scratch / "service.log").open("xb") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
    elapsed = monotonic() - before
    show = subprocess.run(
        [
            "systemctl",
            "--user",
            "show",
            unit,
            "--property=MainPID,ControlPID,Result,CPUUsageNSec,MemoryPeak,MemorySwapPeak",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=6,
    )
    status = dict(line.split("=", 1) for line in show.stdout.splitlines() if "=" in line)
    save_json(
        REPORT / "service.json",
        dict(
            unit=unit,
            command=command,
            exit_code=result.returncode,
            systemd=status,
            elapsed_s=elapsed,
            log_sha256=_sha(scratch / "service.log"),
        ),
    )
    shutil.copyfile(scratch / "service.log", REPORT / "service.log")
    print(unit, result.returncode, elapsed, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=local_output)
    parser.add_argument("python", type=Path)
    parser.add_argument("scratch", type=local_output)
    args = parser.parse_args()
    run(args.bundle, args.python.absolute(), args.scratch)
