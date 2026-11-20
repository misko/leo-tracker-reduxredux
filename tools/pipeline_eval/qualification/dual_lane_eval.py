"""Run byte-equality and matched CPU timing for real dual-CI16 chronological blocks."""

import argparse
import json
import os
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path
from resource import RUSAGE_SELF, getrusage

import numpy as np

from .. import whole_iq
from ..__main__ import THREAD_ENV, local_output, save_json, write
from ..variants import center_union, iq_stream
from ..variants.dual_lane import MODES, DualLane
from . import arrival_queue as pace
from . import dual_lane_build as build
from .differential_pilot_eval import synthetic
from .full_v5_check import _load_case, _sha
from .native_hotpath_eval import NativeCall, trace_rows
from .pilot_kernel_eval import _windows

CORES = {"DS26-0197": (18, 19), "DS29-0316": (19, 18)}
SEGMENTS = (7, 11)
CONTROLS = ("zero", "strong", "silent-rx0", "silent-rx1")
ROLES = ("typed-serial", "split-serial", "split-parallel")
WINDOWS = 32
REPS = 3
MODULE = "tools.pipeline_eval.qualification.dual_lane_eval"


def shot(work, name, samples):
    path = work / f"{name}.ci16"
    write(path, samples.tobytes())
    return dict(file=path.name, iq_sha256=_sha(path))


def block(work, ident, segment):
    case = _load_case(ident)
    scheduled = list(range(WINDOWS))
    excluded = []
    while scheduled:
        try:
            windows = _windows(case, segment, scheduled)
            break
        except iq_stream.IQReadError as exc:
            prefix = "missing IQ or invalid layout for sequence "
            if not str(exc).startswith(prefix):
                raise
            i = int(str(exc).removeprefix(prefix))
            scheduled.remove(i)
            excluded.append(dict(sequence=i, segment=segment, status="excluded", reason=str(exc)))
    else:
        windows = ()
    rows = []
    if [w.sequence for w in windows] != scheduled:
        raise ValueError("source returned different immutable sequence indices")
    for w in windows:
        if w.sample_rate_hz != 10_000_000 or w.samples.shape != (200000, 2, 2):
            raise ValueError("physical duel requires one full dual-RX CI16 window")
        bits = shot(work, f"{ident}-{segment}-{w.sequence}", w.samples)
        whole_iq.checked(work / bits["file"], w.iq_sha256)
        rows.append(
            dict(
                sequence=w.sequence,
                segment=segment,
                case=ident,
                edge=w.target["edge"],
                status="valid",
                visit=int(w.acquisition["global_visit"]),
                counter=w.acquisition["sample_start"],
                **bits,
            )
        )
    return sorted([*rows, *excluded], key=lambda r: r["sequence"])


def freeze(work, report):
    if (report / "source-lock.json").exists():
        raise FileExistsError("prospective native timing already locked")
    build_lock = work / "build/build.json"
    release = whole_iq.read(build_lock)
    for name, digest in release["files"].items():
        whole_iq.checked(build_lock.parent / name, digest)
    iq_stream.MAX_CHUNK_PREFIX = 56 * iq_stream.MIB
    rows = {
        ident: [row for segment in SEGMENTS for row in block(work, ident, segment)]
        for ident in CORES
    }
    controls = []
    for edge in ("upper", "lower"):
        pos, target = synthetic(edge, "strong")
        for kind in CONTROLS:
            iq = np.zeros_like(pos) if kind == "zero" else pos.copy()
            if kind.startswith("silent"):
                iq[:, int(kind[-1]), :] = 0
            pair = shot(work, f"{edge}-{kind}", iq)
            controls.append(dict(edge=edge, kind=kind, target=target, **pair))
    source = report / "source-lock.json"
    files = (
        Path(__file__),
        Path(build.__file__),
        Path(sys.modules[DualLane.__module__].__file__),
        build.LANE_C,
        report / "PROTOCOL.md",
    )
    save_json(
        source,
        dict(
            cases=rows,
            controls=controls,
            cpus=CORES,
            segments=SEGMENTS,
            windows_per_segment=WINDOWS,
            repeats=REPS,
            build_sha256=_sha(build_lock),
            libraries=release["files"],
            sources={str(f): _sha(f) for f in files},
            native_roles=ROLES,
        ),
    )
    write(report / "native-build.json", build_lock.read_bytes())


