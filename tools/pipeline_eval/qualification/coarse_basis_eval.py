"""Qualify a shared-spectrum coarse bank on bounded, authenticated saved IQ."""

import argparse
import gzip
import json
import os
from dataclasses import replace
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np

from ..__main__ import THREAD_ENV, encoded, write
from ..variants import (
    coarse_basis,
    coarse_basis_shift,
    conditioned_cfo_bank,
    original_kernel,
    refine_bank,
)
from ..variants.iq_stream import IQWindow
from ..variants.selective_capture import visit_pairs
from . import capture_detector_lineage, capture_exact_trial, capture_starts
from .coarse_basis_audit import FALLBACK
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import _load_case, _sha, compare_probes
from .original_kernel_trial import decode
from .pilot_kernel_eval import _digest

CASES = {
    "DS26-0237": (37, 43, 53),
    "DS29-0082": (37, 43, 53),
    "DS29-0519": (37, 43, 53),
}
RANKS = (20, 24)
FFT_SIZES = (250, 500, 1000)
REPEATS = 5


def read_iq(ident, visit):
    segment, manifest, window = decode(_load_case(ident), visit)
    return window, dict(
        visit=visit,
        segment=segment,
        sequence=window.sequence,
        iq_sha256=window.iq_sha256,
        manifest_sha256=manifest,
        counter=window.acquisition["sample_start"],
        target=window.target,
    )


def freeze_inputs(work):
    roster = {}
    for case, starts in CASES.items():
        path, digest = capture_detector_lineage.locked_native(_load_case(case), "capture")
        raw = path.read_bytes()
        if _digest(raw) != "sha256:" + digest.removeprefix("sha256:"):
            raise ValueError("validity roster native archive differs from its frozen digest")
        probes = dict(visit_pairs(json.loads(raw)["source"]["probes"]))
        rows = []
        for first in starts:
            visit = next(v for v in range(first, first + 5) if v in probes)
            window, witness = read_iq(case, visit)
            payload = window.samples.tobytes()
            if _digest(payload) != window.iq_sha256 or any(
                p["valid_start_counter"] != witness["counter"] for p in probes[visit]
            ):
                raise ValueError("physical IQ copy differs from its archive or sample clock")
            write(work / f"{case}-{visit}.ci16", payload)
            rows.append(
                dict(
                    witness=witness,
                    rejected=list(range(first, visit)),
                    acquisition=window.acquisition,
                    target_id=window.target_id,
                    rate=window.sample_rate_hz,
                    archive_sha256=digest,
                    archived_probe_sha256=_digest(encoded(probes[visit])),
                )
            )
        roster[case] = rows
    write(work / "fixed-roster.json", encoded(roster) + b"\n")


def captures(window, policy):
    from leo.analysis.starlink import acquisition as acq

    screen = capture_starts.screen_module()
    arguments = []
    orig = acq._folded_anchor_score_grid
    retain = acq._retain_score_map_peaks

    def mock_grid(*args):
        return np.zeros((len(args[3]), args[-1]))

    def save_args(residuals, scores, *opts):
        arguments[-1].append((residuals, *opts))
        return []

    def legacy(*args):
        arguments.append([args])
        return mock_grid(*args)

    def screened(_module, args, residuals, *opts):
        arguments.append([args, (residuals, *opts, args[-1])])
        return mock_grid(*args), []

    if screen is not None:
        with patch.object(screen, "acquire", screened):
            result = capture_starts.coarse_prefix(window, policy)
    else:
        with patch.multiple(
            acq,
            _folded_anchor_score_grid=legacy,
            _retain_score_map_peaks=save_args,
        ):
            result = capture_starts.coarse_prefix(window, policy)
    if result["status"] != "processed" or len(arguments) != 2:
        raise ValueError(f"visit did not expose two valid coarse detector inputs: {result}")
    return orig, retain, arguments


def compare_map(baseline, candidate, retain, ranking):
    left = retain(ranking[0], tuple(baseline), *ranking[1:])
    right = retain(ranking[0], tuple(candidate), *ranking[1:])
    left_keys = [(e, f) for _, e, f in left]
    right_keys = [(e, f) for _, e, f in right]
    delta = abs(baseline - candidate)
    return dict(
        cells=delta.size,
        max_abs=float(delta.max()),
        rms=float(np.sqrt(np.mean(delta**2))),
        ordered=left_keys == right_keys,
        baseline_peaks=left,
        proposed_peaks=right,
        common_peak_keys=len(set(left_keys).intersection(right_keys)),
    )


