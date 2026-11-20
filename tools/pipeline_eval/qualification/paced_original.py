"""Measure the qualified original-quality and fast-wide receivers on a common live FIFO."""

import argparse
import json
import os
import pwd
from contextlib import ExitStack, closing, contextmanager
from itertools import islice
from pathlib import Path
from time import monotonic_ns, thread_time_ns
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from . import arrival_queue as pace
from . import capture_release, recording_to_v5
from . import paced_original_source as source
from .full_v5_check import _sha

CASE, REPORT = source.CASE, source.REPORT
WORK = Path("/var/tmp/leo-paced-original-20261119")
MODULE = "tools.pipeline_eval.qualification.paced_original"
ORIGINAL, WIDE = "original", "wide"
ORDER = (ORIGINAL, WIDE)
WIDE_PIN = "42136b7b48d910bf416772d7c7eb9e127dafb0ee5f54089c58d94820a05a9872"
WIDE_SHA = "db80b772cf9f52941cc0073067816e571308cb43c3096516b77f73ed54986c66"
WIDE_LIB = Path("/var/tmp/leo-on-hit-waveforms-20261119/libraries/DS29-0174/wide-stock.so")
CHECK_VISITS = 16
CLOCK = ("visit", "arrival_ns", "delivery_clock", "sample_start", "sample_end", "status")
PHYSICAL = (
    "visit",
    "sequence",
    "segment",
    "iq_sha256",
    "sample_start",
    "sample_end",
    "generation",
    "clock_anchor",
    "delivery_clock",
    "status",
    "input_bytes",
)


def packet(row):
    marks = ("detector_wall_s", "detector_cpu_s", "grid_calls")
    return {key: value for key, value in row.items() if key not in marks}


def references():
    from . import capture_whole as exact
    from .capture_whole_results import collect
    from .exact_wide_iq_results import detector_rows
    from .fifth_completion_results import native_data
    from .fresh_replay_results import sealed

    measured = sealed(source.ORIGINAL, "prediction-lock.json", source.CAPTURE_SEAL)
    current = whole_iq.read(source.ORIGINAL / "source-lock.json")
    whole_iq.checked(exact.WORK / "source-lock.json", measured["files"]["source-lock.json"])
    shards, workers, _ = collect(exact.WORK, current)
    if len(workers) != len(current["workers"]) or any(w["exit_code"] for w in workers.values()):
        raise ValueError("the complete original detector replay did not publish all shards")
    original = sorted(
        (packet(r) for _, rows in shards.values() for r in rows), key=lambda row: row["visit"]
    )
    original_doc = pace.readgz(source.ORIGINAL / "native.json.gz")
    wide_report = source.SCREEN / "receiver-core/full-stride"
    wide = sealed(wide_report, "prediction-lock.json", WIDE_PIN)
    previous = whole_iq.read(wide_report / "resources.json")[CASE]["control"]
    binding = previous["service"]["binding"]
    folder = Path(binding["attempt"])
    whole_iq.checked(folder / "plan.json", binding["plan_sha256"])
    whole_iq.checked(folder / "service.log", previous["service"]["log_sha256"])
    wide_raw = whole_iq.read(folder / "raw.json")
    member = f"native/control/{CASE}.json.gz"
    wide_doc = native_data(
        whole_iq.checked(wide_report / member, wide["files"][member]),
        wide_raw["native_sha256"].removeprefix("sha256:"),
    )
    wide_visits, _, _ = detector_rows(folder)
    if whole_iq.read(folder / "plan.json")["detector_sha256"] != WIDE_SHA:
        raise ValueError("fast-wide archive came from a different detector")
    data = {ORIGINAL: (original_doc, original), WIDE: (wide_doc, wide_visits)}
    stagespec = whole_iq.read(REPORT / "source-stage-lock.json")["input"]
    for doc, visits in data.values():
        if (
            [r["visit"] for r in visits] != list(range(source.COUNT))
            or [probe for row in visits for probe in row["probes"]] != doc["source"]["probes"]
            or doc["source"]["raw_recording_authority_digest"] != stagespec["raw_recording_sha256"]
            or [r["delivery_clock"] for r in visits] != doc["delivery_clocks"]
        ):
            raise ValueError(
                "the independently authentic full detector payload does not match its clock"
            )
    for left, right in zip(original, wide_visits, strict=True):
        if any(left[name] != right[name] for name in PHYSICAL):
            raise ValueError("original and fast-four packets come from different physical arrivals")
    return data, current


