"""Run paired complete saved-IQ solves with a chronological own-winner hint selector."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from time import monotonic, time_ns
from uuid import uuid4

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from ..variants import causal_track_scout, hinted_glrt
from . import (
    capture_release,
    hinted_whole_raw,
    whole_winner,
    whole_winner_handoff,
    winner_stream_trial,
)
from .full_v5_check import _sha

REPORT = winner_stream_trial.SCREEN / "receiver-core/hinted-whole"
SCHEDULE = {"DS26-0237": (0, ("stock", "hinted")), "DS29-0519": (18, ("hinted", "stock"))}
BUILD = Path("/home/mouse9911/.cache/leo-hinted-glrt-20261119/build-lock.json")
MODULE = "tools.pipeline_eval.qualification.hinted_whole"
LIMIT = 450


def prepare(work):
    work.mkdir(exist_ok=False)
    provenance = whole_iq.read(BUILD)
    libraries = {}
    for role, pin in provenance["library_sha256"].items():
        target = work / f"detector-{role}.so"
        shutil.copyfile(whole_iq.checked(Path(provenance["paths"][role]), pin), target)
        whole_iq.checked(target, pin)
        libraries[role] = dict(path=str(target), sha256=pin)
    bound = work / "receiver"
    winner_stream_trial.install(bound, True)
    source = dict(
        cases={},
        receiver=dict(root=str(bound), files=whole_iq.receiver_identity(bound)),
        libraries=libraries,
        build_lock_sha256=_sha(BUILD),
        memory=whole_iq.MEMORY,
        swap=0,
        cap_s=LIMIT,
        nice=10,
        freeze_ns=time_ns(),
    )
    for ident, (cpu, order) in SCHEDULE.items():
        case, _ = whole_iq.binding(ident)
        capture = capture_release.read_capture(case)
        source["cases"][ident] = dict(
            cpu=cpu,
            order=order,
            capture=capture,
            session_id=case["session_id"],
            tile=case["regions"][0],
            catalog_sha256=case["catalog"]["sha256"],
            capture_native_sha256=case["native"]["sha256"],
            request_sha256=case["request"]["sha256"],
            recording=case["recording"],
        )
    paths = (
        Path(__file__),
        Path(hinted_whole_raw.__file__),
        Path(hinted_glrt.__file__),
        hinted_glrt.HEADER,
        Path(causal_track_scout.__file__),
        Path(whole_iq.__file__),
        Path(whole_iq.recording.__file__),
        Path(whole_iq.raw.__file__),
        Path(whole_winner.__file__),
        Path(whole_winner_handoff.__file__),
        REPORT / "PROTOCOL.md",
        REPORT.parent / "causal-track-scout/source-lock.json",
    )
    source["sources"] = {str(p.relative_to(ROOT)): _sha(p) for p in paths}
    save_json(REPORT / "source-lock.json", source)
    (work / "study.sha256").write_text(_sha(REPORT / "source-lock.json") + "\n")


def partition(out):
    """Make two parity views for the existing bounded, hash-verified handoff."""
    with ExitStack() as stack:
        lanes = [stack.enter_context((out / f"replayed-{i}.jsonl").open("xb")) for i in (0, 1)]
        serial = stack.enter_context((out / "chronological.jsonl").open("rb"))
        terminal = False
        for line in serial:
            if terminal:
                raise ValueError("unexpected data after chronological worker footer")
            row = json.loads(line)
            if row["kind"] == "worker":
                if row != dict(kind="worker", worker=0):
                    raise ValueError("invalid chronological footer")
                terminal = True
            else:
                lanes[row["segment"] % 2].write(line)
        if not terminal:
            raise ValueError("chronological lane never sealed its detector replies")
        for i, handle in enumerate(lanes):
            handle.write(whole_iq.recording.encoded(dict(kind="worker", worker=i)).encode() + b"\n")


def raw_lane(out, case, capture, detector, role, cpu):
    recording = whole_iq.recording
    release = capture_release.producer(case, capture)
    bound_capture = dict(
        capture,
        case={k: case[k] for k in ("id", "run_id", "session_id")},
        segments_sha256=recording.digest(case["recording"]["segments"]),
    )
    recording.save(out / "capture.json", bound_capture)
    recording.save(out / "segments.json", case["recording"]["segments"])
    cmd = [
        "taskset",
        "-c",
        str(cpu),
        "sudo",
        "-n",
        "-u",
        "leo",
        "--",
        "env",
        f"PYTHONPATH={release.root}:{ROOT}",
        f"LEO_HINTED_WHOLE_ROLE={role}",
        *(f"{key}={value}" for key, value in recording.SINGLE_THREAD.items()),
        str(recording.ARCHIVE_PYTHON),
        "-Bu",
        "-m",
        hinted_whole_raw.__name__,
        "0",
        "--case",
        case["id"],
        "--native-library",
        str(detector),
        "--capture",
        recording.encoded(bound_capture),
        "--detector",
        "ordinary",
    ]
    with (
        (out / "segments.json").open("rb") as segments,
        (out / "chronological.jsonl").open("xb") as output,
        (out / "detector.log").open("xb") as log,
    ):
        subprocess.run(cmd, cwd=ROOT, stdin=segments, stdout=output, stderr=log, check=True)
    return bound_capture


def worker(folder):
    plan = whole_iq.read(folder / "plan.json")
    pin, role = plan["binding"], plan["role"]
    if os.sched_getaffinity(0) != {pin["cpu"]} or os.nice(0) != 10:
        raise ValueError("chronological lane lost its predeclared core or priority")
    detector = whole_iq.checked(Path(plan["detector"]["path"]), plan["detector"]["sha256"])
    if whole_iq.receiver_identity(Path(plan["receiver"])) != plan["receiver_files"]:
        raise ValueError("installed position receiver differs from the plan")
    case, request = whole_iq.binding(plan["id"])
    if case["request"]["sha256"] != pin["request_sha256"] or case["recording"] != pin["recording"]:
        raise ValueError("capture or original blind request changed")
    out = folder / "recording"
    out.mkdir()
    start = whole_iq.raw.mark("chronological complete IQ start")
    save_json(folder / "start.json", start)
    capture = raw_lane(out, case, pin["capture"], detector, role, pin["cpu"])
    raw_end = whole_iq.raw.mark("chronological detector complete")
    text = (out / "detector.log").read_text()

    def receipt(prefix):
        found = [
            json.loads(line[len(prefix) :]) for line in text.splitlines() if line.startswith(prefix)
        ]
        if len(found) != 1:
            raise ValueError("incomplete chronological resident receipt")
        return found[0]

    feedback = receipt("hint-summary: ")
    raw = receipt("whole-lane-result: ")
    if (
        feedback["mode"] != role
        or raw["compressed_chunks"] < 1
        or any(
            raw[key]["cgroup"] != start["cgroup"] or raw[key]["cpus"] != [pin["cpu"]]
            for key in ("start", "end")
        )
    ):
        raise ValueError("chronological lane receipt differs from its physical service")
    partition(out)
    with (out / "native.winners").open("xb") as handle:
        summary = whole_winner_handoff.assemble(
            out, case, capture, plan["detector"]["sha256"], handle
        )
    if summary["counts"]["processed_windows"] != len(raw["native_timings_s"]) or (
        feedback["counts"]["visits"] != len(raw["native_timings_s"])
    ):
        raise ValueError("missing detector visits in the position handoff")
    request_path = folder / "position-request.json"
    save_json(request_path, request)
    summary.update(
        raw_end=raw_end,
        position_start=whole_iq.raw.mark("phase release enter"),
        position_request_sha256=_sha(request_path),
        chronological_sha256=_sha(out / "chronological.jsonl"),
        detector_log_sha256=_sha(out / "detector.log"),
        feedback=feedback,
        compressed_chunks=raw["compressed_chunks"],
        compressed_bytes=raw["compressed_bytes"],
    )
    save_json(folder / "raw.json", summary)
    os.execv(
        sys.executable, [sys.executable, "-B", "-m", whole_winner.MODULE, "position", str(folder)]
    )


def execute(work, source, ident):
    bind = source["cases"][ident]
    for role in bind["order"]:
        folder = work / ident / role
        folder.mkdir(exist_ok=False, parents=True)
        save_json(
            folder / "plan.json",
            dict(
                id=ident,
                role=role,
                binding=bind,
                detector=source["libraries"][role],
                receiver=source["receiver"]["root"],
                receiver_files=source["receiver"]["files"],
            ),
        )
        unit = "leo-hinted-whole-" + uuid4().hex[:12]
        command = [
            "systemd-run",
            "--user",
            "--wait",
            "--pipe",
            f"--unit={unit}",
            f"--working-directory={ROOT}",
            f"--property=MemoryMax={whole_iq.MEMORY}",
            "--property=MemorySwapMax=0",
            f"--property=RuntimeMaxSec={LIMIT}s",
            "--property=Nice=10",
            "--property=TimeoutStopSec=5s",
            "--property=KillMode=control-group",
            f"--setenv=TMPDIR={folder}",
            *(f"--setenv={k}={v}" for k, v in whole_iq.recording.SINGLE_THREAD.items()),
            "taskset",
            "-c",
            str(bind["cpu"]),
            sys.executable,
            "-B",
            "-m",
            MODULE,
            "worker",
            str(folder),
        ]
        start = monotonic()
        with (folder / "service.log").open("xb") as log:
            code = subprocess.run(
                command, stdout=log, stderr=subprocess.STDOUT, timeout=LIMIT + 20, check=False
            ).returncode
        state = subprocess.run(
            [
                "systemctl",
                "--user",
                "show",
                unit,
                "--property=Result,MainPID,ControlPID,MemoryPeak,MemorySwapPeak,CPUUsageNSec",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=7,
        )
        fields = dict(line.split("=", 1) for line in state.stdout.splitlines() if "=" in line)
        if fields.get("MainPID") != "0" or fields.get("ControlPID") != "0":
            raise RuntimeError("no terminal receipt for the chronological service")
        save_json(
            folder / "service.json",
            dict(
                unit=unit,
                exit_code=code,
                wall_s=monotonic() - start,
                systemd=fields,
                log_sha256=_sha(folder / "service.log"),
            ),
        )
        print(ident, role, fields.get("Result"), code, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "run", "worker"))
    parser.add_argument("work", type=local_output)
    args = parser.parse_args()
    if args.action == "worker":
        worker(args.work)
    elif args.action == "seal":
        prepare(args.work)
    else:
        source = whole_iq.read(
            whole_iq.checked(
                REPORT / "source-lock.json",
                (args.work / "study.sha256").read_text().strip(),
            )
        )
        for name, pin in source["sources"].items():
            whole_iq.checked(ROOT / name, pin)
        with ThreadPoolExecutor(max_workers=2) as workers:
            list(workers.map(lambda ident: execute(args.work, source, ident), SCHEDULE))


if __name__ == "__main__":
    main()