def offline_repair(baseline, candidate, retain, ranking):
    """Use baseline values on each nominated CFO lane and its timing neighbors."""
    residuals, count, separation, cfo_sep, epochs = ranking
    nominees = retain(residuals, tuple(candidate), 32, separation, cfo_sep, epochs)
    kept = np.full_like(baseline, np.nan)
    for score, epoch, residual in nominees:
        if score > 0:
            lane = residuals.index(residual)
            neighbors = (epoch + np.arange(-6, 7)) % epochs
            kept[lane, neighbors] = baseline[lane, neighbors]
    selected = retain(residuals, tuple(kept), count, separation, cfo_sep, epochs)
    comparator = retain(residuals, tuple(baseline), count, separation, cfo_sep, epochs)
    left, right = ([(e, f) for _, e, f in peaks] for peaks in (comparator, selected))
    return dict(
        nominations=len(nominees),
        rescored_cells=int(np.count_nonzero(np.isfinite(kept))),
        ordered=left == right,
        common_peak_keys=len(set(left).intersection(right)),
        missed_keys=sorted(set(left) - set(right)),
        extra_keys=sorted(set(right) - set(left)),
        rescored_peaks=selected,
    )


def microbenchmark(window, policy, work):
    from leo.analysis.starlink import acquisition as acq

    orig, retain, inputs = captures(window, policy)
    grids = {"prepared": original_kernel.PersistentGrid(work / "prepared/original_kernel.so")}
    grids.update({f"shift{n}": shared_grid(work, n) for n in FFT_SIZES})
    rows = []

    def dispatch(mode, projection, working, prefix):
        if mode in projection:
            return projection[mode].score(working[0], prefix)
        grid = grids[mode]
        result = np.asarray(grid.score_grid(acq, orig, *working))
        if not grid.calls[-1]["applied"]:
            raise ValueError(f"FFT fallback during comparison: {mode}, {working[3]}")
        return result, grid.calls[-1]

    try:
        for args, ranking in inputs:
            for anchors in (args[4], FALLBACK):
                values, frame, rate, bins, _, epochs = args
                working = values, frame, rate, bins, anchors, epochs
                starts = [round(s * rate * acq.OFDM_SYMBOL_DURATION_S) for s in anchors]
                frames = np.rint(np.arange(15) * rate / acq.FRAME_RATE_HZ).astype(np.int32)
                bank = coarse_basis.filters(frame, starts, 44, bins, rate)
                projection = {
                    f"rank{r}": coarse_basis.Projection(
                        work / "projection.so", bank, r, starts, frames, epochs
                    )
                    for r in RANKS
                }
                prefix = acq._power_prefix(values)

                outputs, clocks, cold = {}, [], {}
                order = tuple(grids) + tuple(projection)
                for mode in order:
                    _, cold[mode] = dispatch(mode, projection, working, prefix)
                for turn in range(REPEATS):
                    rotation = (turn + len(rows)) % len(order)
                    modes = order[rotation:] + order[:rotation]
                    timing = {}
                    for mode in modes:
                        cpu, wall = process_time_ns(), perf_counter_ns()
                        scores, receipt = dispatch(mode, projection, working, prefix)
                        timing[mode] = dict(
                            cpu_ns=process_time_ns() - cpu,
                            wall_ns=perf_counter_ns() - wall,
                            kernel=receipt,
                        )
                        outputs[mode] = scores
                    clocks.append(dict(order=modes, measurements=timing))
                baseline = outputs.pop("prepared")
                direct = np.asarray(orig(*working))
                rows.append(
                    dict(
                        anchors=len(anchors),
                        frequencies=list(bins),
                        cold=cold,
                        timings=clocks,
                        prepared_vs_installed=compare_map(direct, baseline, retain, ranking),
                        error={
                            mode: compare_map(direct, a, retain, ranking)
                            for mode, a in outputs.items()
                        },
                        offline_repair={
                            mode: offline_repair(direct, outputs[mode], retain, ranking)
                            for mode in projection
                        },
                    )
                )
    finally:
        for grid in grids.values():
            grid.clear_cache()
    return rows


def shared_grid(work, n):
    return original_kernel.PersistentGrid(work / f"shift-{n}/coarse_basis_shift.so")


def controls(parent):
    empty = np.zeros_like(parent.samples)
    return {
        "empty": replace(parent, samples=empty, iq_sha256=_digest(empty.tobytes())),
        "gaussian": _test_signal(parent, (), 256018),
        "weak_positive": _test_signal(parent, ((731, 48_000, 128),), 256018),
        "strong_positive": _test_signal(parent, ((731, 720_000, 600),), 256018),
        "strong_negative": _test_signal(parent, ((731, -720_000, 600),), 256018),
    }


