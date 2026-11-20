"""Bounded capture-era comparison of the sliding tone basis and tiled bank."""

import argparse
import gzip
import os
import subprocess
import tracemalloc
from dataclasses import replace
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from unittest.mock import patch

import numpy as np

from ..__main__ import THREAD_ENV, encoded, write
from ..variants import anchor_grid, pilot_kernel, spectral_grid
from .full_v5_check import MARGIN_GATE, PRODUCERS, _bind_producer, _load_case, _sha
from .pilot_kernel_eval import _digest, _windows

SCHEDULE = {"development": 2, "holdout": 12}
SEQUENCES = (0, 1, 3, 6)
MODES = ("tiled", "spectral")
REPEATS = 3


def _synthetic(window):
    from leo.analysis.starlink.templates import FRAME_RATE_HZ, qin_edge_pilot_frame

    rate = window.sample_rate_hz
    frame = qin_edge_pilot_frame(rate, window.target["edge"])
    center = (window.target["rf_center_hz"] - window.target["lnb_lo_hz"]
              - window.acquisition["actual_if_center_hz"])
    epoch, cfo = 731, center + 48_000
    signal = np.zeros(len(window.samples), dtype=complex)
    for offset in range(16):
        start = round(offset * rate / FRAME_RATE_HZ) + epoch
        n = min(len(frame), len(signal) - start)
        if n > 0:
            signal[start:start + n] = frame[:n]
    signal *= 10_000 * np.exp(2j * np.pi * cfo / rate * np.arange(len(signal)))
    rng = np.random.default_rng(724698)
    samples = np.clip(np.rint(
        np.stack((signal.real, signal.imag), axis=-1)[:, None, :]
        + rng.normal(0, 500, window.samples.shape)
    ), -32768, 32767).astype("<i2")
    empty = np.zeros_like(samples)
    return {
        "empty": (replace(window, samples=empty, iq_sha256=_digest(empty.tobytes())), None),
        "plant": (replace(window, samples=samples, iq_sha256=_digest(samples.tobytes())),
                  dict(epoch=epoch, cfo=cfo)),
    }


def _positives(result):
    def winners(receiver, fractional):
        margin = "fractional_margin" if fractional else "margin"
        matches = [c for c in receiver.candidates if getattr(c, margin) is not None
                   and getattr(c, margin) >= MARGIN_GATE]
        c = max(matches, key=lambda c: getattr(c, margin), default=None)
        if c is None:
            return dict(count=0, winner=None)
        return dict(count=len(matches), winner=dict(
            rank=c.candidate_rank, epoch=c.epoch_sample, margin=getattr(c, margin),
            cfo=c.fractional_tracking_cfo_hz if fractional else c.tracking_cfo_hz,
            offset=c.fractional_epoch_offset_samples if fractional else None,
        ))

    return {r.receiver_id: dict(integer=winners(r, False), fractional=winners(r, True))
            for r in result.receivers}


def _result_payload(output):
    return output.model_dump(mode="json")


def _run_window(window, call, index):
    original = call(window, "installed")
    tracked = {mode: [] for mode in MODES}
    for repeat in range(REPEATS):
        order = MODES if (index + repeat) % 2 == 0 else MODES[::-1]
        for mode in order:
            tracked[mode].append(call(window, mode))
    tiled = tracked["tiled"][0]
    spectral = tracked["spectral"][0]
    payload = _result_payload(tiled[0])
    equal = all(_result_payload(r[0]) == payload for repetitions in tracked.values()
                for r in repetitions)
    coarse_equal = all(r[2] == tiled[2] for repetitions in tracked.values() for r in repetitions)
    for mode in MODES:
        tracked[mode] = [r[1] for r in tracked[mode]]
    return dict(
        visit=tiled[0].visit, sequence=window.sequence, status=tiled[0].status,
        edge=tiled[0].edge, channel=tiled[0].channel,
        sample_rate_hz=window.sample_rate_hz, sample_count=len(window.samples),
        sample_start_utc_ns=tiled[0].sample_start_utc_ns, iq_sha256=window.iq_sha256,
        equal_payload=equal, exact_tiled_peaks=coarse_equal,
        equal_installed=_result_payload(original[0]) == payload,
        positive_winners=dict(installed=_positives(original[0]), tiled=_positives(tiled[0]),
                              spectral=_positives(spectral[0])),
        payload_sha256={name: _digest(encoded(_result_payload(output[0]))) for name, output in (
            ("installed", original), ("tiled", tiled), ("spectral", spectral)
        )},
        different_payloads=None if equal else {
            "tiled": payload, "spectral": _result_payload(spectral[0])
        },
        timings=dict(tracked, installed=[original[1]]),
    )


def _summary(rows):
    valid = [r for r in rows if r["status"] == "processed"]
    modes = (*MODES, "installed")
    timing = {}
    for mode in modes:
        by_visit = [r["timings"][mode] for r in valid]
        if not by_visit:
            continue
        timing[mode] = {key: median(median(x[key] for x in reps) for reps in by_visit)
                        for key in ("cpu_s", "wall_s", "coarse_cpu_s", "repair_cpu_s")}
        timing[mode]["total_paired_cpu_s"] = sum(x["cpu_s"] for reps in by_visit for x in reps)
    return dict(windows=len(rows), valid=len(valid), timing_median_s=timing,
                equal_payload=all(r["equal_payload"] for r in rows),
                exact_tiled_peaks=all(r["exact_tiled_peaks"] for r in rows),
                equal_installed=all(r["equal_installed"] for r in rows))


