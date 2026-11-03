"""Switch ALGO02 only after exact installed replay and observed idle job ownership."""

import argparse
import json
import os
import select
import signal
import subprocess
import time
from contextlib import suppress
from pathlib import Path

from activate_algo03_runtime import activity
from stage_algo02_runtime import verify

SERVICE = "leo-fast-shared-position.service"
OVERRIDE = Path("/etc/systemd/system") / (SERVICE + ".d/95-runtime-composition.conf")


def property_value(name):
    return subprocess.check_output(["systemctl", "show", SERVICE, "-p", name, "--value"],
                                   text=True).strip()


def environment(pid):
    return dict(p.split("=", 1) for p in Path(f"/proc/{pid}/environ").read_text().split("\0")
                if "=" in p)


def configuration(stage):
    root, pin, python = stage["release"], stage["runtime_manifest_sha256"], stage["python"]
    return ("[Service]\n"
            f"WorkingDirectory={root}\n"
            f"Environment=PYTHONPATH={root}/src:{root}/tools\n"
            "ExecStart=\n"
            f"ExecStart={python} -B -m leo.cli.fast_graph_position "
            "--bulk-root /srv/bulk/leo --maximum-seconds 1200\n"
            f"ExecStartPre={python} -B {root}/tools/stage_algo02_runtime.py verify "
            f"--root {root} --pin {pin}\n")


def check_canary(stage, parity):
    if not (parity["exact"] and parity["tolerance"] == 0 and parity["files"] == 6
            and parity["difference_count"] == 0 and parity["both_calibration_arms_required"]
            and parity["frozen_inputs_verified"] and parity["read_audit"]["verified"]
            and parity["runtime_manifest_sha256"] == stage["runtime_manifest_sha256"]
            and parity["runtime_root"] == stage["release"]):
        raise ValueError("Exact installed ALGO02 canary required")


def activate(stage, parity, *, execute=False):
    root, pin = Path(stage["release"]), stage["runtime_manifest_sha256"]
    if root.parent != Path("/opt/leo-fast-graph-runtime-algo02"):
        raise ValueError("Unexpected ALGO02 runtime root")
    check_canary(stage, parity)
    verify(root, pin)
    pid = int(property_value("MainPID"))
    before = activity(pid)
    if not before["idle"] or not execute:
        return dict(activated=False, before=before, dry_run=not execute)
    expected_old = f"{stage['base']}/src:{stage['base']}/tools"
    if environment(pid).get("PYTHONPATH") != expected_old:
        raise ValueError("Live watcher is not the qualified installed baseline")
    if OVERRIDE.exists():
        raise FileExistsError("Preserve the existing override before another activation")
    handle = os.pidfd_open(pid)
    try:
        signal.pidfd_send_signal(handle, signal.SIGSTOP)
        for _ in range(100):
            states = [p.read_text().split(") ", 1)[1].split()[0]
                      for p in Path(f"/proc/{pid}/task").glob("*/stat")]
            if states and all(s == "T" for s in states):
                break
            time.sleep(.01)
        else:
            raise RuntimeError("Watcher threads did not fully stop")
        frozen = activity(pid)
        if int(property_value("MainPID")) != pid or not frozen["idle"]:
            return dict(activated=False, before=before, frozen=frozen)
        verify(root, pin)
        with OVERRIDE.open("x") as stream:
            stream.write(configuration(stage))
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        signal.pidfd_send_signal(handle, signal.SIGTERM)
        signal.pidfd_send_signal(handle, signal.SIGCONT)
        if not select.select([handle], [], [], 10)[0]:
            raise RuntimeError("Idle watcher did not exit")
        subprocess.run(["systemctl", "start", SERVICE], check=True)
        expected_new = f"{root}/src:{root}/tools"
        for _ in range(100):
            current = int(property_value("MainPID"))
            if current and current != pid:
                with suppress(FileNotFoundError, ProcessLookupError):
                    if environment(current).get("PYTHONPATH") == expected_new:
                        return dict(activated=True, before=before, frozen=frozen, new_pid=current,
                                    runtime=str(root), runtime_manifest_sha256=pin,
                                    activated_utc_ns=time.time_ns(), override=str(OVERRIDE))
            time.sleep(.02)
        raise RuntimeError("Replacement live runtime not verified; inspect without restarting")
    finally:
        with suppress(ProcessLookupError):
            signal.pidfd_send_signal(handle, signal.SIGCONT)
        os.close(handle)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("stage", "canary", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to("/srv/bulk/leo/research") or args.output.exists():
        raise ValueError("New private activation receipt required")
    result = activate(json.loads(args.stage.read_text()), json.loads(args.canary.read_text()),
                      execute=args.execute)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result))
