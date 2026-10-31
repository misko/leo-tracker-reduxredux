"""Stage exact ALGO04 bytes while retaining every frozen ALGO03 scientific member."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

import stage_algo03_release as previous

MANIFEST = "reports/ALGO04/releases/2026-10-31-r1/manifest.json"
MANIFEST_SHA256 = "23a7947a27d7d3c0f13ec70c6fb8155dbff4d842290c991eedb02538381b88a6"
MODEL_VERSION = "algo04-causal-numerical-v1"


def scientific_inventory(source, revision):
    files = previous.scientific_inventory(source, revision)
    payload = previous._git(source, "show", f"{revision}:{MANIFEST}")
    if hashlib.sha256(payload).hexdigest() != MANIFEST_SHA256:
        raise ValueError("Committed ALGO04 manifest differs from sealed r1")
    for name, expected in json.loads(payload)["sha256"].items():
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Unsafe ALGO04 member")
        if (
            hashlib.sha256(previous._git(source, "show", f"{revision}:{name}")).hexdigest()
            != expected
        ):
            raise ValueError("ALGO04 member changed: " + name)
        files[name] = expected
    return {**files, MANIFEST: MANIFEST_SHA256}


def stage(source, revision, python_root, uv, *, execute=False):
    # Reuse the existing immutable installer, never alter an installed release.
    files = scientific_inventory(source, revision)
    old_inventory, old_model, old_sha = (
        previous.scientific_inventory,
        previous.MODEL_VERSION,
        previous.MANIFEST_SHA256,
    )
    try:
        previous.scientific_inventory = lambda *_: files
        previous.MODEL_VERSION, previous.MANIFEST_SHA256 = MODEL_VERSION, MANIFEST_SHA256
        return previous.stage(source, revision, python_root, uv, execute=execute)
    finally:
        previous.scientific_inventory, previous.MODEL_VERSION, previous.MANIFEST_SHA256 = (
            old_inventory,
            old_model,
            old_sha,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--python-root", type=Path, required=True)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            stage(args.source, args.revision, args.python_root, args.uv, execute=args.execute)
        )
    )
