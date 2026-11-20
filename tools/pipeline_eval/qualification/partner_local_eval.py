"""Qualify primary-timed local partner acquisition on sealed chronological CI16."""

import argparse
import gzip
import os
import resource
from contextlib import ExitStack
from itertools import permutations
from pathlib import Path
from time import perf_counter_ns, process_time_ns

import numpy as np

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import iq_stream, partner_local
from ..variants.staggered_native import StaggeredLane
from . import differential_pilot_eval, pilot_kernel_eval
from . import partner_local_build as build
from .arrival_queue import fingerprint
from .full_v5_check import ALIAS_HZ, _from_native, _load_case, _sha, compare_probes

SCHEDULE = {
    "DS26-0237": ("held", (2, 6, 10), 24),
    "DS29-0174": ("held", (2, 6, 10), 24),
    "DS26-0168": ("stress", (3, 7), 16),
    "DS29-0604": ("stress", (3, 7), 16),
}
DEVELOPMENT = ROOT / (
    "reports/2026_11_19_receiver_screening/support-preserving/whole-center-union/native/control"
)
MODES = ("full", "full-on-hit", "local", "parallel")
SYNTHETIC = ("zero", "noise", "strong", "delay1", "delay4", "primary-only", "partner-only")
MAIN, HELPER = 16, 17
REPEATS = 3


def wrap(delta, period):
    return (delta + period / 2) % period - period / 2


def coordinates(row):
    return (
        row["integer_epoch_sample"] + row["fractional_epoch_offset_samples"],
        row["fractional_tracking_cfo_hz"],
    )


def distinct(candidates):
    """Retain the strongest representative of each gated epoch and CFO family."""
    valid = [c for c in candidates if c["passed_fractional_margin_gate"]]
    accepted = []
    for row in sorted(valid, key=lambda r: (-r["fractional_margin"], r["candidate_rank"])):
        epoch, cfo = coordinates(row)
        if all(
            abs(wrap(epoch - pe, partner_local.FRAME)) > 2 or abs(wrap(cfo - pf, ALIAS_HZ)) > 1000
            for pe, pf in map(coordinates, accepted)
        ):
            accepted.append(row)
    return accepted


def gate(row):
    candidates = [_from_native(rank, c) for rank, c in enumerate(row["candidates"], 1)]
    return distinct([c for c in candidates if c is not None])


def pair(left, right):
    return compare_probes({"candidates": left}, {"candidates": right}, partner_local.RATE)


def synthetic(edge, kind):
    source = kind if kind in ("noise", "zero") else "strong"
    samples, truth = differential_pilot_eval.synthetic(edge, source)
    if kind.startswith("delay"):
        delay = int(kind[-1])
        samples[delay:, 1] = samples[:-delay, 1].copy()
        samples[:delay, 1] = 0
        truth["partner_delay"] = delay
    if kind == "primary-only":
        samples[:, 1] = 0
    elif kind == "partner-only":
        samples[:, 0] = 0
    return samples, truth


def source_paths():
    import leo.analysis.starlink.native_short_window as decoder
    import leo.analysis.starlink.templates as templates

    return (
        Path(__file__),
        Path(build.__file__),
        Path(partner_local.__file__),
        Path(partner_local.__file__).with_suffix(".h"),
        Path(pilot_kernel_eval.__file__),
        Path(differential_pilot_eval.__file__),
        Path(iq_stream.__file__),
        Path(decoder.__file__),
        Path(templates.__file__),
        build.REPORT / "PROTOCOL.md",
    )


def science_sources():
    return {str(path.relative_to(ROOT)): _sha(path) for path in source_paths()}


