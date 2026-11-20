"""Compare relocated staggered recording packets to the exact hard source on fixed windows."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from contextlib import ExitStack
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from . import portable_mode_build as bundle
from . import staggered_whole
from .full_v5_check import BULK, _load_case, _sha

CASES = ("DS26-0197", "DS29-0316")
SEGMENTS = (5, 10)
VISITS = 24
CPUS = (6, 7)


def source(case_id):
    case = _load_case(case_id)
    paths, edges = [], set()
    for index in SEGMENTS:
        row = case["recording"]["segments"][index]
        location = BULK / row["path"]
        # The repository's protected archive has a pre-existing read account.
        body = subprocess.check_output(["sudo", "-n", "-u", "leo", "cat", str(location)])
        from hashlib import sha256

        if sha256(body).hexdigest() != row["sha256"]:
            raise ValueError("archived segment differs from its sealed input")
        manifest = json.loads(body)
        edges.update(t["edge"] for t in manifest["configuration"]["targets"])
        paths.append(
            dict(path=str(location), sha256=row["sha256"], windows=manifest["window_count"])
        )
    (edge,) = edges
    return dict(id=case_id, segments=paths, edge=edge, cpus=CPUS)


def reference(job, original):
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window
    from leo.storage import short_window
    from leo.storage.fast_scan import FastSegmentSource

    from ..variants.staggered_native import RfStagger, StaggeredLane
    from .whole_memory_chain_worker import AuthenticatedMember

    main, helper = job["cpus"]
    os.sched_setaffinity(0, {main})
    checked = original / bundle.NATIVE
    whole_iq.checked(checked, job["detector_sha256"])
    state, policy = RfStagger(), FastScanPolicyV2()
    previous = short_window.ShortWindowReader._member
    verified = []

    def member(reader, name, size, digest):
        if any(chunk.payload_relative_path == name for chunk in reader.manifest.chunks):
            path = short_window.confined_path(reader.path, reader.path / name, must_exist=True)
            return AuthenticatedMember(path, size, digest, verified)
        return previous(reader, name, size, digest)

    out = Path(job["out"])
    with ExitStack() as stack:
        stack.enter_context(patch.multiple(staggered_whole, MAIN=main, HELPER=helper))
        stack.enter_context(patch.object(short_window.ShortWindowReader, "_member", member))
        port = stack.enter_context(StaggeredLane(checked, job["edge"], helper_cpu=helper))
        trace = stack.enter_context((out / "staggered-visits.jsonl").open("x"))
        for index, segment in enumerate(job["segments"]):
            sensor = FastSegmentSource(
                dict(
                    path=str(Path(segment["path"]).parent),
                    manifest_digest="sha256:" + segment["sha256"],
                ),
                stop_sequence=VISITS,
            )
            for window in sensor.windows():
                values = json.loads(window.acquisition.get("retune_receipt") or "{}")
                frame = (
                    index,
                    window,
                    values.get("utc_clock_bracket"),
                    values.get("host_delivery_clock"),
                )
                _, row = staggered_whole.run_visit(frame, state, port, analyze_window, policy)
                trace.write(encoded(row).decode() + "\n")
    if not verified:
        raise ValueError("the direct source must authenticate real compressed chunks")
    counters = getrusage(RUSAGE_SELF)
    (out / "process.json").write_text(
        json.dumps(
            dict(
                cpu_s=counters.ru_utime + counters.ru_stime,
                peak_rss_kib=counters.ru_maxrss,
            )
        )
    )


SCRIPT = """
import json, runpy, sys
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
root, job, count = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
entry = runpy.run_path(str(root / 'receive.py'))
entry['verify_package']()
entry['raw_bridge']()
from portable_staggered import capture
request = json.loads(job.read_bytes())
capture(request, visits_per_segment=count)
entry['verify_loaded'](root / 'capture')
actual = getrusage(RUSAGE_SELF)
(Path(request['out']) / 'process.json').write_text(json.dumps(dict(
    cpu_s=actual.ru_utime+actual.ru_stime, peak_rss_kib=actual.ru_maxrss,
)))
"""


def run_one(case, role, package, python, original, work):
    out = work / case["id"] / role
    out.mkdir(parents=True)
    subprocess.run(["setfacl", "-m", "u:leo:rwx", str(out)], check=True)
    job = out / "request.json"
    save_json(job, dict(case, out=str(out)))
    job.chmod(0o644)
    if role == "relocated":
        receiver = [
            "bwrap",
            "--unshare-user",
            "--unshare-net",
            "--unshare-pid",
            "--die-with-parent",
            "--ro-bind",
            "/",
            "/",
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--tmpfs",
            str(ROOT),
            "--tmpfs",
            "/opt",
            "--tmpfs",
            str(original),
            "--bind",
            str(out),
            str(out),
            "--chdir",
            str(out),
            "--clearenv",
            "--setenv",
            "PATH",
            "/usr/bin:/bin",
            "--setenv",
            "TMPDIR",
            str(out),
            "--setenv",
            "MPLCONFIGDIR",
            str(out),
            str(python),
            "-IB",
            "-c",
            SCRIPT,
            str(package),
            str(job),
            str(VISITS),
        ]
    else:
        receiver = [
            "env",
            "PYTHONPATH=" + str(ROOT / "src") + ":" + str(ROOT),
            "MPLCONFIGDIR=" + str(out),
            str(python),
            "-B",
            "-m",
            "tools.pipeline_eval.qualification.portable_mode_check",
            "--reference",
            str(job),
            str(original),
        ]
    usage = out / "usage.txt"
    with (out / "stage.log").open("wb") as log:
        command = [
            "nice",
            "-n",
            "10",
            "taskset",
            "-c",
            ",".join(map(str, CPUS)),
            "/usr/bin/time",
            "-o",
            str(usage),
            "-f",
            "%e %U %S %M",
            "sudo",
            "-n",
            "-u",
            "leo",
            "--",
            "env",
            "OPENBLAS_NUM_THREADS=1",
            "MKL_NUM_THREADS=1",
            "OMP_NUM_THREADS=1",
            *receiver,
        ]
        if role == "relocated":
            receiver_env = receiver.index("--clearenv") + 1
            receiver[receiver_env:receiver_env] = [
                "--setenv",
                "OPENBLAS_NUM_THREADS",
                "1",
                "--setenv",
                "OMP_NUM_THREADS",
                "1",
                "--setenv",
                "MKL_NUM_THREADS",
                "1",
            ]
            command = command[: command.index("bwrap")] + receiver
        subprocess.run(
            command, cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=90, check=True
        )
    wall, *_ = usage.read_text().split()
    actual = whole_iq.read(out / "process.json")
    if not (actual["cpu_s"] > 0 and actual["peak_rss_kib"] > 0):
        raise ValueError("the isolated native receiver did not report its own resource use")
    trace = [
        json.loads(line) for line in (out / "staggered-visits.jsonl").read_bytes().splitlines()
    ]
    return trace, dict(wall_s=float(wall), **actual)


def comparison(expected, moved):
    keys = (
        "visit",
        "status",
        "rf_center_hz",
        "sample_start",
        "sample_end",
        "full_visit_sha256",
        "visit_metadata_sha256",
    )
    seen = Counter()
    if len(expected) != len(moved) or len(expected) != len(SEGMENTS) * VISITS:
        raise ValueError("the bounded native comparison lacks frozen physical visits")
    ledger = []
    for left, right in zip(expected, moved, strict=True):
        if any(left[key] != right[key] for key in keys) or left.get("fifth_lane") != right.get(
            "fifth_lane"
        ):
            raise ValueError("packaged native output differs from the hard reference")
        if right["status"] == "processed":
            rf = right["rf_center_hz"]
            if right["fifth_lane"] != seen[rf] % 2:
                raise ValueError("packaged RF counter advanced outside its actual valid scope")
            seen[rf] += 1
            if [r["cpu"] for r in right["lanes"]] != list(CPUS):
                raise ValueError("the native helper left its CPU")
        elif right["status"] != "invalid_capture" or right.get("fifth_lane") is not None:
            raise ValueError("invalid capture unexpectedly selected an enhanced lane")
        ledger.append({k: right[k] for k in keys} | {"fifth_lane": right.get("fifth_lane")})
    return ledger, dict(
        valid=sum(seen.values()), invalid=len(ledger) - sum(seen.values()), rf=len(seen)
    )


def qualify(package, python, original, work):
    work.mkdir()
    report = bundle.REPORT
    lock = whole_iq.read(whole_iq.checked(original / "build.json", bundle.BUILD_SHA))
    cases = [dict(source(ident), detector_sha256=lock["files"][bundle.NATIVE]) for ident in CASES]
    save_json(
        report / "source-lock.json",
        dict(
            cases=cases,
            segments=SEGMENTS,
            visits_per_segment=VISITS,
            cpu=CPUS,
            package_sha256=_sha(package / "files.json"),
            native_build_sha256=bundle.BUILD_SHA,
            base_sha256=whole_iq.read(package / "files.json")["original_archive_sha256"],
            protocol_sha256=_sha(report / "PROTOCOL.md"),
            code_sha256=_sha(Path(__file__)),
        ),
    )
    results = []
    for index, case in enumerate(cases):
        order = ("reference", "relocated") if index == 0 else ("relocated", "reference")
        outcomes = {role: run_one(case, role, package, python, original, work) for role in order}
        ledger, counts = comparison(outcomes["reference"][0], outcomes["relocated"][0])
        results.append(
            dict(
                id=case["id"],
                order=order,
                ledger=ledger,
                counts=counts,
                timings={role: measured[1] for role, measured in outcomes.items()},
            )
        )
        print(case["id"], counts, flush=True)
    save_json(report / "parity.json", dict(cases=results, identical_packets=True))
    write(report / "native-build.json", (original / "build.json").read_bytes())
    shutil.copyfile(package / "files.json", report / "release-files.json")


if __name__ == "__main__":
    if sys.argv[1] == "--reference":
        reference(whole_iq.read(Path(sys.argv[2])), Path(sys.argv[3]))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("package", type=local_output)
        parser.add_argument("python", type=Path)
        parser.add_argument("original", type=local_output)
        parser.add_argument("work", type=local_output)
        args = parser.parse_args()
        qualify(args.package, args.python.absolute(), args.original, args.work)
