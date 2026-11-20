"""Time same-visit shared-anchor reuse on fixed native capture detector cases."""

import argparse
import gzip
import json
import os
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ..__main__ import THREAD_ENV, encoded, save_json, write
from ..variants import conditioned_cfo_bank, original_kernel, refine_bank, retry_reuse
from ..variants.iq_stream import IQWindow
from ..variants.selective_capture import visit_pairs
from . import capture_detector_lineage, capture_exact_trial
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import _load_case, _sha
from .original_kernel_trial import decode
from .pilot_kernel_eval import _digest

ROSTER = {"DS26-0237": (53, 43), "DS29-0082": (13, 43), "DS29-0519": (155, 43)}
REPEATS = 5


def setup(work):
    work.mkdir()
    candidate, candidate_build = retry_reuse.build(work / "candidate")
    prepared = work / "prepared"
    prepared.mkdir()
    baseline, baseline_build = original_kernel.build(prepared)
    cfo, fused = work / "conditioned.so", work / "fused.so"
    conditioned_cfo_bank.compile_bank(cfo)
    refine_bank.compile_bank(fused)
    return dict(
        libraries={str(x.relative_to(work)): _sha(x) for x in (candidate, baseline, cfo, fused)},
        commands=dict(baseline=baseline_build, candidate=candidate_build),
    )


