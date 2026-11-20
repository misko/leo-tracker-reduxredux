"""Measure complete projected, repaired and original coarse CFO banks."""

import argparse
import gzip
import json
import os
from pathlib import Path
from statistics import median
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np

from ..__main__ import ROOT, THREAD_ENV, encoded, save_json, write
from ..variants import coarse_cfo, fine_batch, original_kernel, prepared_hotpath_peaks
from . import capture_detector_lineage as lineage
from . import capture_exact_trial as exact
from . import fft_length_eval
from .coarse_basis_audit import FALLBACK
from .coarse_basis_eval import captures
from .full_v5_check import _load_case, _sha, compare_probes
from .pilot_kernel_eval import _digest
from .retry_reuse_eval import window_from_lock

INPUTS = Path("/srv/bulk/leo-dev/fft-length-20261120-v1")
REPORT = ROOT / "reports/2026_11_19_receiver_screening/original-schedule/coarse-cfo"
CASES = {"DS26-0237": 2, "DS29-0082": 3, "DS29-0519": 2}
DEV = ("DS29-0519", "DS29-0082")
REPEATS = 5
MODES = ("full256", "full512", "shortlist", "bounded")
RETAIN = prepared_hotpath_peaks.retained_peaks


def read(path):
    return json.loads(path.read_bytes())


def bind(load):
    obj = dict(path=str(load), sha256=_sha(load))
    return obj


def freeze(work):
    prior, held = (INPUTS / p for p in ("input-lock.json", "held-lock.json"))
    linked = read(held)
    if linked["length"] != 256 or linked["roster_sha256"] != _sha(prior):
        raise ValueError("the original prepared comparators lack their qualification")
    ls = Path(read(prior)["variants"]["512"]["path"])
    libs = {"full256": linked["candidate"], "full512": bind(ls)}
    for terms in coarse_cfo.ORDERS:
        lib, command = coarse_cfo.build(work / f"frozen-{terms}", terms)
        libs[str(terms)] = dict(bind(lib), build=command)
    paths = (
        Path(__file__),
        Path(coarse_cfo.__file__),
        coarse_cfo.HEADER,
        coarse_cfo.DIRECT,
        REPORT / "PROTOCOL.md",
        prior,
        held,
    )
    lock = dict(sources={str(p): _sha(p) for p in paths}, libraries=libs, cases=CASES)
    save_json(work / "input-lock.json", lock)


def inputs(work, ident, split):
    lock = read(work / "input-lock.json")
    if os.sched_getaffinity(0) != {lock["cases"][ident]}:
        raise ValueError("run on the assigned single physical core")
    if any(os.environ.get(k) != "1" for k in THREAD_ENV):
        raise ValueError("use one numerical thread")
    for path, sha in lock["sources"].items():
        if _sha(Path(path)) != sha:
            raise ValueError("instrumentation differs from the sealed trial")
    for item in lock["libraries"].values():
        if _sha(Path(item["path"])) != item["sha256"]:
            raise ValueError("coarse library differs from the sealed trial")
    _, policy, producer = lineage.source_lineage(_load_case(ident))
    bound = read(INPUTS / "input-lock.json")["cases"][ident]["rows"]
    windows = [(r, window_from_lock(INPUTS, ident, r)) for r in bound if r["split"] == split]
    return lock, policy, producer, windows


def comparison(lock):
    return {
        mode: original_kernel.PersistentGrid(lock["libraries"][mode]["path"]) for mode in MODES[:2]
    }


def score(grids, acquisition, original, working, ranking):
    outcome = {}
    for mode, grid in grids.items():
        cpu, wall = process_time_ns(), perf_counter_ns()
        rows = grid.score_grid(acquisition, original, *working)
        selected = RETAIN(ranking[0], rows, *ranking[1:])
        dense = np.asarray(rows)
        if mode in map(str, coarse_cfo.ORDERS):
            exact_peaks = grid.restore((ranking[0], rows, *ranking[1:]), dense, RETAIN)
            ideal_bound = grid._inputs()[-1]
        else:
            exact_peaks, ideal_bound = selected, None
        step = dict(
            grid.calls[-1], cpu_ns=process_time_ns() - cpu, wall_ns=perf_counter_ns() - wall
        )
        outcome[mode] = dense, selected, exact_peaks, ideal_bound, step
    return outcome


