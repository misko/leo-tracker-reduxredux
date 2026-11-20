"""Measure matched midpoint native calls on fixed cores without running position."""

import argparse
import gzip
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from uuid import uuid4

from .. import whole_iq
from ..__main__ import ROOT, THREAD_ENV, encoded, local_output, save_json, write
from . import arrival_queue as pace
from . import whole_incremental_trial as incremental
from .full_v5_check import BULK, _sha

WIDTH = 128
CPUS = {"DS26-0197": 20, "DS29-0316": 21}
MODES = (*pace.MODES, "incremental")
MODULE = "tools.pipeline_eval.qualification.arrival_queue_cost"


def extra_events(incremental_sha, report=pace.REPORT):
    root = incremental.REPORT
    lock = whole_iq.read(whole_iq.checked(root / "prediction-lock.json", incremental_sha))

    def file(name):
        return whole_iq.checked(root / name, lock["files"][name])

    result = {i: [] for i in CPUS}
    with gzip.open(file("visits.jsonl.gz"), "rt") as rows:
        for line in rows:
            row = json.loads(line)
            if row["role"] == "incremental":
                result[row["id"]].append(row)
    for ident in result:
        doc = pace.readgz(file(f"{ident}-native.json.gz"))
        # Incremental publishes only measured valid timings. The shared original
        # capture exclusions use unchanged clock and packet measurements.
        stock = pace.readgz(report / f"{ident}-control-events.json.gz")
        result[ident].extend(row for row in stock if row["status"] == "invalid_capture")
        result[ident] = pace.reference_events(doc, sorted(result[ident], key=lambda r: r["visit"]))
    return result, whole_iq.read(file("candidate-lock.json"))["assets"]


def incremental_native(capture, assets, stack):
    import numpy as np

    from leo.analysis.starlink.native_short_window import NativeShortWindow
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame

    from ..variants.incremental_rescue import IncrementalRescueCall, SingleLaneScout

    edge, fs = capture["edge"], 10_000_000
    path = whole_iq.checked(Path(assets["detector"]["path"]), assets["detector"]["sha256"])
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
    scout_path = whole_iq.checked(Path(assets["scout"]["path"]), assets["scout"]["sha256"])
    scout = stack.enter_context(SingleLaneScout(scout_path, edge))
    invoke = IncrementalRescueCall(detector, edge, scout=scout)
    return lambda samples: invoke(samples, decode=detector.analyze)[0]


def window_roster(capture, first, last):
    start, verified = 0, []
    case = capture["case"]
    for index, loc in enumerate(case["recording"]["segments"]):
        manifest = whole_iq.read(whole_iq.checked(BULK / loc["path"], loc["sha256"]))
        end = start + manifest["window_count"]
        if start < last and end > first:
            sub = dict(capture, case=dict(case, recording=dict(case["recording"], segments=[loc])))
            for _, raw, anchor, clock in pace.packets(sub, verified):
                visit = int(raw.acquisition["global_visit"])
                if first <= visit < last:
                    yield index, raw, anchor, clock
        start = end


