"""Measure the released tile publication guard on six frozen measured roof offers."""

import argparse
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
from ..scoring import ARMS, validate_result
from ..variants import compact_tile_decision, compact_tile_interior
from .full_v5_check import BULK, _sha

SCREEN = ROOT / "reports/2026_11_19_receiver_screening"
REPORT = SCREEN / "receiver-core/measured-boundary-policy"
SOURCE = SCREEN / "acquisition-support/outside-predictive"
INSTALL = Path("/home/mouse9911/.cache/compact-blind-20261119-v2/phase-release")
INSTALL_LOCK = SCREEN / "receiver-core/compact-blind/executables.json"
INSTALL_LOCK_SHA = "3ebe89c266085629887389bcbb86ffd510754256c65085f2b8aa43b329309e07"
GUARD_SHA = "38241e8bde0b9b44888869f1360de12dc7e158099fb996152eebc18217757a35"
SOURCE_SHA = "dd128d20f1e61ca1d54ca7276e2fdf7169b0ab87d7fc7417dc1463c650b73944"
WORK = Path("/home/mouse9911/.cache/leo-measured-boundary-policy-20261119")
LIMIT = 210
MODULE = "tools.pipeline_eval.qualification.measured_boundary_policy"
DECISION = "tools.pipeline_eval.variants.compact_tile_decision"
LANES = {
    2: ("DS26-0070", ("15b30a4eff19c1ecd3af", "72aaa1db3143b2f3dc96", "2d257491c63945c990fd")),
    21: ("DS26-0102", ("ae62c6cd475c45788842", "dba84955072d859bf006", "a60af4f23f523c5b9ef3")),
}


def plan(work, report, install):
    if work.exists() or (report / "source-lock.json").exists():
        raise FileExistsError("the six measured offers already have a prospective source lock")
    release = whole_iq.read(whole_iq.checked(INSTALL_LOCK, INSTALL_LOCK_SHA))["phase-release"]
    if whole_iq.receiver_identity(install) != release:
        raise ValueError("the installed phase-release receiver differs from its frozen source")
    whole_iq.checked(Path(compact_tile_interior.__file__), GUARD_SHA)
    if compact_tile_interior.STOP_KM != 0.020:
        raise ValueError("the historical 20 m gate changed")
    original = whole_iq.read(whole_iq.checked(SOURCE / "prediction-lock.json", SOURCE_SHA))
    roster = whole_iq.read(
        whole_iq.checked(SOURCE / "roster.json", original["files"]["roster.json"])
    )
    known = {r["id"]: r for r in roster["cases"] if r["cohort"] == "archived-roof"}
    offers = {}
    for cpu, (recording, ids) in LANES.items():
        case, before = whole_iq.binding(recording)
        job = before["job"]
        native = whole_iq.checked(BULK / case["native"]["path"], case["native"]["sha256"])
        catalogue = whole_iq.checked(BULK / case["catalog"]["path"], case["catalog"]["sha256"])
        for ident in ids:
            parent = known[ident]
            packet = parent["packet"]
            if (
                parent["recording"] != recording
                or packet["mode"] != "native"
                or packet["native"]["sha256"] != case["native"]["sha256"]
                or packet["catalogue"]["sha256"] != case["catalog"]["sha256"]
                or packet["track_config"]["sha256"]
                != job["track_config"]["sha256"].removeprefix("sha256:")
                or packet["offer"]["width_km"] != 25
            ):
                raise ValueError("the exact archived roof offer and capture request differ")
            tile = packet["offer"]
            child = dict(
                native=str(native),
                native_sha256=case["native"]["sha256"],
                session=case["session_id"],
                config=job["track_config"],
                archive=job["tle_root"],
                tile=tile["center"],
                screen=tile["center"],
                width_km=tile["width_km"],
                install=str(install),
                cpu=cpu,
            )
            request = work / ident / "request.json"
            save_json(request, child)
            offers[ident] = dict(
                recording=recording,
                cpu=cpu,
                tile=tile,
                input_sha256=whole_iq.recording.digest(packet)[7:],
                native_sha256=case["native"]["sha256"],
                catalog_sha256=_sha(catalogue),
                request_sha256=_sha(request),
                original_request_sha256=case["request"]["sha256"],
                causal_snapshots=before["causal_snapshots"],
            )
    paths = (
        Path(__file__),
        Path(compact_tile_interior.__file__),
        Path(compact_tile_decision.__file__),
        Path(whole_iq.raw.__file__),
        report / "PROTOCOL.md",
    )
    data = dict(
        offers=offers,
        install=str(install),
        installed_files=release,
        native_sources=whole_iq.native_sources(install),
        paths={str(p): _sha(p) for p in paths},
        parent_prediction_sha256=SOURCE_SHA,
        memory_max=whole_iq.MEMORY,
        swap_max=0,
        limit_s=LIMIT,
        stop_km=compact_tile_interior.STOP_KM,
    )
    save_json(report / "source-lock.json", data)
    save_json(work / "launch-lock.json", {"source_sha256": _sha(report / "source-lock.json")})
    return data


