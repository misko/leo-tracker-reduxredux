"""Profile the prepared capture path independently of performance measurements."""

import argparse
import cProfile
import pstats
from contextlib import ExitStack
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

import numpy as np

from ..__main__ import save_json
from ..variants.original_kernel import PersistentGrid
from ..variants.prepared_hotpath import FineWorkspace
from . import capture_exact_trial as exact
from . import original_kernel_trial as original
from .capture_detector_replay import scan_capture_window
from .capture_runtime import checked, read
from .full_v5_check import _load_case
from .prepared_hotpath_selector import MODES as SELECTORS
from .prepared_hotpath_selector import arm as selector_arm
from .prepared_hotpath_trial import MODES, arm


def libraries():
    lock = read(original.REPORT / "source-lock.json")
    return {
        name: checked(Path(item["path"]), item["sha256"]) for name, item in lock["libs"].items()
    }


def profile(name, visit, output, mode):
    from leo.analysis.starlink import acquisition, fast_scan_scores
    from leo.scanner import fast_scan_analysis, fast_scan_detector

    from . import capture_detector_replay

    case = _load_case(name)
    _, policy, _ = exact.lineage.source_lineage(case)
    _, _, window = original.decode(case, visit)
    libs = libraries()
    grid = PersistentGrid(libs["prepared"])
    fine = FineWorkspace(acquisition)
    elapsed = {}
    profiler = cProfile.Profile()
    original_analyze = fast_scan_analysis.analyze_window
    route = selector_arm if mode in SELECTORS else arm

    def wrap(fn, name):
        def timed(*args, **kwargs):
            started = process_time_ns()
            try:
                return fn(*args, **kwargs)
            finally:
                count, ns = elapsed.get(name, (0, 0))
                elapsed[name] = (count + 1, ns + process_time_ns() - started)

        return timed

    def analyze(win, receiver_ids, predictor, policy):
        return original_analyze(
            win,
            receiver_ids,
            predictor,
            policy,
            detector=wrap(fast_scan_analysis.production_glrt, "production_glrt"),
        )

    try:
        with (
            exact.refiners(libs),
            grid.route(acquisition, exact.starts.screen_module()),
            route(mode, fine),
        ):
            scan_capture_window(window, window.receiver_ids, policy)
            grid.calls.clear()
            with ExitStack() as scope:
                for target, port in (
                    (acquisition, "_folded_anchor_score_grid"),
                    (acquisition, "_retain_score_map_peaks"),
                    (acquisition, "_normalized_frame_scores"),
                    (acquisition, "_normalized_frame_scores_fft"),
                    (acquisition, "_normalized_frame_scores_direct"),
                    (acquisition, "_conditioned_frame_scores"),
                    (acquisition, "normalized_frame_score"),
                    (acquisition, "_pilot_sample_indexes"),
                    (acquisition, "_power_prefix"),
                    (fast_scan_detector, "acquire_symbolwise"),
                    (fast_scan_analysis, "analyze_glrt64_dwell"),
                    (fast_scan_scores, "conditioned_glrt64_score"),
                    (fast_scan_scores, "conditioned_glrt64_scores"),
                    (fast_scan_detector, "conditioned_glrt64_scores"),
                    (fast_scan_detector, "refine_glrt64_epochs"),
                    (capture_detector_replay, "_probe"),
                    (np.fft, "fft"),
                ):
                    label = f"{target.__name__.rsplit('.', 1)[-1]}.{port}"
                    scope.enter_context(
                        patch.object(target, port, wrap(getattr(target, port), label))
                    )
                scope.enter_context(
                    patch.object(
                        fast_scan_analysis, "analyze_window", wrap(analyze, "analyze_window")
                    )
                )
                result, probes = profiler.runcall(
                    scan_capture_window, window, window.receiver_ids, policy
                )
        if result.status != "processed" or len(probes) != 2 or not grid.calls:
            raise ValueError("profile missed dual prepared work")
        stats = pstats.Stats(profiler).sort_stats("tottime")
        save_json(
            output,
            dict(
                case=name,
                mode=mode,
                visit=visit,
                producer=acquisition.__file__,
                iq_sha256=window.iq_sha256,
                scopes={label: dict(count=n, cpu_ns=ns) for label, (n, ns) in elapsed.items()},
                grid=grid.calls,
                functions=[
                    dict(
                        file=file,
                        line=line,
                        function=func,
                        count=stats.stats[key][1],
                        self_s=stats.stats[key][2],
                        inclusive_s=stats.stats[key][3],
                    )
                    for key in stats.fcn_list[:45]
                    for file, line, func in (key,)
                ],
            ),
        )
    finally:
        grid.clear_cache()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=tuple(original.CASES))
    parser.add_argument("visit", type=int)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--mode", default="prepared", choices=tuple(dict.fromkeys((*MODES, *SELECTORS)))
    )
    args = parser.parse_args()
    profile(args.case, args.visit, args.output, args.mode)
