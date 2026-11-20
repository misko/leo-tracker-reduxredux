"""Run the native C detector and compact position receiver on authenticated saved I/Q."""

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic
from unittest.mock import patch

from . import iq_service, whole_iq
from . import original_receiver as original
from .__main__ import ROOT, THREAD_ENV, local_output, save_json
from .qualification import capture_release, capture_whole, portable_field_run
from .qualification.full_v5_check import _sha
from .variants import portable_field

MODULE = "tools.pipeline_eval.portable_receiver"


def prepare(case, out, cpus, raw_limit, position_limit, receiver, smoke):
    from .qualification import capture_whole_results

    if not cpus or len(set(cpus)) != len(cpus) or not set(cpus) <= os.sched_getaffinity(0):
        raise ValueError("choose distinct available CPU numbers")
    if out.is_relative_to(original.BULK / "leo"):
        raise ValueError("choose an output outside the recording archive")
    chunks = original.chunks(case)
    metadata = capture_release.read_capture(case)
    producer = capture_release.producer(case, metadata)
    metadata["case"] = {key: case[key] for key in ("id", "session_id", "run_id")}
    original.binding(case)
    receiver_files = original.receiver_assets(receiver)
    python = whole_iq.checked(capture_whole.recording.ARCHIVE_PYTHON, original.PYTHON_SHA)
    if smoke:
        chunks = chunks[:1]
    if len(cpus) > len(chunks):
        raise ValueError("choose at most one CPU per scheduled chunk, and one for --smoke")
    workers = capture_whole.partition(chunks, frozenset(), cpus)
    out.mkdir(mode=0o755, parents=True, exist_ok=False)
    build = portable_field_run.build(out)
    sources = {
        str(Path(module.__file__)): _sha(Path(module.__file__))
        for module in (
            sys.modules[__name__],
            original,
            whole_iq,
            iq_service,
            capture_release,
            capture_whole,
            capture_whole.recording,
            capture_whole_results,
            portable_field_run,
            portable_field,
        )
    }
    detector = dict(
        backend="portable-c-original-schedule",
        binary_sha256=build["binary"]["sha256"],
        numeric_sources={
            Path(path).relative_to(ROOT).as_posix(): digest
            for path, digest in (
                build["sources"] | {portable_field.__file__: sources[portable_field.__file__]}
            ).items()
        },
    )
    lock = dict(
        id=case["id"],
        case=case,
        recording=case["recording"],
        capture=metadata,
        producer=str(producer.root),
        python=str(python),
        python_sha256=original.PYTHON_SHA,
        cpus=cpus,
        workers=workers,
        smoke=smoke,
        raw_limit_s=raw_limit,
        position_limit_s=position_limit,
        receiver=str(receiver),
        receiver_files=receiver_files,
        build=build,
        detector=detector,
        libraries={"portable_field": build["binary"]},
        sources=build["sources"] | sources,
    )
    save_json(out / "source-lock.json", lock)
    (out / "source-lock.json").chmod(0o444)
    return lock


def worker(attempt):
    plan = whole_iq.read(attempt / "plan.json")
    work, (cpu,) = attempt.parent, plan["cpus"]
    digest = plan["source_lock_sha256"]
    lock = whole_iq.read(whole_iq.checked(work / "source-lock.json", digest))
    save_json(attempt / "start.json", whole_iq.raw.mark("portable receiver worker enter"))
    if plan["stage"] == "position":
        if original.receiver_assets(Path(lock["receiver"])) != lock["receiver_files"]:
            raise ValueError("compact installation changed after the source seal")
        whole_iq.position(attempt)
        return 0
    command = [
        "sudo",
        "-n",
        "-u",
        "leo",
        "--",
        "env",
        f"PYTHONPATH={lock['producer']}:{ROOT}",
        *(f"{key}={value}" for key, value in THREAD_ENV.items()),
        str(whole_iq.checked(Path(lock["python"]), lock["python_sha256"])),
        "-Bu",
        "-m",
        MODULE,
        "shard",
        str(work),
        str(cpu),
        digest,
    ]
    with (
        (work / f"cpu-{cpu}.jsonl").open("xb") as data,
        (work / f"cpu-{cpu}.log").open("xb") as log,
    ):
        return subprocess.run(command, stdout=data, stderr=log, check=False).returncode


