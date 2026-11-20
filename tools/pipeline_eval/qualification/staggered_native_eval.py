"""Replay held chronological IQ through all-four, all-five and real mixed native lanes."""

import argparse
import os
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..variants import center_union, iq_stream
from ..variants.staggered_native import RfStagger, StaggeredLane
from . import combined_native_eval as combined
from . import staggered_native_build as build
from .arrival_queue import fingerprint
from .differential_pilot_eval import synthetic
from .full_v5_check import _from_native, _load_case, _sha
from .native_hotpath_eval import memory, trace_rows
from .pilot_kernel_eval import _windows
from .wide_regional_eval import templates

CASES = combined.CASES
PINS = combined.PINS
SEGMENTS = (5, 10)
ROLES = ("four", "five", "mixed")


def block(work, ident, case, segment, counter):
    schedule = list(range(24))
    exclusions = []
    while schedule:
        try:
            windows = _windows(case, segment, schedule)
            break
        except iq_stream.IQReadError as error:
            key = "missing IQ or invalid layout for sequence "
            if not str(error).startswith(key):
                raise
            sequence = int(str(error).removeprefix(key))
            schedule.remove(sequence)
            exclusions.append(
                dict(segment=segment, sequence=sequence, status="invalid", reason=str(error))
            )
    else:
        windows = ()
    selected = []
    for window in windows:
        center = window.target["rf_center_hz"]
        valid = window.sample_rate_hz == 10_000_000 and window.samples.shape == (200000, 2, 2)
        lane = counter.reserve(center, valid=valid)
        if lane is None:
            exclusions.append(
                dict(
                    segment=segment,
                    sequence=window.sequence,
                    status="invalid",
                    reason="invalid dual CI16 geometry",
                )
            )
            continue
        name = f"{ident}-{segment}-{window.sequence}"
        file = work / (name + ".ci16")
        write(file, window.samples.tobytes())
        whole_iq.checked(file, window.iq_sha256)
        selected.append(
            dict(
                name=name,
                edge=window.target["edge"],
                center_hz=center,
                fifth_lane=lane,
                segment=segment,
                sequence=window.sequence,
                status="valid",
                kind="genuine",
                visit=int(window.acquisition["global_visit"]),
                manifest=case["recording"]["segments"][segment],
                file=file.name,
                iq_sha256=_sha(file),
            )
        )
    return sorted([*selected, *exclusions], key=lambda row: row["sequence"])


def freeze(work):
    compiled = work / "build/build.json"
    receipt = whole_iq.read(compiled)
    for name, digest in receipt["files"].items():
        whole_iq.checked(compiled.parent / name, digest)
    iq_stream.MAX_CHUNK_PREFIX = 56 * iq_stream.MIB
    roster = {}
    prior = (
        (build.combined.REPORT / "native-source-lock.json", "roster"),
        (build.combined.fractional.REPORT / "input-lock.json", "roster"),
        (build.lane.REPORT / "source-lock.json", "cases"),
        (build.lane.hotpath.REPORT / "source-lock.json", "roster"),
    )
    for ident in CASES:
        case = _load_case(ident)
        previously_used = {
            (r["segment"], r["sequence"])
            for path, key in prior
            for r in whole_iq.read(path)[key][ident]
        }
        counter = RfStagger()
        roster[ident] = rows = [
            r for segment in SEGMENTS for r in block(work, ident, case, segment, counter)
        ]
        if any((r["segment"], r["sequence"]) in previously_used for r in rows):
            raise ValueError("held timing block appeared in a parent study")
    for edge in ("lower", "upper"):
        roster[edge] = rows = []
        for kind in ("strong", "noise", "zero"):
            iq, target = (
                (np.zeros((200000, 2, 2), dtype="<i2"), {})
                if kind == "zero"
                else synthetic(edge, kind)
            )
            name = f"{edge}-{kind}"
            file = work / (name + ".ci16")
            write(file, iq.tobytes())
            rows.append(
                dict(
                    name=name,
                    edge=edge,
                    kind=kind,
                    file=file.name,
                    iq_sha256=_sha(file),
                    target=target,
                )
            )
        exact, shifted = templates(10_000_000, edge)
        save_json(
            work / f"{edge}-templates.json",
            {
                k: fingerprint(v.tobytes().hex())
                for k, v in (("exact", exact), ("control", shifted))
            },
        )
    sources = (
        Path(__file__),
        Path(build.__file__),
        compiled,
        build.REPORT / "PROTOCOL.md",
        *[path for path, _ in prior],
        Path(build.lane.hotpath.VARIANTS / "staggered_native.py"),
    )
    lock = build.REPORT / "source-lock.json"
    save_json(
        lock,
        dict(
            recorded=roster,
            pins=PINS,
            repeats=3,
            mode=ROLES,
            files={str(p): _sha(p) for p in sources},
            release=receipt["files"],
            signals={
                edge: whole_iq.read(work / f"{edge}-templates.json") for edge in ("lower", "upper")
            },
        ),
    )


def measure(port, samples, mode, selected=None):
    if mode == "mixed":
        result, profile = port.mixed(samples, selected, trace=True)
    else:
        result, profile = port.analyze(
            samples, {"four": "stock", "five": "fifth", "absent": "absent"}[mode], trace=True
        )
    lanes = profile["lanes"]
    if [lane["cpu"] for lane in lanes] != list(PINS):
        raise ValueError("the native call used different physical core pins")
    region = center_union.Trace()
    for i in range(2):
        region.lanes[i] = port.trace.lanes[i].union
    guides = trace_rows(region)
    scientific = [
        dict(row=row, hint=lane["hint"], support=guide)
        for row, lane, guide in zip(result["rows"], lanes, guides, strict=True)
    ]
    return scientific, profile