def verified(work, report):
    lock = whole_iq.read(report / "source-lock.json")
    for name, digest in lock["sources"].items():
        whole_iq.checked(Path(name), digest)
    whole_iq.checked(work / "build/build.json", lock["build_sha256"])
    for name, digest in lock["libraries"].items():
        whole_iq.checked(work / "build" / name, digest)
    return lock, work / "build" / build.LIBRARY


def sample(work, row):
    data = whole_iq.checked(work / row["file"], row["iq_sha256"])
    return np.fromfile(data, dtype="<i2").reshape(200000, 2, 2)


def runner(stack, library, edge, role, cores):
    if role == "typed-serial":
        port = NativeCall(stack, library, edge)

        def measure(raw, mode):
            rows, hints, region, metric = port.measure(raw, mode)
            clocks = dict(
                wall_ns=round(metric["decoded_wall_ms"] * 1e6),
                typed_ns=round(metric["typed_wall_ms"] * 1e6),
                cpu_ns=round(metric["decoded_cpu_ms"] * 1e6),
                lanes=None,
                glrt_lanes_cpu_ns=[round(r["timings_ms"]["total_cpu"] * 1e6) for r in rows],
            )
            clean = [{k: v for k, v in r.items() if k != "timings_ms"} for r in rows]
            return clean, hints, region, clocks

    else:
        port = stack.enter_context(
            DualLane(library, edge, helper_cpu=cores[1] if role == "split-parallel" else -1)
        )

        def measure(raw, mode):
            output, clocks = port.analyze(raw, mode, trace=True)
            hints = [r["hint"] for r in clocks["lanes"]]
            pins = [r["cpu"] for r in clocks["lanes"]]
            if pins != (list(cores) if role == "split-parallel" else [cores[0]] * 2):
                raise ValueError("native lane ran on a different CPU")
            if mode == "stock":
                return output["rows"], hints, None, clocks
            trace = center_union.Trace()
            for i in (0, 1):
                trace.lanes[i] = port.trace.lanes[i].union
            return output["rows"], hints, trace_rows(trace), clocks

    return measure


def passing(rows):
    return [
        sum(
            c["fractional_epoch"]["status"] == "complete"
            and c["fractional_epoch"]["margin"] >= 0.025
            for c in row["candidates"]
        )
        for row in rows
    ]


def audit_controls(work, lock, library):
    os.sched_setaffinity(0, {18})
    result = []
    for edge in ("upper", "lower"):
        with ExitStack() as stack:
            rolls = {role: runner(stack, library, edge, role, (18, 19)) for role in ROLES}
            for row in lock["controls"]:
                if row["edge"] != edge:
                    continue
                iq = sample(work, row)
                first = None
                for mode in MODES:
                    exact = rolls["typed-serial"](iq, mode)[:3]
                    for role in ROLES[1:]:
                        if rolls[role](iq, mode)[:3] != exact:
                            raise ValueError("zero/signed/single-silent control did not match")
                    if mode == "stock":
                        first = exact[0]
                    if mode == "absent" and exact[0] != first:
                        raise ValueError("both absent hints need the exact no-hint stock result")
                    gates = passing(exact[0])
                    expected = [True, True] if row["kind"] == "strong" else [False, False]
                    if row["kind"].startswith("silent"):
                        expected[1 - int(row["kind"][-1])] = True
                    if [bool(x) for x in gates] != expected:
                        raise ValueError("control improperly admits or discards a physical signal")
                    result.append(
                        dict(
                            edge=edge,
                            kind=row["kind"],
                            mode=mode,
                            gates=gates,
                            hints=exact[1],
                            exact_rows_and_regions=True,
                        )
                    )
    return result


