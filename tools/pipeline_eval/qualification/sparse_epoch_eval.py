"""Qualify the stride-six raw-epoch scout against authenticated capture-era GLRTs."""

import argparse
import gzip
import os
from contextlib import ExitStack
from functools import cache
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from unittest.mock import patch

import numpy as np

from ..__main__ import THREAD_ENV, encoded, local_output, write
from ..variants import anchor_grid, conditioned_cfo_bank, pilot_kernel, refine_bank, sparse_epoch, spectral_grid
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import MARGIN_GATE, PRODUCERS, _bind_producer, _from_production, _load_case, _probe, _sha
from .pilot_kernel_eval import _digest, _windows
from .refine_bank_eval import _noise
from .spectral_grid_eval import _synthetic

METHOD = "sparse_epoch"
MODES = ("control", METHOD)
CASE_CPUS = dict(zip(PRODUCERS, (2, 3), strict=True))
SCHEDULE = {"development": (3, (0, 2)), "early": (4, (0, 2, 5, 7)),
            "late": (8, (0, 2, 5, 7))}


def source_hashes():
    return {path.name: _sha(path) for path in (Path(__file__), Path(sparse_epoch.__file__),
                                               sparse_epoch.SOURCE, spectral_grid.SOURCE,
                                               pilot_kernel.SOURCE)}


def matches(a, b, epochs):
    distance = (a["epoch"] + (a["offset"] or 0) - b["epoch"] - (b["offset"] or 0)) % epochs
    return (min(distance, epochs - distance) <= 2
            and abs(a["cfo"] - b["cfo"]) <= 1000)


def _candidates(result, fractional):
    margin_field = "fractional_margin" if fractional else "margin"
    rows = {}
    for receiver in result.receivers:
        entries = []
        for c in receiver.candidates:
            margin = getattr(c, margin_field)
            cfo = c.fractional_tracking_cfo_hz if fractional else c.tracking_cfo_hz
            if margin is not None and cfo is not None:
                entries.append(dict(rank=c.candidate_rank, epoch=c.epoch_sample, cfo=cfo,
                                    margin=margin, offset=c.fractional_epoch_offset_samples if fractional else None))
        rows[receiver.receiver_id] = entries
    return rows


def _audit(control, trial, epochs):
    report = {}
    for quantity in ("integer", "fractional"):
        a, b = (_candidates(output, quantity == "fractional") for output in (control, trial))
        receivers = {}
        for rid in a.keys() | b.keys():
            left, right = ([c for c in rows.get(rid, []) if c["margin"] >= MARGIN_GATE]
                           for rows in (a, b))
            @cache
            def assign(i, used):
                if i == len(left):
                    return ()
                proposals = [assign(i + 1, used)]
                proposals.extend(((i, j), *assign(i + 1, used | (1 << j)))
                                 for j, c in enumerate(right)
                                 if not used & (1 << j) and matches(left[i], c, epochs))
                return max(proposals, key=len)

            assigned = assign(0, 0)
            pairs = [(left[i], right[j]) for i, j in assigned]
            missed = [x for i, x in enumerate(left) if not any(i == p for p, _ in assigned)]
            added = [y for j, y in enumerate(right) if not any(j == p for _, p in assigned)]
            winners = [max(row, key=lambda c: c["margin"], default=None) for row in (left, right)]
            equal = (winners[0] == winners[1] if None in winners else
                     matches(*winners, epochs) and winners[0] == winners[1])
            receivers[rid] = dict(control=a.get(rid, []), trial=b.get(rid, []),
                                  control_positives=len(left), trial_positives=len(right),
                                  missed_positive=missed, new_positive=added, winners=winners,
                                  winner_equal=equal, matched_margin_delta=[
                                      second["margin"] - first["margin"] for first, second in pairs])
        report[quantity] = receivers
    return report


