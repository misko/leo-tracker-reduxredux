"""Freeze and time the full prepared overlap-save bank across block lengths."""

import argparse
import gzip
import json
import os
from pathlib import Path
from statistics import geometric_mean, median
from time import perf_counter_ns, process_time_ns

import numpy as np

from ..__main__ import ROOT, THREAD_ENV, encoded, save_json, write
from ..variants import capture_batched_fft, capture_fft, fft_length, original_kernel
from ..variants.selective_capture import visit_pairs
from . import capture_detector_lineage as lineage
from .coarse_basis_audit import FALLBACK
from .coarse_basis_eval import captures, compare_map
from .full_v5_check import _load_case, _sha
from .original_kernel_trial import decode
from .pilot_kernel_eval import _digest
from .retry_reuse_eval import window_from_lock

REPORT = ROOT / "reports/2026_11_19_receiver_screening/coarse-and-navigation/fft-length"
DEV = {"DS29-0519": (20,), "DS29-0082": (20,)}
HELD = {
    "DS26-0237": (4, 64),
    "DS29-0082": (2, 80),
    "DS29-0519": (155, 270),
    "DS29-0174": (20, 28),
}
CPUS = {"DS26-0237": 0, "DS29-0082": 1, "DS29-0519": 0, "DS29-0174": 1}
REPEATS = 5
RELEASED_SHA = "26d1e10bb0cf0f15d58d922c46a2b50e38124d54a7efdccfcb8e2ba46783de02"


def case_roster(work, ident):
    case = _load_case(ident)
    path, expected = lineage.locked_native(case, "capture")
    data = path.read_bytes()
    if _digest(data) != "sha256:" + expected.removeprefix("sha256:"):
        raise ValueError("frozen capture authority differs")
    probes = dict(visit_pairs(json.loads(data)["source"]["probes"]))
    rows = []
    for split, numbers in (("development", DEV.get(ident, ())), ("held", HELD[ident])):
        for visit in numbers:
            segment, manifest, window = decode(case, visit)
            if any(
                p["valid_start_counter"] != window.acquisition["sample_start"]
                for p in probes[visit]
            ):
                raise ValueError("waveform and frozen probe clock do not match")
            payload = window.samples.tobytes()
            if _digest(payload) != window.iq_sha256:
                raise ValueError("IQ differs from its authenticated digest")
            write(work / f"{ident}-{visit}.ci16", payload)
            rows.append(
                dict(
                    split=split,
                    visit=visit,
                    segment=segment,
                    manifest_sha256=manifest,
                    sequence=window.sequence,
                    receivers=window.receiver_ids,
                    rate=window.sample_rate_hz,
                    target=window.target,
                    target_id=window.target_id,
                    acquisition=window.acquisition,
                    iq_sha256=window.iq_sha256,
                    probes_sha256=_digest(encoded(probes[visit])),
                )
            )
    return dict(cpu=CPUS[ident], rows=rows, archived_native_sha256=expected)


def freeze(work):
    work.mkdir()
    variants = {}
    for length in fft_length.LENGTHS:
        library, command = fft_length.build(work / f"length-{length}", length)
        variants[str(length)] = dict(
            path=str(library),
            sha256=_sha(library),
            command=command,
            generated={p.name: _sha(p) for p in sorted(library.parent.glob("*.c"))},
        )
    if variants[str(fft_length.RELEASED)]["sha256"] != RELEASED_SHA:
        raise ValueError("generated 512 bank differs from the released baseline")
    files = [
        Path(__file__),
        Path(fft_length.__file__),
        Path(original_kernel.__file__),
        original_kernel.HEADER,
        Path(capture_batched_fft.__file__),
        Path(capture_fft.__file__),
        capture_fft.SOURCE,
        capture_fft.SOURCE.with_name("folded_bank.c"),
        REPORT / "PROTOCOL.md",
        Path("/usr/lib/x86_64-linux-gnu/libfftw3f.so.3"),
    ]
    result = dict(
        cases={k: case_roster(work, k) for k in HELD},
        variants=variants,
        sources={str(p): _sha(p) for p in files},
    )
    save_json(work / "input-lock.json", result)


def checked(work, ident):
    lock = json.loads((work / "input-lock.json").read_bytes())
    case = lock["cases"][ident]
    if os.sched_getaffinity(0) != {case["cpu"]}:
        raise ValueError(f"pin capture worker to CPU {case['cpu']}")
    if any(os.environ.get(k) != "1" for k in THREAD_ENV):
        raise ValueError("every numerical runtime must use one thread")
    for p, sha in lock["sources"].items():
        if _sha(Path(p)) != sha:
            raise ValueError(f"qualification source changed: {p}")
    for info in lock["variants"].values():
        path = Path(info["path"])
        if _sha(path) != info["sha256"]:
            raise ValueError(f"compiled bank changed: {path}")
    _, policy, producer = lineage.source_lineage(_load_case(ident))
    return lock, case, policy, producer


