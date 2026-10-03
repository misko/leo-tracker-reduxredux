#!/usr/bin/env python3
"""Stage additive API/worker overlays over an explicitly pinned deployed parent.

Does not install services or modify a deployed tree. The manifest records every
staged byte and the distinct API/worker parents, preserving worker memory fixes.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    if args.destination.exists():
        raise FileExistsError("release staging destination must be new")
    parent = json.loads((args.parent / "manifest.json").read_text())
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    subprocess.run(["git", "diff", "--exit-code", "HEAD", "--", "src", "web"], cwd=repo, check=True)
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", parent["commit"], commit, "--", "src"], cwd=repo, text=True
    ).splitlines()
    for role in ("api", "worker"):
        destination = args.destination / role / "src"
        shutil.copytree(
            args.parent / role / "src",
            destination,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        for path in destination.rglob("*"):
            path.chmod(0o755 if path.is_dir() else 0o644)
        destination.chmod(0o755)
        for relative in changed:
            path = args.destination / role / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repo / relative, path)
    # Workers previously predated native V8 capture publication. Admit it through
    # the same public readers already used by the deployed API, not a new path parser.
    native_readers = [
        "src/leo/scanner/adaptive_hop.py",
        "src/leo/scanner/persistent_hop.py",
        "src/leo/scanner/adaptive_hop_history.py",
        "src/leo/scanner/host_adaptive_history.py",
        "src/leo/storage/adaptive_hop.py",
        "src/leo/storage/adaptive_hop_history.py",
    ]
    for relative in native_readers:
        shutil.copy2(args.parent / "api" / relative, args.destination / "worker" / relative)
    shutil.copytree(repo / "web" / "dist", args.destination / "web" / "dist")
    manifest = dict(
        commit=commit,
        parent=str(args.parent),
        parent_commit=parent["commit"],
        changed_modules=changed,
        worker_native_readers=native_readers,
        sha256={},
    )
    for path in sorted(args.destination.rglob("*")):
        if path.is_file():
            manifest["sha256"][str(path.relative_to(args.destination))] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    (args.destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        json.dumps(
            dict(destination=str(args.destination), commit=commit, files=len(manifest["sha256"]))
        )
    )


if __name__ == "__main__":
    main()
