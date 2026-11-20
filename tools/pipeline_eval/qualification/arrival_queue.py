"""Replay authenticated native inputs at their captured host-delivery times."""

import argparse
import gzip
import json
import os
import pwd
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from queue import Queue
from threading import BoundedSemaphore, Event, Lock, Thread
from time import monotonic_ns, sleep, thread_time_ns
from unittest.mock import patch
from uuid import uuid4

from .. import iq_service, whole_iq
from ..__main__ import ROOT, THREAD_ENV, encoded, local_output, save_json, write
from . import capture_release, recording_to_v5, whole_center_union
from .full_v5_check import BULK, _sha
from .whole_memory_chain_worker import AuthenticatedMember, mark

PARENT = whole_center_union.REPORT
REPORT = PARENT.with_name("arrival-queue")
CPUS = {"DS26-0197": 18, "DS29-0316": 19}
MODES = ("control", "candidate")
LIMIT_S = 350
WAITING = 1
PREFETCH = 8
NS = 10**9
MODULE = "tools.pipeline_eval.qualification.arrival_queue"


def fingerprint(item):
    return sha256(encoded(item)).hexdigest()


def readgz(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def writegz(path, value):
    write(path, gzip.compress(encoded(value), mtime=0))


def reference_events(doc, visits):
    clocks = doc["delivery_clocks"]
    provenance, source = doc["provenance"], doc["source"]
    invalid = {row["visit"]: row for row in provenance["excluded_windows"]}
    counters = {}
    for p in source["probes"]:
        start = counters.setdefault(p["visit_index"], p["valid_start_counter"])
        if start != p["valid_start_counter"]:
            raise ValueError("the two physical lanes have different native sample counters")
    if (
        len(clocks) != len(visits)
        or len(clocks) != provenance["window_count"]
        or counters.keys() & invalid.keys()
        or counters.keys() | invalid.keys() != set(range(len(clocks)))
    ):
        raise ValueError("full receipt lacks capture and detector clock coverage")
    first = clocks[0]["monotonic_ns"]
    width = source["probe_ms"] * source["sample_rate_hz"] // 1000
    rows = []
    for i, (row, clock) in enumerate(zip(visits, clocks, strict=True)):
        bad = invalid.get(i)
        status = "invalid_capture" if bad else "processed"
        if (row["visit"], row["status"]) != (i, status):
            raise ValueError("sealed timing row has a different visit or hardware exclusion")
        start = bad["sample_start"] if bad else counters[i]
        arrival = clock["monotonic_ns"] - first
        if rows and arrival < rows[-1]["arrival_ns"]:
            raise ValueError("host delivery clocks must be monotonic")
        rows.append(
            dict(
                visit=i,
                arrival_ns=arrival,
                delivery_clock=clock,
                sample_start=start,
                sample_end=bad["sample_end"] if bad else start + width,
                status=status,
                full_visit_sha256=row["full_visit_sha256"],
                detector_cpu_ns=round((row.get("cpu_s") or 0) * NS),
                detector_wall_ns=round((row.get("wall_s") or 0) * NS),
            )
        )
    return rows


def stage(work, report, parent_sha):
    lock_path = PARENT / "prediction-lock.json"
    lock = whole_iq.read(whole_iq.checked(lock_path, parent_sha))
    if set(lock["cases"]) != CPUS.keys():
        raise ValueError("the source study changed the matched physical cases")

    def checked(name):
        return whole_iq.checked(PARENT / name, lock["files"][name])

    parent = whole_iq.read(checked("source-lock.json"))
    active = whole_iq.read(checked("candidate-lock-v2.json"))
    assets = dict(control=parent["detectors"]["control"], **active["assets"])
    for row in assets.values():
        whole_iq.checked(Path(row["path"]), row["sha256"])
    by_run = defaultdict(list)
    with gzip.open(checked("visits.jsonl.gz"), "rt") as visits:
        for raw in visits:
            row = json.loads(raw)
            by_run[row["id"], row["role"]].append(row)
    if work.exists() or (report / "source-lock.json").exists():
        raise FileExistsError("this prospective paced replay already exists")
    work.mkdir(parents=True)
    cases = {}
    for ident, cpu in CPUS.items():
        case, _ = whole_iq.binding(ident)
        capture = dict(
            capture_release.read_capture(case),
            case=case,
            segments_sha256=recording_to_v5.digest(case["recording"]["segments"]),
        )
        if (
            case["recording"] != parent["cases"][ident]["recording"]
            or capture["input_manifest_sha256"] != parent["cases"][ident]["clock_authority"]
        ):
            raise ValueError("saved physical capture differs from the completed controls")
        producer = capture_release.producer(case, capture)
        headers, names = {}, {}
        for mode in MODES:
            name = f"native/{mode}/{ident}.json.gz"
            doc = readgz(checked(name))
            if doc["source"]["session_id"] != case["session_id"] or (
                doc["provenance"]["detector_sha256"] != "sha256:" + assets[mode]["sha256"]
            ):
                raise ValueError("published native factors used different capture or detector")
            rows = reference_events(doc, sorted(by_run[ident, mode], key=lambda r: r["visit"]))
            name = f"{ident}-{mode}-events.json.gz"
            writegz(report / name, rows)
            names[mode] = dict(events=name, sha256=_sha(report / name))
            headers[mode] = [
                doc["clock_anchor"],
                doc["last_sample_counter"],
                doc["source"]["raw_recording_authority_digest"],
            ]
        if headers[MODES[0]] != headers[MODES[1]]:
            raise ValueError("native arms have different raw capture authority")
        cases[ident] = dict(
            cpu=cpu,
            capture=capture,
            producer=str(producer.root),
            modes=names,
            raw_recording_sha256=headers["control"][2],
        )
    programs = (
        Path(__file__),
        Path(recording_to_v5.__file__),
        Path(capture_release.__file__),
        report / "PROTOCOL.md",
    )
    path = report / "source-lock.json"
    save_json(
        path,
        dict(
            parent_prediction_sha256=parent_sha,
            cases=cases,
            assets=assets,
            programs={str(p): _sha(p) for p in programs},
            cap_s=LIMIT_S,
            memory_max=whole_iq.MEMORY,
            memory_swap_max=0,
            waiting_slots=WAITING,
            decoder_prefetch=PREFETCH,
        ),
    )
    save_json(work / "launch-lock.json", {"source_lock_sha256": _sha(path)})


def packets(capture, verified):
    from leo.storage import short_window
    from leo.storage.fast_scan import FastSegmentSource

    manifest_member = short_window.ShortWindowReader._member

    def bounded(reader, name, size, digest):
        if any(chunk.payload_relative_path == name for chunk in reader.manifest.chunks):
            path = short_window.confined_path(reader.path, reader.path / name, must_exist=True)
            return AuthenticatedMember(path, size, digest, verified)
        return manifest_member(reader, name, size, digest)

    with patch.object(short_window.ShortWindowReader, "_member", bounded):
        for index, locator in enumerate(capture["case"]["recording"]["segments"]):
            manifest = whole_iq.checked(BULK / locator["path"], locator["sha256"])
            source = FastSegmentSource(
                dict(path=str(manifest.parent), manifest_digest="sha256:" + locator["sha256"])
            )
            if source.receiver_ids != (0, 1):
                raise ValueError("the paced physical stream requires both recorded receivers")
            for window in source.windows():
                acquisition = window.acquisition
                if window.target["edge"] != capture["edge"]:
                    raise ValueError("saved IQ changes the physical template edge")
                rtune = json.loads(acquisition.get("retune_receipt") or "{}")
                yield (
                    index,
                    window,
                    rtune.get("utc_clock_bracket"),
                    rtune.get("host_delivery_clock"),
                )


def build_native(capture, mode, assets, stack):
    import numpy as np

    from leo.analysis.starlink.native_short_window import NativeShortWindow
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame

    edge, fs = capture["edge"], 10_000_000
    lib = assets[mode]
    path = whole_iq.checked(Path(lib["path"]), lib["sha256"])
    exact = np.asarray(qin_edge_pilot_frame(fs, edge), dtype="<c16")
    control = np.asarray(
        qin_edge_pilot_frame(fs, edge, symbol_roll=CONTROL_SYMBOL_ROLL), dtype="<c16"
    )
    detector = stack.enter_context(
        NativeShortWindow(
            str(path),
            exact,
            control,
            sample_rate_hz=fs,
            receiver_count=2,
            fractional_epoch=True,
        )
    )
    if mode == "control":
        return detector.analyze
    from ..variants.center_union import DifferentialUnionCall
    from ..variants.differential_runtime_fft import FftScout

    scout = assets["scout"]
    scorer = stack.enter_context(
        FftScout(whole_iq.checked(Path(scout["path"]), scout["sha256"]), edge)
    )
    invoke = DifferentialUnionCall(detector, edge, scout=scorer)
    return lambda samples: invoke(samples, decode=detector.analyze)[0]


def native_visit(frame, analyze, detect, policy):
    from leo.contracts.fast_scan import FastScanReceiverV1

    index, window, bracket, clock = frame
    probes = []
    timing = [0, 0]

    def run_native(w, receivers):
        start, cpu = monotonic_ns(), thread_time_ns()
        output = detect(w.samples)
        timing[:] = [monotonic_ns() - start, thread_time_ns() - cpu]
        if [r["receiver_id"] for r in output["rows"]] != [0, 1]:
            raise ValueError("unexpected native physical lane enumeration")
        for row in output["rows"]:
            candidates = (
                recording_to_v5._from_native(k, item) for k, item in enumerate(row["candidates"])
            )
            probes.append(recording_to_v5._probe(w, receivers[row["receiver_id"]], candidates))
        return tuple(FastScanReceiverV1(receiver_id=rx, candidates=()) for rx in receivers)

    status = analyze(window, (0, 1), None, policy, detector=run_native)
    envelope = dict(
        kind="visit",
        segment=index,
        sequence=window.sequence,
        visit=int(window.acquisition["global_visit"]),
        iq_sha256=window.iq_sha256,
        sample_start=status.sample_start,
        sample_end=status.sample_end,
        generation=status.generation,
        status=status.status,
        reason=status.reason,
        rf_mapping_authority=status.rf_mapping_authority,
        probes=probes,
        input_bytes=window.samples.nbytes,
        clock_anchor=bracket,
        delivery_clock=clock,
    )
    return envelope, timing


def execute(attempt):
    if pwd.getpwuid(os.geteuid()).pw_name != "leo":
        # The same read-only archive user runs the unpaced reference reader.
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
                *(f"{name}={value}" for name, value in THREAD_ENV.items()),
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

    plan = whole_iq.read(attempt / "plan.json")
    meta, mode = plan["case"], plan["mode"]
    start = mark("arrival replay initialize")
    save_json(attempt / "worker-start.json", start)
    (attempt / "worker-start.json").chmod(0o644)
    if start["cpus"] != [meta["cpu"]] or start["nice"] < 10:
        raise ValueError("the paced pipeline must use its predeclared single core")
    if not Path(analyze_window.__code__.co_filename).is_relative_to(meta["producer"]):
        raise ValueError("saved-IQ reader imported from an unfrozen runtime")
    capture = meta["capture"]
    policy = FastScanPolicyV2()
    recording_to_v5._bind_producer(
        capture["case"], capture_release.producer(capture["case"], capture), policy
    )
    rows = readgz(whole_iq.checked(Path(plan["events"]), plan["events_sha256"]))
    ready, inbox = Queue(maxsize=PREFETCH), Queue(maxsize=WAITING + 1)
    occupancy, warm, closed = BoundedSemaphore(WAITING + 1), Event(), Event()
    failures, verified, iq_hashes = [], [], []
    source_started = monotonic_ns()

    def prefetch():
        try:
            for frame in packets(capture, verified):
                ready.put((monotonic_ns(), frame))
                if ready.full():
                    warm.set()
            ready.put(None)
        except Exception as exc:
            failures.append(exc)
        finally:
            warm.set()

    with ExitStack() as stack:
        detector = build_native(capture, mode, plan["assets"], stack)
        output = stack.enter_context((attempt / "visits.jsonl").open("x", buffering=1))
        output_lock = Lock()

        def emit(row):
            with output_lock:
                output.write(encoded(row).decode() + "\n")

        def solve(frame, row, *, admitted):
            entered = monotonic_ns() - origin
            packet, (wall, cpu) = native_visit(frame, analyze_window, detector, policy)
            expected = row["full_visit_sha256"]
            if fingerprint(packet) != expected:
                raise ValueError(f"paced native envelope differs at physical visit {row['visit']}")
            end = monotonic_ns() - origin
            if admitted:
                occupancy.release()
            emit(
                dict(
                    row,
                    started_ns=entered,
                    emitted_ns=end,
                    native_wall_ns=wall,
                    native_cpu_ns=cpu,
                    outcome="emitted" if admitted else "invalid_capture",
                )
            )

        def consume():
            try:
                while (job := inbox.get()) is not None:
                    solve(*job, admitted=True)
            except Exception as exc:
                failures.append(exc)
            finally:
                closed.set()

        read_ahead = Thread(target=prefetch, daemon=True)
        worker = Thread(target=consume, daemon=True)
        read_ahead.start()
        if not warm.wait(15) or failures:
            raise RuntimeError(f"IQ prefetch did not start {failures}")
        origin = monotonic_ns() + 50_000_000
        worker.start()
        for row in rows:
            item = ready.get(timeout=5)
            if item is None or failures:
                raise RuntimeError(f"raw stream stopped before completing the recording {failures}")
            available, frame = item
            _, window, _, clock = frame
            w = window.acquisition
            if (int(w["global_visit"]), w["sample_start"], w["sample_end"], clock) != (
                row["visit"],
                row["sample_start"],
                row["sample_end"],
                row["delivery_clock"],
            ):
                raise ValueError(
                    "sample counter/clock changed between live arrival and prior archive"
                )
            iq_hashes.append(window.iq_sha256)
            remaining = origin + row["arrival_ns"] - monotonic_ns()
            if remaining > 0:
                sleep(remaining / NS)
            event = dict(row, available_ns=available - origin, released_ns=monotonic_ns() - origin)
            if row["status"] == "invalid_capture":
                solve(frame, event, admitted=False)
            elif occupancy.acquire(blocking=False):
                inbox.put_nowait((frame, event))
            else:
                emit(dict(event, outcome="queue_drop"))
        if ready.get(timeout=15) is not None:
            raise ValueError("unaccounted raw input at end of paced capture")
        inbox.put(None, timeout=5)
        if not closed.wait(10) or failures:
            raise RuntimeError(f"paced detector did not finish its FIFO {failures}")
    if (
        recording_to_v5.digest([capture["input_manifest_sha256"], iq_hashes])
        != meta["raw_recording_sha256"]
    ):
        raise ValueError("physical IQ digest changed across the scheduled replay")
    save_json(
        attempt / "end.json",
        dict(
            start=start,
            end=mark("paced detector drained"),
            count=len(rows),
            compressed_chunks=len(verified),
            compressed_bytes=sum(verified),
            prefetch_start_ns=source_started,
            pace_origin_ns=origin,
            exact_iq_manifest=True,
            output_sha256=_sha(attempt / "visits.jsonl"),
        ),
    )
    (attempt / "end.json").chmod(0o644)


def plan(work, report):
    path = report / "source-lock.json"
    lock = whole_iq.read(
        whole_iq.checked(path, whole_iq.read(work / "launch-lock.json")["source_lock_sha256"])
    )
    for name, digest in lock["programs"].items():
        whole_iq.checked(Path(name), digest)
    for asset in lock["assets"].values():
        whole_iq.checked(Path(asset["path"]), asset["sha256"])
    return lock


def launch(out, spec, mode, assets, report):
    out.mkdir(parents=True, exist_ok=False)
    data = spec["modes"][mode]
    source = whole_iq.checked(report / data["events"], data["sha256"])
    events = out / "events.json.gz"
    write(events, source.read_bytes())
    events.chmod(0o644)
    save_json(
        out / "plan.json",
        dict(
            case=spec,
            mode=mode,
            assets=assets,
            events=str(events),
            events_sha256=data["sha256"],
            cpus=[spec["cpu"]],
            limit_s=LIMIT_S,
        ),
    )
    (out / "plan.json").chmod(0o644)
    subprocess.run(["setfacl", "-m", "u:leo:rwx", str(out)], check=True)
    unit = "leo-iq-bench-" + uuid4().hex[:12]
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        "--unit=" + unit,
        f"--working-directory={ROOT}",
        f"--property=MemoryMax={whole_iq.MEMORY}",
        "--property=MemorySwapMax=0",
        "--property=Nice=10",
        "--property=KillMode=control-group",
        f"--property=RuntimeMaxSec={LIMIT_S}s",
        f"--setenv=TMPDIR={out}",
        f"--setenv=PYTHONPATH={spec['producer']}:{ROOT}",
        *(f"--setenv={key}={value}" for key, value in THREAD_ENV.items()),
        "taskset",
        "-c",
        str(spec["cpu"]),
        sys.executable,
        "-B",
        "-m",
        MODULE,
        "worker",
        str(out),
    ]
    receipt = iq_service.run(out, command, unit, timeout=LIMIT_S + 20)
    print(
        out.parent.name,
        mode,
        "ok" if iq_service.succeeded(receipt) and (out / "end.json").is_file() else "failed",
        flush=True,
    )


def replay(work, report):
    lock = plan(work, report)

    def run(ident):
        spec = lock["cases"][ident]
        for mode in MODES:
            launch(work / ident / mode, spec, mode, lock["assets"], report)

    with (
        patch.object(iq_service, "MODULE", MODULE),
        ThreadPoolExecutor(max_workers=len(CPUS)) as pool,
    ):
        list(pool.map(run, CPUS))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    setup = sub.add_parser("freeze")
    setup.add_argument("work", type=local_output)
    setup.add_argument("--parent-sha256", required=True)
    setup.add_argument("--out", type=local_output, default=REPORT)
    run = sub.add_parser("replay")
    run.add_argument("work", type=local_output)
    run.add_argument("--out", type=local_output, default=REPORT)
    sub.add_parser("worker").add_argument("attempt", type=local_output)
    args = parser.parse_args()
    if args.action == "freeze":
        stage(args.work, args.out, args.parent_sha256)
    elif args.action == "replay":
        replay(args.work, args.out)
    else:
        execute(args.attempt)


if __name__ == "__main__":
    main()
