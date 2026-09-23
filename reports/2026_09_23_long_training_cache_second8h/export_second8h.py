#!/usr/bin/env python3
"""Export the frozen Sep21 16Z TRAIN cache with at most four readers."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def valid(directory: Path, session_id: str, exporter_hash: str) -> bool:
    receipt, cache = directory / "cache_receipt.json", directory / "state_cache.npz"
    if not receipt.exists() or not cache.exists():
        return False
    value = json.loads(receipt.read_text())
    return (
        value["session_id"] == session_id
        and value["bindings"]["export_tool"] == exporter_hash
        and value["bindings"]["state_cache"] == digest(cache)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--exporter", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    group = manifest["source_group"]
    ids = group["session_ids"]
    if group["utc_8h_start"] != "2026-09-21T16:00:00+00:00" or len(ids) != 79:
        raise ValueError("expected frozen Sep21 16Z group of 79 IDs")
    if not all(manifest["partition_checks"].values()):
        raise ValueError("frozen partition check failed")
    exporter_hash = digest(args.exporter)
    if exporter_hash != manifest["exporter_sha256"]:
        raise ValueError("exporter differs from frozen manifest")
    args.cache_root.mkdir(parents=True, exist_ok=True)
    pending = [item for item in ids if not valid(args.cache_root / item, item, exporter_hash)]

    def one(session_id: str):
        output = args.cache_root / session_id
        if output.exists():
            return session_id, "invalid-existing-cache", None
        command = [
            "sudo",
            "-n",
            "-u",
            "leo",
            sys.executable,
            str(args.exporter),
            "--session-id",
            session_id,
            "--output",
            str(output),
        ]
        done = subprocess.run(command, capture_output=True, text=True)
        if done.returncode == 0 and valid(output, session_id, exporter_hash):
            return session_id, "exported", None
        detail = (done.stderr or done.stdout).strip().splitlines()
        return session_id, "failed", detail[-1] if detail else "no exporter diagnostics"

    with ThreadPoolExecutor(max_workers=4) as pool:
        for session_id, status, error in pool.map(one, pending):
            print(
                json.dumps({"session_id": session_id, "status": status, "error": error}),
                flush=True,
            )
            if status != "exported":
                raise RuntimeError(f"cache export failed closed: {session_id} {status}")
    if not all(valid(args.cache_root / item, item, exporter_hash) for item in ids):
        raise RuntimeError("frozen second TRAIN group is not verified")


if __name__ == "__main__":
    main()
