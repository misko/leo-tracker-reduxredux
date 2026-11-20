"""Verify one prespecified anchor sweep per smoke recording through both detectors."""

import argparse
import gzip
import json
import os
from itertools import groupby
from pathlib import Path
from statistics import mean
from time import perf_counter, process_time

import numpy as np

from ..__main__ import encoded, local_output, write
from ..variants.iq_stream import load_windows
from ..variants.periodic_anchor import ORDINARY_CONTROL, REFERENCE_CONTROL
from .full_v5_check import (
    BULK,
    NATIVE_LIBRARY,
    PRODUCERS,
    _bind_producer,
    _from_native,
    _from_production,
    _load_case,
    _probe,
    _sha,
)
from .recording_to_v5 import SINGLE_THREAD

ORDINARY, CAPTURE_ERA = ORDINARY_CONTROL, REFERENCE_CONTROL
MAX_SCHEDULED_BYTES = 8 * 20_000 * 10 * 2 * 4  # 20 ms × 10 MS/s × 2 complex receivers.


def _timed(operation):
    wall, cpu = perf_counter(), process_time()
    result = operation()
    return result, dict(cpu_s=process_time() - cpu, wall_s=perf_counter() - wall)


def _expected_probes(path, checksum, visits):
    if _sha(path) != checksum:
        raise ValueError("original factor archive changed before raw confirmation")
    document = json.loads(path.read_bytes())
    probes = {visit: [] for visit in visits}
    for row in document["source"]["probes"]:
        if row["visit_index"] in visits:
            probes[row["visit_index"]].append(row)
    exclusions = {row["visit"]: row for row in document["provenance"]["excluded_windows"]}
    return probes, exclusions


