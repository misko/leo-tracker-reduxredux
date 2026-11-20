"""Run the conditional portable receiver from local read-only saved capture manifests."""

import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from . import portable_conditional_build as release
from . import second_on_miss_whole as direct
from .full_v5_check import BULK, _sha

REPORT = release.REPORT
CASES = {"DS26-0014": (2, 3), "DS29-0082": (3, 2)}
LIMIT = 420
PYTHON = Path("/var/tmp/leo-portable-python-20261119/bin/python")
read = whole_iq.read


def manifest(ident, authority):
    case, original = whole_iq.binding(ident)
    job = original["job"]
    if any(
        authority[field] != value
        for field, value in (
            ("request_sha256", case["request"]["sha256"]),
            ("catalog_sha256", case["catalog"]["sha256"]),
            ("capture_native_sha256", case["native"]["sha256"]),
            ("tile", case["regions"][0]),
            ("orbit_snapshots", original["causal_snapshots"]),
            ("recording", case["recording"]),
        )
    ):
        raise ValueError("new portable input differs from the independent verification cohort")
    archive = Path(job["tle_root"])
    return dict(
        schema="leo-portable-receiver-input/v1",
        segments=[
            dict(path=str(BULK / item["path"]), sha256=item["sha256"])
            for item in case["recording"]["segments"]
        ],
        tle=dict(
            path=str(archive),
            snapshots={
                str(path.relative_to(archive)): original["causal_snapshots"][
                    path.name
                ].removeprefix("sha256:")
                for path in archive.rglob("*.tle")
            },
        ),
        track_config=dict(
            path=job["track_config"]["path"],
            sha256=job["track_config"]["sha256"].removeprefix("sha256:"),
        ),
        offer=dict(center=job["search_center"], width_km=25),
        screen_center=job["screen_center"],
    )


def launch(work, package, ident, cpus):
    out = work / ident
    unit = "leo-portable-conditional-" + ident.lower()
    command = [
        "systemd-run",
        "--user",
        "--pipe",
        "--wait",
        "--collect",
        f"--unit={unit}",
        f"--property=RuntimeMaxSec={LIMIT}s",
        "--property=TimeoutStopSec=8s",
        f"--property=MemoryMax={whole_iq.MEMORY}",
        "--property=MemorySwapMax=0",
        "--property=Nice=10",
        "--property=KillMode=control-group",
        "taskset",
        "-c",
        ",".join(map(str, cpus)),
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
        "--tmpfs",
        "/var/tmp/leo-portable-conditional-build2",
        "--tmpfs",
        "/var/tmp/leo-portable-install-20261119",
        "--bind",
        str(out),
        str(out),
        "--chdir",
        str(out),
        "--clearenv",
        "--setenv",
        "PATH",
        "/usr/bin:/bin",
        "--setenv",
        "TMPDIR",
        str(out),
        str(PYTHON),
        "-IB",
        str(package / "receive.py"),
        str(out / "input.json"),
        "--out",
        str(out / "actual"),
        "--detector",
        "second-on-miss",
        "--cpus",
        *map(str, cpus),
        "--raw-deadline",
        "315",
    ]
    start = monotonic()
    log = out / "service.log"
    with log.open("xb") as output:
        result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, check=False)
    save_json(
        out / "service.json",
        dict(
            case=ident,
            command=command,
            exit_code=result.returncode,
            wall_s=monotonic() - start,
            log_sha256=_sha(log),
        ),
    )
    print(ident, "finished", result.returncode, round(monotonic() - start, 1), flush=True)


def run(work, package):
    work.mkdir()
    base = direct.REPORT / "source-lock.json"
    authority = read(base)
    if set(authority["cases"]) != set(CASES):
        raise ValueError("the qualification must run both direct-study baseline captures")
    for ident in CASES:
        out = work / ident
        out.mkdir()
        subprocess.run(["setfacl", "-m", "u:leo:rwx", str(out)], check=True)
        spec = manifest(ident, authority["cases"][ident])
        save_json(out / "input.json", spec)
        (out / "input.json").chmod(0o644)
        write(REPORT / f"{ident}-input.json", (out / "input.json").read_bytes())
    names = ("PROTOCOL.md", *(f"{ident}-input.json" for ident in CASES))
    save_json(
        REPORT / "source-lock.json",
        dict(
            cases=list(CASES),
            cpus=CASES,
            memory_bytes=whole_iq.MEMORY,
            swap_bytes=0,
            limit_s=LIMIT,
            files={name: _sha(REPORT / name) for name in names},
            sources={
                (str(p.relative_to(ROOT))): _sha(p)
                for p in (
                    Path(__file__),
                    base,
                    Path(release.__file__),
                    Path(release.portable_conditional_capture.__file__),
                    *(Path(module.__file__) for module, _ in release.EXTRACTS),
                )
            },
            base_package_sha256=release.BASE_SHA,
            package_manifest_sha256=_sha(package / "files.json"),
            python=str(PYTHON),
        ),
    )
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(lambda case: launch(work, package, case, CASES[case]), CASES))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("package", type=local_output)
    args = parser.parse_args()
    run(args.work, args.package)
