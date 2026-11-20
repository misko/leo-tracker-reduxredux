"""Compare the selected complete overlap-save bank against the installed detector."""

import argparse
import gzip
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np

from .. import original_receiver
from ..__main__ import encoded, save_json, write
from ..variants import fine_batch, original_kernel, prepared_hotpath_peaks
from . import capture_exact_trial as exact
from . import fft_length_sweep as sweep
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import _sha, compare_probes
from .original_kernel_trial import rank_gap
from .pilot_kernel_eval import _digest
from .retry_reuse_eval import window_from_lock

MODES = ("prepared", "selected")


def base_libraries():
    files = {k: original_receiver.KERNELS[k] for k in ("cfo", "fused")}
    files["fine"] = original_receiver.BATCH_LIBRARY_CACHE, original_receiver.BATCH_LIBRARY_SHA
    if any(_sha(path) != sha for path, sha in files.values()):
        raise ValueError("qualified downstream detector library changed")
    return {k: p for k, (p, _) in files.items()}


def qualification_lock(work):
    basis = work / "selection-lock.json"
    inputs = work / "input-lock.json"
    selected = json.loads(basis.read_bytes())
    if selected["input_lock_sha256"] != _sha(inputs):
        raise ValueError("development chose a length on another input panel")
    for case, sha in selected["development"].items():
        if _sha(work / case) != sha:
            raise ValueError("development measurements changed since selection")
    libs = base_libraries()
    length = selected["selected"]
    candidate = selected.get("selected_build")
    if candidate is None:
        if length == 512:
            alternatives = {k: r for k, r in selected["paired_native_ratio"].items() if k != "512"}
            length = int(min(alternatives, key=alternatives.get))
        candidate = json.loads(inputs.read_bytes())["variants"][str(length)]
    if candidate["sha256"] != _sha(Path(candidate["path"])):
        raise ValueError("the selected coarse library changed")
    programs = (
        Path(__file__),
        Path(exact.__file__),
        Path(exact.stages.__file__),
        Path(fine_batch.__file__),
        fine_batch.SOURCE,
        Path(prepared_hotpath_peaks.__file__),
    )
    return dict(
        length=length,
        planner=selected.get("planner", "estimate"),
        candidate=candidate,
        roster_sha256=_sha(inputs),
        selection_sha256=_sha(basis),
        libraries={str(p): _sha(p) for p in libs.values()},
        sources={str(p): _sha(p) for p in programs},
    )


def controls(window):
    zero = np.zeros_like(window.samples)
    return {
        "empty": replace(window, samples=zero, iq_sha256=_digest(zero.tobytes())),
        "positive": _test_signal(window, ((731, 720_000, 600),), 720121),
        "negative": _test_signal(window, ((731, -720_000, 600),), 720121),
        "near_equal": _test_signal(window, ((731, -48_000, 600), (7231, 48_000, 601)), 720121),
    }


def core(window, policy, grid):
    grid.calls.clear()
    result = exact.stages.detector(window, policy, grid)
    if not result["grid_receipts"] or not all(c["applied"] for c in result["grid_receipts"]):
        raise ValueError("held producer did not run the complete native bank")
    return result


def audited(window, policy, grid, acquisition):
    pending = []
    original = grid.score_grid

    def score(*args):
        rows = original(*args)
        pending.append(dict(rows=np.asarray(rows), retention=None))
        return rows

    def retain(residuals, rows, count, samples, hz, epochs):
        peaks = prepared_hotpath_peaks.retained_peaks(residuals, rows, count, samples, hz, epochs)
        pending[-1]["retention"] = dict(
            keys=[(r[1], r[2]) for r in peaks],
            gaps=rank_gap(np.asarray(rows), np.asarray(residuals), count, samples, hz),
        )
        return peaks

    with (
        patch.object(grid, "score_grid", score),
        patch.object(acquisition, "_retain_score_map_peaks", retain),
    ):
        result = core(window, policy, grid)
    if any(row["retention"] is None for row in pending):
        raise ValueError("coarse bank returned a grid without a matched selector call")
    return result, pending


def map_compare(left, right):
    result = []
    for a, b in zip(left, right, strict=True):
        differences = abs(a["rows"] - b["rows"])
        error = float(differences.max(initial=0))
        gaps = [x for x in a["retention"]["gaps"] if x is not None]
        result.append(
            dict(
                cells=differences.size,
                max_error=error,
                smallest_prepared_rank_gap=min(gaps, default=None),
                ambiguous_steps=sum(g <= 2 * error for g in gaps),
                same_ranked_keys=a["retention"]["keys"] == b["retention"]["keys"],
                prepared=a["retention"],
                selected=b["retention"],
            )
        )
    return result


