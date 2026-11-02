"""One bounded adaptive/fast acquisition under the existing capture authority.

The existing systemd timer owns cadence; this adapter only selects the next
mode and launches the qualified recorder. It never runs numerical analysis.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import shutil
import time
import uuid
from pathlib import Path

from leo.acquisition.authority import (
    CapturePausedError,
    CaptureTaskKind,
    LocalCaptureAuthority,
    RadioBusyError,
    RadioResource,
)

SEQUENCE = (("fast", "lower"), ("adaptive", None), ("fast", "upper"), ("adaptive", None))


def save_state(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("x") as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def capture_capacity(config, mode, *, disk_usage=shutil.disk_usage):
    """Reserve capture storage; analysis state is not an acquisition resource."""
    command = config[mode]["command"]
    flag = "--root" if mode == "fast" else "--iq-spool-root"
    if flag not in command:
        return None  # Some bounded adapters own their storage admission check.
    path = Path(command[command.index(flag) + 1]).resolve()
    if path == Path('/mnt/qnap01') or Path('/mnt/qnap01') in path.parents:
        raise ValueError('Capture storage must be local')
    while not path.exists():
        path = path.parent
    reserve = config.get('minimum_capture_free_bytes', 30_000_000_000)
    if isinstance(reserve, bool) or not isinstance(reserve, int) or reserve <= 0:
        raise ValueError('Positive capture reserve required')
    free = disk_usage(path).free
    return dict(path=str(path), free_bytes=free, required_bytes=reserve)


def run_cycle(config, state_path, authority, *, run=subprocess.run, pending_fast=0,
              capacity=capture_capacity):
    state = json.loads(state_path.read_text()) if state_path.exists() else {"completed": 0}
    if state.get("attempts", 0) >= config.get("maximum_attempts", float("inf")):
        return {"state": "deferred", "reason": "bounded verification capture limit reached"}
    mode, edge = SEQUENCE[state["completed"] % len(SEQUENCE)]
    space = capacity(config, mode)
    if space and space['free_bytes'] < space['required_bytes']:
        return dict(state='deferred', reason='insufficient capture storage', storage=space)
    try:
        lease = authority.claim((config["serial"],), task_id=f"shared-scan-{uuid.uuid4().hex}",
                                task_kind=CaptureTaskKind.SCANNER_SWEEP)
    except (CapturePausedError, RadioBusyError) as error:
        return {"state": "deferred", "reason": str(error)}
    with lease:
        token = f"fast8-auto-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-{uuid.uuid4().hex[:8]}"
        command = [part.replace("{edge}", edge or "").replace("{campaign}", token)
                   for part in config[mode]["command"]]
        state.update(mode=mode, edge=edge, state="recording", started_utc_ns=time.time_ns(),
                     campaign=token if mode == "fast" else None,
                     attempts=state.get("attempts", 0) + 1,
                     finished_utc_ns=None, failure=None)
        save_state(state_path, state)
        environment = {**os.environ, **config[mode].get("environment", {})}
        try:
            result = run(command, env=environment, check=False, timeout=380)
            if result.returncode:
                raise RuntimeError(f"{mode} capture exited {result.returncode}")
        except BaseException as error:
            state.update(state="failed", failure=str(error), finished_utc_ns=time.time_ns())
            save_state(state_path, state)
            raise
        state.update(completed=state["completed"] + 1, state="complete", failure=None,
                     finished_utc_ns=time.time_ns())
        save_state(state_path, state)
        return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    bulk = Path(config["bulk_root"])
    authority = LocalCaptureAuthority(bulk / "control", (
        RadioResource(config["serial"], config["serial"], config["uri"]),))
    print(json.dumps(run_cycle(config, args.state, authority)), flush=True)


if __name__ == "__main__":
    main()
