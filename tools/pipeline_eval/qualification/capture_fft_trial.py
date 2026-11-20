"""Paired fresh saved-IQ detector runs with only the deployed folded grid replaced."""

import argparse
import gzip
import importlib
import json
from collections import defaultdict
from contextlib import ExitStack
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from ..__main__ import encoded, local_output, save_json, write
from ..variants import capture_fft
from ..variants.iq_stream import load_windows
from . import capture_detector_lineage as lineage
from . import capture_release, thinned_capture_eval
from .capture_detector_replay import scan_capture_window
from .full_v5_check import BULK, _load_case, _sha

REPORT = lineage.SCREEN / "acquisition-support/capture-fft"
CASES = {
    "DS26-0036": {2: (1, 4), 8: (2, 5)},
    "DS29-0174": {3: (1, 4), 10: (2, 5)},
}
RUNS = 2
FIELDS = (
    "acquisition_inclusive",
    "coarse_inclusive",
    "peak_selection",
    "fine_scores",
    "conditioned_scores",
    "integer_glrt",
    "fractional_glrt",
)


def sealed(lock):
    for filename, want in lock["source_files"].items():
        if _sha(Path(filename)) != want:
            raise ValueError(f"source changed after detector sealing: {filename}")


def source_plan(work):
    work.mkdir()
    lib = capture_fft.build(work / "capture_fft.so")
    sources = (
        Path(__file__),
        Path(capture_fft.__file__),
        capture_fft.SOURCE,
        capture_fft.SOURCE.with_name("folded_bank.c"),
        Path(thinned_capture_eval.__file__),
        Path(lineage.__file__),
        REPORT / "PROTOCOL.md",
        lib,
        Path("/usr/lib/x86_64-linux-gnu/libfftw3.so.3"),
    )
    entries = {}
    for ident, roster in CASES.items():
        case = _load_case(ident)
        receipt = capture_release.read_capture(case)
        producer = capture_release.producer(case, receipt)
        declarations = {}
        for segment, sequences in roster.items():
            location = case["recording"]["segments"][segment]
            windows = load_windows(
                dict(
                    recording_path=str(BULK / location["path"]),
                    recording_sha256="sha256:" + location["sha256"],
                ),
                sequences,
            )
            for window in windows:
                declarations[f"{segment}-{window.sequence}"] = dict(
                    segment=segment,
                    sequence=window.sequence,
                    visit=window.acquisition["global_visit"],
                    iq_sha256=window.iq_sha256,
                    manifest_sha256=location["sha256"],
                )
        entries[ident] = dict(
            root=str(producer.root),
            edge=receipt["edge"],
            run_id=case["run_id"],
            input_manifest_sha256=producer.input_manifest_sha256,
            screen_source={
                str(path): _sha(path)
                for pattern in (
                    "coarse_screen.py",
                    "_screen*.py",
                    "_screen_native/*.so",
                    "_sparse_native/*.so",
                )
                for path in (producer.root / "leo/analysis/starlink").glob(pattern)
            },
            roster=declarations,
        )
    return dict(source_files={str(p): _sha(p) for p in sources}, cases=entries, library=str(lib))


def resident():
    columns = [
        line.split()[1]
        for line in Path("/proc/self/status").read_text().splitlines()
        if line.startswith(("VmRSS:", "VmHWM:"))
    ]
    return dict(zip(("rss_kib", "hwm_kib"), map(int, columns), strict=True))