def run(out, lock):
    from .qualification import capture_whole_results

    assemble = capture_whole_results.assemble

    def portable_assembly(case, source, shards):
        document, counts = assemble(case, source | {"libraries": source["detector"]}, shards)
        document["provenance"]["scope"] = (
            "fresh portable C original acquisition and GLRT from signed CI16"
        )
        return document, counts

    def raw_job(row):
        cpu = row[0]
        receipt = original.service(out / f"raw-{cpu}", cpu, lock["raw_limit_s"], "raw")
        if not iq_service.succeeded(receipt):
            for suffix in ("jsonl", "log"):
                path = out / f"cpu-{cpu}.{suffix}"
                if not path.exists():
                    path.touch(exist_ok=False)
        return cpu, receipt

    with patch.object(original, "MODULE", MODULE), patch.object(iq_service, "MODULE", MODULE):
        started = monotonic()
        with ThreadPoolExecutor(max_workers=len(lock["workers"])) as pool:
            receipts = dict(pool.map(raw_job, lock["workers"]))
        raw_wall = monotonic() - started
        save_json(out / "launch.json", dict(source_lock_sha256=_sha(out / "source-lock.json")))
        save_json(
            out / "raw-exits.json",
            dict(exits={str(cpu): r["exit_code"] for cpu, r in receipts.items()}, wall_s=raw_wall),
        )
        shards, workers, _ = original.collect(out, lock)
        samples = capture_whole_results.summary_rows(shards)
        summary = dict(
            id=lock["id"],
            mode="smoke" if lock["smoke"] else "full",
            raw_wall_s=raw_wall,
            raw_services=receipts,
            workers=workers,
            completed_visits=len(samples),
            scheduled_visits=sum(row[1] for row in lock["workers"]),
            recorded_visits=lock["recording"]["window_count"],
            completed_chunks=len(shards),
            valid_visits=sum(row["status"] == "processed" for row in samples),
            invalid_visits=sum(row["status"] == "invalid_capture" for row in samples),
            grid_calls=sum(row["folded_calls"] for row in samples),
        )
        failed = [receipt for receipt in receipts.values() if not iq_service.succeeded(receipt)]
        if failed:
            return summary | dict(stage="raw", status=original.failure_status(failed))
        if lock["smoke"]:
            return summary | dict(stage="raw", status="stage_only")
        with patch.object(capture_whole_results, "assemble", portable_assembly):
            return summary | original.fit(out, lock, shards)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["worker"] and len(argv) == 2:
        return worker(local_output(argv[1]))
    if argv[:1] == ["shard"] and len(argv) == 4:
        portable_field_run.shard(local_output(argv[1]), int(argv[2]), argv[3])
        return 0
    started = monotonic()
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--case", help="recording ID in the frozen input inventory")
    source.add_argument("--input", type=Path, help="authenticated recording locator JSON")
    parser.add_argument("--input-sha256")
    parser.add_argument("--out", required=True, type=local_output)
    parser.add_argument("--cpus", required=True, nargs="+", type=int)
    parser.add_argument("--raw-limit", type=int, default=600, metavar="SECONDS")
    parser.add_argument("--position-limit", type=int, default=180, metavar="SECONDS")
    parser.add_argument("--receiver", type=local_output, default=original.CALIBRATION)
    parser.add_argument("--smoke", action="store_true", help="replay one complete signed chunk")
    args = parser.parse_args(argv)
    if not (1 <= args.raw_limit <= 600 and 1 <= args.position_limit <= 600):
        parser.error("each service limit must be 1 through 600 seconds")
    try:
        case = original.input_case(args.case, args.input, args.input_sha256)
        lock = prepare(
            case,
            args.out,
            args.cpus,
            args.raw_limit,
            args.position_limit,
            args.receiver,
            args.smoke,
        )
    except (ValueError, OSError) as error:
        parser.error(str(error))
    setup_wall = monotonic() - started
    summary = run(args.out, lock) | dict(
        setup_wall_s=setup_wall, command_wall_s=monotonic() - started
    )
    save_json(args.out / "summary.json", summary)
    portable_field_run.seal(args.out)
    print(json.dumps({key: summary[key] for key in ("id", "stage", "status")}), flush=True)
    return int(summary["status"] in ("failed", "unavailable", "timed_out"))


if __name__ == "__main__":
    raise SystemExit(main())
