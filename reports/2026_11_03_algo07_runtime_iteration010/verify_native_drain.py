"""Test installed watcher shutdown with fake work; never signal a service or collect RF."""

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace


def child(root, source):
    sys.path.insert(0, str(source / "src"))
    from leo.cli import fast_scan
    from leo.storage import fast_scan as storage

    class FakeStore:
        def __init__(self, path):
            self.root = path

        def automatic_workspace(self, name):
            path = self.root / name
            path.mkdir(exist_ok=True)
            return path

    def work(recording, *, glrt_lock, **unused):
        name = recording.name
        (root / (name + "-entered")).touch()
        with glrt_lock:
            # This subprocess stands in for numerical work and has no RF/data access.
            script = ("import pathlib,sys,time; p=pathlib.Path(sys.argv[1]); "
                      "\nwhile not p.exists(): time.sleep(.01)\n")
            process = subprocess.Popen([sys.executable, "-c", script,
                                        str(root / (name + "-release"))])
            (root / (name + "-started")).write_text(str(process.pid))
            code = process.wait(timeout=15)
            (root / (name + "-finished")).write_text(str(code))

    storage.FastScanStore = FakeStore
    fast_scan.discover_automatic = lambda *unused: [root / "first", root / "second"]
    fast_scan.process_automatic = work
    os.environ["LEO_DATABASE_URL"] = "unused-test-port"
    args = SimpleNamespace(bulk_root=root, recording_root=root, capture_serial=None,
        standard_python="unused", standard_script="unused", standard_mode="algo07", glrt_workers=16)
    try:
        fast_scan.watch_automatic(args)
    except KeyboardInterrupt:
        (root / "watcher-drained").touch()
        raise


def wait_file(path, process):
    deadline = time.monotonic() + 10
    while not path.exists():
        if process.poll() is not None or time.monotonic() >= deadline:
            raise RuntimeError("Watcher exited early or timed out waiting for " + path.name)
        time.sleep(.01)


def check(source, root):
    root.mkdir(parents=True, exist_ok=False)
    command = [sys.executable, "-B", str(Path(__file__).resolve()), "--child",
               "--source", str(source), "--output", str(root)]
    with (root / "child.log").open("xb") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            for name in ("first-started", "second-entered"):
                wait_file(root / name, process)
            # Only the watcher main process receives SIGINT, never its process group.
            os.kill(process.pid, signal.SIGINT)
            time.sleep(.1)
            active_preserved = process.poll() is None and not (root / "first-finished").exists()
            (root / "first-release").touch()
            wait_file(root / "second-started", process)
            pending_preserved = process.poll() is None and not (root / "second-finished").exists()
            (root / "second-release").touch()
            code = process.wait(timeout=10)
            completed = {name: (root / (name + "-finished")).read_text()
                         for name in ("first", "second")}
            result = dict(passed=active_preserved and pending_preserved
                and code in (-signal.SIGINT, 128 + signal.SIGINT)
                and set(completed.values()) == {"0"} and (root / "watcher-drained").exists(),
                active_work_preserved=active_preserved, pending_work_preserved=pending_preserved,
                numerical_child_exit_codes=completed, watcher_exit_code=code,
                source=str(source), watcher_sha256=hashlib.sha256(
                    (source / "src/leo/cli/fast_scan.py").read_bytes()).hexdigest(),
                production_signaled=False, RF_collected=False)
            (root / "result.json").write_text(json.dumps(result, indent=2) + "\n")
            return result
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--child", action="store_true")
    args = parser.parse_args()
    if args.child:
        child(args.output.resolve(), args.source.resolve())
    else:
        result = check(args.source.resolve(strict=True), args.output.resolve())
        print(json.dumps(result))
        if not result["passed"]:
            raise SystemExit(1)