def confirm(case_id, schedule_path, library):
    from leo.analysis.starlink.native_short_window import NativeShortWindow
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame
    from leo.contracts.fast_scan import FastScanReceiverV1
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window

    case = _load_case(case_id)
    policy = FastScanPolicyV2()
    prod = _bind_producer(case, PRODUCERS[case_id], policy)
    schedule = json.loads(schedule_path.read_bytes())
    selected = schedule["first_sweep"]
    if (
        schedule["id"] != case_id
        or len(selected) != 8
        or sum(row["payload_bytes"] for row in selected) > MAX_SCHEDULED_BYTES
        or [row["visit"] for row in selected] != schedule["selected_visits"][:8]
    ):
        raise ValueError("raw confirmation does not bind the bounded first selected sweep")
    visits = {row["visit"] for row in selected}
    expected = {
        arm: _expected_probes(Path(schedule["paths"][arm]), schedule["factor_sha256"][arm], visits)
        for arm in (ORDINARY, CAPTURE_ERA)
    }
    rates, edge = policy.sample_rate_hz, selected[0]["edge"]
    exact = np.asarray(qin_edge_pilot_frame(rates, edge), dtype="<c16")
    rolled = np.asarray(
        qin_edge_pilot_frame(rates, edge, symbol_roll=CONTROL_SYMBOL_ROLL), dtype="<c16"
    )
    args = dict(sample_rate_hz=rates, receiver_count=2, fractional_epoch=True)
    library_digest = _sha(library)
    all_measurements = []
    with NativeShortWindow(str(library), exact, rolled, **args) as context:
        for segment, group in groupby(selected, lambda row: row["segment"]):
            scheduled = tuple(group)
            loc = case["recording"]["segments"][segment]
            windows = load_windows(
                dict(
                    recording_path=str(BULK / loc["path"]),
                    recording_sha256="sha256:" + loc["sha256"],
                ),
                [row["sequence"] for row in scheduled],
            )
            for window, registered in zip(windows, scheduled, strict=True):
                visit = registered["visit"]
                if (
                    window.iq_sha256 != registered["iq_sha256"]
                    or window.acquisition["global_visit"] != visit
                    or window.target["channel"] != registered["channel"]
                    or window.target["edge"] != edge
                    or window.samples.nbytes != registered["payload_bytes"]
                ):
                    raise ValueError("bounded IQ window differs from its scheduled visit")

                ordinary_probes = []

                def detector(window, receivers, ordinary_probes=ordinary_probes):
                    rows = context.analyze(window.samples)["rows"]
                    if [row["receiver_id"] for row in rows] != [0, 1]:
                        raise ValueError("ordinary raw detector dropped a physical receiver")
                    ordinary_probes.extend(
                        _probe(
                            window,
                            row["receiver_id"],
                            (
                                _from_native(rank, candidate)
                                for rank, candidate in enumerate(row["candidates"])
                            ),
                        )
                        for row in rows
                    )
                    return tuple(
                        FastScanReceiverV1(receiver_id=rx, candidates=()) for rx in receivers
                    )

                methods = {
                    CAPTURE_ERA: lambda window=window: analyze_window(window, (0, 1), None, policy),
                    ORDINARY: lambda window=window, detector=detector: analyze_window(
                        window, (0, 1), None, policy, detector=detector
                    ),
                }
                measurements = {}
                order = (
                    (ORDINARY, CAPTURE_ERA)
                    if len(all_measurements) % 2
                    else (CAPTURE_ERA, ORDINARY)
                )
                for arm in order:
                    status, timing = _timed(methods[arm])
                    probes = (
                        ordinary_probes
                        if arm == ORDINARY
                        else [
                            _probe(window, row.receiver_id, map(_from_production, row.candidates))
                            for row in status.receivers
                        ]
                    )
                    ref_probes, exclusions = expected[arm]
                    if status.status == "invalid_capture":
                        sample = dict(
                            visit=visit,
                            reason=status.reason,
                            iq_sha256=window.iq_sha256,
                            sample_start=status.sample_start,
                            sample_end=status.sample_end,
                        )
                        equal = not probes and exclusions.get(visit) == sample
                    else:
                        equal = (
                            status.status == "processed"
                            and visit not in exclusions
                            and probes == ref_probes[visit]
                        )
                    if not equal:
                        raise ValueError(f"{arm} raw results differ at visit {visit}")
                    measurements[arm] = dict(
                        factors_equal=True,
                        status=status.status,
                        candidate_count=sum(len(p["candidates"]) for p in probes),
                        **timing,
                    )
                all_measurements.append(
                    dict(
                        visit=visit,
                        iq_sha256=window.iq_sha256,
                        bytes=window.samples.nbytes,
                        measurements=measurements,
                    )
                )
    if len(all_measurements) != 8 or _sha(library) != library_digest:
        raise ValueError("raw confirmation is incomplete or its detector changed")
    valid = [
        row["measurements"]
        for row in all_measurements
        if row["measurements"][ORDINARY]["status"] == "processed"
    ]
    extra = mean(m[CAPTURE_ERA]["cpu_s"] - m[ORDINARY]["cpu_s"] for m in valid)
    estimate = (
        schedule["verified_ordinary_detector_cpu_s"] + extra * schedule["selected_valid_visits"]
    )
    return dict(
        id=case_id,
        schedule_sha256=schedule["schedule_sha256"],
        producer=prod,
        ordinary_library_sha256=library_digest,
        raw_scheduled_visits=len(all_measurements),
        raw_valid_visits=len(valid),
        scheduled_byte_cap=MAX_SCHEDULED_BYTES,
        raw_decoded_scheduled_bytes=sum(r["bytes"] for r in all_measurements),
        measured_valid_detector_cpu_s={
            arm: sum(m[arm]["cpu_s"] for m in valid) for arm in (ORDINARY, CAPTURE_ERA)
        },
        measurement=all_measurements,
        mean_paired_extra_cpu_s=extra,
        modeled_whole_detector_cpu_s=estimate,
        modeled_overhead_cpu_s=extra * schedule["selected_valid_visits"],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=PRODUCERS, required=True)
    parser.add_argument("--schedule", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--library", type=Path, default=NATIVE_LIBRARY)
    args = parser.parse_args()
    if len(os.sched_getaffinity(0)) != 1 or any(
        os.environ.get(key) != value for key, value in SINGLE_THREAD.items()
    ):
        parser.error("pin raw verification to one CPU and one numerical thread")
    report = confirm(
        args.case, args.schedule.resolve(strict=True), args.library.resolve(strict=True)
    )
    write(local_output(args.out), gzip.compress(encoded(report) + b"\n", mtime=0))
    print(args.case, report["raw_valid_visits"], report["modeled_whole_detector_cpu_s"], flush=True)


if __name__ == "__main__":
    main()
