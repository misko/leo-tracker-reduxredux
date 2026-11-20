"""Replay the complete saved IQ through the phase-release winner-stream option."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from .. import iq_service, whole_iq
from ..__main__ import ROOT, local_output, save_json
from ..scoring import validate_result
from . import whole_winner_handoff as handoff

MODULE = "tools.pipeline_eval.qualification.whole_winner"


def raw_receipts(out, cpus, current):
    if whole_iq.read(out / "raw-worker-exits.json") != dict(cpus=cpus, exit_codes=[0, 0]):
        raise ValueError("the raw lanes did not both finish in the requested envelope")
    lanes = []
    prefix = "whole-lane-result: "
    for lane, cpu in enumerate(cpus):
        log = out / f"replayed-{lane}.log"
        rows = [
            json.loads(s[len(prefix) :])
            for s in log.read_text().splitlines()
            if s.startswith(prefix)
        ]
        if len(rows) != 1 or rows[0]["compressed_chunks"] < 1:
            raise ValueError("raw lane lacks its authenticated compressed-input completion")
        for edge in ("start", "end"):
            mark = rows[0][edge]
            if mark["cpus"] != [cpu] or mark["cgroup"] != current["cgroup"]:
                raise ValueError("an IQ decoder left its assigned service or core")
        lanes.extend(rows)
    return lanes


def worker(attempt):
    plan = whole_iq.read(attempt / "plan.json")
    whole_iq.checked(Path(handoff.__file__), plan["handoff_source_sha256"])
    ident, cpus = plan["case"], plan["cpus"]
    detector = whole_iq.checked(Path(plan["detector"]), plan["detector_sha256"])
    receiver = Path(plan["receiver"])
    if whole_iq.receiver_identity(receiver) != plan["receiver_files"]:
        raise ValueError("installed winner-stream receiver differed from the frozen package")
    if whole_iq.native_sources(receiver) != plan["native_sources"]:
        raise ValueError("standalone numerical source authority changed")
    case, request = whole_iq.binding(ident)
    if (
        case["request"]["sha256"] != plan["capture_era_request"]
        or case["recording"] != plan["recording"]
    ):
        raise ValueError("causal request or source recording changed")
    out = attempt / "recording"
    save_json(attempt / "start.json", whole_iq.raw.mark("full recorded IQ enter"))

    def finish(directory, case_id, _deadline, detector_mode):
        if directory != out or case_id != ident or detector_mode != "ordinary":
            raise ValueError("unexpected native producer handoff")
        start = whole_iq.raw.mark("raw complete")
        lanes = raw_receipts(out, cpus, start)
        capture_path = out / "capture.json"
        stream_path = out / "native.winners"
        with stream_path.open("xb") as stream:
            summary = handoff.assemble(
                out,
                case,
                whole_iq.read(capture_path),
                plan["detector_sha256"],
                stream,
            )
        if (
            plan["expected_native"] is not None
            and summary["native_sha256"] != "sha256:" + plan["expected_native"]
        ):
            raise ValueError("fresh raw input differs from the frozen wide native identity")
        if (
            sum(len(row["native_timings_s"]) for row in lanes)
            != summary["counts"]["processed_windows"]
        ):
            raise ValueError("the raw detector call ledger differs from the complete stream")
        whole_iq.checked(detector, plan["detector_sha256"])
        position_request = attempt / "position-request.json"
        save_json(position_request, request)
        summary.update(
            lanes=lanes,
            raw_end=start,
            capture_sha256=whole_iq._sha(capture_path),
            position_request_sha256=whole_iq._sha(position_request),
        )
        summary["position_start"] = whole_iq.raw.mark("winner stream receiver enter")
        save_json(attempt / "raw.json", summary)
        os.execv(sys.executable, [sys.executable, "-B", "-m", MODULE, "position", str(attempt)])

    with patch.object(whole_iq.recording, "MODULE", whole_iq.raw.__name__):
        whole_iq.recording.run_recording(
            ident, out, cpus, plan["limit_s"], native_library=detector, finish=finish
        )


def position(attempt):
    plan, receipt = (whole_iq.read(attempt / name) for name in ("plan.json", "raw.json"))
    job = whole_iq.read(
        whole_iq.checked(
            attempt / "position-request.json",
            receipt["position_request_sha256"],
        )
    )["job"]
    command = [
        sys.executable,
        "-IB",
        plan["receiver"],
        "--native",
        str(attempt / "recording/native.winners"),
        "--native-sha256",
        receipt["private_sha256"],
        "--native-origin-sha256",
        receipt["native_sha256"],
        "--session",
        job["identity"]["session_id"],
        "--track-config",
        job["track_config"]["path"],
        "--config-sha256",
        job["track_config"]["sha256"],
        "--archive",
        job["tle_root"],
        "--tile",
        *map(str, job["search_center"]),
        "--screen-center",
        *map(str, job["screen_center"]),
    ]
    with (attempt / "position.json").open("xb") as stdout:
        subprocess.run(command, cwd=attempt, stdout=stdout, check=True)
    end = whole_iq.raw.mark("both calibration arms returned")
    validate_result(whole_iq.read(attempt / "position.json"))
    save_json(attempt / "end.json", end)


def evaluate(ident, detector, digest, receiver, out, cpus, limit_s, *, expected_native=None):
    out = local_output(out)
    if (
        out.is_relative_to(whole_iq.BULK / "leo")
        or len(cpus) != 2
        or len(set(cpus)) != 2
        or not set(cpus) <= os.sched_getaffinity(0)
        or not 1 <= limit_s <= 600
    ):
        raise ValueError("require local output, two available cores and a bounded service")
    detector, receiver = detector.resolve(), receiver.resolve()
    whole_iq.checked(detector, digest)
    private_module = receiver / "tools/pipeline_eval/variants/winner_stream.py"
    if not private_module.is_file():
        raise ValueError("install a phase-release receiver with the private winner input first")
    case, _ = whole_iq.binding(ident)
    out.mkdir(parents=True, exist_ok=False)
    save_json(
        out / "plan.json",
        dict(
            case=ident,
            cpus=list(cpus),
            limit_s=limit_s,
            detector=str(detector),
            detector_sha256=digest,
            receiver=str(receiver),
            receiver_files=whole_iq.receiver_identity(receiver),
            native_sources=whole_iq.native_sources(receiver),
            capture_era_request=case["request"]["sha256"],
            recording=case["recording"],
            expected_native=expected_native.removeprefix("sha256:") if expected_native else None,
            handoff_source_sha256=whole_iq._sha(Path(handoff.__file__)),
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
        "--property=MemoryMax=" + str(whole_iq.MEMORY),
        "--property=MemorySwapMax=0",
        "--property=Nice=10",
        "--property=KillMode=control-group",
        f"--property=RuntimeMaxSec={limit_s}s",
        "--setenv=TMPDIR=" + str(out),
        *(f"--setenv={k}={v}" for k, v in whole_iq.recording.SINGLE_THREAD.items()),
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
    with patch.object(iq_service, "MODULE", MODULE):
        service = iq_service.run(out, command, unit, timeout=limit_s + 18)
    if not iq_service.succeeded(service) or not (out / "end.json").exists():
        raise RuntimeError(f"saved-IQ winner-stream service failed; see {out / 'service.log'}")
    return service


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="action", required=True)
    run = subs.add_parser("run")
    run.add_argument("--case", required=True)
    run.add_argument("--detector", required=True, type=Path)
    run.add_argument("--detector-sha256", required=True)
    run.add_argument("--receiver", required=True, type=Path)
    run.add_argument("--out", required=True, type=local_output)
    run.add_argument("--cpus", required=True, nargs=2, type=int)
    run.add_argument("--limit-s", type=int, default=286)
    run.add_argument("--expected-native")
    for command in ("worker", "position", "recover"):
        subs.add_parser(command).add_argument("attempt", type=local_output)
    args = parser.parse_args()
    if args.action == "worker":
        worker(args.attempt)
    elif args.action == "position":
        position(args.attempt)
    elif args.action == "recover":
        with patch.object(iq_service, "MODULE", MODULE):
            print(json.dumps(iq_service.reconcile(args.attempt), indent=2, sort_keys=True))
    else:
        evaluate(
            args.case,
            args.detector,
            args.detector_sha256,
            args.receiver,
            args.out,
            args.cpus,
            args.limit_s,
            expected_native=args.expected_native,
        )


if __name__ == "__main__":
    main()
