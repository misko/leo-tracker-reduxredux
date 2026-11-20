"""Replay a complete sealed dual-IQ recording through the staggered native detector."""

import argparse
import os
import subprocess
import sys
from itertools import groupby
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from .. import iq_service, whole_iq
from ..__main__ import ROOT, local_output, save_json
from . import arrival_queue, capture_release, recording_to_v5
from .fractional_runtime_whole import verify_request
from .full_v5_check import BULK, _sha
from .whole_memory_chain_worker import mark

REPORT = arrival_queue.REPORT.parents[1] / "receiver-choice/staggered-whole"
PARENT = REPORT.with_name("fresh-panel")
PARENT_SOURCE_SHA256 = "3c242cadc057614759a17a66959ee2dd4cedd739392d65756c68d2df63ea3f18"
CASES = ("DS26-0144", "DS29-0491")
MAIN, HELPER = 18, 19
LIMIT_S = 480
METHOD = "staggered_native_whole"
MODULE = "tools.pipeline_eval.qualification.staggered_whole"
WRAPPER = ROOT / "tools/pipeline_eval/variants/staggered_native.py"
LIBRARIES = ("libleo-staggered-native.so", "libleo-adaptive-detector.so.1")


def run_visit(frame, state, port, analyze_window, policy):
    rf = frame[1].target["rf_center_hz"]
    telemetry = None

    def detect(samples):
        nonlocal telemetry
        lane = state.reserve(rf, valid=True)
        output, profile = port.mixed(samples, lane, trace=True)
        if profile["fifth_lane"] != lane or [row["cpu"] for row in profile["lanes"]] != [
            MAIN,
            HELPER,
        ]:
            raise ValueError("a detector lane left its assigned physical CPU")
        telemetry = profile
        return output

    packet, _ = arrival_queue.native_visit(frame, analyze_window, detect, policy)
    if (telemetry is not None) != (packet["status"] == "processed"):
        raise ValueError("staggered dispatch must advance on one valid native visit only")
    receipt = dict(
        visit=packet["visit"],
        status=packet["status"],
        rf_center_hz=rf,
        sample_start=packet["sample_start"],
        sample_end=packet["sample_end"],
        full_visit_sha256=arrival_queue.fingerprint(packet),
        visit_metadata_sha256=arrival_queue.fingerprint(
            dict(
                packet,
                probes=[
                    {k: v for k, v in p.items() if k != "candidates"} for p in packet["probes"]
                ],
            )
        ),
        **(telemetry or {}),
    )
    return packet, receipt


def raw(attempt):
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window

    from ..variants.staggered_native import RfStagger, StaggeredLane

    plan = whole_iq.read(attempt / "plan.json")
    capture = plan["capture"]
    producer = capture_release.producer(capture["case"], capture)
    if not Path(analyze_window.__code__.co_filename).is_relative_to(producer.root):
        raise ValueError("loaded raw reader differs from the sealed acquisition release")
    policy = FastScanPolicyV2()
    recording_to_v5._bind_producer(capture["case"], producer, policy)
    libraries = {
        name: whole_iq.checked(Path(item["path"]), item["sha256"])
        for name, item in plan["assets"].items()
    }
    lib = libraries[LIBRARIES[0]]
    start, verified, lanes = mark("staggered raw enter"), [], [[], []]
    if start["cpus"] != [MAIN] or start["nice"] < 10:
        raise ValueError("staggered source reader must run on the declared caller CPU")
    state = RfStagger()
    with (
        StaggeredLane(lib, capture["edge"], helper_cpu=HELPER) as port,
        (attempt / "visits.jsonl").open("x") as receipts,
    ):
        for index, frames in groupby(arrival_queue.packets(capture, verified), key=lambda f: f[0]):
            locator = capture["case"]["recording"]["segments"][index]
            manifest_path = whole_iq.checked(BULK / locator["path"], locator["sha256"])
            manifest = whole_iq.read(manifest_path)
            stream, total_cpu, count = lanes[index % 2], 0, 0
            for frame in frames:
                packet, receipt = run_visit(frame, state, port, analyze_window, policy)
                stream.append(packet)
                receipts.write(recording_to_v5.encoded(receipt) + "\n")
                count += 1
                total_cpu += receipt.get("cpu_ns", 0)
            stream.append(
                dict(
                    kind="segment",
                    segment=index,
                    count=count,
                    path=str(manifest_path.parent),
                    manifest_digest="sha256:" + locator["sha256"],
                    radio_id=manifest["radio"]["serial"],
                    library_sha256="sha256:" + plan["assets"][LIBRARIES[0]]["sha256"],
                    detector_cpu_s=total_cpu / 1e9,
                )
            )
            print(f"segment {index}: {count} authenticated visits", flush=True)
    for lane, stream in enumerate(lanes):
        stream.append(dict(kind="worker", worker=lane))
    native, counts = recording_to_v5.native_document(capture["case"], lanes, capture)
    native["provenance"]["scope"] = (
        "fresh staggered fractional GLRT on the complete sealed recording"
    )
    name = attempt / "recording/native.json"
    recording_to_v5.save(name, native)
    name.chmod(0o644)
    save_json(
        attempt / "raw-worker.json",
        dict(
            start=start,
            end=mark("staggered raw complete"),
            counts=counts,
            compressed_chunks=len(verified),
            compressed_bytes=sum(verified),
            native_sha256=_sha(name),
            trace_sha256=_sha(attempt / "visits.jsonl"),
        ),
    )
    (attempt / "raw-worker.json").chmod(0o644)