def part(work, lock, library, ident):
    cores = CORES[ident]
    os.sched_setaffinity(0, {cores[0]})
    valid = [r for r in lock["cases"][ident] if r["status"] == "valid"]
    measures, matches = [], []
    if len({r["edge"] for r in valid}) != 1:
        raise ValueError("the fixed timing cohort requires one authenticated edge per recording")
    with ExitStack() as stack:
        calls = {role: runner(stack, library, valid[0]["edge"], role, cores) for role in ROLES}
        warm = sample(work, valid[0])
        for call in calls.values():
            for mode in MODES[:2]:
                call(warm, mode)
        for index, row in enumerate(valid):
            iq = sample(work, row)
            for mode in MODES[:2]:
                reference = None
                for rep in range(REPS):
                    turn = (index + rep) % len(ROLES)
                    for role in ROLES[turn:] + ROLES[:turn]:
                        decoded, hints, regions, clocks = calls[role](iq, mode)
                        key = pace.fingerprint([decoded, hints, regions])
                        if reference is None:
                            reference = key
                            matches.append(
                                dict(
                                    id=ident,
                                    mode=mode,
                                    visit=row["visit"],
                                    output_sha256=key,
                                    candidates=sum(len(r["candidates"]) for r in decoded),
                                    gated=sum(passing(decoded)),
                                    hints=hints,
                                )
                            )
                        if key != reference:
                            raise ValueError(
                                f"role {role} changed scientific bytes for {ident} "
                                f"visit {row['visit']}"
                            )
                        measures.append(
                            dict(
                                id=ident,
                                mode=mode,
                                role=role,
                                repeat=rep,
                                visit=row["visit"],
                                counter=row["counter"],
                                iq_sha256=row["iq_sha256"],
                                **clocks,
                            )
                        )
    return measures, matches


def memory(work, lock, library, ident, role):
    cores = CORES[ident]
    os.sched_setaffinity(0, {cores[0]})
    picked = [r for r in lock["cases"][ident] if r["status"] == "valid"][:8]
    with ExitStack() as stack:
        call = runner(stack, library, picked[0]["edge"], role, cores)
        for row in picked:
            window = sample(work, row)
            for mode in MODES[:2]:
                call(window, mode)
        return dict(
            id=ident,
            role=role,
            peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
            visits=len(picked),
            cpus=list(cores) if role == "split-parallel" else [cores[0]],
        )


def measure(work, report):
    lock, library = verified(work, report)
    controls = audit_controls(work, lock, library)
    results, quantified, usage = [], [], []
    for ident in CORES:
        metrics, matches = part(work, lock, library, ident)
        results.extend(metrics)
        quantified.extend(matches)
        for role in ROLES:
            command = [
                sys.executable,
                "-B",
                "-m",
                MODULE,
                "memory",
                str(work),
                "--out",
                str(report),
                "--case",
                ident,
                "--role",
                role,
            ]
            raw = subprocess.check_output(command, env=os.environ | THREAD_ENV, timeout=30)
            usage.append(json.loads(raw))
        print(ident, len(metrics), len(matches), flush=True)
    footprint = report / "native-measurements.json.gz"
    pace.writegz(footprint, dict(rows=results, parity=quantified, controls=controls, memory=usage))
    files = (
        footprint,
        report / "source-lock.json",
        report / "native-build.json",
        report / "PROTOCOL.md",
    )
    save_json(
        report / "native-lock.json", dict(cases=list(CORES), files={p.name: _sha(p) for p in files})
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "measure", "memory"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("--out", type=local_output, default=build.REPORT)
    parser.add_argument("--case", choices=CORES)
    parser.add_argument("--role", choices=ROLES)
    args = parser.parse_args()
    if args.action == "memory":
        source, lib = verified(args.work, args.out)
        print(json.dumps(memory(args.work, source, lib, args.case, args.role)))
    else:
        {"freeze": freeze, "measure": measure}[args.action](args.work, args.out)
