"""Counterbalance the three detector paths on one pinned main/helper pair."""

import argparse
import json
import os
import subprocess
import sys
from contextlib import ExitStack, contextmanager
from pathlib import Path
from uuid import uuid4

import numpy as np

from .. import whole_iq
from ..__main__ import ROOT, THREAD_ENV, local_output, save_json
from ..variants import iq_stream
from . import combined_native_build as build
from . import dual_lane_eval as lane
from . import native_hotpath_eval as hot
from .arrival_queue import fingerprint
from .full_v5_check import _load_case, _sha

CASES = ("DS26-0197", "DS29-0316")
PINS = (20, 21)
SEGMENTS = (3, 8)
ROLES = ("serial", "parallel", "fused")
MODULE = "tools.pipeline_eval.qualification.combined_native_eval"


def freeze(work):
    library = build.lane.LIBRARY
    fused = work / "build/build.json"
    owned = {"serial": build.LANE, "parallel": build.LANE, "fused": fused.parent}
    receipts = {role: whole_iq.read(parent / "build.json") for role, parent in owned.items()}
    for role, parent in owned.items():
        for file, digest in receipts[role]["files"].items():
            whole_iq.checked(parent / file, digest)
    iq_stream.MAX_CHUNK_PREFIX = 56 * iq_stream.MIB
    old = (
        build.lane.REPORT / "source-lock.json",
        build.fractional.REPORT / "input-lock.json",
        build.lane.hotpath.REPORT / "source-lock.json",
    )
    seen = {ident: set() for ident in CASES}
    for path in old:
        receipt = whole_iq.read(path)
        for ident in CASES:
            seen[ident].update(
                (row["segment"], row["sequence"])
                for row in receipt.get("roster", receipt.get("cases"))[ident]
            )
    rows = {}
    for ident in CASES:
        case = _load_case(ident)
        rows[ident] = [
            row for segment in SEGMENTS for row in hot._freeze_block(work, case, ident, segment)
        ]
        if any((r["segment"], r["sequence"]) in seen[ident] for r in rows[ident]):
            raise ValueError("combined detector used a component timing window")
    for edge in ("lower", "upper"):
        controls = rows[edge] = []
        for kind in ("strong", "noise", "zero"):
            if kind == "zero":
                samples, target = np.zeros((200000, 2, 2), dtype="<i2"), {}
            else:
                samples, target = lane.synthetic(edge, kind)
            name = f"{edge}-{kind}"
            controls.append(
                dict(
                    name=name, edge=edge, kind=kind, target=target, **lane.shot(work, name, samples)
                )
            )
    source = build.REPORT / "native-source-lock.json"
    programs = (*old, Path(__file__), Path(build.__file__), build.REPORT / "PROTOCOL.md", fused)
    save_json(
        source,
        dict(
            roster=rows,
            cpus=PINS,
            memory_max=whole_iq.MEMORY,
            swap_max=0,
            sources={str(p): _sha(p) for p in programs},
            libraries={
                role: dict(path=str(root / library), files=receipts[role]["files"])
                for role, root in owned.items()
            },
        ),
    )


def resources():
    line = next(
        s for s in Path("/proc/self/cgroup").read_text().splitlines() if s.startswith("0::")
    )
    root = Path("/sys/fs/cgroup") / line[3:].lstrip("/")
    stat = {
        k: int(v) for k, v in (row.split() for row in (root / "cpu.stat").read_text().splitlines())
    }
    files = {
        key: (root / key).read_text().strip()
        for key in ("memory.peak", "memory.max", "memory.swap.max", "memory.events")
    }
    if (files["memory.max"], files["memory.swap.max"]) != (str(whole_iq.MEMORY), "0"):
        raise ValueError("short comparison did not enter the requested memory and swap cgroup")
    return dict(membership=line[3:], cpu_stat=stat, memory=files, peak_rss_kib=hot.memory())


def worker(work, role, edge):
    lock = whole_iq.read(build.REPORT / "native-source-lock.json")
    item = lock["libraries"][role]
    lib = Path(item["path"])
    for name, digest in item["files"].items():
        whole_iq.checked(lib.parent / name, digest)
    if os.sched_getaffinity(0) != {PINS[0]}:
        raise ValueError("caller did not bind its fixed CPU")
    with ExitStack() as stack:
        call = lane.runner(
            stack, lib, edge, "typed-serial" if role == "serial" else "split-parallel", PINS
        )
        maps = Path("/proc/self/maps").read_text()
        if str(lib.parent / build.lane.hotpath.DETECTOR) not in maps:
            raise ValueError("cgroup loaded an incorrect detector DSO")
        print(json.dumps(resources()), flush=True)
        last = None
        for line in sys.stdin:
            fixture, mode = json.loads(line)
            if mode == "resources":
                print(json.dumps(resources()), flush=True)
                continue
            if fixture != last:
                sample = lane.sample(work, fixture)
                last = fixture
            rows, hints, support, clocks = call(sample, mode)
            gates = lane.passing(rows)
            payload = dict(rows=rows, hints=hints, support=support, gates=gates)
            counts = [len(r["candidates"]) for r in rows]
            print(
                json.dumps(
                    dict(
                        sha256=fingerprint(payload),
                        rows_sha256=fingerprint(rows),
                        counts=counts,
                        gates=gates,
                        hints=hints,
                        clocks=clocks,
                    )
                ),
                flush=True,
            )


