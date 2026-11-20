"""Check exact active-grid publication on saved dual-RX CI16."""

import argparse
import json
import os
import subprocess
import sys
from contextlib import ExitStack, contextmanager
from pathlib import Path

import numpy as np

from .. import whole_iq
from ..__main__ import THREAD_ENV, local_output, save_json, write
from ..variants import center_union, iq_stream
from ..variants.staggered_native import RfStagger, StaggeredLane
from . import fifth_arm
from . import native_pruning_build as build
from . import staggered_native_eval as source
from .arrival_queue import fingerprint
from .fifth_arm_results import endpoint
from .full_v5_check import _load_case, _sha
from .native_hotpath_eval import call, trace_rows

PINS = (0, 1)
SEGMENTS = (6, 9)
ROLES = ("control", "candidate")
MODES = ("four", "five", "mixed")
MODULE = "tools.pipeline_eval.qualification.native_pruning_eval"
HARD = Path.home() / ".cache/leo-fifth-arm-20261119"


def freeze(work):
    compiled = work / "build/build.json"
    binary = whole_iq.read(compiled)
    for role, files in binary["library_sha256"].items():
        for name, digest in files.items():
            whole_iq.checked(compiled.parent / role / name, digest)
    iq_stream.MAX_CHUNK_PREFIX = 56 * iq_stream.MIB
    prior = build.staggered.REPORT / "source-lock.json"
    used = whole_iq.read(prior)["recorded"]
    roster = {}
    for ident in source.CASES:
        case = _load_case(ident)
        next_lane = RfStagger()
        roster[ident] = [
            row for s in SEGMENTS for row in source.block(work, ident, case, s, next_lane)
        ]
        prior_ids = {(r["segment"], r["sequence"]) for r in used[ident]}
        if any((r["segment"], r["sequence"]) in prior_ids for r in roster[ident]):
            raise ValueError("a prior timing window entered this held roster")
    prior_dir = fifth_arm.REPORT
    prior_seal = whole_iq.read(prior_dir / "result-lock.json")["files"]
    old_path = whole_iq.checked(prior_dir / "source-lock.json", prior_seal["source-lock.json"])
    original = whole_iq.read(old_path)["input"]
    for key, row in original.items():
        if key.startswith("DS"):
            raw = whole_iq.checked(HARD / row["file"], row["sha256"])
            write(work / row["file"], raw.read_bytes())
            roster.setdefault(row["edge"], []).append(
                dict(
                    name=key,
                    edge=row["edge"],
                    kind=row["kind"],
                    target=row["target"],
                    receiver=row["receiver"],
                    file=row["file"],
                    iq_sha256=row["sha256"],
                )
            )
    for edge in ("lower", "upper"):
        for kind in ("strong", "noise", "zero"):
            iq, target = (
                (np.zeros((200000, 2, 2), dtype="<i2"), {})
                if kind == "zero"
                else source.synthetic(edge, kind)
            )
            name = f"{edge}-{kind}"
            path = work / (name + ".ci16")
            write(path, iq.tobytes())
            if name in original:
                whole_iq.checked(path, original[name]["sha256"])
            roster[edge].append(
                dict(
                    name=name,
                    edge=edge,
                    kind=kind,
                    target=target,
                    file=path.name,
                    iq_sha256=_sha(path),
                )
            )
    files = (
        Path(__file__),
        Path(build.__file__),
        build.HEADER,
        build.REPORT / "PROTOCOL.md",
        prior,
        old_path,
        compiled,
        Path(source.__file__),
    )
    save_json(
        build.REPORT / "source-lock.json",
        dict(
            roster=roster,
            pins=PINS,
            roles=ROLES,
            replay_modes=MODES,
            source={str(p): _sha(p) for p in files},
            library_sha256=binary["library_sha256"],
        ),
    )


def decoded(port, sample, action, selected):
    if action == "mixed":
        result, clocks = port.mixed(sample, selected, trace=True)
    else:
        result, clocks = port.analyze(
            sample, {"four": "stock", "five": "fifth", "absent": "absent"}[action], trace=True
        )
    if [r["cpu"] for r in clocks["lanes"]] != list(PINS):
        raise ValueError("saved-IQ detector moved off the matched cores")
    stage = {
        key: sum(getattr(out, attribute) for out in port.out.rows[:2])
        for key, attribute in (
            ("coarse_cpu_ms", "coarse_ms"),
            ("proposals_cpu_ms", "proposal_ms"),
            ("fractional_cpu_ms", "fractional_epoch_ms"),
            ("fine_cpu_ms", "fine_fft_ms"),
            ("glrt_cpu_ms", "glrt_ms"),
            ("conditioned_cpu_ms", "conditioned_ms"),
        )
    }
    trace = center_union.Trace()
    active = []
    for i in range(2):
        trace.lanes[i] = port.trace.lanes[i].union
        lane = trace.lanes[i]
        epochs = set(lane.stock_epochs[: lane.stock_epoch_count])
        if lane.added_epochs:
            epochs.update(range(max(lane.hint - 1, 0), min(lane.hint + 2, 13333)))
        if len(epochs) != lane.active_epochs:
            raise ValueError("active epoch read-set does not match the exact union trace")
        active.append(sorted(epochs))
    hints = [r["hint"] for r in clocks["lanes"]]
    rows, support = result["rows"], trace_rows(trace)
    return rows, hints, support, active, clocks, stage


