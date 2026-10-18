"""Verify this report's frozen evidence and materialize an empty scratch tree."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def materialize(destination):
    report = Path(__file__).resolve().parent
    destination = destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("destination must be empty; existing research will not be overwritten")
    source_manifest = json.loads((report / "source_manifest.json").read_text())
    inputs = json.loads((report / "input_manifest.json").read_text())
    pending = {}
    for relative, expected in source_manifest["sources_sha256"].items():
        data = (report / "run_sources" / relative).read_bytes()
        if digest(data) != expected:
            raise ValueError(f"source hash mismatch: {relative}")
        pending[relative] = data
    for relative, record in inputs["files"].items():
        source = report / record["storage"]
        data = source.read_bytes()
        if record["compression"] == "gzip":
            data = gzip.decompress(data)
        if digest(data) != record["sha256"]:
            raise ValueError(f"input hash mismatch: {relative}")
        pending[relative] = data
    for relative in pending:
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError(f"unsafe destination path: {relative}")
    for relative, data in pending.items():
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    print(f"Verified and materialized {len(pending)} files in {destination}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    materialize(parser.parse_args().destination)
