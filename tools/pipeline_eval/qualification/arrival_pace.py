"""Pace a short authenticated stored-IQ prefix at its recorded monotonic intervals."""

import argparse
import json
import os
import sys
import time
from hashlib import sha256
from itertools import islice
from pathlib import Path
from queue import Queue
from threading import Thread

from tools.pipeline_eval.qualification import recording_to_v5 as authority

CASE = "DS26-0036"
PREFIX = 96
CPU = 16
WAITING = 32


def measure(native_path, expected_native, expected_library, metadata):
    import numpy as np

    from leo.analysis.starlink.native_short_window import NativeShortWindow
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame
    from leo.contracts.fast_scan import FastScanReceiverV1
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window
    from leo.storage.fast_scan import FastSegmentSource

    if os.sched_getaffinity(0) != {CPU} or os.nice(0) < 10:
        raise ValueError("recorded pacing uses CPU 16 at nice 10 or lower priority")
    blob = sys.stdin.buffer.read() if native_path == Path("-") else native_path.read_bytes()
    if sha256(blob).hexdigest() != expected_native:
        raise ValueError("ordinary native factor SHA changed")
    reference = json.loads(blob)
    if authority._sha(authority.NATIVE_LIBRARY) != expected_library:
        raise ValueError("native detector library differs from the whole-IQ reference")
    case, capture = (metadata[key] for key in ("case", "capture"))
    if (
        case["id"] != CASE
        or case["session_id"] != reference["source"]["session_id"]
        or capture["segments_sha256"] != authority.digest(case["recording"]["segments"])
    ):
        raise ValueError("paced archive metadata differs from the ordinary capture")
    producer = authority.capture_release.producer(case, capture)
    policy = FastScanPolicyV2()
    authority._bind_producer(case, producer, policy)
    if not Path(analyze_window.__code__.co_filename).is_relative_to(producer.root):
        raise ValueError("pacing must use the recorded detector adapter")
    locator = case["recording"]["segments"][0]
    directory = (authority.BULK / locator["path"]).resolve().parent
    source = FastSegmentSource(
        dict(path=str(directory), manifest_digest="sha256:" + locator["sha256"])
    )
    archived_rows = {i: [] for i in range(PREFIX)}
    for row in reference["source"]["probes"]:
        if row["visit_index"] < PREFIX:
            archived_rows[row["visit_index"]].append(row)
    clocks = reference["delivery_clocks"]
    window_stream = source.windows()
    try:
        windows = list(islice(window_stream, PREFIX))
    finally:
        window_stream.close()
    ids = [int(w.acquisition["global_visit"]) for w in windows]
    if ids != list(range(PREFIX)) or source.receiver_ids != (0, 1):
        raise ValueError("the paced prefix must contain the complete fixed physical cohort")
    for ident, window in zip(ids, windows, strict=True):
        clock = json.loads(window.acquisition["retune_receipt"])["host_delivery_clock"]
        if clock != clocks[ident]:
            raise ValueError("recorded delivery clock differs from ordinary source")
    offsets = [clocks[i]["monotonic_ns"] - clocks[0]["monotonic_ns"] for i in ids]
    if not 0 < offsets[-1] < 10**10:
        raise ValueError("pacing must remain within the bounded prefix")

    edge = capture["edge"]
    rate = policy.sample_rate_hz
    exact = np.asarray(qin_edge_pilot_frame(rate, edge), dtype="<c16")
    control = np.asarray(
        qin_edge_pilot_frame(rate, edge, symbol_roll=CONTROL_SYMBOL_ROLL), dtype="<c16"
    )
    queue = Queue(maxsize=WAITING)
    failures, measured = [], []
    with NativeShortWindow(
        str(authority.NATIVE_LIBRARY),
        exact,
        control,
        sample_rate_hz=rate,
        receiver_count=2,
        fractional_epoch=True,
    ) as native:

        def consume():
            try:
                while (job := queue.get()) is not None:
                    ident, window, release = job
                    start, cpu = time.monotonic_ns(), time.thread_time_ns()
                    observed = []

                    def detector(window, receivers, observed=observed):
                        result = native.analyze(window.samples)
                        for row in result["rows"]:
                            rx = row["receiver_id"]
                            candidates = (
                                authority._from_native(k, item)
                                for k, item in enumerate(row["candidates"])
                            )
                            observed.append(authority._probe(window, receivers[rx], candidates))
                        return tuple(
                            FastScanReceiverV1(receiver_id=rx, candidates=()) for rx in receivers
                        )

                    status = analyze_window(
                        window, source.receiver_ids, None, policy, detector=detector
                    )
                    finished, cpu_ns = time.monotonic_ns(), time.thread_time_ns() - cpu
                    if observed != archived_rows[ident]:
                        raise ValueError(f"{ident} paced detector differs from ordinary native")
                    measured.append(
                        dict(
                            visit=ident,
                            released_ns=release - origin,
                            started_ns=start - origin,
                            finished_ns=finished - origin,
                            worker_cpu_ns=cpu_ns,
                            status=status.status,
                            iq_sha256=window.iq_sha256,
                        )
                    )
            except Exception as error:
                failures.append(repr(error))

        lane = Thread(target=consume)
        lane.start()
        origin = time.monotonic_ns() + 30_000_000
        for i, window, offset in zip(ids, windows, offsets, strict=True):
            remaining = origin + offset - time.monotonic_ns()
            if remaining > 0:
                time.sleep(remaining / 1e9)
            queue.put((i, window, time.monotonic_ns()), timeout=2)
        queue.put(None, timeout=2)
        lane.join(timeout=8)
        if lane.is_alive() or failures or len(measured) != PREFIX:
            raise ValueError(f"paced worker incomplete {failures}")
    return dict(
        id=CASE,
        native_sha256=expected_native,
        library_sha256=expected_library,
        manifest_sha256=locator["sha256"],
        cpu=CPU,
        nice=os.nice(0),
        predecoded=True,
        waiting_slots=WAITING,
        requested_offsets_ns=offsets,
        observations=measured,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("native", type=Path)
    parser.add_argument("native_sha256")
    parser.add_argument("library_sha256")
    parser.add_argument("--metadata", type=json.loads, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            measure(args.native, args.native_sha256, args.library_sha256, args.metadata),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