def measure(spec):
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window

    if os.sched_getaffinity(0) != {spec["cpu"]} or not Path(
        analyze_window.__code__.co_filename
    ).is_relative_to(spec["producer"]):
        raise ValueError("matched runtime changed core or recorded raw implementation")
    policy = FastScanPolicyV2()
    capture = spec["capture"]
    pace.recording_to_v5._bind_producer(
        capture["case"], pace.capture_release.producer(capture["case"], capture), policy
    )
    first, last = spec["first"], spec["last"]
    result = []
    with ExitStack() as stack:
        runners = {m: pace.build_native(capture, m, spec["assets"], stack) for m in pace.MODES}
        runners["incremental"] = incremental_native(capture, spec["incremental_assets"], stack)
        for step, frame in enumerate(window_roster(capture, first, last)):
            pos = step % len(MODES)
            if step == 0:
                for detect in runners.values():
                    pace.native_visit(frame, analyze_window, detect, policy)
            for order, mode in enumerate(MODES[pos:] + MODES[:pos]):
                envelope, (wall, cpu) = pace.native_visit(
                    frame, analyze_window, runners[mode], policy
                )
                digest = pace.fingerprint(envelope)
                if envelope["visit"] != first + step or digest != spec["digests"][mode][step]:
                    raise ValueError(f"matched {mode} disagrees with sealed complete native packet")
                result.append(
                    dict(
                        visit=envelope["visit"],
                        mode=mode,
                        order=order,
                        status=envelope["status"],
                        iq_sha256=envelope["iq_sha256"],
                        sample_start=envelope["sample_start"],
                        envelope_sha256=digest,
                        detector_wall_ns=wall,
                        detector_cpu_ns=cpu,
                    )
                )
    if len(result) != WIDTH * len(MODES):
        raise ValueError("all native paths must use the full continuous midpoint roster")
    return result


def probe(work, report, incremental_sha):
    pin = pace.plan(work, report)
    extras, assets = extra_events(incremental_sha, report)
    cases = {}
    for ident, spec in pin["cases"].items():
        rows = {
            m: pace.readgz(whole_iq.checked(report / d["events"], d["sha256"]))
            for m, d in spec["modes"].items()
        }
        rows["incremental"] = extras[ident]
        first = len(rows["control"]) // 2 - WIDTH // 2
        last = first + WIDTH
        cases[ident] = dict(
            spec,
            cpu=CPUS[ident],
            first=first,
            last=last,
            incremental_assets=assets,
            assets=pin["assets"],
            digests={
                m: [r["full_visit_sha256"] for r in sequence[first:last]]
                for m, sequence in rows.items()
            },
        )
    path = report / "same-core-lock.json"
    save_json(
        path,
        dict(
            cases=cases,
            programmes_sha256=_sha(Path(__file__)),
            incremental_parent_sha256=incremental_sha,
            main_source_lock_sha256=_sha(report / "source-lock.json"),
        ),
    )

    def run(ident):
        spec = cases[ident]
        unit = "leo-arrival-cost-" + uuid4().hex[:12]
        command = [
            "systemd-run",
            "--user",
            "--wait",
            "--pipe",
            "--quiet",
            f"--unit={unit}",
            "--property=Nice=10",
            "--property=RuntimeMaxSec=75s",
            "--property=MemoryMax=512M",
            "--property=MemorySwapMax=0",
            "--property=KillMode=control-group",
            "taskset",
            "-c",
            str(spec["cpu"]),
            "sudo",
            "-n",
            "-u",
            "leo",
            "--",
            "env",
            f"PYTHONPATH={spec['producer']}:{ROOT}",
            *(f"{k}={v}" for k, v in THREAD_ENV.items()),
            str(pace.recording_to_v5.ARCHIVE_PYTHON),
            "-B",
            "-m",
            MODULE,
            "worker",
        ]
        receipt = subprocess.run(command, input=encoded(spec), capture_output=True, timeout=90)
        write(report / f"{ident}-same-core-service.log", receipt.stderr)
        receipt.check_returncode()
        evidence = json.loads(receipt.stdout)
        return [dict(id=ident, cpu=spec["cpu"], **r) for r in evidence]

    with ThreadPoolExecutor(max_workers=2) as pool:
        measured = [row for trial in pool.map(run, CPUS) for row in trial]
    pace.writegz(report / "same-core-visits.json.gz", measured)


if __name__ == "__main__":
    if sys.argv[1:] == ["worker"]:
        print(json.dumps(measure(json.load(sys.stdin)), allow_nan=False))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("work", type=local_output)
        parser.add_argument("--incremental-sha256", required=True)
        parser.add_argument("--out", type=local_output, default=pace.REPORT)
        args = parser.parse_args()
        probe(args.work, args.out, args.incremental_sha256)
