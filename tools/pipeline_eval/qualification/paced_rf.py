"""Run the frozen oldest-RF one-waiting policy against authentic saved IQ at original pace."""

import argparse
import os
import pwd
from contextlib import ExitStack
from pathlib import Path
from queue import Queue
from threading import Condition, Event, Lock, Thread
from time import monotonic_ns, sleep
from unittest.mock import patch

from .. import iq_service, whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..variants import rf_waiting
from . import arrival_queue as pace
from . import capture_release, paced_original, recording_to_v5
from .full_v5_check import _sha
from .whole_memory_chain_worker import mark

CASE = paced_original.CASE
REPORT = paced_original.REPORT.with_name("paced-rf")
WORK = Path("/var/tmp/leo-paced-rf-20261119")
MODULE = "tools.pipeline_eval.qualification.paced_rf"
MODE = "oldest_rf"
CPU = 12
PARENT_SHA = "fae6b27efd9d16d072ed2f3c04c3b83670262981af61221c8ab44b24b2ac9384"


class Waiting:
    """A single irrevocable dispatch and a single replaceable waiting slot."""

    def __init__(self):
        self.changed = Condition()
        self.active = False
        self.dispatch = self.waiter = None
        self.last_start = {}
        self.closed = False

    def offer(self, frame, event, rf):
        with self.changed:
            job = (frame, event, rf)
            if not self.active and self.dispatch is None:
                self.dispatch = job
                self.changed.notify()
                return "immediate", None, None
            if self.waiter is None:
                self.waiter = job
                return "waiting", None, None
            _, old, pending_rf = self.waiter
            starts = [self.last_start.get(k) for k in (pending_rf, rf)]
            if rf_waiting.replace_waiter(MODE, pending_rf, rf, self.last_start):
                self.waiter = job
                return "replaced_waiter", old, starts
            return "rejected", old, starts

    def start(self, timestamp):
        with self.changed:
            self.changed.wait_for(lambda: self.dispatch is not None or self.closed)
            if self.dispatch is None:
                return None
            frame, event, rf = self.dispatch
            self.dispatch = None
            self.active = True
            started = timestamp()
            self.last_start[rf] = started
            return frame, event, started

    def finish(self):
        with self.changed:
            self.active = False
            self.dispatch, self.waiter = self.waiter, None
            self.changed.notify()

    def close(self):
        with self.changed:
            self.closed = True
            self.changed.notify_all()


class Chronological:
    def __init__(self, sink):
        self.next = 0
        self.waiting = {}
        self.lock = Lock()
        self.sink = sink

    def retire(self, row):
        with self.lock:
            visit = row["visit"]
            if visit < self.next or visit in self.waiting:
                raise ValueError("An acquisition retired twice")
            self.waiting[visit] = row
            while self.next in self.waiting:
                self.sink(self.waiting.pop(self.next))
                self.next += 1