def detector(window, policy, fft):
    from leo.analysis.starlink import acquisition
    from leo.scanner import fast_scan_detector

    screen_name = "leo.analysis.starlink.coarse_screen"
    screen = importlib.import_module(screen_name) if importlib.util.find_spec(screen_name) else None
    times = defaultdict(int)
    attempts = []

    def timed(fn, key):
        def wrapper(*args, **kwargs):
            start = process_time_ns()
            result = fn(*args, **kwargs)
            times[key] += process_time_ns() - start
            return result

        return wrapper

    original_acquire = fast_scan_detector.acquire_symbolwise

    def acquisition_call(samples, rate, calibration, *, edge, config):
        start = process_time_ns()
        result = original_acquire(samples, rate, calibration, edge=edge, config=config)
        elapsed = process_time_ns() - start
        times["acquisition_inclusive"] += elapsed
        attempts.append(
            dict(
                receiver_id=calibration.receiver_id,
                anchor_symbols=list(config.anchor_symbols),
                edge=edge,
                acquired=[
                    dict(
                        rank=c.rank,
                        coarse_epoch=c.coarse_epoch_sample,
                        coarse_cfo_hz=c.coarse_residual_cfo_hz,
                        refined_epoch=c.refined_epoch_sample,
                        cfo_hz=c.absolute_cfo_hz,
                    )
                    for c in result.candidates
                ],
            )
        )
        return result

    initial_rss = resident()
    saved_calls = len(fft.calls) if fft is not None else 0
    wall, cpu = perf_counter_ns(), process_time_ns()
    with ExitStack() as routed:
        if fft is not None:
            routed.enter_context(fft.route(acquisition, screen))
        coarse_target = acquisition if screen is None else screen
        coarse_port = "_folded_anchor_score_grid" if screen is None else "acquire"
        routed.enter_context(
            patch.object(
                coarse_target,
                coarse_port,
                timed(getattr(coarse_target, coarse_port), "coarse_inclusive"),
            )
        )
        for target, name, key in (
            (acquisition, "_retain_score_map_peaks", "peak_selection"),
            (acquisition, "_normalized_frame_scores", "fine_scores"),
            (acquisition, "_conditioned_frame_scores", "conditioned_scores"),
            (fast_scan_detector, "conditioned_glrt64_scores", "integer_glrt"),
            (fast_scan_detector, "refine_glrt64_epochs", "fractional_glrt"),
        ):
            routed.enter_context(patch.object(target, name, timed(getattr(target, name), key)))
        routed.enter_context(
            patch.object(fast_scan_detector, "acquire_symbolwise", acquisition_call)
        )
        result, probes = scan_capture_window(window, window.receiver_ids, policy)
    wall, cpu = perf_counter_ns() - wall, process_time_ns() - cpu
    after = resident()
    scope = fft.calls[saved_calls:] if fft is not None else []
    if fft is not None and times["coarse_inclusive"] and not any(c["applied"] for c in scope):
        raise ValueError("nonempty candidate worker did not execute the FFT grid")
    return dict(
        status=result.status,
        public=result.model_dump(mode="json"),
        probes=probes,
        attempts=attempts,
        cpu_ns=cpu,
        wall_ns=wall,
        rss_before=initial_rss,
        rss_after=after,
        stages_cpu_ns={key: times[key] for key in FIELDS},
        grid_receipts=scope,
    )


def pair(window, policy, fft, repetitions, index):
    rows = []
    for turn in range(repetitions):
        labels = ("installed", "fft")
        if (turn + index) % 2:
            labels = labels[::-1]
        matched = {
            label: detector(window, policy, fft if label == "fft" else None) for label in labels
        }
        rows.append(matched)
    return rows


def run(ident, lock):
    case = _load_case(ident)
    frozen = lock["cases"][ident]
    _, policy, producer = lineage.source_lineage(case)
    require = producer["capture"]
    if any(require[k] != frozen[k] for k in ("run_id", "root", "input_manifest_sha256")):
        raise ValueError("the installed capture runtime differs from its preflight authority")
    if any(_sha(Path(p)) != h for p, h in frozen["screen_source"].items()):
        raise ValueError("the installed screen source has changed")
    started = process_time_ns()
    fft = capture_fft.FullGrid(Path(lock["library"]))
    setup = process_time_ns() - started
    observed, probes = [], []
    for index, expected in enumerate(frozen["roster"].values()):
        location = case["recording"]["segments"][expected["segment"]]
        (window,) = load_windows(
            dict(
                recording_path=str(BULK / location["path"]),
                recording_sha256="sha256:" + location["sha256"],
            ),
            [expected["sequence"]],
        )
        if (
            window.iq_sha256 != expected["iq_sha256"]
            or window.acquisition["global_visit"] != expected["visit"]
            or location["sha256"] != expected["manifest_sha256"]
        ):
            raise ValueError("fresh raw input differs from the sealed archive")
        rows = pair(window, policy, fft, RUNS, index)
        observed.append(dict(expected, rows=rows))
        probes.append(window)
        print(ident, expected["visit"], rows[0]["fft"]["status"], flush=True)
    valid = next(
        w
        for w, r in zip(probes, observed, strict=True)
        if (r["rows"][0]["installed"]["status"] == "processed")
    )
    controls = {}
    for index, (name, window) in enumerate(thinned_capture_eval.controls(valid).items()):
        controls[name] = dict(
            iq_sha256=window.iq_sha256,
            rows=pair(window, policy, fft, 1, index),
        )
        print(ident, name, controls[name]["rows"][0]["fft"]["status"], flush=True)
    return dict(
        id=ident,
        producer=producer,
        setup_cpu_ns=setup,
        process_memory=resident(),
        captures=observed,
        controls=controls,
        candidate_source_sha256=_sha(Path(lock["library"])),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", *CASES))
    parser.add_argument("work", type=Path)
    args = parser.parse_args()
    target = REPORT / "source-lock.json"
    work = local_output(args.work)
    if args.action == "freeze":
        if target.exists():
            raise FileExistsError(target)
        save_json(target, source_plan(work))
    else:
        lock = json.loads(target.read_bytes())
        sealed(lock)
        result = run(args.action, lock)
        write(REPORT / f"{args.action}.json.gz", gzip.compress(encoded(result), mtime=0))
