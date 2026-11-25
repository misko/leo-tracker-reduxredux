"""Admit only the prepared ordinary DS30-0274 RAM-only control."""

import argparse
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from held_shrink_0274 import (AUTHORITY, BLOCK, CASE, EXPERIMENT, STAGE, ram, ready_runtime, run_worker, trial)  # noqa: E402


PLAN = "750e8188f3d17631b86aba46789ff8f6f116db9b58e64f19625ca00a93868265"
READY = "cf68a3a34816b1fddeac0f063a3d1e7e61529e2d51dbb090c2f4cd0c3c80ea07"
PROOF = "781a3f80e1a9b0817b2956d2abc981bbf9a5abc8974166af18c6f60f7abba278"
RAM_SOURCE = "f57e82cb0695a0683c61c34d6ceac4653499f8ea2526ffcaf4ce47fdafdd4067"


def launch(pid, *, probe=False):
    root = BLOCK/"ordinary"
    capsule = BLOCK/"ordinary-capsule"
    proof = capsule/"verified-isolation.json"
    plan = trial.document(root/"plan.json", PLAN)
    trial.document(root/"ready.json", READY)
    trial.document(proof, PROOF)
    if trial.identifier(Path(ram.__file__)) != RAM_SOURCE or plan["cell"] != "ordinary":
        raise ValueError("Expected the frozen ordinary-only placement and isolation source")
    ports = SimpleNamespace(trial=trial, CASE=CASE, ROOT=root, STAGE=STAGE, AUTHORITY=AUTHORITY,
                            CATALOGUE=plan["catalogue_pin"], ready_runtime=ready_runtime,
                            EXPERIMENT=EXPERIMENT)
    command = ram.command

    def measured(layout, mode):
        argv = command(layout, mode)
        split = argv.index("--")+1
        resources = root/("preflight-resource.txt" if probe else "worker-resource.txt")
        argv[split:split] = ["/usr/bin/time", "-q", "-f", "%U %S %M %I %O", "-o", str(resources)]
        return argv

    with patch.multiple(ram, ROOT=capsule, OUTPUT=capsule/"output", PROOF=proof,
                        PLAN=PLAN, READY=READY, saved=ports, __file__=run_worker.__code__.co_filename,
                        MODE_ARGS=("--cell","ordinary"), EXTRA_FILE_NAMES=("ready.json",), command=measured):
        if not probe:
            return ram.watch(pid, PROOF)
        import subprocess
        with (ram.OUTPUT/"plan.json").open("rb") as descriptor:
            return subprocess.run(measured(ram.bindings(), "sandbox-preflight"),
                                  stdin=descriptor, timeout=8, check=False).returncode


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--driver-pid", type=int)
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    if args.driver_pid is None and not args.probe:
        parser.error("The official driver PID is required to watch")
    sys.exit(launch(args.driver_pid, probe=args.probe))