def one_visit(window, policy, grids, libraries, index, *, archive=None):
    from leo.analysis.starlink import acquisition

    installed = exact.stages.detector(window, policy, None)
    if archive and _digest(encoded(installed["probes"])) != archive:
        raise ValueError("the installed detector does not match the authenticated capture")
    fine = fine_batch.FineBatch(libraries["fine"], acquisition)
    if not fine.compatible:
        raise ValueError("the qualified batched fine runtime sentinel failed")
    timings, payloads = [], {}
    with (
        exact.refiners(libraries),
        fine.route(),
        patch.object(acquisition, "_retain_score_map_peaks", prepared_hotpath_peaks.retained_peaks),
    ):
        for mode in MODES:
            core(window, policy, grids[mode])
        for repeat in range(sweep.REPEATS if archive else 2):
            order = MODES if (repeat + index) % 2 == 0 else MODES[::-1]
            pair = {}
            for mode in order:
                before = fine.fallbacks, fine.calls
                run = core(window, policy, grids[mode])
                replay = {k: run.pop(k) for k in ("public", "attempts", "probes")}
                if payloads.setdefault(mode, replay) != replay:
                    raise ValueError("timed detector payload changed between repeats")
                pair[mode] = dict(
                    run,
                    fine_calls=fine.calls - before[1],
                    fine_fallbacks=fine.fallbacks - before[0],
                )
            timings.append(dict(order=order, measurements=pair))
        base, left = audited(window, policy, grids["prepared"], acquisition)
        chosen, right = audited(window, policy, grids["selected"], acquisition)
    maps = map_compare(left, right) if len(left) == len(right) else []
    matching = [
        compare_probes(a, b, window.sample_rate_hz)
        for a, b in zip(
            installed["probes"],
            chosen["probes"],
            strict=True,
        )
    ]
    return dict(
        input_sha256=window.iq_sha256,
        archive_sha256=archive,
        timings=timings,
        maps=maps,
        same_grid_count=len(left) == len(right),
        same_prepared=base["public"] == chosen["public"],
        same_installed=installed["public"] == chosen["public"],
        same_attempts=base["attempts"] == chosen["attempts"],
        same_installed_attempts=installed["attempts"] == chosen["attempts"],
        matching=matching,
        payloads=dict(installed=installed, **payloads),
    )


def replay(work, ident):
    lock, case, policy, producer = sweep.checked(work, ident)
    declared = json.loads((work / "held-lock.json").read_bytes())
    if declared != qualification_lock(work):
        raise ValueError("held replay requires the predeclared selection and sources")
    grids = {
        "prepared": original_kernel.PersistentGrid(lock["variants"]["512"]["path"]),
        "selected": original_kernel.PersistentGrid(declared["candidate"]["path"]),
    }
    libraries = base_libraries()
    rows = []
    try:
        windows = [r for r in case["rows"] if r["split"] == "held"]
        for index, record in enumerate(windows):
            window = window_from_lock(work, ident, record)
            result = one_visit(
                window, policy, grids, libraries, index, archive=record["probes_sha256"]
            )
            rows.append(dict(visit=record["visit"], **result))
            print(
                ident,
                record["visit"],
                result["same_prepared"],
                result["same_installed"],
                flush=True,
            )
        if ident in ("DS26-0237", "DS29-0082"):
            parent = window_from_lock(work, ident, windows[0])
            for index, (name, window) in enumerate(controls(parent).items()):
                result = one_visit(window, policy, grids, libraries, index)
                rows.append(dict(control=name, **result))
                print(ident, name, result["same_prepared"], result["same_installed"], flush=True)
    finally:
        for grid in grids.values():
            grid.clear_cache()
    write(
        work / f"{ident}-held.json.gz",
        gzip.compress(
            encoded(
                dict(
                    ident=ident,
                    cpu=case["cpu"],
                    producer=producer,
                    length=declared["length"],
                    rows=rows,
                    held_lock_sha256=_sha(work / "held-lock.json"),
                )
            ),
            mtime=0,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("case", choices=tuple(sweep.HELD), nargs="?")
    args = parser.parse_args()
    if args.case is None:
        save_json(args.work / "held-lock.json", qualification_lock(args.work))
    else:
        replay(args.work, args.case)