def replay(case_id, split, directory):
    from leo.analysis.starlink import acquisition, fast_scan_scores
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window

    policy = FastScanPolicyV2()
    case = _load_case(case_id)
    producer = _bind_producer(case, PRODUCERS[case_id], policy)
    library = directory / "spectral.so"
    control_library = directory / "tiled.so"
    spectral_grid.compile_filter(library)
    pilot_kernel.compile_filter(control_library)
    control = anchor_grid.native_grid(control_library)
    spectral = spectral_grid.SpectralGrid(library, control)
    sampler = anchor_grid.fractional_sampler(fast_scan_scores.fractional_take)
    original_grid = acquisition._folded_anchor_score_grid
    original_retain = acquisition._retain_score_map_peaks

    def call(window, mode, *, audit_maps=None):
        spectral.receipts.clear()
        timings, peaks = [], []
        original = mode == "installed"
        grid = {"installed": original_grid, "tiled": control, "spectral": spectral.score_grid}[mode]
        keep = {"installed": original_retain, "tiled": anchor_grid.retained_peaks,
                "spectral": spectral.retain_peaks}[mode]

        def trace_grid(*args):
            begin = process_time()
            grid_rows = grid(*args)
            timings.append(process_time() - begin)
            if audit_maps is not None:
                audit_maps.append(np.asarray(grid_rows).copy())
            return grid_rows

        def trace_peaks(*args):
            result = keep(*args)
            peaks.append(result)
            return result

        with (patch.object(acquisition, "_folded_anchor_score_grid", trace_grid),
              patch.object(acquisition, "_retain_score_map_peaks", trace_peaks),
              patch.object(fast_scan_scores, "fractional_take",
                           fast_scan_scores.fractional_take if original else sampler)):
            start, cpu = perf_counter(), process_time()
            result = analyze_window(window, window.receiver_ids, None, policy)
            spent = dict(cpu_s=process_time() - cpu, wall_s=perf_counter() - start)
        return result, dict(spent, coarse_cpu_s=sum(timings),
                            repair_cpu_s=sum(r.get("repair_cpu_s", 0) for r in spectral.receipts),
                            spectral_grids=spectral.receipts.copy()), peaks

    segment = SCHEDULE[split]
    windows = _windows(case, segment, SEQUENCES)
    rows = []
    for window in windows:
        row = _run_window(window, call, len(rows))
        rows.append(row)
        print(case_id, split, row["visit"], row["status"], row["equal_payload"], flush=True)
    memory = {}
    controls = {}
    valid = next(w for w, r in zip(windows, rows, strict=True) if r["status"] == "processed")
    audit_maps = {mode: [] for mode in MODES}
    for mode in MODES:
        call(valid, mode, audit_maps=audit_maps[mode])
    dense_audit = [dict(
        max_error=float(np.max(abs(tiled - proposed))),
        cells=tiled.size, error_bound=receipt.get("error_bound"),
        fallback=receipt.get("fallback"),
    ) for tiled, proposed, receipt in zip(
        audit_maps["tiled"], audit_maps["spectral"], spectral.receipts, strict=True
    )]
    if split == "development":
        for mode in MODES:
            tracemalloc.start()
            call(valid, mode)
            memory[mode] = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
        for kind, (window, truth) in _synthetic(valid).items():
            row = _run_window(window, call, 0)
            row["plant_truth"] = truth
            controls[kind] = row
    sources = (
        Path(__file__), spectral_grid.SOURCE, Path(spectral_grid.__file__), pilot_kernel.SOURCE,
    )
    return dict(
        case=case_id, split=split, segment=segment, cpus=sorted(os.sched_getaffinity(0)),
        producer=producer, rows=rows, summary=_summary(rows), controls=controls,
        compiler=subprocess.check_output(["cc", "--version"], text=True).splitlines()[0],
        dense_grid_audit=dict(visit=valid.acquisition["global_visit"], grids=dense_audit),
        traced_peak_bytes=memory, mixed_process_rss_high_water_kib=getrusage(RUSAGE_SELF).ru_maxrss,
        source_sha256={p.name: _sha(p) for p in sources},
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=PRODUCERS, required=True)
    parser.add_argument("--split", choices=SCHEDULE, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cpus = os.sched_getaffinity(0)
    single_thread = all(os.environ.get(k) == "1" for k in THREAD_ENV)
    if len(cpus) != 1 or not cpus <= {12, 13, 14} or not single_thread:
        parser.error("pin one CPU from 12–14 and set every numerical runtime thread count to one")
    with TemporaryDirectory(prefix="leo-spectral-grid-") as work:
        result = replay(args.case, args.split, Path(work))
    write(args.out, gzip.compress(encoded(result) + b"\n", mtime=0))


if __name__ == "__main__":
    main()
