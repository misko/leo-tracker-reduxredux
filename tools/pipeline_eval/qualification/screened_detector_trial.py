"""Measure the untouched capture detector and exact fractional row reuse."""

import argparse
import gzip
import importlib.util
import json
from collections import defaultdict
from contextlib import ExitStack
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from ..__main__ import encoded, local_output, save_json, write
from ..variants import screened_detector
from ..variants.iq_stream import load_windows
from . import capture_detector_lineage as lineage
from . import capture_fft_trial, capture_release, thinned_capture_eval
from .full_v5_check import BULK, _load_case, _sha

REPORT = lineage.SCREEN / "receiver-core/screened-detector"
ROSTER = {
    "DS26-0036": {4: (1, 4), 9: (2, 5)},
    "DS29-0174": {5: (1, 4), 11: (2, 5)},
}
MODES = ("installed", "reuse")
REPETITIONS = 3


def windows(ident):
    case = _load_case(ident)
    for segment, sequences in ROSTER[ident].items():
        location = case["recording"]["segments"][segment]
        for window in load_windows(
            dict(
                recording_path=str(BULK / location["path"]),
                recording_sha256="sha256:" + location["sha256"],
            ),
            sequences,
        ):
            yield (
                window,
                dict(
                    segment=segment,
                    sequence=window.sequence,
                    visit=window.acquisition["global_visit"],
                    iq_sha256=window.iq_sha256,
                    manifest_sha256=location["sha256"],
                ),
            )


def freeze():
    receivers = {}
    for ident in ROSTER:
        case = _load_case(ident)
        capture = capture_release.read_capture(case)
        producer = capture_release.producer(case, capture)
        starlink = producer.root / "leo/analysis/starlink"
        source = [
            *starlink.glob("fast_scan_*.py"),
            *starlink.glob("*screen*.py"),
            *starlink.glob("_screen_native/*.so"),
            *starlink.glob("_sparse_native/*.so"),
            *starlink.glob("_native_acquisition*.so"),
            starlink / "acquisition.py",
            starlink / "templates.py",
            producer.root / "leo/scanner/fast_scan_analysis.py",
            producer.root / "leo/scanner/fast_scan_detector.py",
        ]
        receivers[ident] = dict(
            root=str(producer.root),
            manifest_sha256=producer.input_manifest_sha256,
            edge=capture["edge"],
            roster=[receipt for _, receipt in windows(ident)],
            source_sha256={str(path): _sha(path) for path in sorted(source)},
        )
    helpers = (
        screened_detector,
        capture_fft_trial,
        capture_release,
        lineage,
        thinned_capture_eval,
    )
    return dict(
        cases=receivers,
        source_files={
            str(path): _sha(path)
            for path in (Path(__file__), *(Path(mod.__file__) for mod in helpers))
        },
        repetitions=REPETITIONS,
    )


def detector(window, policy, mode):
    from leo.analysis.starlink import fast_scan_scores as scores

    clocks = defaultdict(int)
    counts = defaultdict(int)
    screen_receipts = []

    def timed(fn, key):
        def wrapper(*args, **kwargs):
            started = process_time_ns()
            result = fn(*args, **kwargs)
            clocks[key] += process_time_ns() - started
            counts[key] += 1
            return result

        return wrapper

    name = "leo.analysis.starlink.coarse_screen"
    screen = importlib.import_module(name) if importlib.util.find_spec(name) is not None else None
    setup_cpu, setup_wall = process_time_ns(), perf_counter_ns()
    with ExitStack() as stack:
        sampler = stack.enter_context(screened_detector.route(scores)) if mode == "reuse" else None
        setup_cpu, setup_wall = process_time_ns() - setup_cpu, perf_counter_ns() - setup_wall
        ports = [
            (scores, "fractional_take", "lanczos"),
            (scores, "conditioned_glrt64_scores", "five_cell_batch"),
            (scores, "conditioned_glrt64_score", "continuous_conditional"),
        ]
        if screen is not None:
            original = screen.acquire

            def observed(*args, **kwargs):
                return original(*args, **kwargs, observer=screen_receipts.append)

            stack.enter_context(patch.object(screen, "acquire", observed))
            ports.extend(
                (
                    (screen, "screen_grid", "screen_fp32_grid"),
                    (screen, "select", "screen_selection_and_exact"),
                    (screen.ExactColumns, "__call__", "screen_exact_columns"),
                )
            )
        for target, attr, key in ports:
            stack.enter_context(patch.object(target, attr, timed(getattr(target, attr), key)))
        result = capture_fft_trial.detector(window, policy, None)

    result.update(
        setup_cpu_ns=setup_cpu,
        setup_wall_ns=setup_wall,
        refinement_cpu_ns=dict(clocks),
        refinement_calls=dict(counts),
        screened_calls=screen_receipts,
        work=sampler.receipts() if sampler is not None else None,
    )
    return result


def paired(window, policy, repetitions, index):
    rows = []
    for turn in range(repetitions):
        labels = MODES if (turn + index) % 2 == 0 else MODES[::-1]
        rows.append({mode: detector(window, policy, mode) for mode in labels})
    return rows


def run(ident, lock, cold=None):
    capture_fft_trial.sealed(lock)
    expected = lock["cases"][ident]
    for filename, digest in expected["source_sha256"].items():
        if _sha(Path(filename)) != digest:
            raise ValueError(f"capture runtime changed: {filename}")
    _, policy, producer = lineage.source_lineage(_load_case(ident))
    binding = producer["capture"]
    if (
        binding["root"] != expected["root"]
        or binding["input_manifest_sha256"] != expected["manifest_sha256"]
    ):
        raise ValueError("worker is not the sealed capture-era producer")

    inputs = list(windows(ident))
    if [r for _, r in inputs] != expected["roster"]:
        raise ValueError("sealed saved-IQ binding changed")
    if cold is not None:
        window, receipt = inputs[0]
        return dict(producer=producer, capture=receipt, row=detector(window, policy, cold))

    # One untimed full call warms process-level template, memo and FFT caches
    # equally. Reuse is visit-scoped, so no input-dependent result is retained.
    detector(inputs[0][0], policy, "installed")
    captures = []
    for i, (window, receipt) in enumerate(inputs):
        matches = paired(window, policy, lock["repetitions"], i)
        captures.append(dict(receipt, pairs=matches))
        print(ident, receipt["visit"], matches[0]["installed"]["status"], flush=True)
    controls = {
        label: dict(iq_sha256=window.iq_sha256, pairs=paired(window, policy, 1, i))
        for i, (label, window) in enumerate(thinned_capture_eval.controls(inputs[0][0]).items())
    }
    return dict(producer=producer, captures=captures, controls=controls)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=("freeze", *ROSTER))
    parser.add_argument("work", type=Path)
    parser.add_argument("--cold", choices=MODES)
    args = parser.parse_args()
    work = local_output(args.work)
    work.mkdir(parents=True, exist_ok=True)
    lock_path = work / "source-lock.json"
    if args.case == "freeze":
        if lock_path.exists():
            raise FileExistsError(lock_path)
        save_json(lock_path, freeze())
    else:
        result = run(args.case, json.loads(lock_path.read_bytes()), args.cold)
        tag = f"-cold-{args.cold}" if args.cold else ""
        write(work / f"{args.case}{tag}.json.gz", gzip.compress(encoded(result), mtime=0))
