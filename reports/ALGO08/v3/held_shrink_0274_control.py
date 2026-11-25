"""Admit one prepared DS30-0274 RAM-only saved cell."""

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
HALF = ("2d44dc0056610e1d428f04b6618d2f7b14666ac7bc5b6c333e9401ef3c92aed1",
        "8382090850a73f9646d8b80cd01a071da2459093255b1f4baed608995d904a47",
        "2574cf66808679462e36712dc82dc8c0fbb41083fe1e7d2821ab6c13a4e203ed")
PARITY = "3417ef13038efa7c44f863ceff7fb5656c56a0c95860110a1b634e5ba6ee4a24"
RAM_SOURCE = "f57e82cb0695a0683c61c34d6ceac4653499f8ea2526ffcaf4ce47fdafdd4067"


def launch(pid, *, probe=False, cell="ordinary"):
    root = BLOCK/cell
    capsule = BLOCK/f"{cell}-capsule"
    plan_pin, ready_pin, proof_pin = (PLAN, READY, PROOF) if cell == "ordinary" else HALF
    if cell != "ordinary":
        parity = trial.document(BLOCK/"ordinary-capsule/output/ordinary-parity.json", PARITY)
        if not parity["exact_ordinary_reproduction"]:
            raise ValueError("A shrink may run only after exact ordinary scientific parity")
    proof = capsule/"verified-isolation.json"
    plan = trial.document(root/"plan.json", plan_pin)
    trial.document(root/"ready.json", ready_pin)
    trial.document(proof, proof_pin)
    if trial.identifier(Path(ram.__file__)) != RAM_SOURCE or plan["cell"] != cell:
        raise ValueError("Expected the frozen cell and isolation source")
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
                        PLAN=plan_pin, READY=ready_pin, saved=ports, __file__=run_worker.__code__.co_filename,
                        MODE_ARGS=("--cell",cell), EXTRA_FILE_NAMES=("ready.json",), command=measured):
        if not probe:
            return ram.watch(pid, proof_pin)
        import subprocess
        with (ram.OUTPUT/"plan.json").open("rb") as descriptor:
            return subprocess.run(measured(ram.bindings(), "sandbox-preflight"),
                                  stdin=descriptor, timeout=8, check=False).returncode


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--driver-pid", type=int)
    parser.add_argument("--cell", choices=("ordinary", "half-blend"), default="ordinary")
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    if args.driver_pid is None and not args.probe:
        parser.error("The official driver PID is required to watch")
    sys.exit(launch(args.driver_pid, probe=args.probe, cell=args.cell))