def replay(attempt, plan, ledger):
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window

    meta = plan["case"]
    start = mark("RF-paced guarded waiting queue")
    save_json(attempt / "worker-start.json", start)
    if start["cpus"] != [meta["cpu"]] or start["nice"] < 10:
        raise ValueError("Receiver must use the predeclared one-core affinity and priority")
    if not Path(analyze_window.__code__.co_filename).is_relative_to(meta["producer"]):
        raise ValueError("Receiver must use the frozen original capture producer")
    capture = meta["capture"]
    policy = FastScanPolicyV2()
    recording_to_v5._bind_producer(
        capture["case"], capture_release.producer(capture["case"], capture), policy
    )
    waiting, ready, warm = Waiting(), Queue(pace.PREFETCH), Event()
    failures, verified, hashes = [], [], []

    def prefetch():
        try:
            for frame in pace.packets(capture, verified):
                ready.put((monotonic_ns(), frame))
                if ready.full():
                    warm.set()
            ready.put(None)
        except Exception as exc:
            failures.append(exc)
        finally:
            warm.set()

    with ExitStack() as stack:
        native = pace.build_native(capture, paced_original.ORIGINAL, plan["assets"], stack)
        trace = stack.enter_context((attempt / "visits.jsonl").open("x", buffering=1))
        arrivals = stack.enter_context((attempt / "admission.jsonl").open("x", buffering=1))

        def terminal(row):
            row["retired_ns"] = relative()
            trace.write(encoded(row).decode() + "\n")

        retire = Chronological(terminal).retire

        def relative():
            return monotonic_ns() - origin

        def solve(frame, event, entered, outcome):
            packet, (wall, cpu) = pace.native_visit(frame, analyze_window, native, policy)
            complete = relative()
            if pace.fingerprint(packet) != event["full_visit_sha256"]:
                raise ValueError(f"Original detector packet changed for visit {event['visit']}")
            if outcome == "emitted":
                waiting.finish()
            retire(
                dict(
                    event,
                    outcome=outcome,
                    started_ns=entered,
                    emitted_ns=complete,
                    native_wall_ns=wall,
                    native_cpu_ns=cpu,
                    packet=packet,
                )
            )

        def consume():
            try:
                while (job := waiting.start(relative)) is not None:
                    solve(*job, "emitted")
            except Exception as exc:
                failures.append(exc)

        reading = Thread(target=prefetch, daemon=True)
        receiver = Thread(target=consume, daemon=True)
        reading.start()
        if not warm.wait(15) or failures:
            raise RuntimeError(f"Staged I/Q prefetch did not start: {failures}")
        origin = monotonic_ns() + 50_000_000
        receiver.start()
        for row in ledger:
            loaded = ready.get(timeout=5)
            if loaded is None or failures:
                raise RuntimeError(f"Staged I/Q source stopped early: {failures}")
            available, frame = loaded
            _, window, _, clock = frame
            w = window.acquisition
            physical = (int(w["global_visit"]), w["sample_start"], w["sample_end"], clock)
            if physical != (
                row["visit"],
                row["sample_start"],
                row["sample_end"],
                row["delivery_clock"],
            ):
                raise ValueError("Staged visit counter or original release clock changed")
            hashes.append(window.iq_sha256)
            delay = row["arrival_ns"] - relative()
            if delay > 0:
                sleep(delay / pace.NS)
            event = dict(row, available_ns=available - origin, released_ns=relative())
            if row["status"] == "invalid_capture":
                arrivals.write(
                    encoded(dict(visit=row["visit"], action="invalid_capture")).decode() + "\n"
                )
                solve(frame, event, relative(), "invalid_capture")
                continue
            channel, center = window.target["channel"], window.target["rf_center_hz"]
            if type(channel) is not int or type(center) is not int or center != row["center_hz"]:
                raise ValueError("Raw acquisition RF key differs from independent clock")
            event["rf_key"] = [channel, center]
            action, old, starts = waiting.offer(frame, event, (channel, center))
            audit = dict(
                visit=row["visit"],
                action=action,
                rf_key=event["rf_key"],
                compared_waiter=old["visit"] if old else None,
                last_starts_ns=starts,
            )
            arrivals.write(encoded(audit).decode() + "\n")
            if action == "rejected":
                retire(dict(event, outcome="queue_drop", queue_reason="rejected"))
            elif action == "replaced_waiter":
                retire(
                    dict(
                        old, outcome="queue_drop", queue_reason="replaced", replaced_by=row["visit"]
                    )
                )
        if ready.get(timeout=15) is not None:
            raise ValueError("Unaccounted staged acquisition at the end of the original clock")
        waiting.close()
        receiver.join(timeout=10)
        if receiver.is_alive() or failures:
            raise RuntimeError(f"Original detector did not drain the bounded queue: {failures}")
    if (
        recording_to_v5.digest([capture["input_manifest_sha256"], hashes])
        != meta["raw_recording_sha256"]
    ):
        raise ValueError("Recorded I/Q identities changed")
    end = dict(
        start=start,
        end=mark("RF-paced drained"),
        count=len(hashes),
        pace_origin_ns=origin,
        exact_iq_manifest=True,
        output_sha256=_sha(attempt / "visits.jsonl"),
        admission_sha256=_sha(attempt / "admission.jsonl"),
    )
    save_json(attempt / "end.json", end)
    (attempt / "end.json").chmod(0o644)


def worker(attempt):
    if pwd.getpwuid(os.geteuid()).pw_name != "leo":
        with patch.object(pace, "MODULE", MODULE):
            pace.execute(attempt)
        return
    plan = whole_iq.read(attempt / "plan.json")
    spec = plan["case"]
    whole_iq.checked(Path(spec["source"]) / "ready.json", spec["ready_sha256"])
    ledger = pace.readgz(whole_iq.checked(Path(plan["events"]), plan["events_sha256"]))
    with paced_original.configured(spec, paced_original.ORIGINAL, plan["assets"], ledger):
        replay(attempt, plan, ledger)


def run(work):
    candidate = whole_iq.checked(paced_original.REPORT / "source-lock.json", PARENT_SHA)
    parent = whole_iq.read(candidate)
    spec = dict(parent["cases"][CASE], cpu=CPU)
    data = spec["modes"][paced_original.ORIGINAL]
    path = whole_iq.checked(paced_original.REPORT / data["events"], data["sha256"])
    ready = Path(spec["source"]) / "ready.json"
    whole_iq.checked(ready, spec["ready_sha256"])
    forecast = REPORT.parent / "queue-selection/forecast-lock.json"
    programs = (
        Path(__file__),
        Path(rf_waiting.__file__),
        Path(paced_original.__file__),
        Path(pace.__file__),
        REPORT / "PROTOCOL.md",
    )
    write(REPORT / "events.json.gz", path.read_bytes())
    spec["modes"] = {MODE: dict(events="events.json.gz", sha256=_sha(path))}
    save_json(
        REPORT / "source-lock.json",
        dict(
            cases={CASE: spec},
            assets=parent["assets"],
            original_parent_sha256=PARENT_SHA,
            forecast_lock_sha256=_sha(forecast),
            programs={str(p): _sha(p) for p in programs},
            memory_max=whole_iq.MEMORY,
            memory_swap_max=0,
            waiting_slots=1,
            cap_s=pace.LIMIT_S,
        ),
    )
    with patch.object(pace, "MODULE", MODULE), patch.object(iq_service, "MODULE", MODULE):
        pace.launch(work / CASE / MODE, spec, MODE, parent["assets"], REPORT)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "worker"))
    parser.add_argument("work", type=local_output, nargs="?", default=WORK)
    args = parser.parse_args()
    (run if args.action == "run" else worker)(args.work)
