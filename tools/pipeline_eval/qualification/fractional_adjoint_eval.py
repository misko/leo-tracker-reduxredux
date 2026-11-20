"""Compare transposed continuous GLRT scoring on fixed authenticated visits."""

import argparse
import gzip
import os
import tracemalloc
from contextlib import ExitStack
from itertools import zip_longest
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from unittest.mock import patch

import numpy as np

from ..__main__ import THREAD_ENV, encoded, write
from ..variants import (
    anchor_grid,
    conditioned_cfo_bank,
    fractional_adjoint,
    pilot_kernel,
    refine_bank,
    spectral_grid,
)
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import PRODUCERS, _bind_producer, _from_production, _load_case, _probe, _sha
from .pilot_kernel_eval import _digest, _windows
from .refine_bank_eval import _noise
from .spectral_grid_eval import _positives, _synthetic

METHOD = "fractional_adjoint"
MODES = ("control", METHOD)
CASE_CPUS = dict(zip(PRODUCERS, (2, 3), strict=True))
SCHEDULE = {"development": (3, (0, 2)), "early": (7, (0, 2, 5, 7)),
            "late": (10, (0, 2, 5, 7))}
FIELDS = ("fractional_exact_score", "fractional_control_score", "fractional_margin")


def compare(control, trial):
    a, b = (o.model_dump(mode="json") for o in (control, trial))
    left, right = a.pop("receivers"), b.pop("receivers")
    forbidden = []
    if a != b:
        forbidden.append("window_geometry_or_status")
    changed, maxima = [], dict.fromkeys(FIELDS, 0.0)
    for x, y in zip_longest(left, right):
        if x is None or y is None or x["receiver_id"] != y["receiver_id"]:
            forbidden.append("receiver_sequence")
            continue
        for old, new in zip_longest(x["candidates"], y["candidates"]):
            if old is None or new is None:
                forbidden.append("candidate_count")
                continue
            differences = {k: (v, new[k]) for k, v in old.items() if v != new[k]}
            eligible = all(
                p["fractional_margin"] is not None and p["fractional_margin"] < 0.025
                for p in (old, new)
            )
            if differences:
                changed.append(dict(receiver=x["receiver_id"], rank=old["candidate_rank"],
                                    fields=differences))
            for key, (before, after) in differences.items():
                if eligible and key in FIELDS and before is not None and after is not None:
                    maxima[key] = max(maxima[key], abs(before - after))
                else:
                    forbidden.append(key)
    winners_equal = _positives(control) == _positives(trial)
    return dict(
        exact_payload=not changed and not forbidden, positive_winners_equal=winners_equal,
        changed_negative_fields=changed, forbidden_changes=forbidden, max_error=maxima,
        passed=not forbidden and winners_equal and max(maxima.values()) <= 1e-9,
    )


def _timed(window, call, index, repeat_count):
    modes, timing, stable = {}, {name: [] for name in MODES}, True
    for rep in range(repeat_count):
        order = MODES if (index + rep) % 2 == 0 else MODES[::-1]
        for mode in order:
            outcome, row = call(window, mode)
            stable &= modes.setdefault(mode, outcome) == outcome
            timing[mode].append(row)
    original, trial = (modes[mode] for mode in MODES)
    probes = {mode: [_probe(window, r.receiver_id, map(_from_production, r.candidates))
                     for r in output.receivers] for mode, output in modes.items()}
    return dict(
        visit=trial.visit, sequence=window.sequence, iq_sha256=window.iq_sha256,
        sample_start=trial.sample_start, sample_end=trial.sample_end,
        policy_status=trial.status, reason=trial.reason, stable=stable,
        equal_status=(trial.status, trial.reason) == (original.status, original.reason),
        production=probes["control"], native=probes[METHOD], timings=timing,
        comparison=compare(original, trial),
        payload_sha256={m: _digest(encoded(o.model_dump(mode="json"))) for m, o in modes.items()},
        positive_winners={m: _positives(o) for m, o in modes.items()},
    )


def timing_summary(rows):
    valid = [r for r in rows if r["policy_status"] == "processed"]
    totals, medians = {}, {}
    for mode in MODES:
        data = [r["timings"][mode] for r in valid]
        for field in ("full_cpu_s", "full_wall_s", "continuous_cpu_s"):
            totals.setdefault(mode, {})[field] = sum(z[field] for group in data for z in group)
            medians.setdefault(mode, {})[field] = (
                median(median(z[field] for z in group) for group in data) if data else None
            )
    return dict(valid=len(valid), scheduled=len(rows), totals=totals, medians=medians)


def sources():
    return (Path(__file__), Path(fractional_adjoint.__file__), fractional_adjoint.SOURCE)