def block(work, ident, case, segment, count):
    sequences = list(range(count))
    prefix = "missing IQ or invalid layout for sequence "
    while sequences:
        try:
            windows = pilot_kernel_eval._windows(case, segment, sequences)
            break
        except iq_stream.IQReadError as exc:
            if not str(exc).startswith(prefix):
                raise
            sequence = int(str(exc).removeprefix(prefix))
            sequences.remove(sequence)
            yield dict(sequence=sequence, status="invalid", reason=str(exc))
    else:
        windows = ()
    for window in windows:
        if window.sample_rate_hz != partner_local.RATE or window.samples.shape != (200000, 2, 2):
            yield dict(
                sequence=window.sequence, status="invalid", reason="invalid dual CI16 geometry"
            )
            continue
        name = f"{ident}-{segment}-{window.sequence}"
        path = work / f"{name}.ci16"
        write(path, window.samples.tobytes())
        whole_iq.checked(path, window.iq_sha256)
        yield dict(
            name=name,
            edge=window.target["edge"],
            segment=segment,
            sequence=window.sequence,
            status="valid",
            kind="genuine",
            visit=int(window.acquisition["global_visit"]),
            manifest=case["recording"]["segments"][segment],
            file=path.name,
            iq_sha256=_sha(path),
            rf_center_hz=window.target["rf_center_hz"],
        )


def materialize(work):
    iq_stream.MAX_CHUNK_PREFIX = 56 * iq_stream.MIB
    planned = {
        case: dict(cohort=cohort, segments=segments, sequences=list(range(count)))
        for case, (cohort, segments, count) in SCHEDULE.items()
    }
    save_json(build.REPORT / "selection.json", dict(real=planned, controls=SYNTHETIC, rx0=True))
    work.mkdir(exist_ok=False)
    roster = []
    for ident, (cohort, segments, limit) in SCHEDULE.items():
        case = _load_case(ident)
        for segment in segments:
            try:
                scheduled = sorted(
                    block(work, ident, case, segment, limit), key=lambda row: row["sequence"]
                )
                roster.extend(
                    dict(row, recording=ident, cohort=cohort, segment=segment) for row in scheduled
                )
            except (OSError, iq_stream.IQReadError) as exc:
                roster.extend(
                    dict(
                        recording=ident,
                        cohort=cohort,
                        segment=segment,
                        sequence=seq,
                        status="unavailable",
                        reason=str(exc),
                    )
                    for seq in range(limit)
                )
            print(ident, segment, len(roster), flush=True)
    for edge in ("lower", "upper"):
        for kind in SYNTHETIC:
            samples, truth = synthetic(edge, kind)
            name = f"{edge}-{kind}"
            path = work / (name + ".ci16")
            write(path, samples.tobytes())
            roster.append(
                dict(
                    name=name,
                    edge=edge,
                    kind=kind,
                    truth=truth,
                    file=path.name,
                    cohort="control",
                    status="valid",
                    iq_sha256=_sha(path),
                )
            )
    save_json(work / "inputs.json", roster)


def freeze(work):
    samples = whole_iq.read(work / "input/inputs.json")
    paths = work / "build/build.json"
    binaries = whole_iq.read(paths)
    parallel = build.PARENT / "candidate/libleo-staggered-native.so"
    old_build = whole_iq.read(build.PARENT / "build.json")
    parallel_files = {
        parallel.parent / k: v for k, v in old_build["library_sha256"]["candidate"].items()
    }
    for path, digest in parallel_files.items():
        whole_iq.checked(path, digest)
    lock = dict(
        selection_sha256=_sha(build.REPORT / "selection.json"),
        sources=science_sources(),
        input_inventory={
            **whole_iq.read(ROOT / "tools/pipeline_eval/frozen/provenance.json")["files"]
        },
        build={"sha256": _sha(paths), "candidate": binaries["candidate"]},
        parallel={str(path): digest for path, digest in parallel_files.items()},
        roster=samples,
        cpu=[MAIN, HELPER],
        repeats=REPEATS,
    )
    save_json(build.REPORT / "source-lock.json", lock)


def cleaned(row):
    return {key: value for key, value in row.items() if key != "timings_ms"}


def run_one(port, parallel, iq, mode):
    wall, cpu = perf_counter_ns(), process_time_ns()
    if mode == "parallel":
        document, profile = parallel.analyze(iq, mode="absent", trace=True)
        if [row["cpu"] for row in profile["lanes"]] != [MAIN, HELPER]:
            raise RuntimeError("parallel modes left their reserved cores")
    else:
        document, profile = port.analyze(iq, mode=mode, trace=True)
    result = dict(wall_ns=perf_counter_ns() - wall, cpu_ns=process_time_ns() - cpu, profile=profile)
    rows = document["rows"]
    for lane, row in enumerate(rows):
        if "timings_ms" in row:
            result[f"rx{lane}_stage_ms"] = row["timings_ms"]
    return [cleaned(row) for row in rows], result


