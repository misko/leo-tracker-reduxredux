"""Compare real OS demand on the existing authenticated DS30-0169 first member."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from unittest.mock import patch

from . import independent_8ms_0169 as prior
from . import incremental_ingress as ingress
from .full_short_cold import freeze


HERE = Path(__file__).resolve().parent
REFERENCE = Path("/dev/shm/leo-independent-8ms-0169-result02/measured8.json")
REFERENCE_PIN = "0c6055720b8f4d0a50c7e446165256f0a1431a6d9a7734358e7f2a41f0c12c19"
PACKET_SHA = "b2a16bc1290bd3cabf383e85cd32d2438e3c84ccd4cac25f4ba168738314e9eb"
PROTOCOL = HERE/"incremental-live-eight-protocol.md"
ORDERS = (("whole", "incremental"), ("incremental", "whole"))
GATE_NS = 10_000_000


def worker(mode, output):
    from .full_short_run import checked_recipe

    scope = prior.read(prior.STAGED/"scope.json")
    path, member = ingress.staged_scope()
    before = prior.residency(scope)
    expected = prior.read(REFERENCE, expected=REFERENCE_PIN)
    original = ingress.ceiling
    recipe = checked_recipe(eight_ms=True)
    with (patch.object(original, "ORIGINAL", prior.EIGHT.parent),
          patch.object(original, "SHORT_SHA", prior.EIGHT_SHA),
          patch.object(original, "recipe", lambda _: recipe)):
        row = ingress.run_arm(mode, output.with_suffix(".detections.json"), None, path, member, expected)
    after = prior.residency(scope)
    reads = row["delivery"]
    if (row["packet_sha256"] != PACKET_SHA or row["verified_windows"] != 64
            or row["completed_stereo"] != 51 or row["process_input_blocks"]
            or row["acquisition"]["native_schedule"]["native_calls"] != {"full": 16, "short_primary": 86}
            or reads["sleep_ns"] or reads["offset"] != member["compressed_bytes"]
            or before != after or not row["sealed"] or row["error"] is not None):
        raise ValueError("Expected actual, unpaced delivery, verified and sealed on the original resident member")
    if mode == "incremental":
        if not 1 < reads["positive_reads"] or not 0 < row["stats"]["max_read_object_bytes"] <= ingress.BLOCK:
            raise ValueError("Incremental delivery did not exercise the bounded file-like reader")
    elif reads["positive_reads"] != 1:
        raise ValueError("The whole-buffer control did not execute one ordinary descriptor read")
    freeze(output, dict(row, member=member, residency=before, archived_20_8_sha256=REFERENCE_PIN))


def advances(pairs):
    for pair in pairs:
        a, b = (pair[mode]["result"] for mode in ("whole", "incremental"))
        if (a["cpu_ns"] - b["cpu_ns"] < GATE_NS
                or a["acquisition"]["acquire_wall_ns"] <= b["acquisition"]["acquire_wall_ns"]):
            return False
    return len(pairs) == len(ORDERS)


def launch(root):
    from .scout_readout_trial import check_machine
    from .short_raw_diagnostic import measure

    machine = check_machine()
    if root.parent.resolve() != Path("/dev/shm") or not os.sched_getaffinity(0) == {2}:
        raise ValueError("Use a fresh tmpfs output under the shared CPU2 lock")
    prior.residency(prior.read(prior.STAGED/"scope.json"))
    checkout = HERE.parents[2]
    git = ["git", "-c", f"safe.directory={checkout}", "-C", str(checkout)]
    if subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("Commit the exact comparison before launch")
    root.mkdir(mode=0o700)
    release = ingress.release.RELEASE
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, (
        checkout, HERE, release/"src", release, ingress.release.PAYLOAD))))
    command = ["/usr/bin/timeout", "--kill-after=2s", "20s", release/"venv/bin/python",
               "-BPs", "-m", __spec__.name, "worker"]
    freeze(root/"binding.json", dict(machine=machine, reference=REFERENCE_PIN, order=ORDERS,
          command=list(map(str, command)),
          commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
          sources={path.name: sha256(path.read_bytes()).hexdigest() for path in (
              Path(__file__), PROTOCOL, HERE/"incremental_ingress.py", HERE/"receiver_ceiling_0169.py",
              HERE/"independent_8ms_0169.py")}))
    pairs = []
    for index, order in enumerate(ORDERS):
        pair = {}
        for mode in order:
            stem = root/f"{index}-{mode}"
            output = stem.with_suffix(".json")
            process = measure([*command, mode, output], env, stem)
            freeze(stem.with_suffix(".clock.json"), process)
            if process["exit_code"]:
                raise RuntimeError(process["stderr_tail"])
            result = json.loads(output.read_bytes())
            pair[mode] = dict(process=process, result=result, file_sha256=sha256(output.read_bytes()).hexdigest())
        pairs.append(pair)
    freeze(root/"result.json", dict(pairs=pairs, dense_eligible=advances(pairs),
                                    packet_sha256=PACKET_SHA, arrival="actual unpaced OS demand"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("launch").add_argument("root", type=Path)
    child = actions.add_parser("worker")
    child.add_argument("mode", choices=("whole", "incremental"))
    child.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.action == "launch":
        launch(args.root)
    else:
        worker(args.mode, args.output)
