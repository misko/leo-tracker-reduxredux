"""Process qualified radio visits concurrently and hand them to the reader in arrival order."""

import os
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from itertools import islice
from pathlib import Path
from queue import SimpleQueue
from time import perf_counter_ns, thread_time_ns


def ordered(items, prepare, capacity):
    """Start at most capacity items. Only the head may be handed back to the recorder."""
    if capacity not in (1, 2):
        raise ValueError("one or two in-flight windows are supported")
    source = iter(items)
    waiting = deque(prepare(item) for item in islice(source, capacity))
    while waiting:
        yield waiting.popleft()
        waiting.extend(prepare(item) for item in islice(source, 1))


def capture(job):
    # These are the detector and contract modules shipped with the standalone receiver.
    import native_bridge as bridge
    from conditional_policy import RfStagger, detect

    from leo.analysis.starlink.native_short_window import NativeShortWindow
    from leo.contracts.fast_scan import FastScanReceiverV1
    from leo.scanner.fast_scan_analysis import analyze_window

    workers = job["visit_workers"]
    if workers not in (1, 2) or job["detector"] not in ("partner-on-hit", "second-on-miss"):
        raise ValueError("unknown antenna schedule or unsupported worker count")
    os.sched_setaffinity(0, job["cpus"][:workers])
    library = Path(__file__).resolve().parent.parent / "stock-wide.so"
    if bridge._sha(library) != job["detector_sha256"]:
        raise ValueError("antenna acquisition requires its declared detector binary")
    output = Path(job["out"])
    schedule = RfStagger()
    on_hit = job["detector"] == "partner-on-hit"
    receiver_pair = tuple(FastScanReceiverV1(receiver_id=rx, candidates=()) for rx in (0, 1))
    visit_count = 0

    @contextmanager
    def detector_batch(*args, receiver_count, **kwargs):
        if receiver_count != 2:
            raise ValueError("a two-antenna recording is required")
        with ExitStack() as stack:
            # Construct the native FFT plans sequentially. Each analysis owns a distinct plan.
            free = SimpleQueue()
            for _ in range(workers):
                free.put(stack.enter_context(NativeShortWindow(*args, receiver_count=1, **kwargs)))
            pool = stack.enter_context(ThreadPoolExecutor(max_workers=workers))

            def observe(window, primary):
                native = free.get()
                try:
                    cpu, wall = thread_time_ns(), perf_counter_ns()
                    data, partner = detect(native, window.samples, primary, on_hit=on_hit)
                    elapsed, used = perf_counter_ns() - wall, thread_time_ns() - cpu
                finally:
                    free.put(native)
                return data["rows"], dict(
                    visit=window.acquisition["global_visit"],
                    rf_center_hz=window.target["rf_center_hz"],
                    primary_receiver=primary,
                    partner_required=partner,
                    detector_cpu_ns=used,
                    detector_wall_ns=elapsed,
                )

            def records(source, policy):
                def prepare(window):
                    nonlocal visit_count
                    if window.acquisition["global_visit"] != visit_count:
                        raise ValueError("the saved visits must arrive in contiguous capture order")
                    visit_count += 1
                    future = None

                    def submit(valid, receivers):
                        nonlocal future
                        primary = schedule.reserve(valid.target["rf_center_hz"])
                        future = pool.submit(observe, valid, primary)
                        return receiver_pair

                    # The capture's ordinary quality gate calls submit only on valid windows.
                    status = analyze_window(
                        window, source.receiver_ids, None, policy, detector=submit
                    )
                    return window, status, future

                for window, status, future in ordered(source.windows(), prepare, workers):
                    if future is None:
                        yield window, (status, [], 0.0)
                        continue
                    rows, timing = future.result()
                    if [row["receiver_id"] for row in rows] != [0, 1]:
                        raise ValueError("detector output changed physical receiver order")
                    probes = [
                        bridge._probe(
                            window,
                            row["receiver_id"],
                            (bridge._from_native(i, c) for i, c in enumerate(row["candidates"])),
                        )
                        for row in rows
                    ]
                    audit.write(bridge.encoded(timing) + "\n")
                    yield window, (status, probes, timing["detector_cpu_ns"] / 1e9)

            yield records

    with ExitStack() as stack:
        audit = stack.enter_context((output / "conditional-visits.jsonl").open("x"))
        lanes = [stack.enter_context((output / f"lane-{rx}.jsonl").open("x")) for rx in (0, 1)]
        bridge.stream_range(
            library,
            0,
            job["segments"],
            "saved-recording",
            job["authority"],
            outputs=lanes,
            observation_factory=detector_batch,
        )
    if visit_count != job["count"]:
        raise ValueError("the raw service omitted scheduled visits")
