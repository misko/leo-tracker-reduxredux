"""Qualify a relocated raw-only partner-on-hit release with matched whole-waveform runs."""

import argparse
import json
import subprocess
import tarfile
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import monotonic
from uuid import uuid4

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..variants.iq_stream import _read_prefix
from . import portable_conditional_trial as prior
from .full_v5_check import _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/antenna-confirmation/portable-stream"
WORK = Path("/var/tmp/leo-portable-stream-20261119")
SCHEDULE = {"DS26-0168": ("lower", (6, 7), (1, 2)), "DS29-0174": ("upper", (8, 9), (2, 1))}
RAW_LIMIT = 315
LIMIT = 420
PYTHON = prior.PYTHON
STOCK = "db80b772cf9f52941cc0073067816e571308cb43c3096516b77f73ed54986c66"


def source(ident, edge):
    case, request = whole_iq.binding(ident)
    center = request["job"]
    expected = dict(
        request_sha256=case["request"]["sha256"],
        catalog_sha256=case["catalog"]["sha256"],
        capture_native_sha256=case["native"]["sha256"],
        tile=case["regions"][0],
        orbit_snapshots=request["causal_snapshots"],
        recording=case["recording"],
    )
    manifest = prior.manifest(ident, expected)
    windows = []
    for item in manifest["segments"]:
        contents = _read_prefix(Path(item["path"]), 65_537)
        if len(contents) > 65_536 or sha256(contents).hexdigest() != item["sha256"]:
            raise ValueError("Raw capture manifest differs from its sealed digest")
        segment = json.loads(contents)
        if {t["edge"] for t in segment["configuration"]["targets"]} != {edge}:
            raise ValueError("The saved recording's authenticated RF edge changed")
        windows.append(segment["window_count"])
    if (
        manifest["offer"] != dict(center=center["search_center"], width_km=25)
        or sum(windows) != (case["recording"]["window_count"])
    ):
        raise ValueError("Offer or complete original raw window count changed")
    if any(Path(item["path"]).is_relative_to(ROOT) for item in manifest["segments"]):
        raise ValueError("The raw-only request must be usable with the repository hidden")
    return manifest, dict(edge=edge, windows=windows, **expected)


def freeze_inputs(work):
    inventory = {}
    work.mkdir(exist_ok=False)
    for ident, (edge, cpus, order) in SCHEDULE.items():
        inputs, bound = source(ident, edge)
        name = f"{ident}-input.json"
        save_json(REPORT / name, inputs)
        for count in order:
            out = work / ident / f"workers-{count}"
            out.mkdir(parents=True, exist_ok=False)
            subprocess.run(["setfacl", "-m", "u:leo:rwx", str(out)], check=True)
            request = out / "input.json"
            write(request, (REPORT / name).read_bytes())
            request.chmod(0o644)
        inventory[ident] = dict(bound, cpus=cpus, order=order, manifest_sha256=_sha(REPORT / name))
    programs = (Path(__file__), Path(prior.__file__))
    plan = dict(
        cases=inventory,
        memory_bytes=whole_iq.MEMORY,
        swap_bytes=0,
        service_limit_s=LIMIT,
        raw_limit_s=RAW_LIMIT,
        files={
            name: _sha(REPORT / name)
            for name in ("PROTOCOL.md", *(f"{i}-input.json" for i in SCHEDULE))
        },
        programs={str(file.relative_to(ROOT)): _sha(file) for file in programs},
    )
    save_json(REPORT / "input-lock.json", plan)


def package_binding(package, tar_path, expected):
    tar = whole_iq.checked(tar_path, expected)
    path = package / "files.json"
    with tarfile.open(tar) as archived:
        (index,) = [m for m in archived.getmembers() if m.name.endswith("/files.json")]
        payload = archived.extractfile(index).read()
        if payload != path.read_bytes():
            raise ValueError("Relocated package index differs from the released archive")
        pins = json.loads(payload)["files"]
    for name, digest in pins.items():
        file = (package / name).resolve(strict=True)
        if not file.is_relative_to(package):
            raise ValueError("Relocated release member escapes the read-only package")
        whole_iq.checked(file, digest)
    if pins["stock-wide.so"] != STOCK:
        raise ValueError("Packaged stock-wide binary differs from the previous detector")
    return dict(
        path=str(package), archive=str(tar), archive_sha256=_sha(tar), manifest_sha256=_sha(path)
    )


def command_for(out, package, cpus, count, unit, hidden):
    return [
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
        *(arg for folder in (ROOT, Path("/opt"), *hidden) for arg in ("--tmpfs", str(folder))),
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
        "partner-on-hit",
        "--visit-workers",
        str(count),
        "--cpus",
        *map(str, cpus),
        "--raw-deadline",
        str(RAW_LIMIT),
    ]


def launch(work, package, case, ident, count, hidden):
    out = work / ident / f"workers-{count}"
    whole_iq.checked(out / "input.json", case["manifest_sha256"])
    unit = f"leo-portable-stream-{ident.lower()}-{count}-{uuid4().hex[:6]}"
    command = command_for(out, package, case["cpus"], count, unit, hidden)
    log = out / "service.log"
    began = monotonic()
    save_json(out / "launch.json", dict(id=ident, visit_workers=count, unit=unit, command=command))
    with log.open("xb") as output:
        print(ident, "starting", count, "visit workers", flush=True)
        status = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, check=False)
    elapsed = monotonic() - began
    save_json(
        out / "service.json",
        dict(
            id=ident,
            visit_workers=count,
            command=command,
            wall_s=elapsed,
            exit_code=status.returncode,
            log_sha256=_sha(log),
        ),
    )
    print(ident, count, "finished", status.returncode, round(elapsed, 2), flush=True)


def dispatch(work, package, tar, digest, hidden):
    source_file = REPORT / "input-lock.json"
    lock = whole_iq.read(source_file)
    for name, expected in lock["files"].items():
        whole_iq.checked(REPORT / name, expected)
    for name, expected in lock["programs"].items():
        whole_iq.checked(ROOT / name, expected)
    bound = package_binding(package, tar, digest)
    save_json(
        REPORT / "source-lock.json",
        dict(
            input_lock_sha256=_sha(source_file),
            package=bound,
            stock_wide_sha256=STOCK,
            python=str(PYTHON),
            hidden=[str(p) for p in hidden],
        ),
    )

    def pair(ident):
        case = lock["cases"][ident]
        for count in case["order"]:
            launch(work, package, case, ident, count, hidden)

    with ThreadPoolExecutor(2) as pool:
        list(pool.map(pair, SCHEDULE))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    freeze = actions.add_parser("freeze")
    freeze.add_argument("--work", type=local_output, default=WORK)
    run = actions.add_parser("run")
    run.add_argument("--work", type=local_output, default=WORK)
    run.add_argument("--package", type=local_output, required=True)
    run.add_argument("--archive", type=Path, required=True)
    run.add_argument("--sha256", required=True)
    run.add_argument("--hide", type=Path, action="append", default=[])
    args = parser.parse_args()
    if args.action == "freeze":
        freeze_inputs(args.work)
    else:
        dispatch(args.work, args.package, args.archive, args.sha256, args.hide)
