#!/usr/bin/env python3
"""Reproduce the frozen full-8h TRAIN cache export with four bounded workers."""

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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--exporter", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    ids = manifest["source_group"]["session_ids"]
    if len(ids) != 72 or manifest["source_group"]["utc_8h_start"] != "2026-09-21T00:00:00+00:00":
        raise ValueError("expected frozen Sep21 00Z group of 72 IDs")
    exporter_hash = digest(args.exporter)
    if exporter_hash != manifest["exporter_sha256"]:
        raise ValueError("exporter differs from frozen manifest")
    args.cache_root.mkdir(parents=True, exist_ok=True)
    pending = [sid for sid in ids if not valid(args.cache_root / sid, sid, exporter_hash)]

    def one(sid):
        output = args.cache_root / sid
        if output.exists():
            return sid, "invalid-existing-cache"
        command = [
            "sudo",
            "-n",
            "-u",
            "leo",
            sys.executable,
            str(args.exporter),
            "--session-id",
            sid,
            "--output",
            str(output),
        ]
        done = subprocess.run(command, capture_output=True, text=True)
        return sid, "exported" if done.returncode == 0 and valid(
            output, sid, exporter_hash
        ) else "failed"

    with ThreadPoolExecutor(max_workers=4) as pool:
        for sid, status in pool.map(one, pending):
            print(json.dumps({"session_id": sid, "status": status}), flush=True)
            if status != "exported":
                raise RuntimeError(f"cache export failed closed: {sid} {status}")
    if not all(valid(args.cache_root / sid, sid, exporter_hash) for sid in ids):
        raise RuntimeError("full frozen group is not verified")


if __name__ == "__main__":
    main()
