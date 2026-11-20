"""Benchmark a short-window GLRT library and installed compact receiver on one full recording."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from . import iq_service
from .__main__ import ROOT, local_output, save_json
from .qualification import recording_to_v5 as recording
from .qualification import whole_memory_chain_worker as raw
from .qualification.fractional_runtime_whole import verify_request
from .qualification.full_v5_check import BULK, _load_case, _sha
from .scoring import validate_result

MODULE = "tools.pipeline_eval.whole_iq"
MEMORY = 512 * 1024**2


def read(path):
    return json.loads(path.read_bytes())


def checked(path, digest):
    if _sha(path) != digest.removeprefix("sha256:"):
        raise ValueError(f"file differs from declared SHA-256: {path}")
    return path


def binding(ident):
    case = _load_case(ident)
    req = checked(BULK / case["request"]["path"], case["request"]["sha256"])
    request = read(req)
    job = request["job"]
    if (
        job["evaluation_reference"] is not None
        or job["identity"]["session_id"] != case["session_id"]
    ):
        raise ValueError("the receiver requires the original truth-free recording request")
    archive = Path(job["tle_root"])
    history = {p.name: _sha(p) for p in archive.rglob("*.tle")}
    if not history or history != {
        k: v.removeprefix("sha256:") for k, v in request["causal_snapshots"].items()
    }:
        raise ValueError("causal orbit archive differs from the frozen request")
    checked(Path(job["track_config"]["path"]), job["track_config"]["sha256"])
    return case, request


def receiver_identity(path):
    names = ["__main__.py", "tools/__init__.py", "native/manifest.json", "projector.so"]
    names.extend(str(p.relative_to(path)) for p in sorted((path / "native").rglob("*.so")))
    # Include the actual runtime sources so a modified installation cannot share a receipt.
    names.extend(str(p.relative_to(path)) for p in sorted(path.rglob("*.py")))
    return {name: _sha(path / name) for name in names}


def native_sources(receiver):
    receiver = receiver.resolve()
    manifest = read(receiver / "native/manifest.json")
    artifacts = {
        "source": "leo/analysis/localization_v4/native_bound.c",
        "wrapper": "leo/analysis/localization_v4/native_bound.py",
        "binary": "native/native_bound.so",
    }
    for field, name in artifacts.items():
        path = receiver / name
        if Path(manifest[field]).resolve() != path:
            raise ValueError(f"native manifest does not bind {name} in this installation")
        checked(path, manifest[field + "_sha256"])
    names = (artifacts["source"], "tools/pipeline_eval/variants/orbit_projector.c")
    return {name: _sha(receiver / name) for name in names}


def complete_raw(out, case, cpus, library_sha):
    ends = read(out / "raw-worker-exits.json")
    if ends != dict(cpus=cpus, exit_codes=[0, 0]):
        raise ValueError("the two raw lanes must both complete on their assigned cores")
    raw_end = raw.mark("raw complete")
    lanes, observations = [], []
    for lane, cpu in enumerate(cpus):
        with (out / f"replayed-{lane}.jsonl").open() as stream:
            lanes.append(list(map(json.loads, stream)))
        prefix = "whole-lane-result: "
        lines = (out / f"replayed-{lane}.log").read_text().splitlines()
        receipts = [json.loads(line[len(prefix) :]) for line in lines if line.startswith(prefix)]
        if len(receipts) != 1:
            raise ValueError("raw lane missing its terminal receipt")
        row = receipts[0]
        if (
            any(
                row[edge]["cpus"] != [cpu] or row[edge]["cgroup"] != raw_end["cgroup"]
                for edge in ("start", "end")
            )
            or row["compressed_chunks"] < 1
        ):
            raise ValueError("raw lane left its bound capture service")
        observations.append(row)
    doc, counts = recording.native_document(case, lanes, read(out / "capture.json"))
    if (
        doc["provenance"]["detector_sha256"] != "sha256:" + library_sha
        or sum(len(r["native_timings_s"]) for r in observations) != counts["processed_windows"]
    ):
        raise ValueError("native call ledger differs from the assembled detector input")
    source = doc["source"]
    summary = dict(
        raw_end=raw_end,
        counts=counts,
        lanes=observations,
        input_manifest_sha256=source["input_manifest_sha256"],
        raw_authority=source["raw_recording_authority_digest"],
        clock_sha256=recording.digest(
            [doc["clock_anchor"], doc["delivery_clocks"], doc["last_sample_counter"]]
        ),
        excluded_sha256=recording.digest(doc["provenance"]["excluded_windows"]),
        probes_sha256=recording.digest(
            [{k: v for k, v in p.items() if k != "candidates"} for p in source["probes"]]
        ),
    )
    recording.save(out / "native.json", doc)
    return summary


def worker(attempt):
    plan = read(attempt / "plan.json")
    ident, cpus = plan["case"], plan["cpus"]
    detector = checked(Path(plan["detector"]), plan["detector_sha256"])
    receiver = Path(plan["receiver"])
    if receiver_identity(receiver) != plan["receiver_files"]:
        raise ValueError("installed position receiver differs from the bound release")
    if "native_sources" in plan and native_sources(receiver) != plan["native_sources"]:
        raise ValueError("native receiver sources changed after starting this attempt")
    case, original = binding(ident)
    out = attempt / "recording"
    start = raw.mark("full recorded IQ enter")
    save_json(attempt / "start.json", start)

    def finish(directory, case_id, deadline, mode):
        if directory != out or case_id != ident or mode != "ordinary":
            raise ValueError("unexpected raw recording handoff")
        summary = complete_raw(out, case, cpus, plan["detector_sha256"])
        native = out / "native.json"
        result = recording.bind_request(case, native, out / "request.json")
        request = read(out / "request.json")
        verify_request(
            request, original, native_path=str(native), native_sha256=result["native_sha256"]
        )
        summary.update(
            native_sha256=result["native_sha256"], request_sha256=_sha(out / "request.json")
        )
        summary["position_start"] = raw.mark("standalone receiver enter")
        save_json(attempt / "raw.json", summary)
        checked(detector, plan["detector_sha256"])
        # Release the decoded frame and factor buffers before starting the position process.
        # The service's original elapsed deadline applies across this process replacement.
        os.execv(sys.executable, [sys.executable, "-B", "-m", MODULE, "position", str(attempt)])

    with patch.object(recording, "MODULE", raw.__name__):
        recording.run_recording(
            ident, out, cpus, plan["limit_s"], native_library=detector, finish=finish
        )


def position(attempt, *, publish=None):
    plan = read(attempt / "plan.json")
    summary = read(attempt / "raw.json")
    path = checked(attempt / "recording/request.json", summary["request_sha256"])
    job = read(path)["job"]
    tile = dict(center=job["search_center"], width_km=25.0)
    command = [
        sys.executable,
        "-IB",
        plan["receiver"],
        "--native",
        job["native_input"]["path"],
        "--native-sha256",
        summary["native_sha256"],
        "--session",
        job["identity"]["session_id"],
        "--track-config",
        job["track_config"]["path"],
        "--config-sha256",
        job["track_config"]["sha256"],
        "--archive",
        job["tle_root"],
        "--tile",
        *map(str, tile["center"]),
        "--screen-center",
        *map(str, job["screen_center"]),
    ]
    path = attempt / "position.json"
    if publish is None:
        with path.open("xb") as output:
            subprocess.run(command, cwd=attempt, stdout=output, check=True)
    else:
        command.extend(("--width-km", str(tile["width_km"])))
        solved = subprocess.run(command, cwd=attempt, stdout=subprocess.PIPE, check=True)
        result = publish(json.loads(solved.stdout), tile)
        validate_result(result)
        payload = (json.dumps(result, allow_nan=False) + "\n").encode()
        with path.open("xb") as output:
            output.write(payload)
    end = raw.mark("both calibration arms returned")
    validate_result(read(path))
    save_json(attempt / "end.json", end)


def evaluate(ident, detector, detector_sha256, receiver, out, cpus, limit_s):
    out = local_output(out)
    if out.is_relative_to(BULK / "leo"):
        raise ValueError("use a local output outside the recording archive")
    if len(cpus) != 2 or len(set(cpus)) != 2 or not set(cpus) <= os.sched_getaffinity(0):
        raise ValueError("choose two distinct available cores")
    if not 1 <= limit_s <= 600:
        raise ValueError("the per-recording deadline must be 1 to 600 seconds")
    checked(detector, detector_sha256)
    sources = native_sources(receiver)
    case, _ = binding(ident)
    release = receiver_identity(receiver)
    out.mkdir(parents=True, exist_ok=False)
    save_json(
        out / "plan.json",
        dict(
            case=ident,
            cpus=list(cpus),
            limit_s=limit_s,
            detector=str(detector),
            detector_sha256=_sha(detector),
            receiver=str(receiver),
            receiver_files=release,
            native_sources=sources,
            capture_era_request=case["request"]["sha256"],
            recording=case["recording"],
        ),
    )
    unit = "leo-iq-bench-" + uuid4().hex[:12]
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        "--unit=" + unit,
        "--working-directory=" + str(ROOT),
        "--property=MemoryMax=" + str(MEMORY),
        "--property=MemorySwapMax=0",
        "--property=Nice=10",
        "--property=KillMode=control-group",
        "--property=RuntimeMaxSec=" + str(limit_s) + "s",
        "--setenv=TMPDIR=" + str(out),
        *("--setenv=" + k + "=" + v for k, v in recording.SINGLE_THREAD.items()),
        "taskset",
        "-c",
        ",".join(map(str, cpus)),
        sys.executable,
        "-B",
        "-m",
        MODULE,
        "worker",
        str(out),
    ]
    records = iq_service.run(out, command, unit, timeout=limit_s + 18)
    if not iq_service.succeeded(records) or not (out / "end.json").is_file():
        raise RuntimeError(f"saved-IQ service did not complete; see {out / 'service.log'}")
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    run = commands.add_parser(
        "run", help="replay every visit through both calibrated position fits"
    )
    run.add_argument("--case", required=True)
    run.add_argument("--detector", type=Path, required=True)
    run.add_argument("--detector-sha256", required=True)
    run.add_argument(
        "--receiver", type=Path, required=True, help="installed cavity_runtime directory"
    )
    run.add_argument("--out", type=local_output, required=True, help="new local attempt directory")
    run.add_argument("--cpus", nargs=2, type=int, required=True)
    run.add_argument("--limit-s", type=int, default=360)
    commands.add_parser("worker", help=argparse.SUPPRESS).add_argument("attempt", type=local_output)
    commands.add_parser("position", help=argparse.SUPPRESS).add_argument(
        "attempt", type=local_output
    )
    args = parser.parse_args()
    if args.action == "worker":
        worker(args.attempt)
    elif args.action == "position":
        position(args.attempt)
    else:
        evaluate(
            args.case,
            args.detector.resolve(),
            args.detector_sha256,
            args.receiver.resolve(),
            args.out,
            args.cpus,
            args.limit_s,
        )


if __name__ == "__main__":
    main()
