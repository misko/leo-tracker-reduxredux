"""Qualify a tap-sharing VNNI screen without changing installed verification."""

import argparse
import gzip
import json
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np

from ..__main__ import encoded, local_output, save_json, write
from ..variants import screened_detector_grid as variant
from . import screened_detector_trial as trial

IDENT = "DS29-0174"
ROSTER = {IDENT: {5: (4,), 11: (2, 5), 12: (3,)}}
LABELS = ("installed", "vnni_pair")
NUM_PAIRS = 3


def freeze(work):
    library = variant.build(work / "screened_detector_grid.so")
    with patch.object(trial, "ROSTER", ROSTER):
        lock = trial.freeze()
    lock["repetitions"] = NUM_PAIRS
    lock["library"] = str(library)
    lock["source_files"].update(
        {
            str(path): trial._sha(path)
            for path in (Path(__file__), Path(variant.__file__), variant.SOURCE, library)
        }
    )
    return lock


def paired(window, policy, candidate, repetitions, index):
    rows = []
    for turn in range(repetitions):
        order = LABELS if (turn + index) % 2 == 0 else LABELS[::-1]
        rows.append({label: detector(window, policy, candidate, label) for label in order})
    return rows


def detector(window, policy, grid, label):
    if label == "installed":
        return trial.detector(window, policy, "installed")
    before = (grid.calls, grid.cells, grid.fallbacks)
    with grid.route():
        row = trial.detector(window, policy, "installed")
    row["grid_work"] = dict(
        calls=grid.calls - before[0],
        cells=grid.cells - before[1],
        fallbacks=grid.fallbacks - before[2],
    )
    return row


def audit(window, policy, grid):
    from leo.analysis.starlink import coarse_screen

    original = coarse_screen.screen_grid
    rows = []
    with grid.route(coarse_screen):
        replacement = coarse_screen.screen_grid

        def both(*args):
            before = grid.fallbacks
            observed = replacement(*args)
            control = original(*args)
            a, b = np.asarray(control), np.asarray(observed)
            rows.append(
                dict(
                    shape=a.shape,
                    cells=a.size,
                    different_cells=int(np.count_nonzero(a != b)),
                    max_abs=float(np.max(np.abs(a - b))),
                    fallback=grid.fallbacks != before,
                )
            )
            return observed

        with patch.object(coarse_screen, "screen_grid", both):
            trial.detector(window, policy, "installed")
    return rows


def run(lock, cold=None):
    trial.capture_fft_trial.sealed(lock)
    verified = lock["cases"][IDENT]
    for filename, digest in verified["source_sha256"].items():
        if trial._sha(Path(filename)) != digest:
            raise ValueError(f"capture runtime changed: {filename}")
    _, policy, producer = trial.lineage.source_lineage(trial._load_case(IDENT))
    authority = producer["capture"]
    if (
        authority["root"] != verified["root"]
        or authority["input_manifest_sha256"] != verified["manifest_sha256"]
    ):
        raise ValueError("install is not the sealed capture-era producer")
    with patch.object(trial, "ROSTER", ROSTER):
        inputs = list(trial.windows(IDENT))
    if [receipt for _, receipt in inputs] != verified["roster"]:
        raise ValueError("sealed IQ changed")
    setup_wall, setup_cpu = perf_counter_ns(), process_time_ns()
    grid = variant.Grid(Path(lock["library"])) if cold != "installed" else None
    setup = dict(cpu_ns=process_time_ns() - setup_cpu, wall_ns=perf_counter_ns() - setup_wall)
    first = inputs[0][0]
    if cold is not None:
        return dict(
            setup=setup,
            capture=inputs[0][1],
            row=detector(first, policy, grid, cold),
            producer=producer,
        )
    # Equal initial setup of common installed template and FFT caches.
    detector(first, policy, grid, "installed")
    captures = []
    for index, (window, receipt) in enumerate(inputs):
        pairs = paired(window, policy, grid, lock["repetitions"], index)
        capture = dict(receipt, pairs=pairs, cells=audit(window, policy, grid))
        print(IDENT, receipt["visit"], capture["cells"], flush=True)
        captures.append(capture)
    controls = {}
    for index, (label, window) in enumerate(trial.thinned_capture_eval.controls(first).items()):
        controls[label] = dict(
            pairs=paired(window, policy, grid, 1, index),
            cells=audit(window, policy, grid),
            iq_sha256=window.iq_sha256,
        )
    return dict(setup=setup, producer=producer, captures=captures, controls=controls)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run", *LABELS))
    parser.add_argument("work", type=Path)
    args = parser.parse_args()
    work = local_output(args.work)
    work.mkdir(parents=True, exist_ok=True)
    seal = work / "grid-source-lock.json"
    if args.action == "freeze":
        if seal.exists():
            raise FileExistsError(seal)
        save_json(seal, freeze(work))
    else:
        lock = json.loads(seal.read_bytes())
        result = run(lock, cold=args.action if args.action in LABELS else None)
        write(work / f"grid-{args.action}.json.gz", gzip.compress(encoded(result), mtime=0))