def worker(attempt):
    plan = whole_iq.read(attempt / "plan.json")
    case = plan["capture"]["case"]
    with patch.object(whole_iq, "_load_case", return_value=case):
        _, original = whole_iq.binding(plan["case"])
    receiver = Path(plan["receiver"])
    if (
        case["id"] != plan["case"]
        or whole_iq.receiver_identity(receiver) != plan["receiver_files"]
        or whole_iq.native_sources(receiver) != plan["native_sources"]
    ):
        raise ValueError("staggered whole capture or numerical receiver changed")
    for path, digest in plan["sources"].items():
        whole_iq.checked(ROOT / path, digest)
    start = mark("staggered complete service enter")
    save_json(attempt / "start.json", start)
    if start["cpus"] != sorted((MAIN, HELPER)):
        raise ValueError("staggered service must start on both declared host cores")
    command = [
        "taskset",
        "-c",
        str(MAIN),
        "sudo",
        "-n",
        "-u",
        "leo",
        "--",
        "env",
        f"PYTHONPATH={plan['producer']}:{ROOT}",
        f"TMPDIR={attempt}",
        *(f"{k}={v}" for k, v in recording_to_v5.SINGLE_THREAD.items()),
        str(recording_to_v5.ARCHIVE_PYTHON),
        "-B",
        "-m",
        MODULE,
        "raw",
        str(attempt),
    ]
    subprocess.run(command, check=True)
    summary = whole_iq.read(attempt / "raw-worker.json")
    if any(summary[edge]["cgroup"] != start["cgroup"] for edge in ("start", "end")):
        raise ValueError("the archived reader left the original service")
    whole_iq.checked(attempt / "visits.jsonl", summary["trace_sha256"])
    native = whole_iq.checked(attempt / "recording/native.json", summary["native_sha256"])
    request = attempt / "recording/request.json"
    result = recording_to_v5.bind_request(case, native, request)
    verify_request(
        whole_iq.read(request),
        original,
        native_path=str(native),
        native_sha256=result["native_sha256"],
    )
    summary.update(request_sha256=_sha(request), position_start=mark("staggered position enter"))
    save_json(attempt / "raw.json", summary)
    os.execv(
        sys.executable, [sys.executable, "-B", "-m", whole_iq.MODULE, "position", str(attempt)]
    )