@contextmanager
def service(work, role, edge):
    unit = f"leo-combined-native-{role}-{uuid4().hex[:10]}"
    command = [
        "systemd-run",
        "--user",
        "--quiet",
        "--wait",
        "--pipe",
        "--unit=" + unit,
        "--property=MemoryMax=536870912",
        "--property=MemorySwapMax=0",
        "--property=Nice=10",
        "--property=RuntimeMaxSec=115s",
        "--property=KillMode=control-group",
        f"--working-directory={ROOT}",
        *(f"--setenv={k}={v}" for k, v in THREAD_ENV.items()),
        "taskset",
        "-c",
        str(PINS[0]),
        sys.executable,
        "-B",
        "-m",
        MODULE,
        "worker",
        str(work),
        role,
        edge,
    ]
    with subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1
    ) as handle:
        try:
            first = handle.stdout.readline()
            if not first:
                raise ValueError(f"failed to enter capped {role} service")
            yield handle, json.loads(first)
        finally:
            handle.stdin.close()
            try:
                status = handle.wait(timeout=5)
            except subprocess.TimeoutExpired:
                handle.kill()
                status = handle.wait()
            if status:
                raise ValueError(f"capped {role} service exited with {status}")


def same_roles(results):
    return len({r["sha256"] for r in results.values()}) == 1


def run(work, smoke=False):
    lock_path = build.REPORT / "native-source-lock.json"
    lock = whole_iq.read(lock_path)
    for path, digest in lock["sources"].items():
        whole_iq.checked(Path(path), digest)
    output = {}
    for ident in CASES:
        genuine = [f for f in lock["roster"][ident] if f["status"] == "valid"]
        edge = genuine[0]["edge"]
        if smoke:
            genuine = genuine[:2]
        with ExitStack() as stack:
            roles = {r: stack.enter_context(service(work, r, edge)) for r in ROLES}
            for runner, _ in roles.values():
                for mode in lane.MODES[:2]:
                    hot.call(runner, genuine[0], mode)
            measures = []
            for i, specimen in enumerate(genuine + lock["roster"][edge]):
                control = specimen["kind"] != "genuine"
                row = dict(fixture=specimen, modes={})
                for mode in lane.MODES if control else lane.MODES[:2]:
                    row["modes"][mode] = repeats = []
                    for rep in range(1 if smoke else 3):
                        start = (i + rep) % 3
                        result = {
                            r: hot.call(roles[r][0], specimen, mode)
                            for r in ROLES[start:] + ROLES[:start]
                        }
                        if not same_roles(result):
                            raise ValueError(
                                f"complete scientific parity failed: {specimen['name']} {mode}"
                            )
                        if control:
                            gates = result["fused"]["gates"]
                            if [bool(x) for x in gates] != [specimen["kind"] == "strong"] * 2:
                                raise ValueError("signed/noise/zero control changed the gate")
                        repeats.append(result)
                if (
                    control
                    and row["modes"]["absent"][0]["fused"]["rows_sha256"]
                    != row["modes"]["stock"][0]["fused"]["rows_sha256"]
                ):
                    raise ValueError("absent-hint rows differ")
                measures.append(row)
            output[ident] = dict(
                rows=measures,
                start={r: v for r, (_, v) in roles.items()},
                end={r: hot.call(port, None, "resources") for r, (port, _) in roles.items()},
            )
        print(ident, "held exact", len(genuine), flush=True)
    save_json(
        work / ("native-smoke.json" if smoke else "native-results.json"),
        dict(
            cases=output,
            source_lock_sha256=_sha(lock_path),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run", "smoke", "worker"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("role", nargs="?")
    parser.add_argument("edge", nargs="?")
    args = parser.parse_args()
    if args.action == "worker":
        worker(args.work, args.role, args.edge)
    elif args.action == "freeze":
        freeze(args.work)
    else:
        run(args.work, args.action == "smoke")
