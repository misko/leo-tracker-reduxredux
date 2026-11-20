"""Replay ordinary dual native GLRT on complete IQ visits in the frozen 180 s prefix."""

import argparse
import json
import os
import signal
import subprocess
from contextlib import ExitStack, suppress
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from ..__main__ import local_output
from ..variants import contiguous_prefix as prefix
from ..variants.iq_stream import _read_prefix
from . import capture_release
from . import recording_to_v5 as replay
from .contiguous_prefix_trial import position
from .full_v5_check import BULK, NATIVE_LIBRARY, REPO, _sha
from .single_chain_trial import archive

MODULE = "tools.pipeline_eval.qualification.contiguous_prefix_raw"
CASES = ("DS26-0036", "DS29-0082")
RAW_DEADLINE_S = 360


def scopes(segments, visit_count):
    selected = []
    remaining = visit_count
    for locator in segments:
        raw = _read_prefix(BULK / locator["path"], 65_537)
        if len(raw) > 65_536 or sha256(raw).hexdigest() != locator["sha256"]:
            raise ValueError("prefix locator does not bind the frozen raw manifest")
        manifest = json.loads(raw)
        count = manifest["window_count"]
        stop = min(remaining, count)
        boundary_end = next(
            chunk["first_sequence"] + chunk["window_count"]
            for chunk in manifest["chunks"]
            if chunk["first_sequence"] < stop <= chunk["first_sequence"] + chunk["window_count"]
        )
        selected.append(
            dict(locator, stop_sequence=stop, archive_boundary_tail=boundary_end - stop)
        )
        remaining -= stop
        if remaining == 0:
            break
    if remaining:
        raise ValueError("prefix visit count is outside the frozen recording")
    return selected


def worker(library, lane, job):
    from leo.storage import fast_scan

    paths = {
        str((BULK / row["path"]).resolve().parent): row["stop_sequence"] for row in job["segments"]
    }
    source = fast_scan.FastSegmentSource

    def open_prefix(entry):
        return source(entry, stop_sequence=paths[entry["path"]])

    with patch.object(fast_scan, "FastSegmentSource", open_prefix):
        replay.stream_range(
            library, lane, job["segments"], job["capture"]["case"]["id"], job["capture"]
        )


def consolidate(reference, scopes, lanes, library_sha):
    """Close every worker receipt and verify independently regenerated probes."""
    visits, cpu, segments = [], 0.0, set()
    for lane, rows in enumerate(lanes):
        if not rows or rows[-1] != dict(kind="worker", worker=lane):
            raise ValueError("raw prefix lane failed to publish its terminal receipt")
        pending = []
        for row in rows[:-1]:
            index = row["segment"]
            if not 0 <= index < len(scopes) or index % 2 != lane:
                raise ValueError("raw visit lies outside its frozen segment scope")
            if row["kind"] == "visit":
                pending.append(row)
                continue
            scope = scopes[index]
            if (
                row["kind"] != "segment"
                or index in segments
                or row["detector"] != "ordinary"
                or row["library_sha256"] != library_sha
                or row["path"] != str((BULK / scope["path"]).parent)
                or row["manifest_digest"] != "sha256:" + scope["sha256"]
                or len(pending) != scope["stop_sequence"]
                or row["count"] != len(pending)
                or any(v["segment"] != index or v["sequence"] != i for i, v in enumerate(pending))
            ):
                raise ValueError("raw prefix segment failed its frozen scope")
            segments.add(index)
            cpu += row["detector_cpu_s"]
            visits.extend(pending)
            pending.clear()
        if pending:
            raise ValueError("raw prefix lane has visits without a closing segment receipt")
    if segments != set(range(len(scopes))):
        raise ValueError("raw prefix omitted a selected segment")
    visits.sort(key=lambda row: row["visit"])
    clocks = reference["delivery_clocks"]
    anchor = reference["clock_anchor"]
    if (
        len(visits) != len(clocks)
        or [v["clock_anchor"] for v in visits if v["clock_anchor"]] != [anchor]
        or visits[-1]["sample_end"] != reference["last_sample_counter"]
    ):
        raise ValueError("prefix clock anchor or end counter differs from original input")
    excluded, probes, iq_hashes = [], [], []
    for expected, (visit, clock) in enumerate(zip(visits, clocks, strict=True)):
        if visit["visit"] != expected or visit["delivery_clock"] != clock:
            raise ValueError("fresh prefix changed the original visit order or delivery time")
        iq_hashes.append(visit["iq_sha256"])
        if visit["status"] == "invalid_capture" and not visit["probes"]:
            excluded.append(
                {
                    key: visit[key]
                    for key in ("visit", "reason", "iq_sha256", "sample_start", "sample_end")
                }
            )
        elif visit["status"] == "processed" and [p["receiver_id"] for p in visit["probes"]] == [
            0,
            1,
        ]:
            probes.extend(visit["probes"])
        else:
            raise ValueError("fresh prefix visit did not produce its native validity status")
    if (
        excluded != reference["provenance"]["excluded_windows"]
        or probes != reference["source"]["probes"]
    ):
        raise ValueError("fresh prefix native candidates or exclusions differ from archived native")
    identity = replay.digest(
        [prefix.POLICY, "fresh-ordinary-native", library_sha, scopes, iq_hashes, probes]
    )
    document = dict(
        reference,
        source=dict(
            reference["source"],
            analysis_manifest_sha256=identity,
            raw_recording_authority_digest=replay.digest([scopes, iq_hashes]),
            probes=probes,
        ),
        provenance=dict(
            reference["provenance"],
            run_id="replay-" + identity[7:39],
            scope="fresh ordinary native GLRT on the contiguous 180 s prefix",
        ),
    )
    return document, dict(
        raw_detector_cpu_s=cpu,
        raw_segments=len(scopes),
        raw_iq_bytes=sum(v["input_bytes"] for v in visits),
        raw_exact_probe_rows=len(probes),
        raw_exact_candidates=sum(len(p["candidates"]) for p in probes),
        native_library_sha256=library_sha,
        archive_boundary_tail_windows=scopes[-1]["archive_boundary_tail"],
    )