def timed(grids, acquisition, original, args, layout):
    timings, maps = {}, {}
    for length in layout:
        grid = grids[length]
        begin, wall = process_time_ns(), perf_counter_ns()
        rows = grid.score_grid(acquisition, original, *args)
        elapsed, wall = process_time_ns() - begin, perf_counter_ns() - wall
        native = grid.calls[-1]
        if not native["applied"] or native["fft_length"] != int(length):
            raise ValueError("the full grid must run every measured length")
        timings[length] = dict(cpu_ns=elapsed, wall_ns=wall, **native)
        maps[length] = np.asarray(rows)
    return timings, maps


def sweep(work, ident):
    from leo.analysis.starlink import acquisition

    lock, case, policy, producer = checked(work, ident)
    grids = {k: original_kernel.PersistentGrid(v["path"]) for k, v in lock["variants"].items()}
    baseline = str(fft_length.RELEASED)
    rows = []
    try:
        for record in (r for r in case["rows"] if r["split"] == "development"):
            window = window_from_lock(work, ident, record)
            installed, rank, lanes = captures(window, policy)
            for receiver, (args, ranking) in enumerate(lanes):
                for anchors in (args[4], FALLBACK):
                    working = *args[:4], anchors, args[5]
                    layout = tuple(map(str, fft_length.LENGTHS))
                    cold, _ = timed(grids, acquisition, installed, working, layout)
                    cycles = []
                    for rep in range(REPEATS):
                        rotate = (rep + len(rows)) % len(layout)
                        order = layout[rotate:] + layout[:rotate]
                        sample, maps = timed(grids, acquisition, installed, working, order)
                        cycles.append(dict(order=order, timing=sample))
                    accuracy = {
                        length: compare_map(maps[baseline], grid, rank, ranking)
                        for length, grid in maps.items()
                        if length != baseline
                    }
                    rows.append(
                        dict(
                            visit=record["visit"],
                            receiver=receiver,
                            anchors=len(anchors),
                            timings=cycles,
                            first=cold,
                            vs_prepared=accuracy,
                        )
                    )
                    print(
                        ident,
                        receiver,
                        len(anchors),
                        {
                            k: round(
                                median(t["timing"][k]["native_cpu_ns"] for t in cycles) / 1e6, 2
                            )
                            for k in layout
                        },
                        flush=True,
                    )
    finally:
        for grid in grids.values():
            grid.clear_cache()
    write(
        work / f"{ident}-development.json.gz",
        gzip.compress(
            encoded(
                dict(
                    ident=ident,
                    cpu=case["cpu"],
                    producer=producer,
                    rows=rows,
                    lock_sha256=_sha(work / "input-lock.json"),
                )
            ),
            mtime=0,
        ),
    )


def select(work):
    baseline = str(fft_length.RELEASED)
    names = [f"{ident}-development.json.gz" for ident in DEV]
    summaries = [json.loads(gzip.decompress((work / n).read_bytes())) for n in names]
    input_sha = _sha(work / "input-lock.json")
    if any(s["lock_sha256"] != input_sha or len(s["rows"]) != 4 for s in summaries):
        raise ValueError("development sweep has incomplete physical coverage or bindings")
    rows = [r for case in summaries for r in case["rows"]]
    ranking = {}
    for size in map(str, fft_length.LENGTHS):
        ratios = [
            median(
                t["timing"][size]["native_cpu_ns"] / t["timing"][baseline]["native_cpu_ns"]
                for t in row["timings"]
            )
            for row in rows
        ]
        ranking[size] = geometric_mean(ratios)
    winner = min(ranking, key=lambda k: (ranking[k], int(k)))
    result = dict(
        selected=int(winner),
        paired_native_ratio=ranking,
        input_lock_sha256=input_sha,
        development={k: _sha(work / k) for k in names},
    )
    save_json(work / "selection-lock.json", result)
    print(result, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "sweep", "select"))
    parser.add_argument("work", type=Path)
    parser.add_argument("case", choices=tuple(DEV), nargs="?")
    args = parser.parse_args()
    if args.action == "sweep":
        sweep(args.work, args.case)
    else:
        {"freeze": freeze, "select": select}[args.action](args.work)