def worker(work, role, edge):
    config = whole_iq.read(build.REPORT / "source-lock.json")
    root = work / "build" / role
    for name, digest in config["library_sha256"][role].items():
        whole_iq.checked(root / name, digest)
    if os.sched_getaffinity(0) != {PINS[0]}:
        raise ValueError("benchmark caller must use only CPU0")
    lib = root / build.staggered.LIBRARY
    with StaggeredLane(lib, edge, helper_cpu=PINS[1]) as port:
        binding = root / build.staggered.DETECTOR
        if str(binding) not in Path("/proc/self/maps").read_text():
            raise ValueError("dynamic loader picked the wrong scientific detector")
        print(json.dumps(dict(loaded=str(binding), sha256=_sha(binding))), flush=True)
        prior = None
        active_four = None
        for line in sys.stdin:
            row, mode = json.loads(line)
            if row != prior:
                path = whole_iq.checked(work / row["file"], row["iq_sha256"])
                sample = np.fromfile(path, dtype="<i2").reshape(200000, 2, 2)
                _, _, _, active_four, _, _ = decoded(port, sample, "absent", None)
                prior = row
            action, selected = mode if isinstance(mode, list) else (mode, row.get("fifth_lane"))
            rows, hints, support, active, clocks, stages = decoded(port, sample, action, selected)
            chosen = [
                active[i]
                if (action == "five" or action == "absent" or (action == "mixed" and selected == i))
                else active_four[i]
                for i in range(2)
            ]
            testimony = dict(
                sha256=fingerprint([rows, hints, support]),
                rows_sha256=fingerprint(rows),
                lanes=[fingerprint([rows[i], hints[i], support[i]]) for i in range(2)],
                target=endpoint(rows[row["receiver"]], row["target"])
                if "receiver" in row
                else None,
                gains=[len(source.gates(dict(row=rr))) for rr in rows],
                candidates=sum(len(rr["candidates"]) for rr in rows),
                active=chosen,
            )
            if row["kind"] == "strong":
                test = dict(
                    integer_epoch_sample=row["target"]["epoch"],
                    fractional_epoch_offset_samples=0,
                    fractional_tracking_cfo_hz=row["target"]["cfo_hz"],
                    fractional_margin=0,
                )
                testimony["control_physical_pass"] = [
                    endpoint(r, test)["physical_passes"] for r in rows
                ]
            print(json.dumps(dict(science=testimony, clocks=clocks, stages=stages)), flush=True)


@contextmanager
def participant(work, role, edge):
    command = [sys.executable, "-m", MODULE, "worker", str(work), role, edge]
    with subprocess.Popen(
        command,
        text=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        env=os.environ | THREAD_ENV,
        bufsize=1,
    ) as proc:
        try:
            first = proc.stdout.readline()
            if not first:
                raise ValueError("native worker did not construct its detector")
            yield proc, json.loads(first)
        finally:
            proc.stdin.close()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


def exact(calls):
    reference, optimized = (calls[role]["science"] for role in ROLES)
    return reference == optimized


def run(work, smoke=False):
    path = build.REPORT / "source-lock.json"
    lock = whole_iq.read(path)
    for item, digest in lock["source"].items():
        whole_iq.checked(Path(item), digest)
    captures = {}
    for case in source.CASES:
        held = [r for r in lock["roster"][case] if r["status"] == "valid"]
        edge = held[0]["edge"]
        if smoke:
            held = held[:2]
        with ExitStack() as stack:
            roles = {role: stack.enter_context(participant(work, role, edge)) for role in ROLES}
            for proc, _ in roles.values():
                for mode in MODES:
                    call(proc, held[0], mode)
            measurements = []
            for i, row in enumerate(held + lock["roster"][edge]):
                modes = {}
                control = row["kind"] != "genuine"
                plan = (
                    (
                        ("four", "four"),
                        ("five", "five"),
                        ("mixed_0", ["mixed", 0]),
                        ("mixed_1", ["mixed", 1]),
                        ("absent", "absent"),
                    )
                    if control
                    else tuple((m, m) for m in MODES)
                )
                for mode, args in plan:
                    modes[mode] = repeats = []
                    for rep in range(1 if control or smoke else 3):
                        order = ROLES if (i + rep) % 2 == 0 else ROLES[::-1]
                        pair = {r: call(roles[r][0], row, args) for r in order}
                        if not exact(pair):
                            save_json(
                                work / "failure.json",
                                dict(case=case, fixture=row, mode=mode, pair=pair),
                            )
                            raise ValueError(
                                f"coarse read-set changes a detector field on {row['name']}/{mode}"
                            )
                        repeats.append(pair)
                if control:
                    receipts = {m: pairs[0]["candidate"]["science"] for m, pairs in modes.items()}
                    if receipts["four"]["rows_sha256"] != receipts["absent"]["rows_sha256"]:
                        raise ValueError("absent-hint public result differs from stock")
                    if row["kind"] == "strong" and not all(
                        all(v["control_physical_pass"]) for v in receipts.values()
                    ):
                        raise ValueError("signed plant was not physically recovered")
                    if row["kind"] in ("zero", "noise") and any(
                        any(v["gains"]) for v in receipts.values()
                    ):
                        raise ValueError("null control produced a gated RF result")
                measurements.append(dict(fixture=row, modes=modes))
            captures[case] = dict(rows=measurements, workers={r: p[1] for r, p in roles.items()})
        print(case, len(held), "exact", flush=True)
    save_json(
        work / ("smoke.json" if smoke else "measurements.json"),
        dict(
            cases=captures,
            source_lock_sha256=_sha(path),
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("freeze", "smoke", "run", "worker"))
    p.add_argument("work", type=local_output)
    p.add_argument("role", nargs="?")
    p.add_argument("edge", nargs="?")
    args = p.parse_args()
    if args.action == "worker":
        worker(args.work, args.role, args.edge)
    elif args.action == "freeze":
        freeze(args.work)
    else:
        run(args.work, args.action == "smoke")
