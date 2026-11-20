"""Replay signed dual IQ through the resident portable detector and compact fits."""

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

from .. import iq_service, whole_iq
from .. import original_receiver as original
from ..__main__ import ROOT, THREAD_ENV, local_output, save_json
from ..variants import portable_field
from . import capture_whole as capture
from .capture_release import producer, read_capture
from .full_v5_check import _from_production, _probe, _sha

MODULE = "tools.pipeline_eval.qualification.portable_field_run"
CASE = "DS26-0020"
PROTOCOL = (
    ROOT
    / "reports/2026_11_19_receiver_screening/native-receiver/portable-field/SCORING-PROTOCOL.md"
)
PROTOCOL_SHA = "80c57275f989e685392fc3e47b8ceacf46b3a28031e1dbd2ec172483be5f55ff"


def build(out):
    from . import portable_verifier_run as verifier

    binary = out / "portable-field.so"
    coarse = portable_field.SOURCE.with_name("portable_coarse.c")
    sources = (portable_field.SOURCE, coarse, *verifier.SOURCES[1:])
    flags = [flag for flag in verifier.BUILD_FLAGS if flag not in ("-static", "-fstack-usage")]
    command = [
        "cc",
        *flags,
        "-march=x86-64-v3",
        "-shared",
        "-fPIC",
        "-I",
        str(verifier.KERNEL / "native_presence"),
        *map(str, sources),
        "-lm",
        "-o",
        str(binary),
    ]
    subprocess.run(command, check=True, cwd=out, env=os.environ | {"TMPDIR": str(out)}, timeout=45)
    binary.chmod(0o444)
    headers = (
        *(
            coarse.with_name(name)
            for name in (
                "portable_coarse.h",
                "portable_coarse_qin.h",
                "portable_verifier.h",
                "portable_fine.h",
            )
        ),
        verifier.KERNEL / "native_presence/fft.h",
    )
    return dict(
        command=command,
        tool=subprocess.check_output(["cc", "--version"], text=True).splitlines()[0],
        binary=dict(path=str(binary), sha256=_sha(binary), bytes=binary.stat().st_size),
        sources={str(path): _sha(path) for path in (*sources, *headers)},
    )


def prepare(out, cpus, smoke):
    from . import capture_whole_results as results

    if not cpus or len(cpus) != len(set(cpus)) or not set(cpus) <= os.sched_getaffinity(0):
        raise ValueError("choose distinct available CPU numbers")
    if out.is_relative_to(original.BULK / "leo"):
        raise ValueError("choose scratch outside the recording archive")
    case = original.input_case(CASE, None, None)
    scope = original.chunks(case)
    metadata = read_capture(case)
    release = producer(case, metadata)
    metadata["case"] = {key: case[key] for key in ("id", "session_id", "run_id")}
    original.binding(case)
    receiver = original.CALIBRATION
    receiver_files = original.receiver_assets(receiver)
    python = whole_iq.checked(capture.recording.ARCHIVE_PYTHON, original.PYTHON_SHA)
    scoring = whole_iq.checked(PROTOCOL, PROTOCOL_SHA)
    if smoke:
        scope = scope[:1]
    if len(cpus) > len(scope):
        raise ValueError("choose at most one CPU per signed chunk")
    workers = capture.partition(scope, frozenset(), cpus)
    out.mkdir(mode=0o755, parents=True, exist_ok=False)
    compiled = build(out)
    programs = (
        Path(__file__),
        *(
            Path(m.__file__)
            for m in (
                portable_field,
                capture,
                results,
                capture.recording,
                original,
                whole_iq,
            )
        ),
    )
    lock = dict(
        id=CASE,
        case=case,
        capture=metadata,
        recording=case["recording"],
        producer=str(release.root),
        python=str(python),
        python_sha256=original.PYTHON_SHA,
        cpus=cpus,
        workers=workers,
        smoke=smoke,
        raw_limit_s=600,
        position_limit_s=180,
        receiver=str(receiver),
        receiver_files=receiver_files,
        build=compiled,
        scoring_protocol_sha256=_sha(scoring),
        libraries={"portable_field": compiled["binary"]},
        sources=compiled["sources"] | {str(path): _sha(path) for path in (*programs, scoring)},
    )
    save_json(out / "source-lock.json", lock)
    (out / "source-lock.json").chmod(0o444)
    return lock