def _timed(window, call, index, repeats):
    outputs, timing, stable = {}, {mode: [] for mode in MODES}, True
    for repeat in range(repeats):
        for mode in (MODES if (index + repeat) % 2 == 0 else MODES[::-1]):
            output, clock = call(window, mode)
            stable &= outputs.setdefault(mode, output) == output
            timing[mode].append(clock)
    a, b = (outputs[mode] for mode in MODES)
    probes = {mode: [_probe(window, rx.receiver_id, map(_from_production, rx.candidates))
                     for rx in output.receivers] for mode, output in outputs.items()}
    payloads = {mode: output.model_dump(mode="json") for mode, output in outputs.items()}
    return dict(visit=b.visit, sequence=window.sequence, iq_sha256=window.iq_sha256,
                sample_start=b.sample_start, sample_end=b.sample_end, policy_status=b.status,
                reason=b.reason, stable=stable,
                equal_status=(a.status, a.reason) == (b.status, b.reason),
                timings=timing, exact_payload=a == b,
                payload_sha256={mode: _digest(encoded(p)) for mode, p in payloads.items()},
                production=probes["control"], native=probes[METHOD], payloads=payloads,
                audit=_audit(a, b, round(window.sample_rate_hz / 750)))


def replay(case_id, split, workspace):
    from leo.analysis.starlink import acquisition, fast_scan_scores
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner import fast_scan_detector
    from leo.scanner.fast_scan_analysis import analyze_window

    case, policy = _load_case(case_id), FastScanPolicyV2()
    producer = _bind_producer(case, PRODUCERS[case_id], policy)
    segment, sequence = SCHEDULE[split]
    helpers = dict(tiled=pilot_kernel.compile_filter, spectral=spectral_grid.compile_filter,
                   fused=refine_bank.compile_bank, cfo=conditioned_cfo_bank.compile_bank,
                   sparse=sparse_epoch.compile_grid)
    paths = {name: workspace / f"{name}.so" for name in helpers}
    for name, compile_library in helpers.items():
        compile_library(paths[name])
    tiled = anchor_grid.native_grid(paths["tiled"])
    grids = {"control": spectral_grid.SpectralGrid(paths["spectral"], tiled),
             METHOD: sparse_epoch.SparseEpochGrid(paths["sparse"], tiled)}
    fused = refine_bank.RefinementBank(paths["fused"], fast_scan_scores)
    if not fused.compatible:
        raise ValueError("Locked fused scorer is incompatible with NumPy runtime")
    conditioner = conditioned_cfo_bank.ConditionedBank(paths["cfo"], acquisition)
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
            output = analyze_window(window, window.receiver_ids, None, policy)
            clock = dict(full_cpu_s=process_time() - cpu, full_wall_s=perf_counter() - wall,
                         coarse_cpu_s=sum(r["coarse_cpu_s"] + r.get("repair_cpu_s", 0)
                                          for r in grid.receipts), grids=grid.receipts.copy())
        return output, clock

    windows = _windows(case, segment, sequence)
    rows = []
    for index, window in enumerate(windows):
        row = _timed(window, call, index, 3)
        original = analyze_window(window, window.receiver_ids, None, policy)
        expected = _digest(encoded(original.model_dump(mode="json")))
        row["matches_original_control"] = row["payload_sha256"]["control"] == expected
        rows.append(row)
        print(case_id, split, row["visit"], row["policy_status"], row["exact_payload"],
              row["matches_original_control"], flush=True)

    controls = {}
    if split == "development":
        first = next(w for w, row in zip(windows, rows, strict=True)
                     if row["policy_status"] == "processed")
        plants = _synthetic(first)
        for label, signals in dict(faint_on=((732, 48000, 128),), faint_between=((735, 48000, 128),),
                                   adjacent=((731, 47950, 3500), (928, 48050, 3500))).items():
            plants[label] = (_test_signal(first, signals, 830819), {"signals": signals})
        plants["noise"] = (_noise(first), None)
        for name, (window, truth) in plants.items():
            controls[name] = dict(_timed(window, call, 0, 1), truth=truth)

    return dict(case=case_id, split=split, segment=segment, producer=producer, rows=rows,
                controls=controls, source_sha256=source_hashes(),
                library_sha256={key: _sha(path) for key, path in paths.items()},
                cpus=sorted(os.sched_getaffinity(0)), numpy=np.__version__)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=PRODUCERS, required=True)
    parser.add_argument("--split", choices=SCHEDULE, required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if os.sched_getaffinity(0) != {CASE_CPUS[args.case]} or any(
        os.environ.get(name) != "1" for name in THREAD_ENV
    ):
        parser.error("pin the designated core and set all numerical threads to one")
    with TemporaryDirectory(prefix="sparse-epoch-") as tmp:
        result = replay(args.case, args.split, Path(tmp))
    write(local_output(args.out), gzip.compress(encoded(result), mtime=0))


if __name__ == "__main__":
    main()