def bind_ledger(clock, raw):
    if len(clock) != len(raw):
        raise ValueError("candidate reference did not cover the full clock")
    events = []
    for due, packet in zip(clock, raw, strict=True):
        if any(due[k] != packet[k] for k in CLOCK if k != "arrival_ns"):
            raise ValueError("candidate reference changed timing or physical admission metadata")
        if due["status"] == "processed" and (
            [p["receiver_id"] for p in packet["probes"]] != [0, 1]
            or any(p["actual_rf_hz"] != due["center_hz"] for p in packet["probes"])
        ):
            raise ValueError(
                "complete original packet does not bind both physical receivers and RF"
            )
        events.append(dict(due, full_visit_sha256=pace.fingerprint(packet)))
    return events


def freeze(work):
    if work.exists() or (REPORT / "source-lock.json").exists():
        raise FileExistsError("this complete paired replay already has a frozen source")
    data, former = references()
    clock = pace.readgz(REPORT / "clock-events.json.gz")
    ready = whole_iq.read(source.SOURCE / "ready.json")
    files = ("ready.json", "members.json.gz")
    for name in files:
        write(REPORT / name, (source.SOURCE / name).read_bytes())
    staged = whole_iq.read(REPORT / "source-stage-lock.json")["input"]
    if (
        ready["raw_recording_sha256"] != staged["raw_recording_sha256"]
        or ready["windows"] != source.COUNT
        or ready["bytes"] != source.COUNT * source.spool.WINDOW_BYTES
        or former["producer"] != staged["producer"]
        or former["python"] != staged["python"]
    ):
        raise ValueError("ready IQ and original detector configuration differ")
    modes = {}
    for role in ORDER:
        name = f"{role}-events.json.gz"
        pace.writegz(REPORT / name, bind_ledger(clock, data[role][1]))
        modes[role] = dict(events=name, sha256=_sha(REPORT / name))
    programs = {
        str(path): _sha(path)
        for path in (
            Path(__file__),
            Path(pace.__file__),
            Path(source.__file__),
            Path(source.spool.__file__),
            REPORT / "PROTOCOL.md",
            REPORT / "clock-events.json.gz",
            REPORT / "source-stage-lock.json",
        )
    }
    spec = dict(
        staged,
        cpu=source.MAIN,
        modes=modes,
        source=str(source.SOURCE),
        ready_sha256=_sha(REPORT / "ready.json"),
        python_sha256=former["python_sha256"],
    )
    assets = dict(
        former["libraries"],
        control=dict(path=str(whole_iq.checked(WIDE_LIB, WIDE_SHA)), sha256=WIDE_SHA),
    )
    lock = dict(
        id=CASE,
        cases={CASE: spec},
        order=ORDER,
        cpus=[source.MAIN, source.STAGING],
        programs=former["sources"] | programs,
        assets=assets,
        memory_max=whole_iq.MEMORY,
        memory_swap_max=0,
        waiting_slots=1,
        limit_s=pace.LIMIT_S,
        measured_original=source.CAPTURE_SEAL,
        measured_wide=WIDE_PIN,
        source_cgroup=ready["end"]["cgroup"],
    )
    work.mkdir(mode=0o755, exist_ok=False)
    save_json(REPORT / "source-lock.json", lock)
    save_json(work / "launch-lock.json", dict(source_lock_sha256=_sha(REPORT / "source-lock.json")))


def original_visit(frame, analyze, policy, grid, valid):
    from .capture_detector_replay import scan_capture_window

    segment, window, bracket, delivery = frame

    def unexpected(*_):
        raise ValueError("a hardware-invalid arrival entered the original detector")

    tick, cpu = monotonic_ns(), thread_time_ns()
    if valid:
        # Only the detector consumer owns the grid. Invalid events use the policy path below.
        grid.calls.clear()
        status, probes = scan_capture_window(window, (0, 1), policy)
        if (
            status.status != "processed"
            or len(grid.calls) < 2
            or not all(row["applied"] for row in grid.calls)
        ):
            raise ValueError("original retained visit did not execute the qualified full grid")
        grid.calls.clear()
    else:
        status = analyze(window, (0, 1), None, policy, detector=unexpected)
        probes = []
        if status.status != "invalid_capture":
            raise ValueError("hardware-invalid sample support changed")
    elapsed = monotonic_ns() - tick, thread_time_ns() - cpu
    return dict(
        kind="visit",
        segment=segment,
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
        delivery_clock=delivery,
    ), elapsed


