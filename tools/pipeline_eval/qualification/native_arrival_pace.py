"""Measure a one-CPU portable C FIFO over the first authenticated IQ chunk."""

import argparse
import json
import os
from pathlib import Path
from threading import Condition, Thread
from time import monotonic_ns, sleep, thread_time_ns
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import local_output
from ..scoring import distribution
from ..variants import native_arrival as queue, portable_field
from . import capture_whole as capture
from .full_v5_check import _from_production, _probe, _sha


def observe(source, detector, policy, windows, reference, arrivals, rf_bins):
    from leo.contracts.fast_scan import FastScanReceiverV1
    from leo.scanner.fast_scan_analysis import analyze_window

    waiting = queue.Waiting(queue.Policy.FIFO, queue.WAITING, queue.LAG_NS, rf_bins)
    gate = Condition()
    running, errors = [], []
    events = [dict(visit=a.visit, scheduled_ns=a.time_ns) for a in arrivals]
    empty = tuple(FastScanReceiverV1(receiver_id=i, candidates=()) for i in source.receiver_ids)
    for a, window in zip(arrivals, windows, strict=True):
        status = analyze_window(window, source.receiver_ids, None, policy, detector=lambda *_: empty)
        if (status.status == "processed") != a.valid:
            raise ValueError("the predecoded IQ validity differs from the full C gate")
    origin = monotonic_ns() + 100_000_000
    producer_finished = False

    def mark_expired(now):
        for i in waiting.expire(now):
            events[i]["outcome"] = "expired_waiting"

    def consume():
        try:
            while True:
                with gate:
                    gate.wait_for(lambda: waiting or producer_finished)
                    start = monotonic_ns() - origin
                    mark_expired(start)
                    if not waiting:
                        if producer_finished:
                            return
                        continue
                    arrival = waiting.dispatch()
                    i = arrival.visit
                    running.append(i)
                    events[i]["start_ns"] = start
                cpu = thread_time_ns()
                detector.attempts = []
                measured = analyze_window(windows[i], source.receiver_ids, None, policy, detector=detector)
                probes = [_probe(windows[i], p.receiver_id, map(_from_production, p.candidates))
                          for p in measured.receivers]
                done, spent = monotonic_ns() - origin, thread_time_ns() - cpu
                if measured.status != "processed" or probes != reference[i]["probes"]:
                    raise ValueError(f"paced portable C probe pair differs at visit {i}")
                with gate:
                    events[i].update(finish_ns=done, cpu_ns=spent, outcome=(
                        "ready" if done - arrival.time_ns <= queue.LAG_NS else "expired_running"
                    ))
                    running.clear()
        except Exception as error:
            errors.append(error)

    worker = Thread(target=consume)
    worker.start()
    for arrival in arrivals:
        remaining = origin + arrival.time_ns - monotonic_ns()
        if remaining > 0:
            sleep(remaining / queue.NS)
        with gate:
            now = monotonic_ns() - origin
            i = arrival.visit
            events[i]["release_ns"] = now
            mark_expired(now)
            if arrival.valid:
                discard = waiting.admit(arrival)
                if discard is not None:
                    events[discard[0]]["outcome"] = discard[1]
            else:
                events[i]["outcome"] = "invalid_capture"
            gate.notify()
    with gate:
        at_last = dict(waiting=waiting.ids(), running=running[:])
        producer_finished = True
        gate.notify()
    worker.join(timeout=5)
    if errors:
        raise errors[0]
    if worker.is_alive() or any("outcome" not in event for event in events):
        raise ValueError("paced one-worker replay lacks complete terminal outcomes")
    deadline = arrivals[-1].time_ns + queue.LAG_NS
    active = [r["visit"] for r in events if r.get("start_ns", deadline + 1) <= deadline < r["finish_ns"]]
    return dict(events=events, last_delivery=at_last, final_deadline=dict(waiting=[], running=active))