def check_pair(raw, off, on, tile):
    if raw != off:
        raise ValueError("guard-off CLI changed the installed receiver bytes")
    original, decision = map(json.loads, (off, on))
    for r in (original, decision):
        validate_result(r)
    if decision != compact_tile_interior.guard(original, tile):
        raise ValueError("guard-on CLI differs from the authenticated 20 m policy")
    if original["status"] == "ok":
        for arm in ARMS:
            a, b = original["arms"][arm], decision["arms"][arm]
            kept = b["latlon"] if decision["status"] == "ok" else b["forced_latlon"]
            if kept != a["latlon"] or b.get("rf_rms_hz") != a.get("rf_rms_hz"):
                raise ValueError("publication rule changed the numerical endpoint or RF fit")
    return original, decision


def worker(out):
    r = whole_iq.read(out / "request.json")
    if os.sched_getaffinity(0) != {r["cpu"]}:
        raise ValueError("the numerical service left its pinned CPU")
    save_json(out / "start.json", whole_iq.raw.mark("compact installed enter"))
    argv = [
        sys.executable,
        "-IB",
        r["install"],
        "--native",
        r["native"],
        "--native-sha256",
        r["native_sha256"],
        "--session",
        r["session"],
        "--track-config",
        r["config"]["path"],
        "--config-sha256",
        r["config"]["sha256"],
        "--archive",
        r["archive"],
        "--tile",
        *map(str, r["tile"]),
        "--screen-center",
        *map(str, r["screen"]),
        "--width-km",
        str(r["width_km"]),
    ]
    with (out / "installed.json").open("xb") as stream:
        subprocess.run(argv, cwd=out, stdout=stream, check=True)
    save_json(out / "solver-end.json", whole_iq.raw.mark("installed solver returned"))
    blob = (out / "installed.json").read_bytes()
    command = [sys.executable, "-B", "-m", DECISION]
    start = monotonic()
    off = subprocess.run(
        command, cwd=ROOT, input=blob, capture_output=True, timeout=5, check=True
    ).stdout
    off_s = monotonic() - start
    argv = command + [
        "--interior-guard",
        "--tile",
        *map(str, r["tile"]),
        "--width-km",
        str(r["width_km"]),
    ]
    start = monotonic()
    on = subprocess.run(
        argv, cwd=ROOT, input=off, capture_output=True, timeout=5, check=True
    ).stdout
    on_s = monotonic() - start
    check_pair(blob, off, on, dict(center=r["tile"], width_km=r["width_km"]))
    write(out / "guard-off.json", off)
    write(out / "guard-on.json", on)
    save_json(
        out / "end.json",
        dict(
            whole_iq.raw.mark("both publication decisions returned"),
            guard_off_wall_s=off_s,
            guard_on_wall_s=on_s,
        ),
    )


def launch_case(work, ident, lock):
    out = work / ident
    row = lock["offers"][ident]
    whole_iq.checked(out / "request.json", row["request_sha256"])
    unit = "leo-measured-boundary-" + uuid4().hex[:12]
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
        str(row["cpu"]),
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
            command, stdout=log, stderr=subprocess.STDOUT, timeout=LIMIT + 35
        ).returncode
    status = subprocess.run(
        [
            "systemctl",
            "--user",
            "show",
            unit,
            "--property=Result,MainPID,ControlPID,CPUUsageNSec,MemoryPeak,MemorySwapPeak,ActiveEnterTimestampMonotonic,InactiveEnterTimestampMonotonic",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=6,
    )
    terminal = dict(line.split("=", 1) for line in status.stdout.splitlines() if "=" in line)
    if any(terminal.get(k) != "0" for k in ("MainPID", "ControlPID")):
        raise RuntimeError("could not verify terminal service before the next offer")
    save_json(
        out / "service.json",
        dict(
            unit=unit,
            state=terminal,
            exit_code=code,
            supervisor_s=monotonic() - tick,
            log_sha256=_sha(out / "service.log"),
        ),
    )
    print(ident, terminal.get("Result"), code, flush=True)


def execute(work, report, install):
    lock = plan(work, report, install)

    def lane(pair):
        for ident in pair[1]:
            launch_case(work, ident, lock)

    with ThreadPoolExecutor(max_workers=2) as workers:
        list(workers.map(lane, LANES.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    run = sub.add_parser("run")
    run.add_argument("--work", type=local_output, default=WORK)
    run.add_argument("--out", type=local_output, default=REPORT)
    run.add_argument("--install", type=Path, default=INSTALL)
    sub.add_parser("worker").add_argument("path", type=local_output)
    args = parser.parse_args()
    if args.action == "worker":
        worker(args.path)
    else:
        execute(args.work, args.out, args.install)


if __name__ == "__main__":
    main()
