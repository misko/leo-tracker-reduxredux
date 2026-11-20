"""Pair exact guarded-acquisition reuse with Q10 and audit a safe pruning bound."""

import argparse
import gzip
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ..__main__ import ROOT, THREAD_ENV, encoded, write
from ..variants import (
    anchor_grid,
    certified_glrt,
    conditioned_cfo_bank,
    dense_q10,
    pilot_kernel,
    refine_bank,
)
from . import certified_glrt_bounds, dense_q10_eval, sparse_epoch_eval, spectral_grid_eval
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import PRODUCERS, _bind_producer, _load_case, _sha
from .pilot_kernel_eval import _digest, _windows
from .refine_bank_eval import _noise

METHOD = "certified_glrt"
CPU = 12
SCHEDULE = {"early": (12, (0, 2, 5, 7)), "late": (13, (0, 2, 5, 7))}
REPORT = ROOT / "reports/2026_11_19_receiver_screening/recovery/certified-glrt"
LOCK = REPORT / "source-lock.json"


def sources():
    paths = (
        Path(__file__),
        Path(certified_glrt.__file__),
        Path(certified_glrt_bounds.__file__),
        REPORT / "PROTOCOL.md",
    )
    return dense_q10_eval.frozen_sources() | {str(p.relative_to(ROOT)): _sha(p) for p in paths}


class AuditedGrid(dense_q10.DenseQ10Grid):
    def __init__(self, library, control):
        super().__init__(library, control)
        self.audit = False
        self.observed = []
        self.bounds = []
        self.inputs = None

    def score_grid(self, *args):
        self.inputs = args if self.audit else None
        return super().score_grid(*args)

    def retain_peaks(self, residuals, scores, count, epoch_separation, cfo_separation, epochs):
        peaks = super().retain_peaks(
            residuals, scores, count, epoch_separation, cfo_separation, epochs
        )
        if self.inputs is not None and len(peaks) == count:
            values = self.inputs[0]
            if not any(certified_glrt.same_bytes(values, seen) for seen in self.observed):
                self.observed.append(values.copy())
                self.bounds.append(
                    certified_glrt_bounds.diagnostic(*self.inputs, cutoff=peaks[-1][0])
                )
        return peaks


def _timed(window, call, index, repeats):
    row = sparse_epoch_eval._timed(window, call, index, repeats)
    for field in ("timings", "payload_sha256", "payloads"):
        row[field][METHOD] = row[field].pop("sparse_epoch")
    return row


def replay(case_id, workspace, limits, source):
    from leo.analysis.starlink import acquisition, fast_scan_scores
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window

    case, policy = _load_case(case_id), FastScanPolicyV2()
    producer = _bind_producer(case, PRODUCERS[case_id], policy)
    build = dict(
        tiled=pilot_kernel.compile_filter,
        dense=dense_q10.compile_grid,
        cfo=conditioned_cfo_bank.compile_bank,
        fused=refine_bank.compile_bank,
    )
    paths = {name: workspace / f"{name}.so" for name in build}
    for name, compile_library in build.items():
        compile_library(paths[name])
    direct = anchor_grid.native_grid(paths["tiled"])
    baseline = AuditedGrid(paths["dense"], direct)
    trial = certified_glrt.ReusedGrid(paths["dense"], direct, acquisition._normalized_frame_scores)
    conditioner = conditioned_cfo_bank.ConditionedBank(paths["cfo"], acquisition)
    fused = refine_bank.RefinementBank(paths["fused"], fast_scan_scores)
    if not fused.compatible:
        raise ValueError("Fused kernel is incompatible with this capture-era runtime")
    raw_guard = conditioner.guarded_acquisition
    active = False

    def toggle_guard(function):
        control_guard = raw_guard(function)
        trial_guard = trial.guarded_acquisition(control_guard)

        def guarded(*args, **kwargs):
            return (trial_guard if active else control_guard)(*args, **kwargs)

        return guarded

    with patch.object(conditioner, "guarded_acquisition", toggle_guard):
        evaluate = dense_q10_eval._paired_call(
            {"control": baseline, "sparse_epoch": trial}, fused, conditioner, policy
        )

    def call(window, mode):
        nonlocal active
        active = mode == "sparse_epoch"
        trial.reuse.clear()
        with patch.object(acquisition, "_normalized_frame_scores", trial.fine_scores):
            outcome, timing = evaluate(window, mode)
        timing["reuse"] = trial.reuse.copy()
        return outcome, timing

    panels, controls = {}, {}
    for split in limits:
        segment, sequence = SCHEDULE[split]
        windows, rows = _windows(case, segment, sequence), []
        for index, window in enumerate(windows):
            row = _timed(window, call, index, 2)
            original = analyze_window(window, window.receiver_ids, None, policy)
            digest = _digest(encoded(original.model_dump(mode="json")))
            row["matches_original_control"] = digest == row["payload_sha256"]["control"]
            rows.append(row)
            print(case_id, split, row["visit"], row["exact_payload"], flush=True)
        first = next(
            w for w, row in zip(windows, rows, strict=True) if row["policy_status"] == "processed"
        )
        baseline.audit = True
        baseline.observed.clear()
        baseline.bounds.clear()
        call(first, "control")
        baseline.audit = False
        panels[split] = dict(segment=segment, rows=rows, bounds=baseline.bounds.copy())
        if split == "early":
            empty, _ = spectral_grid_eval._synthetic(first)["empty"]
            faint = _test_signal(first, ((735, 48000, 128),), 830819)
            for name, window in dict(empty=empty, faint=faint, noise=_noise(first)).items():
                controls[name] = _timed(window, call, 0, 1)
    return dict(
        case=case_id,
        producer=producer,
        panels=panels,
        controls=controls,
        source_sha256=source,
        library_sha256={name: _sha(path) for name, path in paths.items()},
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=PRODUCERS, required=True)
    args = parser.parse_args()
    if os.sched_getaffinity(0) != {CPU} or any(os.environ.get(k) != "1" for k in THREAD_ENV):
        parser.error("pin the dedicated CPU and numerical threads")
    frozen = sources()
    if LOCK.read_bytes() != encoded(frozen) + b"\n":
        raise ValueError("Predeclared source lock differs from the measured implementation")
    with TemporaryDirectory(prefix="certified-glrt-") as work:
        result = replay(args.case, Path(work), tuple(SCHEDULE), frozen)
    if frozen != sources():
        raise ValueError("Implementation changed during replay")
    write(REPORT / f"{args.case}-replay.json.gz", gzip.compress(encoded(result), mtime=0))


if __name__ == "__main__":
    main()
