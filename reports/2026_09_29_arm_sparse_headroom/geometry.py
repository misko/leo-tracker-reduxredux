"""Explicit bounded physical compatibility checks; never timing qualification."""

import argparse
import json
import shlex
import subprocess
from pathlib import Path

from execute import HERE, connection, digest, save


def main(args):
    remote, upload = connection(args)
    root = json.loads((HERE / "execution-panel.json").read_text())["remote_root"]
    executable = root + "/geometry-" + digest(args.binary)[:16]
    upload(args.binary, executable)
    remote("chmod +x " + shlex.quote(executable))
    evidence = {
        "binary_sha256": digest(args.binary),
        "cases": [],
        "scope": "physical ARM correctness, unpinned; no timing claim",
    }
    for rate in (2500000, 5000000, 7500000, 10000000):
        for dwell in (120, 240, 360):
            if args.case and f"{rate}:{dwell}" not in args.case:
                continue
            command = "ulimit -v 220000 && " + shlex.join(
                [executable, "--rate-hz", str(rate), "--dwell-ms", str(dwell)]
            )
            try:
                output = remote("( " + command + " ) 2>&1", timeout=300)
                status = 0
            except subprocess.CalledProcessError as error:
                output, status = error.output, error.returncode
            evidence["cases"].append(
                {
                    "rate_hz": rate,
                    "dwell_ms": dwell,
                    "strides_ms": [10, 20, 120],
                    "virtual_memory_limit_kib": 220000,
                    "returncode": status,
                    "output": output,
                }
            )
            save(args.output, evidence)
            print(rate, dwell, status, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--password-file", type=Path, required=True)
    parser.add_argument("--target", default="root@192.168.1.15")
    parser.add_argument("--case", action="append")
    parser.add_argument("--output", type=Path, default=HERE / "hardware-geometry.json")
    main(parser.parse_args())