def compare(rows, seeds):
    primary, partner = (gate(row) for row in rows["parallel"])
    selected = gate(rows["local"][1])
    dispatch = bool(seeds)
    if rows["full"] != rows["parallel"]:
        raise ValueError("same-source sequential control disagreed with parallel full")
    if not rows["local"][0] == rows["full-on-hit"][0] == rows["parallel"][0]:
        raise ValueError("primary output changed")
    if dispatch != bool(primary) or (not dispatch and (selected or rows["local"][1]["candidates"])):
        raise ValueError("partner invocation violated the primary gate")
    if dispatch and rows["full-on-hit"][1] != rows["parallel"][1]:
        raise ValueError("full on-hit control changed partner peak rows")
    reachable = [
        c
        for c in partner
        if any(abs(wrap(coordinates(c)[0] - e, partner_local.FRAME)) <= 2 for e in seeds)
    ]
    return dict(
        dispatch=dispatch,
        seeds=seeds,
        primary=primary,
        stock_partner=partner,
        local_partner=selected,
        reachable=reachable,
        matches=pair(partner, selected),
        reachable_matches=pair(reachable, selected),
    )


def replay(work):
    if os.sched_getaffinity(0) != {MAIN}:
        raise ValueError("pin the benchmark caller to CPU16")
    plan = whole_iq.read(build.REPORT / "source-lock.json")
    if plan["sources"] != science_sources():
        raise ValueError("held scientific source changed after freeze")
    binary = plan["build"]["candidate"]
    candidate = whole_iq.checked(Path(binary["path"]), binary["sha256"])
    for path, digest in plan["parallel"].items():
        whole_iq.checked(Path(path), digest)
    wrapper = build.PARENT / "candidate/libleo-staggered-native.so"
    primary_reference = wrapper.parent / "libleo-adaptive-detector.so.1"
    result = []
    orders = tuple(permutations(MODES))
    for edge in ("lower", "upper"):
        with ExitStack() as stack:
            parallel = stack.enter_context(StaggeredLane(wrapper, edge, helper_cpu=HELPER))
            if str(primary_reference) not in Path("/proc/self/maps").read_text():
                raise ValueError("parallel run did not load the released active-grid library")
            port = stack.enter_context(partner_local.PartnerLocal(candidate, edge))
            warm = synthetic(edge, "strong")[0]
            for mode in MODES:
                run_one(port, parallel, warm, mode)
            for index, entry in enumerate(plan["roster"]):
                if entry.get("edge") != edge or entry["status"] != "valid":
                    continue
                path = whole_iq.checked(work / "input" / entry["file"], entry["iq_sha256"])
                iq = np.fromfile(path, dtype="<i2").reshape(200000, 2, 2)
                loads = dict(rows={}, samples={mode: [] for mode in MODES})
                for repeat in range(REPEATS):
                    for mode in orders[(index + 7 * repeat) % len(orders)]:
                        rows, clock = run_one(port, parallel, iq, mode)
                        if mode in loads["rows"] and rows != loads["rows"][mode]:
                            raise ValueError("identical input produced a different candidate")
                        loads["rows"][mode] = rows
                        loads["samples"][mode].append(clock)
                seeds = loads["samples"]["local"][0]["profile"]["seeds"]
                result.append(
                    dict(
                        entry=entry,
                        clocks=loads["samples"],
                        comparison=compare(loads["rows"], seeds),
                        rows_sha256={k: fingerprint(v) for k, v in loads["rows"].items()},
                        rows=loads["rows"],
                    )
                )
                if (len(result) % 24) == 0:
                    print("measured", len(result), flush=True)
    formatted = dict(
        source_lock_sha256=_sha(build.REPORT / "source-lock.json"),
        attempts=len(plan["roster"]),
        measurements=result,
        process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    )
    write(build.REPORT / "paired.json.gz", gzip.compress(encoded(formatted), mtime=0))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("materialize", "freeze", "replay"))
    p.add_argument("work", type=local_output)
    ns = p.parse_args()
    if ns.action == "materialize":
        materialize(ns.work / "input")
    elif ns.action == "freeze":
        freeze(ns.work)
    else:
        replay(ns.work)
