"""Pair the full-epoch Q10 bank and binary64 bank on authenticated capture visits."""

import argparse
import gzip
import os
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from unittest.mock import patch

import numpy as np

from ..__main__ import ROOT, THREAD_ENV, encoded, local_output, write
from ..variants import (
    anchor_grid,
    conditioned_cfo_bank,
    dense_q10,
    pilot_kernel,
    refine_bank,
    spectral_grid,
)
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import PRODUCERS, _bind_producer, _load_case, _sha
from .pilot_kernel_eval import _digest, _windows
from .refine_bank_eval import _noise
from .sparse_epoch_eval import _timed
from .spectral_grid_eval import _synthetic

METHOD = "dense_q10"
CPUS = dict(zip(PRODUCERS, (2, 3), strict=True))
SCHEDULE = {
    "development": (3, (0, 2)),
    "early": (5, (0, 2, 5, 7)),
    "late": (9, (0, 2, 5, 7)),
}
REPORT = ROOT / "reports/2026_11_19_receiver_screening/factors/glrt-dense"
LOCK = REPORT / "source-lock.json"


def frozen_sources():
    from . import sparse_epoch_eval

    return {
        str(path.relative_to(ROOT)): _sha(path)
        for path in (
            Path(__file__),
            Path(sparse_epoch_eval.__file__),
            Path(dense_q10.__file__),
            dense_q10.SOURCE,
            Path(spectral_grid.__file__),
            spectral_grid.SOURCE,
            Path(anchor_grid.__file__),
            pilot_kernel.SOURCE,
            Path(refine_bank.__file__),
            refine_bank.SOURCE,
            Path(conditioned_cfo_bank.__file__),
            conditioned_cfo_bank.SOURCE,
            REPORT / "PROTOCOL.md",
        )
    }


def _timed_pair(window, call, index, repeats):
    # Reuse the sealed full-payload and one-to-one audit implementation used by the earlier scout.
    row = _timed(window, call, index, repeats)
    for key in ("timings", "payload_sha256", "payloads"):
        row[key][METHOD] = row[key].pop("sparse_epoch")
    return row


def _paired_call(grids, fused, conditioner, policy):
    from leo.analysis.starlink import acquisition, fast_scan_scores
    from leo.scanner import fast_scan_detector
    from leo.scanner.fast_scan_analysis import analyze_window

    guarded = conditioner.guarded_acquisition(fast_scan_detector.acquire_symbolwise)
    sampler = anchor_grid.fractional_sampler(fast_scan_scores.fractional_take)

    def call(window, mode):
        grid = grids[mode]
        grid.receipts.clear()
        fused.reset()
        conditioner.reset()
        bindings = (
            (acquisition, "_folded_anchor_score_grid", grid.score_grid),
            (acquisition, "_retain_score_map_peaks", grid.retain_peaks),
            (acquisition, "_conditioned_frame_scores", conditioner.score),
            (fast_scan_detector, "acquire_symbolwise", guarded),
            (fast_scan_detector, "conditioned_glrt64_scores", fused.integer),
            (fast_scan_scores, "conditioned_glrt64_scores", fused.integer),
            (fast_scan_scores, "conditioned_glrt64_score", fused.fractional),
            (fast_scan_scores, "fractional_take", sampler),
        )
        with ExitStack() as stack:
            for module, name, function in bindings:
                stack.enter_context(patch.object(module, name, function))
            cpu, wall = process_time(), perf_counter()
            result = analyze_window(window, window.receiver_ids, None, policy)
            clock = dict(
                full_cpu_s=process_time() - cpu,
                full_wall_s=perf_counter() - wall,
                coarse_cpu_s=sum(
                    r["coarse_cpu_s"] + r.get("repair_cpu_s", 0) for r in grid.receipts
                ),
                grids=grid.receipts.copy(),
            )
        return result, clock

    return call