def run_detector(window, policy, grids, refiners, row, *, archived_probe_sha256=None):
    installed = capture_exact_trial.stages.detector(window, policy, None)
    if archived_probe_sha256 and _digest(encoded(installed["probes"])) != archived_probe_sha256:
        raise ValueError("installed detector did not reproduce the authenticated archived probes")
    outputs, timings, repeated_equal = {}, [], True
    for repeat in range(REPEATS):
        order = tuple(grids) if (repeat + row) % 2 == 0 else tuple(reversed(grids))
        pair = {}
        for name in order:
            grid = grids[name]
            grid.calls.clear()
            with capture_exact_trial.refiners(refiners):
                response = capture_exact_trial.stages.detector(window, policy, grid)
            candidate = {k: response[k] for k in ("public", "probes", "attempts")}
            repeated_equal &= outputs.setdefault(name, candidate) == candidate
            pair[name] = {k: v for k, v in response.items() if k not in candidate}
        timings.append(dict(order=order, detectors=pair))
    shifted, prepared = (outputs[k] for k in ("shifted", "prepared"))
    installed_comparisons = [
        compare_probes(p, q, window.sample_rate_hz)
        for p, q in zip(installed["probes"], shifted["probes"], strict=True)
    ]
    return dict(
        repeated_equal=repeated_equal,
        equal_public=shifted["public"] == prepared["public"],
        equal_coarse_path=shifted["attempts"] == prepared["attempts"],
        equal_installed=shifted["public"] == installed["public"],
        prepared_equal_installed=prepared["public"] == installed["public"],
        installed_positive_matching=installed_comparisons,
        timings=timings,
        outputs=dict(installed=installed, **outputs),
    )


def read_lock(work, ident, stage):
    if len(os.sched_getaffinity(0)) != 1 or not os.sched_getaffinity(0) <= {2, 3}:
        raise ValueError("pin exactly one CPU from 2 or 3")
    if any(os.environ.get(key) != "1" for key in THREAD_ENV):
        raise ValueError("set each numerical runtime to one thread")
    _, policy, provenance = capture_detector_lineage.source_lineage(_load_case(ident))
    lock = json.loads((work / "fixed-roster.json").read_bytes())
    case = lock[ident]
    start = 0 if stage == "development" else 1
    stop = 1 if stage == "development" else len(case)
    rows = []
    for expected in case[start:stop]:
        witness = expected["witness"]
        raw = (work / f"{ident}-{witness['visit']}.ci16").read_bytes()
        if _digest(raw) != witness["iq_sha256"]:
            raise ValueError("local copy differs from the fixed IQ and capture lock")
        samples = np.frombuffer(raw, dtype="<i2").reshape(200_000, 2, 2)
        window = IQWindow(
            witness["sequence"],
            samples,
            (0, 1),
            expected["rate"],
            expected["acquisition"],
            expected["target_id"],
            witness["target"],
            witness["iq_sha256"],
        )
        archived = {"archived_probe_sha256": expected["archived_probe_sha256"]}
        rows.append((window, witness | archived))
    return policy, provenance, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "freeze", "development", "held"))
    parser.add_argument("work", type=Path)
    parser.add_argument("case", choices=tuple(CASES), nargs="?")
    parser.add_argument("--fft-size", type=int, choices=FFT_SIZES)
    cli = parser.parse_args()
    if cli.action == "build":
        cli.work.mkdir(parents=True, exist_ok=True)
        prepared = cli.work / "prepared"
        prepared.mkdir()
        original_kernel.build(prepared)
        for length in FFT_SIZES:
            coarse_basis_shift.build(cli.work / f"shift-{length}", length)
        coarse_basis.compile_projection(cli.work / "projection.so")
        conditioned_cfo_bank.compile_bank(cli.work / "conditioned.so")
        refine_bank.compile_bank(cli.work / "fused.so")
        return
    if cli.action == "freeze":
        freeze_inputs(cli.work)
        return
    policy, provenance, physical = read_lock(cli.work, cli.case, cli.action)
    runs = []
    if cli.action == "development":
        for window, witness in physical:
            measured = microbenchmark(window, policy, cli.work)
            runs.append(dict(witness=witness, measurements=measured))
    else:
        grids = {
            "prepared": original_kernel.PersistentGrid(cli.work / "prepared/original_kernel.so"),
            "shifted": shared_grid(cli.work, cli.fft_size),
        }
        refiners = {
            key: cli.work / name for key, name in (("cfo", "conditioned.so"), ("fused", "fused.so"))
        }
        try:
            for index, (window, witness) in enumerate(physical):
                result = run_detector(
                    window,
                    policy,
                    grids,
                    refiners,
                    index,
                    archived_probe_sha256=witness["archived_probe_sha256"],
                )
                print(cli.case, witness["visit"], result["equal_public"], flush=True)
                runs.append(dict(witness=witness, **result))
            if cli.case != "DS29-0519":
                for label, window in controls(physical[0][0]).items():
                    result = run_detector(window, policy, grids, refiners, len(runs))
                    print(cli.case, label, result["equal_public"], flush=True)
                    runs.append(dict(control=label, iq_sha256=window.iq_sha256, **result))
        finally:
            for grid in grids.values():
                grid.clear_cache()
    sources = [Path(__file__), Path(coarse_basis.__file__), coarse_basis.SOURCE]
    out = dict(
        case=cli.case,
        action=cli.action,
        cpu=sorted(os.sched_getaffinity(0)),
        provenance=provenance,
        fft_size=cli.fft_size,
        runs=runs,
        sources={str(p): _sha(p) for p in sources},
    )
    write(cli.work / f"{cli.case}-{cli.action}.json.gz", gzip.compress(encoded(out), mtime=0))


if __name__ == "__main__":
    main()
