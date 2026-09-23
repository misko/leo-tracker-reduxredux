"""Continue the existing run after its live baseline process exits; never restart it."""

import argparse
import json
import os
import subprocess
import sys
import time

from export import HERE, ROOT, digest


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-pid", type=int, required=True)
    args = parser.parse_args()
    deadline = time.monotonic() + 7200
    while alive(args.baseline_pid):
        if time.monotonic() > deadline:
            raise TimeoutError("existing baseline still live; left untouched")
        time.sleep(5)
    if not (HERE / "baseline/inference.json").is_file():
        raise RuntimeError("baseline exited without sealed output; do not restart")
    frozen = json.loads((HERE / "execution_sources.json").read_text())["sources"]
    for name in ("timing.py", "evaluate.py", "plot.py"):
        for source, expected in frozen.items():
            if digest(HERE / source) != expected:
                raise RuntimeError(f"execution source changed: {source}")
        print(f"Starting {name}", flush=True)
        subprocess.run([sys.executable, str(HERE / name)], cwd=ROOT, check=True)
        print(f"Completed {name}", flush=True)


if __name__ == "__main__":
    main()