def replay_prefix(case_id, output, cpus, library):
    started = perf_counter()
    case, _, _, ordinary = archive(case_id, "ordinary-native")
    reference, metrics = prefix.restrict(ordinary, prefix=True)
    capture = capture_release.read_capture(case)
    subset = scopes(case["recording"]["segments"], metrics["scheduled_visits"])
    capture.update(
        case={key: case[key] for key in ("id", "run_id", "session_id")},
        segments_sha256=replay.digest(subset),
    )
    root = capture_release.producer(case, capture).root
    output.mkdir(parents=True, exist_ok=False)
    raw_job = output / "raw-job.json"
    replay.save(raw_job, dict(capture=capture, segments=subset))
    children = []
    with ExitStack() as files:
        try:
            for lane, cpu in enumerate(cpus):
                command = (
                    "taskset",
                    "-c",
                    str(cpu),
                    "sudo",
                    "-n",
                    "-u",
                    "leo",
                    "--",
                    "env",
                    f"PYTHONPATH={root}:{REPO}",
                    *(f"{name}={value}" for name, value in replay.SINGLE_THREAD.items()),
                    str(replay.ARCHIVE_PYTHON),
                    "-Bu",
                    "-m",
                    MODULE,
                    "--native-library",
                    str(library),
                    "worker",
                    str(lane),
                )
                children.append(
                    subprocess.Popen(
                        command,
                        cwd=REPO,
                        start_new_session=True,
                        stdin=files.enter_context(raw_job.open("rb")),
                        stdout=files.enter_context((output / f"lane-{lane}.jsonl").open("xb")),
                        stderr=files.enter_context((output / f"lane-{lane}.log").open("xb")),
                    )
                )
            exits = [
                child.wait(timeout=max(0, RAW_DEADLINE_S - (perf_counter() - started)))
                for child in children
            ]
            if exits != [0, 0]:
                raise ChildProcessError(f"native prefix lane exit codes {exits}")
        finally:
            for child in children:
                if child.poll() is None:
                    with suppress(ProcessLookupError):
                        os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
    lanes = []
    for lane in (0, 1):
        with (output / f"lane-{lane}.jsonl").open() as stream:
            lanes.append(list(map(json.loads, stream)))
    document, receipt = consolidate(reference, subset, lanes, "sha256:" + _sha(library))
    fresh = output / "native.json"
    replay.save(fresh, document)
    selection_wall = perf_counter() - started
    metrics.update(receipt, raw_replay_and_assembly_wall_s=selection_wall)
    affinity = os.sched_getaffinity(0)
    os.sched_setaffinity(0, {cpus[0]})
    try:
        receipt = position(case, fresh, output, metrics, "ordinary-native-raw-prefix")
    finally:
        os.sched_setaffinity(0, affinity)
    print(
        case_id, receipt["result"]["status"], "batch_seconds", perf_counter() - started, flush=True
    )


def full_control(case_id, output):
    case, path, _, ordinary = archive(case_id, "ordinary-native")
    _, metrics = prefix.restrict(ordinary, prefix=False)
    output.mkdir(parents=True, exist_ok=False)
    receipt = position(case, path, output, metrics, "ordinary-native-full-control")
    print(
        case_id, receipt["result"]["status"], "solver_seconds", receipt["worker_wall_s"], flush=True
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-library", type=Path, default=NATIVE_LIBRARY)
    actions = parser.add_subparsers(dest="action", required=True)
    read = actions.add_parser("replay")
    read.add_argument("case", choices=CASES)
    read.add_argument("--out", type=local_output, required=True)
    read.add_argument("--cpus", type=int, nargs=2, required=True)
    control = actions.add_parser("full-control")
    control.add_argument("case", choices=CASES)
    control.add_argument("--out", type=local_output, required=True)
    collect = actions.add_parser("worker")
    collect.add_argument("lane", type=int, choices=(0, 1))
    args = parser.parse_args()
    if args.action == "worker":
        import sys

        worker(args.native_library.resolve(strict=True), args.lane, json.load(sys.stdin))
    elif args.action == "full-control":
        if len(os.sched_getaffinity(0)) != 1:
            parser.error("pin the full control to one CPU")
        full_control(args.case, args.out)
    else:
        if len(set(args.cpus)) != 2 or not set(args.cpus) <= os.sched_getaffinity(0):
            parser.error("select two distinct available CPUs")
        replay_prefix(args.case, args.out, args.cpus, args.native_library.resolve(strict=True))


if __name__ == "__main__":
    main()