def check_mixed(roles, selected):
    expected = [roles["five"][i] if i == selected else roles["four"][i] for i in range(2)]
    return roles["mixed"] == expected


def gates(lane):
    return [
        point
        for i, c in enumerate(lane["row"]["candidates"])
        if (point := _from_native(i, c)) and point["passed_fractional_margin_gate"]
    ]


def control(specimen, port, samples):
    four, _ = measure(port, samples, "four")
    five, _ = measure(port, samples, "five")
    absent, _ = measure(port, samples, "absent")
    if [x["row"] for x in absent] != [x["row"] for x in four]:
        raise ValueError("the old absent-hint behavior differs from stock")
    observed = []
    for chosen in (0, 1):
        mixed, _ = measure(port, samples, "mixed", chosen)
        if not check_mixed(dict(four=four, five=five, mixed=mixed), chosen):
            raise ValueError("a mixed signed or null lane did not match its own branch")
        lane_gates = [gates(lane) for lane in mixed]
        if specimen["kind"] == "strong":
            target = specimen["target"]
            if not all(
                any(
                    abs(c["fractional_tracking_cfo_hz"] - target["cfo_hz"]) < 800
                    and abs(c["integer_epoch_sample"] - target["epoch"]) <= 2
                    for c in lane
                )
                for lane in lane_gates
            ):
                raise ValueError("signed plant disappeared or moved its physical CFO/epoch")
        elif any(lane_gates):
            raise ValueError("null control crossed the fractional gate")
        observed.append(
            dict(
                fifth_lane=chosen,
                hints=[lane["hint"] for lane in mixed],
                gates=list(map(len, lane_gates)),
                sha256=[fingerprint(lane) for lane in mixed],
            )
        )
    return dict(fixture=specimen, variants=observed, absent_exact=True)


def run(work):
    lockfile = build.REPORT / "source-lock.json"
    lock = whole_iq.read(lockfile)
    for name, digest in lock["files"].items():
        whole_iq.checked(Path(name), digest)
    folder = work / "build"
    for name, digest in lock["release"].items():
        whole_iq.checked(folder / name, digest)
    if os.sched_getaffinity(0) != {PINS[0]}:
        raise ValueError("run the staggered detector on caller CPU20")
    result = {}
    for ident in CASES:
        held = [r for r in lock["recorded"][ident] if r["status"] == "valid"]
        edge = held[0]["edge"]
        if any(r["edge"] != edge for r in held):
            raise ValueError("recording changes its authenticated template edge")
        with ExitStack() as stack:
            lib = folder / build.LIBRARY
            port = stack.enter_context(StaggeredLane(lib, edge, helper_cpu=PINS[1]))
            from ..variants.dual_lane import DualLane

            parent = stack.enter_context(
                DualLane(build.PARENT / build.lane.LIBRARY, edge, helper_cpu=PINS[1])
            )
            if str(folder / build.DETECTOR) not in Path("/proc/self/maps").read_text():
                raise ValueError("staggered ABI loaded a different sibling detector")
            warm = np.fromfile(work / held[0]["file"], dtype="<i2").reshape(200000, 2, 2)
            for role in ROLES:
                measure(port, warm, role, held[0]["fifth_lane"])
            measures = []
            for index, specimen in enumerate(held):
                path = whole_iq.checked(work / specimen["file"], specimen["iq_sha256"])
                samples = np.fromfile(path, dtype="<i2").reshape(200000, 2, 2)
                choice = specimen["fifth_lane"]
                reference = None
                calls = []
                for rep in range(3):
                    turn = (index + rep) % len(ROLES)
                    order = ROLES[turn:] + ROLES[:turn]
                    evaluated = {role: measure(port, samples, role, choice) for role in order}
                    science = {role: x[0] for role, x in evaluated.items()}
                    if not check_mixed(science, choice):
                        raise ValueError(
                            f"mixed lanes differ from the fixed branches: {specimen['name']}"
                        )
                    keys = {
                        role: [fingerprint(lane) for lane in lanes]
                        for role, lanes in science.items()
                    }
                    if reference is not None and keys != reference:
                        raise ValueError("warm repetition changed scientific rows or support")
                    reference = keys
                    metrics = {role: x[1] for role, x in evaluated.items()}
                    calls.append(dict(order=order, metrics=metrics))
                if specimen["sequence"] < 2:
                    for role in ROLES[:2]:
                        observed, _ = measure(parent, samples, role)
                        if [fingerprint(lane) for lane in observed] != reference[role]:
                            raise ValueError(
                                "existing branch ABI changed versus the frozen combined receiver"
                            )
                measures.append(
                    dict(
                        fixture=specimen,
                        payload_sha256=reference,
                        counts={
                            k: [len(lane["row"]["candidates"]) for lane in parts]
                            for k, parts in science.items()
                        },
                        gated={
                            k: [len(gates(lane)) for lane in parts] for k, parts in science.items()
                        },
                        hints={k: [lane["hint"] for lane in parts] for k, parts in science.items()},
                        timing=calls,
                    )
                )
            controls = []
            for specimen in lock["recorded"][edge]:
                path = whole_iq.checked(work / specimen["file"], specimen["iq_sha256"])
                controls.append(
                    control(specimen, port, np.fromfile(path, dtype="<i2").reshape(200000, 2, 2))
                )
        result[ident] = dict(rows=measures, controls=controls, peak_rss_kib=memory())
        print(ident, "exact", len(measures), flush=True)
    save_json(work / "measurements.json", dict(cases=result, source_lock_sha256=_sha(lockfile)))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("freeze", "run"))
    p.add_argument("work", type=local_output)
    args = p.parse_args()
    {"freeze": freeze, "run": run}[args.action](args.work)
