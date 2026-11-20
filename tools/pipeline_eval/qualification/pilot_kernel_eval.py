"""Measure the tiled coarse pilot bank against the capture-era anchor fast path."""

import argparse
import cProfile
import gzip
import os
import pstats
import subprocess
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from unittest.mock import patch

from ..__main__ import THREAD_ENV, encoded, write
from ..variants import anchor_grid, anchor_receiver, pilot_kernel
from ..variants.iq_stream import load_windows
from .full_v5_check import (
    BULK,
    MARGIN_GATE,
    PRODUCERS,
    _bind_producer,
    _from_production,
    _load_case,
    _measure,
    _probe,
    _sha,
)

MODES = ("control", "tiled")
SEGMENTS = (5, 11)
SEQUENCES = (1, 3, 5, 7)
REPEATS = 3


def _windows(case, segment, sequences):
    locator = case["recording"]["segments"][segment]
    return load_windows(
        dict(
            recording_path=str(BULK / locator["path"]),
            recording_sha256="sha256:" + locator["sha256"],
        ),
        sequences,
    )


def alternating_order(window_index, repeat):
    return MODES if (window_index + repeat) % 2 == 0 else MODES[::-1]


def _payload(result):
    return encoded(result.model_dump(mode="json"))


def _digest(payload):
    return "sha256:" + sha256(payload).hexdigest()


def _compare_peaks(left, right):
    def keys(calls):
        return [[(e, f) for _, e, f in peaks] for peaks in calls]

    if keys(left) != keys(right):
        return False, None
    delta = max(
        (
            abs(x[0] - y[0])
            for a, b in zip(left, right, strict=True)
            for x, y in zip(a, b, strict=True)
        ),
        default=0.0,
    )
    return True, delta


def _profile(case, call):
    windows = _windows(case, 3, range(4))
    profile = cProfile.Profile()
    with profile:
        outputs = [call(window, "control")[0] for window in windows]
    stats = pstats.Stats(profile)
    return dict(
        segment=3,
        windows=[dict(visit=out.visit, status=out.status, edge=out.edge) for out in outputs],
        self_s=stats.total_tt,
        functions=[
            dict(
                function=function,
                file=Path(file).name,
                line=line,
                calls=count,
                self_s=self_s,
                total_s=total_s,
            )
            for (file, line, function), (_, count, self_s, total_s, _) in sorted(
                stats.stats.items(), key=lambda item: item[1][3], reverse=True
            )[:28]
        ],
    )


def _timed_window(window, call, index, segment):
    timing = []
    first_payload, first_output = None, None
    same_payload = True
    for repeat in range(REPEATS):
        order = alternating_order(index, repeat)
        pair = dict(order=order, timings={}, payload_sha256={})
        for mode in order:
            output, elapsed, _ = call(window, mode)
            document = _payload(output)
            if first_payload is None:
                first_payload, first_output = document, output
            same_payload &= document == first_payload
            pair["timings"][mode] = elapsed
            pair["payload_sha256"][mode] = _digest(document)
        timing.append(pair)

    control, _, control_peaks = call(window, "control", trace=True)
    tiled, _, tiled_peaks = call(window, "tiled", trace=True)
    same_payload &= first_payload == _payload(control) == _payload(tiled)
    equal_peaks, peak_max_delta = _compare_peaks(control_peaks, tiled_peaks)
    candidates = [c for receiver in first_output.receivers for c in receiver.candidates]

    def probes(output):
        return [
            _probe(window, receiver.receiver_id, map(_from_production, receiver.candidates))
            for receiver in output.receivers
        ]

    return dict(
        segment_index=segment,
        sequence=window.sequence,
        visit=control.visit,
        iq_sha256=window.iq_sha256,
        sample_start=control.sample_start,
        sample_end=control.sample_end,
        sample_start_utc_ns=control.sample_start_utc_ns,
        channel=control.channel,
        edge=control.edge,
        policy_status=control.status,
        reason=control.reason,
        equal_status=(control.status, control.reason) == (tiled.status, tiled.reason),
        equal_payload=same_payload,
        equal_coarse_peak_keys=equal_peaks,
        coarse_peak_count=sum(map(len, control_peaks)),
        coarse_peak_score_max_delta=peak_max_delta,
        control_coarse_peaks=control_peaks,
        tiled_coarse_peaks=tiled_peaks if not equal_peaks else None,
        n_candidates=len(candidates),
        integer_gate_passes=sum(c.passed_margin_gate for c in candidates),
        fractional_gate_passes=sum(
            c.fractional_margin is not None and c.fractional_margin >= MARGIN_GATE
            for c in candidates
        ),
        production=probes(control),
        native=probes(tiled),
        repeats=timing,
    )


