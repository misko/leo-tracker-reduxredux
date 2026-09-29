#!/usr/bin/env python3
"""Verify the lean publication staging without compiled binaries."""
import hashlib
import io
import json
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
manifest = json.loads((ROOT / "publication-manifest.json").read_text())


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


checks = []
for name, record in manifest["archives"].items():
    archive = ROOT / "source-archives" / name
    checks.append((f"archive:{name}", digest(archive.read_bytes()) == record["sha256"]))
    with tarfile.open(archive, "r:gz") as stream:
        members = {m.name: m for m in stream.getmembers() if m.isfile()}
        for relative, expected in record["files"].items():
            member_name = f"{record['root']}/{relative}"
            extracted = stream.extractfile(members[member_name])
            checks.append((f"source:{name}:{relative}",
                           extracted is not None and digest(extracted.read()) == expected))

for relative, expected in manifest["build_receipts"].items():
    checks.append((f"receipt:{relative}", digest((ROOT / relative).read_bytes()) == expected))

failed = [name for name, passed in checks if not passed]
print(json.dumps({"passed": not failed, "checks": len(checks), "failed": failed}, indent=2))
if failed:
    raise SystemExit(1)