def development(work, ident):
    from leo.analysis.starlink import acquisition

    lock, policy, producer, windows = inputs(work, ident, "development")
    grids = comparison(lock)
    for terms in coarse_cfo.ORDERS:
        key = str(terms)
        grids[key] = coarse_cfo.Interpolated(
            lock["libraries"][key]["path"], terms, grids["full256"], repair="shortlist"
        )
    traces = []
    try:
        for record, window in windows:
            original, _, batches = captures(window, policy)
            for receiver, (args, ranking) in enumerate(batches):
                for symbols in (args[4], FALLBACK):
                    working = *args[:4], symbols, args[-1]
                    score(grids, acquisition, original, working, ranking)
                    paired = []
                    order = tuple(grids)
                    for repeat in range(REPEATS):
                        shift = (repeat + len(traces)) % len(order)
                        rotated = order[shift:] + order[:shift]
                        results = score(
                            {k: grids[k] for k in rotated}, acquisition, original, working, ranking
                        )
                        paired.append(
                            dict(order=rotated, observations={k: v[-1] for k, v in results.items()})
                        )
                    known, exact, *_ = results["full256"]
                    keys = {(e, f) for _, e, f in exact}
                    comparisons = {}
                    for terms in map(str, coarse_cfo.ORDERS):
                        approximate, proposed, repaired, bounds, _ = results[terms]
                        initial = {(e, f) for _, e, f in proposed}
                        final = {(e, f) for _, e, f in repaired}
                        gap = abs(approximate - known)
                        needed = approximate + bounds >= exact[-1][0]
                        comparisons[terms] = dict(
                            cells=gap.size,
                            max_delta=float(gap.max()),
                            original_peaks=len(keys),
                            provisional_matches=len(initial & keys),
                            repaired_matches=len(final & keys),
                            largest_support_mean_ideal_error=float(bounds.max()),
                            ideal_exceeds_envelope=int(
                                np.count_nonzero(gap > bounds + coarse_cfo.NUMERICAL_SLACK)
                            ),
                            optimistic_required_cells=int(
                                coarse_cfo.interval_neighbors(needed).sum()
                            ),
                        )
                    traces.append(
                        dict(
                            visit=record["visit"],
                            receiver=receiver,
                            anchors=len(symbols),
                            paired=paired,
                            comparisons=comparisons,
                        )
                    )
                    print(ident, receiver, len(symbols), comparisons, flush=True)
    finally:
        for grid in grids.values():
            grid.clear_cache()
    write(
        work / f"{ident}-development.json.gz",
        gzip.compress(
            encoded(
                dict(
                    ident=ident,
                    producer=producer,
                    traces=traces,
                    lock_sha256=_sha(work / "input-lock.json"),
                )
            ),
            mtime=0,
        ),
    )


def select(work):
    names = [f"{case}-development.json.gz" for case in DEV]
    data = [json.loads(gzip.decompress((work / name).read_bytes())) for name in names]
    binding = _sha(work / "input-lock.json")
    if any(r["lock_sha256"] != binding or len(r["traces"]) != 4 for r in data):
        raise ValueError("development coverage differs from the frozen plan")
    traces = [r for doc in data for r in doc["traces"]]
    ranks = {
        str(k): dict(
            missed=sum(
                r["comparisons"][str(k)]["original_peaks"]
                - r["comparisons"][str(k)]["repaired_matches"]
                for r in traces
            ),
            median_cpu_ns=median(
                v["observations"][str(k)]["cpu_ns"] for r in traces for v in r["paired"]
            ),
        )
        for k in coarse_cfo.ORDERS
    }
    selected = min(ranks, key=lambda k: (ranks[k]["missed"], ranks[k]["median_cpu_ns"], int(k)))
    save_json(
        work / "selection-lock.json",
        dict(
            selected=int(selected),
            ranks=ranks,
            lock_sha256=binding,
            development={name: _sha(work / name) for name in names},
        ),
    )
    print(selected, ranks, flush=True)