@contextmanager
def configured(spec, role, assets, ledger):
    base_detector = pace.build_native
    if _sha(Path(spec["python"])) != spec["python_sha256"]:
        raise ValueError("original capture Python identity changed")

    def source_windows(capture, verified):
        if capture != spec["capture"] or verified:
            raise ValueError("receiver can only read the single bound staged capture")
        with patch.object(source.spool, "COUNT", source.COUNT):
            yield from source.spool.packets(Path(spec["source"]))

    def detector(capture, mode, bindings, stack):
        return None if mode == ORIGINAL else base_detector(capture, "control", bindings, stack)

    with ExitStack() as stack:
        if role == ORIGINAL:
            from leo.analysis.starlink import acquisition

            from . import capture_exact_trial as original

            libs = {
                k: whole_iq.checked(Path(bindings["path"]), bindings["sha256"])
                for k, bindings in assets.items()
                if k != "control"
            }
            grid = original.capture_fft.FullGrid(libs["batched32"])
            stack.enter_context(original.refiners(libs))
            stack.enter_context(grid.route(acquisition, original.starts.screen_module()))

            def visit(frame, analyze, detect, policy):
                window = frame[1]
                due = ledger[int(window.acquisition["global_visit"])]
                valid = due["status"] == "processed"
                if valid and window.target["rf_center_hz"] != due["center_hz"]:
                    raise ValueError(
                        "original visit's current RF center differs from sealed metadata"
                    )
                return original_visit(frame, analyze, policy, grid, valid)

            stack.enter_context(patch.object(pace, "native_visit", visit))
        stack.enter_context(
            patch.multiple(pace, MODULE=MODULE, build_native=detector, packets=source_windows)
        )
        stack.enter_context(patch.object(pace.iq_service, "MODULE", MODULE))
        yield


def preflight(folder):
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window

    plan = whole_iq.read(folder / "source-lock.json")
    spec = plan["cases"][CASE]
    capture = spec["capture"]
    policy = FastScanPolicyV2()
    recording_to_v5._bind_producer(
        capture["case"], capture_release.producer(capture["case"], capture), policy
    )
    with (
        patch.object(source.spool, "COUNT", source.COUNT),
        closing(source.spool.packets(Path(spec["source"]))) as windows,
    ):
        frames = list(islice(windows, CHECK_VISITS))
    receipts = {}
    for role in ORDER:
        meta = spec["modes"][role]
        ledger = pace.readgz(whole_iq.checked(folder / meta["events"], meta["sha256"]))
        with configured(spec, role, plan["assets"], ledger), ExitStack() as stack:
            detector = pace.build_native(capture, role, plan["assets"], stack)
            matches = []
            for expected, frame in zip(ledger[:CHECK_VISITS], frames, strict=True):
                measured, timing = pace.native_visit(frame, analyze_window, detector, policy)
                digest = pace.fingerprint(measured)
                if digest != expected["full_visit_sha256"]:
                    raise ValueError(f"{role} did not reproduce complete visit {expected['visit']}")
                matches.append(
                    dict(
                        visit=expected["visit"],
                        status=expected["status"],
                        sha256=digest,
                        wall_ns=timing[0],
                        cpu_ns=timing[1],
                    )
                )
            receipts[role] = matches
    if {r["status"] for r in receipts[ORIGINAL]} != {"processed", "invalid_capture"}:
        raise ValueError("fixed short original preflight missed one hardware status")
    print(json.dumps(dict(case=CASE, examined=CHECK_VISITS, observed=receipts), indent=2))


def worker(attempt):
    if pwd.getpwuid(os.geteuid()).pw_name != "leo":
        with patch.object(pace, "MODULE", MODULE):
            pace.execute(attempt)
        return
    plan = whole_iq.read(attempt / "plan.json")
    spec = plan["case"]
    ready = whole_iq.read(
        whole_iq.checked(Path(spec["source"]) / "ready.json", spec["ready_sha256"])
    )
    if ready["raw_recording_sha256"] != spec["raw_recording_sha256"]:
        raise ValueError("receiver opened a different staged capture")
    ledger = pace.readgz(whole_iq.checked(attempt / "events.json.gz", plan["events_sha256"]))
    with configured(spec, plan["mode"], plan["assets"], ledger):
        pace.execute(attempt)


def run(work):
    plan = pace.plan(work, REPORT)
    smoke = whole_iq.read(REPORT / "preflight.json")
    if [*smoke["observed"]] != list(ORDER) or smoke["examined"] != CHECK_VISITS:
        raise ValueError("both real raw branches must pass the declared prefix")
    with patch.object(pace, "MODULE", MODULE), patch.object(pace.iq_service, "MODULE", MODULE):
        for role in ORDER:
            group = plan["source_cgroup"]
            charge = dict(start=source.spool.charge(group))
            pace.launch(work / CASE / role, plan["cases"][CASE], role, plan["assets"], REPORT)
            charge["end"] = source.spool.charge(group)
            save_json(REPORT / f"raw/{role}/source-charge.json", charge)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "preflight", "run", "worker"))
    parser.add_argument("work", type=local_output, nargs="?", default=WORK)
    args = parser.parse_args()
    {"freeze": freeze, "preflight": preflight, "run": run, "worker": worker}[args.action](args.work)