def shard(work, cpu, digest):
    from leo.scanner.fast_scan_analysis import analyze_window
    from leo.storage import short_window

    lock = whole_iq.read(whole_iq.checked(work / "source-lock.json", digest))
    for path, expected in lock["sources"].items():
        whole_iq.checked(Path(path), expected)
    library = lock["libraries"]["portable_field"]
    binary = whole_iq.checked(Path(library["path"]), library["sha256"])
    _, _, chunks = next(row for row in lock["workers"] if row[0] == cpu)
    policy, start = capture.policy_for(lock), capture.resources.memory()
    if start["cpus"] != [cpu]:
        raise ValueError("worker outside its planned CPU")
    member, verified = short_window.ShortWindowReader._member, []

    def stream(reader, name, size, expected):
        if any(chunk.payload_relative_path == name for chunk in reader.manifest.chunks):
            path = short_window.confined_path(reader.path, reader.path / name, must_exist=True)
            return capture.resources.AuthenticatedMember(path, size, expected, verified)
        return member(reader, name, size, expected)

    def emit(record):
        print(capture.recording.encoded(record), flush=True)

    valid = 0
    edge = lock["capture"]["edge"]
    setup_wall, setup_cpu = perf_counter(), process_time()
    with (
        portable_field.Detector(binary, edge) as detector,
        patch.object(short_window.ShortWindowReader, "_member", stream),
    ):
        setup_wall, setup_cpu = perf_counter() - setup_wall, process_time() - setup_cpu
        for segment, first, stop, base in chunks:
            source = capture.open_span(lock, segment, first, stop)
            count, history, opened = 0, len(verified), perf_counter()
            for window in source.windows():
                acquisition = window.acquisition
                if (
                    window.target["edge"] != edge
                    or acquisition["global_visit"] != base + first + count
                ):
                    raise ValueError("signed physical edge or global window ordering changed")
                retune = json.loads(acquisition.get("retune_receipt") or "{}")
                detector.attempts = []
                wall, cpu_time = perf_counter(), process_time()
                status = analyze_window(
                    window, source.receiver_ids, None, policy, detector=detector
                )
                probes = [
                    _probe(window, row.receiver_id, map(_from_production, row.candidates))
                    for row in status.receivers
                ]
                wall, cpu_time = perf_counter() - wall, process_time() - cpu_time
                if status.status == "processed" and [p["receiver_id"] for p in probes] == [0, 1]:
                    valid += 1
                elif status.status != "invalid_capture" or probes or detector.attempts:
                    raise ValueError("original capture validity contract changed")
                emit(
                    dict(
                        kind="visit",
                        segment=segment,
                        sequence=window.sequence,
                        visit=acquisition["global_visit"],
                        iq_sha256=window.iq_sha256,
                        sample_start=status.sample_start,
                        sample_end=status.sample_end,
                        generation=status.generation,
                        status=status.status,
                        reason=status.reason,
                        rf_mapping_authority=status.rf_mapping_authority,
                        probes=probes,
                        input_bytes=window.samples.nbytes,
                        grid_calls=len(detector.attempts),
                        clock_anchor=retune.get("utc_clock_bracket"),
                        delivery_clock=retune.get("host_delivery_clock"),
                        detector_wall_s=wall,
                        detector_cpu_s=cpu_time,
                        portable_groups=detector.attempts,
                    )
                )
                count += 1
            if count != stop - first or len(verified) != history + 1:
                raise ValueError("capture chunk is incomplete or failed authentication")
            emit(
                dict(
                    kind="chunk",
                    segment=segment,
                    first=first,
                    stop=stop,
                    path=str(source.reader.path),
                    manifest_digest=source.manifest_digest,
                    radio_id=source.radio["serial"],
                    compressed_bytes=verified[-1],
                    wall_s=perf_counter() - opened,
                )
            )
    whole_iq.checked(binary, library["sha256"])
    emit(
        dict(
            kind="worker",
            cpu=cpu,
            count=valid,
            start=start,
            end=capture.resources.memory(),
            source_lock_sha256=digest,
            setup_wall_s=setup_wall,
            setup_cpu_s=setup_cpu,
            portable_workspace_bytes=detector.workspace_bytes,
        )
    )


