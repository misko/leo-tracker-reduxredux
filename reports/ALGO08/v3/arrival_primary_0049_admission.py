"""Admit the single prepared primary-arrival worker through the ordinary gates."""

import argparse
from pathlib import Path
import sys
from time import time_ns
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from arrival_primary_0049 import EXPERIMENT, RUNNER, trial  # noqa: E402
from graph_half_blend_trial import direct_pressure, ready_runtime  # noqa: E402
from joint_recovery_0049_direct import check_quiet, require_cached, require_driver_idle  # noqa: E402
from joint_recovery_0049_wait import CHILD_LIMIT_S, lease, run_child  # noqa: E402


ROOT = Path("/dev/shm/leo-v3-0049-arrival-primary-02")
PLAN_PIN = "e96381e53482c6b75ea1da40393b2ba2759600471e4fb7bbcadf1dadc087c5e9"
READY_PIN = "5292a12d00c1d0f8fda650d698b05c8a3999e4ac57cf034d99a4ea33fca7137c"
WATCH_S = 120


def checked(root, pin):
    if root != ROOT or pin != PLAN_PIN or trial.identifier(Path(trial.__file__)) != RUNNER:
        raise ValueError("Expected the exact authenticated prepared packet and original saved worker")
    ready = trial.document(root / "ready.json", READY_PIN)
    plan = trial.document(root / "plan.json", pin)
    if (ready["plan_sha256"] != pin or ready["protocol"] != trial.protocol(EXPERIMENT)
            or ready["payload"] != plan["change"]["derived_native_sha256"] or ready["solver_runs"]
            or plan["sources"] != trial.source_pins(EXPERIMENT)):
        raise ValueError("The frozen preflight or its detector and worker bindings changed")
    trial.document(root / "derived-native.json", ready["payload"])


def watch(pid, duration):
    if not 0 < duration <= WATCH_S:
        raise ValueError("Use one bounded passive admission watch")
    checked(ROOT, PLAN_PIN)
    machine = trial.attrs(expected_priority="idle")
    runtime = ready_runtime()
    import second_curve_gate_trial as admission

    if trial.identifier(Path(admission.__file__)) != runtime.PRIOR_WATCH:
        raise ValueError("The existing field deferral proof changed")
    binding = dict(driver=Path(__file__).resolve(), plan_pin=PLAN_PIN,
                   protocol=trial.protocol(EXPERIMENT), budget=CHILD_LIMIT_S, flags=[])

    def admit(case, watch_root, proof, ready_pin, event):
        if (case != trial.CASE or watch_root != ROOT / "admission" or proof != ROOT / "ready.json"
                or ready_pin != READY_PIN):
            raise ValueError("Wrong prepared admission scope")
        admission.event_admits(event)
        require_driver_idle(pid)
        quiet = check_quiet()
        with lease() as fd:
            admission.event_admits(event)
            require_driver_idle(pid)
            cache = require_cached()
            quiet_after_lease = direct_pressure(continuous=False)
            require_driver_idle(pid)
            admission.event_admits(event)
            return run_child(ROOT, fd, dict(event=event, quiet=quiet, quiet_after_lease=quiet_after_lease,
                                          cache=cache, driver_pid=pid, admitted_unix_ns=time_ns()),
                             machine, binding=binding)["exit_code"]

    with (patch.object(admission, "WINDOW_S", duration), patch.object(admission, "launch", admit)):
        return admission.watch(trial.CASE, ROOT / "admission", ROOT / "ready.json", READY_PIN)


def worker(root, pin, lease_fd):
    checked(root, pin)
    trial.attrs(expected_priority="idle")
    intent = trial.document(root / "child-intent.json")
    if intent["admission"]["event"]["unix_ns"] > intent["admission"]["admitted_unix_ns"]:
        raise ValueError("The child's recorded admission precedes the official deferral")
    trial.worker(root, pin, EXPERIMENT, lease_fd=lease_fd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    active = commands.add_parser("watch")
    active.add_argument("driver_pid", type=int)
    active.add_argument("--wait-s", type=float, default=WATCH_S)
    child = commands.add_parser("worker")
    child.add_argument("root", type=Path)
    child.add_argument("--pin", required=True)
    child.add_argument("--lease-fd", type=int, required=True)
    commands.add_parser("check")
    args = parser.parse_args()
    if args.action == "watch":
        sys.exit(watch(args.driver_pid, args.wait_s))
    if args.action == "worker":
        worker(args.root, args.pin, args.lease_fd)
    else:
        checked(ROOT, PLAN_PIN)
        print(READY_PIN)
