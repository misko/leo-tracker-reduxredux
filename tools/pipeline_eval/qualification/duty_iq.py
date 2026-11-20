"""Time channel scheduling and pilot acquisition on the same decoded waveform windows."""

import argparse
import gzip
import json
import os
from contextlib import ExitStack
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

from ..__main__ import encoded, write
from ..variants import anchor_grid
from ..variants.anchor_receiver import KERNEL
from ..variants.channel_schedule import SCHEDULES, analyze_scheduled
from ..variants.iq_stream import load_windows
from .full_v5_check import (
    BULK,
    PRODUCERS,
    _bind_producer,
    _from_production,
    _load_case,
    _measure,
    _probe,
    _sha,
)


def replay(case_id, library):
    from leo.analysis.starlink import acquisition, fast_scan_scores
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window

    case, policy = _load_case(case_id), FastScanPolicyV2()
    producer = _bind_producer(case, PRODUCERS[case_id], policy)
    faster = anchor_grid.native_grid(library)
    sample = anchor_grid.fractional_sampler(fast_scan_scores.fractional_take)
    modes = [(engine, s) for engine in ("original", "accelerated") for s in ("all", *SCHEDULES)]
    rows = []
    for index in (3, 10):
        segment = case["recording"]["segments"][index]
        windows = load_windows(
            dict(
                recording_path=str(BULK / segment["path"]),
                recording_sha256="sha256:" + segment["sha256"],
            ),
            range(8),
        )
        for window in windows:
            capture = window.acquisition
            shift = len(rows) % len(modes)
            order = modes[shift:] + modes[:shift]
            if len(rows) // len(modes) % 2:
                order = order[::-1]
            outcomes, timing = {}, {}
            for engine, schedule in order:
                with ExitStack() as stack:
                    if engine == "accelerated":
                        stack.enter_context(
                            patch.object(acquisition, "_folded_anchor_score_grid", faster)
                        )
                        stack.enter_context(
                            patch.object(
                                acquisition, "_retain_score_map_peaks", anchor_grid.retained_peaks
                            )
                        )
                        stack.enter_context(
                            patch.object(fast_scan_scores, "fractional_take", sample)
                        )
                    start, cpu = perf_counter(), process_time()
                    out = analyze_scheduled(window, schedule, analyze_window, policy)
                    elapsed_cpu, elapsed = process_time() - cpu, perf_counter() - start
                timing[engine + "/" + schedule] = dict(
                    wall_s=elapsed, cpu_s=elapsed_cpu, called=out is not None
                )
                outcomes[engine, schedule] = out
            base = outcomes["original", "all"]
            equal = {}
            for engine, schedule in modes:
                out = outcomes[engine, schedule]
                if out is None:
                    equal[engine + "/" + schedule] = None
                else:
                    equal[engine + "/" + schedule] = (
                        out.status == base.status
                        and out.reason == base.reason
                        and out.receivers == base.receivers
                    )
            native = [
                outcomes["accelerated", s]
                for s in SCHEDULES
                if outcomes["accelerated", s] is not None
            ]
            if len(native) != 1:
                raise ValueError(
                    "complementary schedules must call exactly one detector per window"
                )

            def probes(out, window):
                return [
                    _probe(window, r.receiver_id, map(_from_production, r.candidates))
                    for r in out.receivers
                ]

            rows.append(
                dict(
                    visit=capture["global_visit"],
                    segment=index,
                    sequence=window.sequence,
                    channel=window.target["channel"],
                    iq_sha256=window.iq_sha256,
                    sample_start=capture["sample_start"],
                    sample_end=capture["sample_end"],
                    policy_status=base.status,
                    reason=base.reason,
                    order=order,
                    equal=equal,
                    timing=timing,
                    production=probes(base, window),
                    native=probes(native[0], window),
                    n_candidates=sum(len(r.candidates) for r in base.receivers),
                )
            )
            print(case_id, rows[-1]["visit"], base.status, flush=True)
    return dict(
        case=case_id,
        producer=producer,
        cpus=sorted(os.sched_getaffinity(0)),
        rows=rows,
        kernel_sha256=_sha(library),
        kernel_source_sha256=_sha(KERNEL),
        anchor_grid_sha256=_sha(Path(anchor_grid.__file__)),
        archive_audit=_measure(case, rows, window.sample_rate_hz),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", choices=tuple(PRODUCERS), required=True)
    p.add_argument("--library", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    if len(os.sched_getaffinity(0)) != 1 or any(
        os.environ.get(k) != "1"
        for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")
    ):
        p.error("use one CPU of affinity and one numerical thread")
    data = replay(args.case, args.library)
    write(args.out, gzip.compress(encoded(data) + b"\n", mtime=0))
    print(
        json.dumps(
            {k: data["archive_audit"][k] for k in ("archived_probe_rows", "exact_probe_rows")}
        )
    )