def measure(native, source_sha, seal_path, seal_sha):
    from leo.storage import short_window

    (cpu,) = os.sched_getaffinity(0)
    lock = whole_iq.read(whole_iq.checked(native / "source-lock.json", source_sha))
    seal = whole_iq.read(whole_iq.checked(seal_path, seal_sha))["files"]
    if seal["source-lock.json"] != source_sha or lock["smoke"]:
        raise ValueError("pace check must replay the sealed full native capture path")
    raw_cpu, segment, first, stop = next(
        (c, s, f, end) for c, _, parts in lock["workers"]
        for s, f, end, _ in parts if (s, f) == (0, 0)
    )
    raw_name = f"cpu-{raw_cpu}.jsonl"
    raw_path = whole_iq.checked(native / raw_name, seal[raw_name])
    with raw_path.open() as stream:
        reference = [r for r in map(json.loads, stream)
                     if r["kind"] == "visit" and r["segment"] == segment and first <= r["sequence"] < stop]
    lib = lock["libraries"]["portable_field"]
    binary = whole_iq.checked(Path(lib["path"]), lib["sha256"])
    checked, original_member = [], short_window.ShortWindowReader._member

    def authenticate(reader, name, size, expected):
        if any(chunk.payload_relative_path == name for chunk in reader.manifest.chunks):
            path = short_window.confined_path(reader.path, reader.path / name, must_exist=True)
            return capture.resources.AuthenticatedMember(path, size, expected, checked)
        return original_member(reader, name, size, expected)

    policy = capture.policy_for(lock)
    source = capture.open_span(lock, segment, first, stop)
    before = monotonic_ns()
    with patch.object(short_window.ShortWindowReader, "_member", authenticate):
        windows = list(source.windows())
    predecode_ns = monotonic_ns() - before
    if len(checked) != 1 or len(windows) != len(reference) or len(reference) != stop - first:
        raise ValueError("paced replay did not authenticate exactly one whole signed payload")
    origin = reference[0]["delivery_clock"]["monotonic_ns"]
    arrivals = []
    for i, (window, row) in enumerate(zip(windows, reference, strict=True)):
        a = window.acquisition
        signed_clock = json.loads(a["retune_receipt"])["host_delivery_clock"]
        if (i, window.iq_sha256, a["global_visit"], a["sample_start"], a["sample_end"], signed_clock) != (
            row["visit"], row["iq_sha256"], row["visit"], row["sample_start"], row["sample_end"], row["delivery_clock"],
        ):
            raise ValueError("paced replay clocks or raw bytes differ from the full native visit")
        arrivals.append(queue.Arrival(i, signed_clock["monotonic_ns"] - origin,
                                      window.target["rf_center_hz"], row["status"] == "processed"))
    if arrivals[-1].time_ns > 5 * queue.NS:
        raise ValueError("paced check exceeds the fixed short recording budget")
    rf_bins = sorted({a.rf for a in arrivals})
    with portable_field.Detector(binary, lock["capture"]["edge"]) as detector:
        result = observe(source, detector, policy, windows, reference, arrivals, rf_bins)
    events = result["events"]
    clocks = {k: [round(row[f"detector_{k}_s"] * queue.NS) for row in reference] for k in ("cpu", "wall")}
    models = {k: queue.simulate(arrivals, clock, 1, queue.Policy.FIFO, rf_bins) for k, clock in clocks.items()}
    return dict(
        **result, models=models, cpu=cpu, nice=os.nice(0), source_sha256=source_sha,
        run_seal_sha256=seal_sha, ledger_sha256=seal[raw_name], library_sha256=lib["sha256"],
        manifest_digest=source.manifest_digest, predecode_ns=predecode_ns,
        predecoded_iq_bytes=sum(w.samples.nbytes for w in windows), compressed_bytes=checked[0],
        producer_lateness_ms=distribution((r["release_ns"] - r["scheduled_ns"]) / 1e6 for r in events),
        started_cpu_ms=distribution(r["cpu_ns"] / 1e6 for r in events if "cpu_ns" in r),
        started_wall_ms=distribution((r["finish_ns"] - r["start_ns"]) / 1e6 for r in events if "cpu_ns" in r),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("native", type=local_output)
    parser.add_argument("source_sha256")
    parser.add_argument("seal", type=local_output)
    parser.add_argument("seal_sha256")
    args = parser.parse_args()
    result = measure(args.native, args.source_sha256, args.seal, args.seal_sha256)
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