def one(window, policy, grids, labs, index, expected=None):
    from leo.analysis.starlink import acquisition

    installed = exact.stages.detector(window, policy, None)
    if expected and _digest(encoded(installed["probes"])) != expected:
        raise ValueError("installed archive failed its exact detector match")
    fine = fine_batch.FineBatch(labs["fine"], acquisition)
    if not fine.compatible:
        raise ValueError("batched fine arithmetic does not match the qualified capture release")
    timing, payload = [], {}

    def run(mode):
        grid = grids[mode]
        grid.calls.clear()
        observed = exact.stages.detector(window, policy, grid)
        public = {p: observed.pop(p) for p in ("public", "attempts", "probes")}
        if mode in payload and payload[mode] != public:
            raise ValueError("detector payload changed across identical repeats")
        payload[mode] = public
        return observed

    with (
        exact.refiners(labs),
        fine.route(),
        patch.object(acquisition, "_retain_score_map_peaks", RETAIN),
    ):
        for mode in MODES:
            run(mode)
        for repeat in range(REPEATS if expected else 2):
            rotation = (repeat + index) % len(MODES)
            order = MODES[rotation:] + MODES[:rotation]
            timing.append(dict(order=order, observations={m: run(m) for m in order}))
    comparisons = {}
    for mode in MODES:
        result = payload[mode]
        comparisons[mode] = dict(
            complete_equal=result["public"] == installed["public"],
            matches_prepared=result == payload["full256"],
            same_ranked_attempts=result["attempts"] == payload["full256"]["attempts"],
            accepted=[
                compare_probes(a, b, window.sample_rate_hz)
                for a, b in zip(
                    installed["probes"],
                    result["probes"],
                    strict=True,
                )
            ],
        )
    return dict(
        iq_sha256=window.iq_sha256,
        archived_sha256=expected,
        timing=timing,
        comparisons=comparisons,
        payload=payload,
        installed=installed,
    )


def held(work, ident):
    lock, policy, producer, windows = inputs(work, ident, "held")
    selected = read(work / "selection-lock.json")
    if selected["lock_sha256"] != _sha(work / "input-lock.json") or any(
        _sha(work / k) != h for k, h in selected["development"].items()
    ):
        raise ValueError("the development seal changed")
    terms = selected["selected"]
    grids = comparison(lock)
    for mode in MODES[2:]:
        grids[mode] = coarse_cfo.Interpolated(
            lock["libraries"][str(terms)]["path"], terms, grids["full256"], repair=mode
        )
    labs = fft_length_eval.base_libraries()
    rows = []
    try:
        for i, (record, window) in enumerate(windows):
            tested = one(window, policy, grids, labs, i, record["probes_sha256"])
            rows.append(dict(visit=record["visit"], **tested))
            print(
                ident,
                record["visit"],
                {k: v["matches_prepared"] for k, v in tested["comparisons"].items()},
                flush=True,
            )
        if ident in ("DS26-0237", "DS29-0082"):
            for i, (name, window) in enumerate(fft_length_eval.controls(windows[0][1]).items()):
                rows.append(dict(control=name, **one(window, policy, grids, labs, i)))
    finally:
        for grid in grids.values():
            grid.clear_cache()
    write(
        work / f"{ident}-held.json.gz",
        gzip.compress(
            encoded(
                dict(
                    ident=ident,
                    producer=producer,
                    rows=rows,
                    selection_sha256=_sha(work / "selection-lock.json"),
                )
            ),
            mtime=0,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "development", "select", "held"))
    parser.add_argument("work", type=Path)
    parser.add_argument("case", choices=tuple(CASES), nargs="?")
    args = parser.parse_args()
    fn = {"freeze": freeze, "development": development, "select": select, "held": held}[args.action]
    fn(args.work, args.case) if args.case else fn(args.work)