def replay(case_id, split, workspace):
    from leo.analysis.starlink import acquisition, fast_scan_scores
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner import fast_scan_detector
    from leo.scanner.fast_scan_analysis import analyze_window

    case, policy = _load_case(case_id), FastScanPolicyV2()
    producer = _bind_producer(case, PRODUCERS[case_id], policy)
    segment, sequence = SCHEDULE[split]
    paths = {m: workspace / f"{m}.so" for m in ("tiled", "spectral", "fused", "cfo", "adjoint")}
    pilot_kernel.compile_filter(paths["tiled"])
    spectral_grid.compile_filter(paths["spectral"])
    refine_bank.compile_bank(paths["fused"])
    conditioned_cfo_bank.compile_bank(paths["cfo"])
    fractional_adjoint.compile_bank(paths["adjoint"])
    coarse = spectral_grid.SpectralGrid(paths["spectral"], anchor_grid.native_grid(paths["tiled"]))
    fused = refine_bank.RefinementBank(paths["fused"], fast_scan_scores)
    if not fused.compatible:
        raise ValueError("Locked fused scorer is incompatible with NumPy runtime")
    conditioner = conditioned_cfo_bank.ConditionedBank(paths["cfo"], acquisition)
    adjoint = fractional_adjoint.Adjoint(paths["adjoint"], fused)
    kept = conditioner.guarded_acquisition(fast_scan_detector.acquire_symbolwise)
    sampler = anchor_grid.fractional_sampler(fast_scan_scores.fractional_take)

    def call(window, mode):
        coarse.receipts.clear()
        fused.reset()
        conditioner.reset()
        adjoint.reset()
        scorer = adjoint.score if mode == METHOD else fused.fractional
        elapsed, calls = 0.0, 0

        def scalar(*args, **kwargs):
            nonlocal elapsed, calls
            start = process_time()
            score = scorer(*args, **kwargs)
            elapsed += process_time() - start
            calls += 1
            return score

        bindings = (
            (acquisition, "_folded_anchor_score_grid", coarse.score_grid),
            (acquisition, "_retain_score_map_peaks", coarse.retain_peaks),
            (acquisition, "_conditioned_frame_scores", conditioner.score),
            (fast_scan_detector, "acquire_symbolwise", kept),
            (fast_scan_detector, "conditioned_glrt64_scores", fused.integer),
            (fast_scan_scores, "conditioned_glrt64_scores", fused.integer),
            (fast_scan_scores, "conditioned_glrt64_score", scalar),
            (fast_scan_scores, "fractional_take", sampler),
        )
        with ExitStack() as stack:
            for mod, name, function in bindings:
                stack.enter_context(patch.object(mod, name, function))
            cpu, wall = process_time(), perf_counter()
            result = analyze_window(window, window.receiver_ids, None, policy)
            return result, dict(full_cpu_s=process_time() - cpu, full_wall_s=perf_counter() - wall,
                                continuous_cpu_s=elapsed, continuous_calls=calls,
                                adjoint=adjoint.receipts)

    rows = []
    windows = _windows(case, segment, sequence)
    for window in windows:
        row = _timed(window, call, len(rows), 3)
        original = analyze_window(window, window.receiver_ids, None, policy)
        expected = _digest(encoded(original.model_dump(mode="json")))
        row["matches_original_control"] = row["payload_sha256"]["control"] == expected
        rows.append(row)
        print(case_id, split, row["visit"], row["policy_status"], row["comparison"]["passed"],
              row["matches_original_control"], flush=True)
    controls, memory = {}, {}
    if split == "development":
        valid = (w for w, r in zip(windows, rows, strict=True) if r["policy_status"] == "processed")
        first = next(valid)
        for mode in MODES:
            tracemalloc.start()
            call(first, mode)
            memory[mode] = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
        plants = _synthetic(first)
        plants["faint"] = (_test_signal(first, ((731, 48000, 128),), 830819), {"epoch": 731})
        near = ((731, 47950, 3500), (928, 48050, 3500))
        plants["adjacent"] = (_test_signal(first, near, 830819), {"signals": near})
        plants["noise"] = (_noise(first), None)
        for name, (w, truth) in plants.items():
            controls[name] = dict(_timed(w, call, 0, 1), truth=truth)
    return dict(
        case=case_id, split=split, segment=segment, producer=producer, rows=rows,
        summary=timing_summary(rows), controls=controls, traced_peak_bytes=memory,
        source_sha256={path.name: _sha(path) for path in sources()},
        library_sha256={key: _sha(path) for key, path in paths.items()},
        cpus=sorted(os.sched_getaffinity(0)), numpy=np.__version__,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=PRODUCERS, required=True)
    parser.add_argument("--split", choices=SCHEDULE, required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    single = all(os.environ.get(k) == "1" for k in THREAD_ENV)
    if not single or os.sched_getaffinity(0) != {CASE_CPUS[args.case]}:
        parser.error("pin the designated CPU and set one numerical thread")
    with TemporaryDirectory(prefix="fractional-adjoint-") as workspace:
        result = replay(args.case, args.split, Path(workspace))
    write(args.out, gzip.compress(encoded(result) + b"\n", mtime=0))


if __name__ == "__main__":
    main()
