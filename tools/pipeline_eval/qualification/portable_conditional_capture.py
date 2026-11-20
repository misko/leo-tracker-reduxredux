"""Run the frozen primary-miss policy in the stock saved-capture reader."""

import os
from contextlib import ExitStack
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch


def capture(job):
    # These modules are supplied by the verified portable release.
    import native_bridge
    from conditional_policy import RfStagger, detect

    from leo.analysis.starlink import native_short_window
    from leo.storage.fast_scan import FastSegmentSource

    out = Path(job["out"])
    library = Path(__file__).resolve().parent.parent / "stock-wide.so"
    if native_bridge._sha(library) != job["detector_sha256"]:
        raise ValueError("the one-receiver ABI must come from the packaged stock library")
    constructor, windows = native_short_window.NativeShortWindow, FastSegmentSource.windows
    schedule = RfStagger()
    current, last, executed = None, -1, False

    class PhysicalNative:
        def __init__(self, *args, receiver_count, **kwargs):
            if receiver_count != 2:
                raise ValueError("the public packet must retain both physical slots")
            self.native = constructor(*args, receiver_count=1, **kwargs)

        def __enter__(self):
            self.native.__enter__()
            return self

        def __exit__(self, *args):
            return self.native.__exit__(*args)

        def analyze(self, samples):
            nonlocal executed
            if current is None or executed:
                raise ValueError("one conditional dispatch is allowed per qualified raw window")
            executed = True
            visit, rf = current
            primary = schedule.reserve(rf)
            tick, cpu = perf_counter_ns(), process_time_ns()
            result, partner = detect(self.native, samples, primary)
            cpu_ns, wall_ns = process_time_ns() - cpu, perf_counter_ns() - tick
            audit.write(
                native_bridge.encoded(
                    dict(
                        visit=visit,
                        rf_center_hz=rf,
                        primary_receiver=primary,
                        partner_required=partner,
                        detector_cpu_ns=cpu_ns,
                        detector_wall_ns=wall_ns,
                    )
                )
                + "\n"
            )
            return result

    def chronological(source):
        nonlocal current, last, executed
        for window in windows(source):
            visit = int(window.acquisition["global_visit"])
            if visit != last + 1:
                raise ValueError("RF scheduling must include every raw visit in capture order")
            last = visit
            current, executed = (visit, window.target["rf_center_hz"]), False
            yield window
            current = None

    os.sched_setaffinity(0, {job["cpus"][0]})
    with ExitStack() as stack:
        audit = stack.enter_context((out / "conditional-visits.jsonl").open("x"))
        lanes = [stack.enter_context((out / f"lane-{lane}.jsonl").open("x")) for lane in range(2)]
        stack.enter_context(patch.object(native_short_window, "NativeShortWindow", PhysicalNative))
        stack.enter_context(patch.object(FastSegmentSource, "windows", chronological))
        native_bridge.stream_range(
            library, 0, job["segments"], "saved-recording", job["authority"], outputs=lanes
        )
    if last + 1 != job["count"]:
        raise ValueError("conditional raw worker omitted a sealed visit")