def freeze(work, report, build):
    parent_path = whole_iq.checked(PARENT / "source-lock.json", PARENT_SOURCE_SHA256)
    parent = whole_iq.read(parent_path)
    if tuple(sorted(parent["cases"])) != CASES:
        raise ValueError("staggered whole must use precisely the fresh stock/fifth pair")
    declared = whole_iq.read(build / "build.json")
    assets = {name: dict(path=str(build / name), sha256=_sha(build / name)) for name in LIBRARIES}
    for name, spec in assets.items():
        if declared["files"][name] != spec["sha256"]:
            raise ValueError(f"staggered build authority changed for {name}")
    shared = {k: parent[k] for k in ("receiver", "receiver_files", "native_sources")}
    if whole_iq.receiver_identity(Path(parent["receiver"])) != shared["receiver_files"]:
        raise ValueError("fresh panel's frozen receiver is unavailable")
    work.mkdir(parents=True, exist_ok=False, mode=0o755)
    sources = {
        str(path.relative_to(ROOT)): _sha(path)
        for path in (
            Path(__file__),
            WRAPPER,
            ROOT / "tools/pipeline_eval/variants/dual_lane.py",
            Path(arrival_queue.__file__),
            Path(recording_to_v5.__file__),
            Path(whole_iq.__file__),
            report / "PROTOCOL.md",
        )
    }
    cases = {}
    for ident in CASES:
        parent_case = parent["cases"][ident]
        case = parent_case["case"]
        with patch.object(whole_iq, "_load_case", return_value=case):
            _, original = whole_iq.binding(ident)
        capture = capture_release.read_capture(case)
        if capture["input_manifest_sha256"] != parent_case["clock_authority"]:
            raise ValueError("the raw capture clock differs from the prospective parent")
        capture.update(
            case=case, segments_sha256=recording_to_v5.digest(case["recording"]["segments"])
        )
        cases[ident] = dict(
            **shared,
            assets=assets,
            sources=sources,
            case=ident,
            capture=capture,
            producer=str(capture_release.producer(case, capture).root),
            cpus=[MAIN, HELPER],
            limit_s=LIMIT_S,
            causal_snapshots=original["causal_snapshots"],
        )
    lock = dict(
        cases=cases,
        inputs_sha256=_sha(parent_path),
        assets=assets,
        sources=sources,
        build_sha256=_sha(build / "build.json"),
        memory_max=whole_iq.MEMORY,
        swap_max=0,
        rules=dict(
            rf_key="explicit target RF center in Hz", invalid_consumes=False, initial_fifth_lane=0
        ),
    )
    save_json(report / "source-lock.json", lock)
    save_json(work / "launch-lock.json", dict(source_sha256=_sha(report / "source-lock.json")))


def launch(work, report):
    lock = whole_iq.read(
        whole_iq.checked(
            report / "source-lock.json", whole_iq.read(work / "launch-lock.json")["source_sha256"]
        )
    )
    whole_iq.checked(PARENT / "source-lock.json", lock["inputs_sha256"])
    for ident, plan in lock["cases"].items():
        out = work / ident
        out.mkdir(exist_ok=False)
        (out / "recording").mkdir()
        save_json(out / "plan.json", plan)
        (out / "plan.json").chmod(0o644)
        subprocess.run(["setfacl", "-m", "u:leo:rwx", str(out), str(out / "recording")], check=True)
        unit = "leo-iq-bench-" + uuid4().hex[:12]
        command = [
            "systemd-run",
            "--user",
            "--wait",
            "--pipe",
            "--unit=" + unit,
            "--working-directory=" + str(ROOT),
            f"--property=MemoryMax={whole_iq.MEMORY}",
            "--property=MemorySwapMax=0",
            "--property=Nice=10",
            "--property=KillMode=control-group",
            f"--property=RuntimeMaxSec={LIMIT_S}s",
            "--setenv=TMPDIR=" + str(out),
            *(f"--setenv={k}={v}" for k, v in recording_to_v5.SINGLE_THREAD.items()),
            "taskset",
            "-c",
            f"{MAIN},{HELPER}",
            sys.executable,
            "-B",
            "-m",
            MODULE,
            "worker",
            str(out),
        ]
        with patch.object(iq_service, "MODULE", MODULE):
            receipt = iq_service.run(out, command, unit, timeout=LIMIT_S + 20)
        print(ident, receipt.get("exit_code"), (out / "end.json").exists(), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run", "worker", "raw"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("--report", type=local_output, default=REPORT)
    parser.add_argument("--build", type=local_output)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work, args.report, args.build)
    elif args.action == "run":
        launch(args.work, args.report)
    else:
        {"worker": worker, "raw": raw}[args.action](args.work)


if __name__ == "__main__":
    main()
