"""Compare the complete capture-era detector with the short-filter and peak-selection changes."""

import argparse
import gzip
import hashlib
import json
import os
from contextlib import ExitStack
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

from ..__main__ import encoded, write
from ..variants import anchor_grid
from ..variants.iq_stream import load_windows
from .full_v5_check import (
    BULK,
    PRODUCERS,
    _bind_producer,
    _from_production,
    _load_case,
    _measure,
    _probe,
)


def replay(case_id, library, segments=(1, 4, 8, 12), sequences=(1, 3, 5, 7)):
    from leo.analysis.starlink import acquisition, fast_scan_scores
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window

    case, policy = _load_case(case_id), FastScanPolicyV2()
    identity = _bind_producer(case, PRODUCERS[case_id], policy)
    grid = anchor_grid.native_grid(library)
    sampler = anchor_grid.fractional_sampler(fast_scan_scores.fractional_take)
    rows = []
    for segment_index in segments:
        locator = case["recording"]["segments"][segment_index]
        windows = load_windows(
            dict(
                recording_path=str(BULK / locator["path"]),
                recording_sha256="sha256:" + locator["sha256"],
            ),
            sequences,
        )
        for window in windows:
            capture = window.acquisition
            row = dict(
                visit=capture["global_visit"],
                iq_sha256=window.iq_sha256,
                sample_start=capture["sample_start"],
                sample_end=capture["sample_end"],
                segment_index=segment_index,
                sequence=window.sequence,
            )
            docs = {}
            order = ("production", "native") if len(rows) % 2 == 0 else ("native", "production")
            for mode in order:
                with ExitStack() as stack:
                    if mode == "native":
                        stack.enter_context(
                            patch.object(acquisition, "_folded_anchor_score_grid", grid)
                        )
                        stack.enter_context(
                            patch.object(
                                acquisition, "_retain_score_map_peaks", anchor_grid.retained_peaks
                            )
                        )
                        stack.enter_context(
                            patch.object(fast_scan_scores, "fractional_take", sampler)
                        )
                    start, cpu = perf_counter(), process_time()
                    result = analyze_window(window, window.receiver_ids, None, policy)
                    row[mode + "_cpu_s"] = process_time() - cpu
                    row[mode + "_wall_s"] = perf_counter() - start
                docs[mode] = result
                row[mode] = [
                    _probe(window, r.receiver_id, map(_from_production, r.candidates))
                    for r in result.receivers
                ]
            baseline, candidate = docs["production"], docs["native"]
            row.update(
                policy_status=baseline.status,
                reason=baseline.reason,
                order=order,
                equal_status=(baseline.status, baseline.reason)
                == (candidate.status, candidate.reason),
                equal_receivers=baseline.receivers == candidate.receivers,
                n_candidates=sum(len(r.candidates) for r in baseline.receivers),
            )
            rows.append(row)
            print(case_id, row["visit"], row["policy_status"], row["equal_receivers"], flush=True)
    audit = _measure(case, rows, window.sample_rate_hz)
    return dict(
        case=case_id,
        producer=identity,
        cpus=sorted(os.sched_getaffinity(0)),
        kernel_sha256=hashlib.sha256(library.read_bytes()).hexdigest(),
        source_sha256=hashlib.sha256(Path(anchor_grid.__file__).read_bytes()).hexdigest(),
        archive_audit=audit,
        rows=rows,
    )


def main():
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
            {
                k: v
                for k, v in data["archive_audit"].items()
                if k in ("archived_probe_rows", "exact_probe_rows")
            }
        )
    )


if __name__ == "__main__":
    main()