def freeze(work):
    build = setup(work)
    sources = [Path(__file__), Path(retry_reuse.__file__), original_kernel.HEADER]
    cases = {}
    for ident, numbers in ROSTER.items():
        case = _load_case(ident)
        path, expected = capture_detector_lineage.locked_native(case, "capture")
        raw = path.read_bytes()
        if _digest(raw) != "sha256:" + expected.removeprefix("sha256:"):
            raise ValueError("archived native probe digest differs from the original inventory")
        probes = dict(visit_pairs(json.loads(raw)["source"]["probes"]))
        sealed = []
        for visit in numbers:
            segment, manifest, window = decode(case, visit)
            clock = window.acquisition["sample_start"]
            if any(row["valid_start_counter"] != clock for row in probes[visit]):
                raise ValueError("archive and local physical IQ counter differ")
            payload = window.samples.tobytes()
            if _digest(payload) != window.iq_sha256:
                raise ValueError("physical IQ bytes differ from their index digest")
            write(work / f"{ident}-{visit}.ci16", payload)
            sealed.append(
                dict(
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
        cases[ident] = dict(archive_native_sha256=expected, windows=sealed)
    save_json(
        work / "source-lock.json",
        dict(
            build=build,
            files={str(p): _sha(p) for p in sources},
            cases=cases,
        ),
    )


def window_from_lock(work, ident, row):
    path = work / f"{ident}-{row['visit']}.ci16"
    raw = path.read_bytes()
    if _digest(raw) != row["iq_sha256"]:
        raise ValueError("local physical bytes differ from sealed capture")
    return IQWindow(
        row["sequence"],
        np.frombuffer(raw, dtype="<i2").reshape(200_000, 2, 2),
        tuple(row["receivers"]),
        row["rate"],
        row["acquisition"],
        row["target_id"],
        row["target"],
        row["iq_sha256"],
    )


def controls(window):
    empty = np.zeros_like(window.samples)
    signed = _test_signal(window, ((731, -720_000, 600),), 763457)
    return {
        "zero_tie": replace(window, samples=empty, iq_sha256=_digest(empty.tobytes())),
        "both_positive": signed,
    }


def run_window(window, policy, grids, refiners, row, *, compare_archive=None):
    def detector(grid):
        grid.calls.clear()
        with capture_exact_trial.refiners(refiners):
            return capture_exact_trial.stages.detector(window, policy, grid)

    def audit(grid):
        maps = []
        original = grid.score_grid

        def capture(*args):
            rows = original(*args)
            maps.append(np.asarray(rows))
            return rows

        with patch.object(grid, "score_grid", capture):
            result = detector(grid)
        return result, maps

    installed = capture_exact_trial.stages.detector(window, policy, None)
    if compare_archive and _digest(encoded(installed["probes"])) != compare_archive:
        raise ValueError("installed archive did not reproduce for physical visit")
    timed, saved = [], {}
    repeats = REPEATS if compare_archive else 2
    for repeat in range(repeats):
        order = tuple(grids) if (row + repeat) % 2 == 0 else tuple(reversed(grids))
        pair = {}
        for mode in order:
            values = detector(grids[mode])
            public = {k: values.pop(k) for k in ("public", "probes", "attempts")}
            if saved.setdefault(mode, public) != public:
                raise ValueError("candidate output changed across identical visits")
            pair[mode] = values
        timed.append(dict(order=order, measurements=pair))
    baseline, previous = audit(grids["prepared"])
    candidate, current = audit(grids["reuse"])
    if len(previous) != len(current):
        raise ValueError("shared cache changed retry invocation count")
    public_equal = baseline["public"] == candidate["public"]
    attempts_equal = baseline["attempts"] == candidate["attempts"]
    maps = [
        dict(
            mode=record["cache_mode"],
            anchor_count=record["anchors"],
            cells=first.size,
            scores_identical=bool(np.array_equal(first, second)),
            max_difference=float(np.max(abs(first - second))),
            prepared_inverse_calls=control["inverse_ffts"],
            reuse_inverse_calls=record["inverse_ffts"],
        )
        for first, second, control, record in zip(
            previous,
            current,
            baseline["grid_receipts"],
            candidate["grid_receipts"],
            strict=True,
        )
    ]
    return dict(
        iq_sha256=window.iq_sha256,
        archived_probes=compare_archive,
        public_equal=public_equal,
        attempts_equal=attempts_equal,
        installed_equal=candidate["public"] == installed["public"],
        public=saved,
        maps=maps,
        timing=timed,
    )


def replay(work, ident):
    affinity = os.sched_getaffinity(0)
    if len(affinity) != 1 or not affinity <= {2, 3}:
        raise ValueError("pin CPU 2 or 3")
    if any(os.environ.get(key) != "1" for key in THREAD_ENV):
        raise ValueError("use one numerical thread")
    lock = json.loads((work / "source-lock.json").read_bytes())
    files = lock["files"] | {str(work / p): h for p, h in lock["build"]["libraries"].items()}
    if any(_sha(Path(p)) != h for p, h in files.items()):
        raise ValueError("variant bytes differ from the source freeze")
    _, policy, producer = capture_detector_lineage.source_lineage(_load_case(ident))
    grids = {
        "prepared": original_kernel.PersistentGrid(work / "prepared/original_kernel.so"),
        "reuse": retry_reuse.Grid(work / "candidate/retry_reuse.so"),
    }
    refiners = {"cfo": work / "conditioned.so", "fused": work / "fused.so"}
    rows = []
    try:
        bound = lock["cases"][ident]["windows"]
        windows = [window_from_lock(work, ident, row) for row in bound]
        for index, (window, expected) in enumerate(zip(windows, bound, strict=True)):
            result = run_window(
                window,
                policy,
                grids,
                refiners,
                index,
                compare_archive=expected["probes_sha256"],
            )
            rows.append(dict(visit=expected["visit"], **result))
            print(ident, expected["visit"], result["public_equal"], result["maps"], flush=True)
        if ident in ("DS29-0082", "DS29-0519"):
            for label, window in controls(windows[0]).items():
                rows.append(dict(control=label, **run_window(window, policy, grids, refiners, 0)))
    finally:
        for grid in grids.values():
            grid.clear_cache()
    result = dict(case=ident, producer=producer, cpu=sorted(affinity), runs=rows)
    write(work / f"{ident}.json.gz", gzip.compress(encoded(result), mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("case", choices=tuple(ROSTER), nargs="?")
    args = parser.parse_args()
    if args.case is None:
        freeze(args.work)
    else:
        replay(args.work, args.case)
