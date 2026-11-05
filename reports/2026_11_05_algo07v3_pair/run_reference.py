"""Restore hash-bound historical helpers only inside a private namespace.

External oracle harness. The native ALGO07v3 process never imports this code or
receives the reference result. No host source files or production state change.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def run(args):
    rows = json.loads(args.bindings.read_bytes())
    if not rows or len({row["target"] for row in rows}) != len(rows):
        raise ValueError("Unique frozen source bindings required")
    for row in rows:
        source, target = Path(row["source"]), Path(row["target"])
        if not source.is_absolute() or not target.is_absolute():
            raise ValueError("Absolute namespace bindings required")
        if hashlib.sha256(source.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("Historical source bytes differ from the frozen manifest")
        if not target.is_file():
            raise ValueError("Binding target must already be a file")
    before = os.readlink("/proc/self/ns/mnt")
    os.unshare(os.CLONE_NEWNS | os.CLONE_NEWNET)
    if os.readlink("/proc/self/ns/mnt") == before:
        raise RuntimeError("Refusing to bind files in the host namespace")
    subprocess.run(["mount", "--make-rprivate", "/"], check=True)
    for row in rows:
        subprocess.run(["mount", "--bind", row["source"], row["target"]], check=True)
        subprocess.run(["mount", "-o", "remount,bind,ro", row["target"]], check=True)
        if hashlib.sha256(Path(row["target"]).read_bytes()).hexdigest() != row["sha256"]:
            raise RuntimeError("Private source binding did not take effect")
    command = [
        sys.executable,
        "-B",
        "tools/benchmark_algo07_star_case.py",
        "--case",
        str(args.case),
        "--side",
        "reference",
        "--publication-plan",
        str(args.publication_plan),
        "--presentation-manifest",
        str(args.presentation_manifest),
        "--output",
        str(args.output),
        "--resume-completed-checkpoints",
    ]
    with args.output.with_suffix(".namespace.json").open("x") as stream:
        json.dump(
            dict(
                bindings=rows,
                command=command,
                private_mount=True,
                private_network=True,
                parent_mount_namespace=before,
                mount_namespace=os.readlink("/proc/self/ns/mnt"),
            ),
            stream,
            indent=2,
        )
        stream.write("\n")
    os.execvpe(command[0], command, os.environ)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("bindings", "case", "publication-plan", "presentation-manifest", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