def replay(case_id, split, workspace, source_lock, controls=False):
    from leo.analysis.starlink import acquisition, fast_scan_scores
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window

    case, policy = _load_case(case_id), FastScanPolicyV2()
    producer = _bind_producer(case, PRODUCERS[case_id], policy)
    segment, sequence = SCHEDULE[split]
    build = dict(
        tiled=pilot_kernel.compile_filter,
        spectral=spectral_grid.compile_filter,
        fused=refine_bank.compile_bank,
        cfo=conditioned_cfo_bank.compile_bank,
        quantized=dense_q10.compile_grid,
    )
    paths = {name: workspace / f"{name}.so" for name in build}
    for name, compile_library in build.items():
        compile_library(paths[name])
    tiled = anchor_grid.native_grid(paths["tiled"])
    grids = {
        "control": spectral_grid.SpectralGrid(paths["spectral"], tiled),
        "sparse_epoch": dense_q10.DenseQ10Grid(paths["quantized"], tiled),
    }
    fused = refine_bank.RefinementBank(paths["fused"], fast_scan_scores)
    if not fused.compatible:
        raise ValueError("Fused refinement is incompatible with the capture-era NumPy runtime")
    conditioner = conditioned_cfo_bank.ConditionedBank(paths["cfo"], acquisition)
    call = _paired_call(grids, fused, conditioner, policy)

    windows = _windows(case, segment, sequence)
    rows = []
    for index, window in enumerate(windows):
        row = _timed_pair(window, call, index, 3)
        original = analyze_window(window, window.receiver_ids, None, policy)
        expected = _digest(encoded(original.model_dump(mode="json")))
        row["matches_original_control"] = row["payload_sha256"]["control"] == expected
        rows.append(row)
        print(
            case_id,
            split,
            row["visit"],
            row["policy_status"],
            row["exact_payload"],
            row["matches_original_control"],
            flush=True,
        )

    plants = {}
    if controls:
        first = next(
            w for w, row in zip(windows, rows, strict=True) if row["policy_status"] == "processed"
        )
        examples = _synthetic(first)
        for label, signals in {
            "faint_on": ((732, 48000, 128),),
            "faint_between": ((735, 48000, 128),),
            "adjacent": ((731, 47950, 3500), (928, 48050, 3500)),
        }.items():
            examples[label] = (_test_signal(first, signals, 830819), {"signals": signals})
        examples["noise"] = (_noise(first), None)
        for label, (window, truth) in examples.items():
            plants[label] = dict(_timed_pair(window, call, 0, 1), truth=truth)

    return dict(
        case=case_id,
        split=split,
        segment=segment,
        producer=producer,
        rows=rows,
        controls=plants,
        source_sha256=source_lock,
        library_sha256={name: _sha(path) for name, path in paths.items()},
        cpus=sorted(os.sched_getaffinity(0)),
        numpy=np.__version__,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=PRODUCERS, required=True)
    parser.add_argument("--split", choices=SCHEDULE, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--controls", action="store_true")
    parser.add_argument("--engineering", action="store_true")
    args = parser.parse_args()
    if args.engineering and (args.split != "development" or args.controls):
        parser.error("only the development raw visits may run before the code freeze")
    if os.sched_getaffinity(0) != {CPUS[args.case]} or any(
        os.environ.get(k) != "1" for k in THREAD_ENV
    ):
        parser.error("pin the selected CPU and all numerical threads to one")
    sources = frozen_sources()
    if not args.engineering and LOCK.read_bytes() != encoded(sources) + b"\n":
        raise ValueError("The predeclared source lock does not reproduce current bytes")
    with TemporaryDirectory(prefix="dense-q10-") as temporary:
        result = replay(args.case, args.split, Path(temporary), sources, args.controls)
    if frozen_sources() != sources:
        raise ValueError("The source changed while the scorer was active")
    write(local_output(args.out), gzip.compress(encoded(result), mtime=0))


if __name__ == "__main__":
    main()