def replay(case_id, directory, *, profile_only=False):
    from leo.analysis.starlink import acquisition, fast_scan_scores
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window

    case, policy = _load_case(case_id), FastScanPolicyV2()
    producer = _bind_producer(case, PRODUCERS[case_id], policy)
    libraries = {mode: directory / f"{mode}.so" for mode in MODES}
    anchor_receiver.compile_filter(libraries["control"])
    if not profile_only:
        pilot_kernel.compile_filter(libraries["tiled"])
    grids = {
        mode: anchor_grid.native_grid(path) for mode, path in libraries.items() if path.is_file()
    }
    sampler = anchor_grid.fractional_sampler(fast_scan_scores.fractional_take)

    def call(window, mode, *, trace=False):
        peaks = []

        def traced_peaks(*args):
            retained = anchor_grid.retained_peaks(*args)
            peaks.append(retained)
            return retained

        keep = traced_peaks if trace else anchor_grid.retained_peaks
        with (
            patch.object(acquisition, "_folded_anchor_score_grid", grids[mode]),
            patch.object(acquisition, "_retain_score_map_peaks", keep),
            patch.object(fast_scan_scores, "fractional_take", sampler),
        ):
            wall, cpu = perf_counter(), process_time()
            result = analyze_window(window, window.receiver_ids, None, policy)
            timing = dict(cpu_s=process_time() - cpu, wall_s=perf_counter() - wall)
        return result, timing, peaks

    receipt = dict(
        case=case_id,
        producer=producer,
        cpus=sorted(os.sched_getaffinity(0)),
        compiler=subprocess.check_output(["cc", "--version"], text=True).splitlines()[0],
        compiler_flags=anchor_receiver.FLAGS,
        library_sha256={mode: _sha(libraries[mode]) for mode in grids},
        source_sha256={
            "control": _sha(anchor_receiver.KERNEL),
            "tiled": _sha(pilot_kernel.SOURCE),
            "grid": _sha(Path(anchor_grid.__file__)),
            "evaluation": _sha(Path(__file__)),
        },
    )
    if profile_only:
        return dict(receipt, profile=_profile(case, call))
    rows = []
    for segment in SEGMENTS:
        for window in _windows(case, segment, SEQUENCES):
            row = _timed_window(window, call, len(rows), segment)
            rows.append(row)
            print(case_id, row["visit"], row["policy_status"], row["equal_payload"], flush=True)
    # If candidate receiver lists differ, retain the failed replay rather than aborting
    # the archive audit's controlled strict pairing. Audit original rows independently.
    archive_rows = [dict(row, native=row["production"]) for row in rows]
    audit = _measure(case, archive_rows, window.sample_rate_hz)
    del audit["receivers"]
    return dict(receipt, rows=rows, archive_audit=audit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=tuple(PRODUCERS), required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--profile", action="store_true")
    args = parser.parse_args()
    if len(os.sched_getaffinity(0)) != 1 or any(os.environ.get(k) != "1" for k in THREAD_ENV):
        parser.error("use one CPU of affinity and one thread per numerical runtime")
    with TemporaryDirectory(prefix="pilot-kernel-") as work:
        result = replay(args.case, Path(work), profile_only=args.profile)
    write(args.out, gzip.compress(encoded(result) + b"\n", mtime=0))


if __name__ == "__main__":
    main()
