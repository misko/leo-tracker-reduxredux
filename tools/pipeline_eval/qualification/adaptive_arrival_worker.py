"""Run one authenticated radio stream through a real bounded detector queue."""

import json
import os
import pwd
import sys
from contextlib import ExitStack
from pathlib import Path
from queue import Queue
from threading import Event, Lock, Thread
from time import monotonic_ns, sleep

from .. import whole_iq
from ..__main__ import THREAD_ENV, encoded, save_json
from ..variants.arrival_policy import ArrivalPolicy
from . import arrival_queue as pace
from . import capture_release, recording_to_v5
from .full_v5_check import _sha
from .whole_memory_chain_worker import mark

MODULE = "tools.pipeline_eval.qualification.adaptive_arrival"


def detector_calls(capture, assets, mode, stack):
    import numpy as np

    from leo.analysis.starlink.native_short_window import NativeShortWindow
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame

    from ..variants.center_union import DifferentialUnionCall
    from ..variants.differential_runtime_fft import FftScout

    fs = 10_000_000
    edge = capture["edge"]
    lib = assets["candidate"]
    detector = stack.enter_context(
        NativeShortWindow(
            str(whole_iq.checked(Path(lib["path"]), lib["sha256"])),
            np.asarray(qin_edge_pilot_frame(fs, edge), dtype="<c16"),
            np.asarray(
                qin_edge_pilot_frame(fs, edge, symbol_roll=CONTROL_SYMBOL_ROLL), dtype="<c16"
            ),
            sample_rate_hz=fs,
            receiver_count=2,
            fractional_epoch=True,
        )
    )
    calls = {"stock": detector.analyze}
    if mode != "stock":
        lib = assets["scout"]
        scout = stack.enter_context(
            FftScout(whole_iq.checked(Path(lib["path"]), lib["sha256"]), edge)
        )
        fifth = DifferentialUnionCall(detector, edge, scout=scout)
        calls["fifth"] = lambda samples: fifth(samples, decode=detector.analyze)[0]
    return calls


def matching_clock(frame, event):
    _, window, _, clock = frame
    acquisition = window.acquisition
    if (
        int(acquisition["global_visit"]),
        acquisition["sample_start"],
        acquisition["sample_end"],
        clock,
    ) != (event["visit"], event["sample_start"], event["sample_end"], event["delivery_clock"]):
        raise ValueError("recorded arrival clock or sample interval changed")


def execute(attempt):
    if pwd.getpwuid(os.geteuid()).pw_name != "leo":
        os.execv(
            "/usr/bin/sudo",
            [
                "sudo",
                "-n",
                "-u",
                "leo",
                "--",
                "env",
                f"TMPDIR={attempt}",
                f"PYTHONPATH={os.environ['PYTHONPATH']}",
                *(f"{k}={v}" for k, v in THREAD_ENV.items()),
                str(recording_to_v5.ARCHIVE_PYTHON),
                "-B",
                "-m",
                MODULE,
                "worker",
                str(attempt),
            ],
        )
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window

    request = json.loads((attempt / "plan.json").read_bytes())
    spec = request["case"]
    capture = spec["capture"]
    start = mark("adaptive detector initialized")
    if start["cpus"] != [spec["cpu"]] or start["nice"] < 10:
        raise ValueError("detector did not start on the assigned host core")
    if not Path(analyze_window.__code__.co_filename).is_relative_to(spec["producer"]):
        raise ValueError("the recorded waveforms require their pinned decoder")
    policy = FastScanPolicyV2()
    recording_to_v5._bind_producer(
        capture["case"], capture_release.producer(capture["case"], capture), policy
    )
    rows = pace.readgz(whole_iq.checked(attempt / "events.json.gz", request["events_sha256"]))
    source, inbox = Queue(maxsize=pace.PREFETCH), Queue(maxsize=2)
    primed, done = Event(), Event()
    admission = ArrivalPolicy(request["mode"])
    failures, verified, iq_hashes = [], [], []

    def prefetch():
        try:
            for frame in pace.packets(capture, verified):
                source.put((monotonic_ns(), frame))
                if source.full():
                    primed.set()
            source.put(None)
        except Exception as exc:
            failures.append(exc)
        finally:
            primed.set()

    with ExitStack() as stack:
        calls = detector_calls(capture, request["assets"], request["mode"], stack)
        output = stack.enter_context((attempt / "visits.jsonl").open("x", buffering=1))
        log_lock = Lock()

        def emit(event):
            with log_lock:
                output.write(encoded(event).decode() + "\n")

        def process(frame, event, selected, expected):
            started = monotonic_ns() - origin
            packet, (wall, cpu) = pace.native_visit(
                frame, analyze_window, calls[selected or "stock"], policy
            )
            actual = pace.fingerprint(packet)
            if actual != expected:
                raise ValueError(f"visit {event['visit']} does not reproduce its selected detector")
            emitted = monotonic_ns() - origin
            if selected:
                admission.finish()
            emit(
                dict(
                    event,
                    policy=selected,
                    actual_sha256=actual,
                    native_wall_ns=wall,
                    native_cpu_ns=cpu,
                    started_ns=started,
                    emitted_ns=emitted,
                    outcome="emitted" if selected else "invalid_capture",
                )
            )

        def consume():
            try:
                while (item := inbox.get()) is not None:
                    process(*item)
            except Exception as exc:
                failures.append(exc)
            finally:
                done.set()

        Thread(target=prefetch, daemon=True).start()
        if not primed.wait(15) or failures:
            raise RuntimeError(f"could not prefetch archived radio stream {failures}")
        origin = monotonic_ns() + 50_000_000
        Thread(target=consume, daemon=True).start()
        for row in rows:
            item = source.get(timeout=5)
            if item is None or failures:
                raise RuntimeError(f"radio stream ended early {failures}")
            ready, frame = item
            matching_clock(frame, row)
            iq_hashes.append(frame[1].iq_sha256)
            remaining = origin + row["arrival_ns"] - monotonic_ns()
            if remaining > 0:
                sleep(remaining / pace.NS)
            event = {
                k: row[k] for k in ("visit", "arrival_ns", "sample_start", "sample_end", "status")
            }
            event.update(available_ns=ready - origin, released_ns=monotonic_ns() - origin)
            if row["status"] == "invalid_capture":
                process(frame, event, None, row["stock"])
                continue
            before, selected = admission.admit()
            event["outstanding_at_admission"] = before
            if selected:
                inbox.put_nowait((frame, event, selected, row[selected]))
            else:
                emit(dict(event, outcome="queue_drop", policy=None))
        if source.get(timeout=15) is not None:
            raise ValueError("extra decoded frames beyond original capture")
        inbox.put(None, timeout=5)
        if not done.wait(10) or failures:
            raise RuntimeError(f"detector queue did not drain {failures}")
    digest = recording_to_v5.digest([capture["input_manifest_sha256"], iq_hashes])
    if digest != spec["raw_recording_sha256"]:
        raise ValueError("complete physical sample hash chain changed")
    save_json(
        attempt / "end.json",
        dict(
            start=start,
            end=mark("detector drained"),
            output_sha256=_sha(attempt / "visits.jsonl"),
            raw_recording_sha256=digest,
            compressed_chunks=len(verified),
            compressed_bytes=sum(verified),
        ),
    )
    (attempt / "end.json").chmod(0o644)


if __name__ == "__main__":
    execute(Path(sys.argv[1]))