def worker(attempt):
    plan = whole_iq.read(attempt / "plan.json")
    work, (cpu,) = attempt.parent, plan["cpus"]
    digest = plan["source_lock_sha256"]
    lock = whole_iq.read(whole_iq.checked(work / "source-lock.json", digest))
    save_json(attempt / "start.json", whole_iq.raw.mark("portable field worker enter"))
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
        lock["python"],
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
    from . import capture_whole_results as results

    def raw_job(row):
        cpu = row[0]
        return cpu, original.service(out / f"raw-{cpu}", cpu, lock["raw_limit_s"], "raw")

    with patch.object(original, "MODULE", MODULE), patch.object(iq_service, "MODULE", MODULE):
        started = perf_counter()
        with ThreadPoolExecutor(max_workers=len(lock["workers"])) as pool:
            receipts = dict(pool.map(raw_job, lock["workers"]))
        raw_wall = perf_counter() - started
        save_json(out / "launch.json", dict(source_lock_sha256=_sha(out / "source-lock.json")))
        save_json(
            out / "raw-exits.json",
            dict(
                exits={str(cpu): row["exit_code"] for cpu, row in receipts.items()},
                wall_s=raw_wall,
            ),
        )
        shards, workers, _ = original.collect(out, lock)
        samples = results.summary_rows(shards)
        summary = dict(
            id=CASE,
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
        failed = [row for row in receipts.values() if not iq_service.succeeded(row)]
        if failed:
            return summary | dict(stage="raw", status=original.failure_status(failed))
        if lock["smoke"]:
            return summary | dict(stage="raw", status="stage_only")

        assemble = results.assemble

        def portable(case, source, parts):
            document, counts = assemble(case, source, parts)
            document["provenance"]["scope"] = (
                "fresh portable C original acquisition and GLRT from signed CI16"
            )
            return document, counts

        with patch.object(results, "assemble", portable):
            return summary | original.fit(out, lock, shards)


def seal(out):
    files = {
        str(path.relative_to(out)): _sha(path) for path in sorted(out.rglob("*")) if path.is_file()
    }
    save_json(out / "run-seal.json", dict(files=files))


def main():
    if sys.argv[1:2] == ["worker"] and len(sys.argv) == 3:
        return worker(local_output(sys.argv[2]))
    if sys.argv[1:2] == ["shard"] and len(sys.argv) == 5:
        shard(local_output(sys.argv[2]), int(sys.argv[3]), sys.argv[4])
        return 0
    started = perf_counter()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=local_output)
    parser.add_argument("--cpus", nargs="+", type=int, default=list(range(8)))
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    lock = prepare(args.out, args.cpus, args.smoke)
    setup_wall = perf_counter() - started
    summary = run(args.out, lock) | dict(
        setup_wall_s=setup_wall, command_wall_s=perf_counter() - started
    )
    save_json(args.out / "summary.json", summary)
    seal(args.out)
    print(json.dumps({key: summary[key] for key in ("id", "stage", "status")}), flush=True)
    return int(summary["status"] in ("failed", "unavailable", "timed_out"))


if __name__ == "__main__":
    raise SystemExit(main())
