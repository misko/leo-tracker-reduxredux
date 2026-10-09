"""Verify the controlled archive, then restore receipts into a new directory."""

import hashlib
import json
import sys
import tarfile
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent


def main():
    destination = Path(sys.argv[1])
    if destination.exists():
        raise ValueError("Destination must not exist")
    manifest = json.loads((HERE / "receipts-manifest.json").read_text())
    archive = HERE / "receipts.tar.gz"
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == manifest["archive_sha256"]
    payload = {}
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        assert len(members) == len(manifest["files"])
        for member in members:
            name = PurePosixPath(member.name)
            assert member.isfile() and not name.is_absolute() and ".." not in name.parts
            assert member.name in manifest["files"] and member.name not in payload
            assert member.name in ("result.json", "fresh-calibration.json") or (
                len(name.parts) == 2 and name.parts[0] == "stages" and name.suffix == ".json"
            )
            data = tar.extractfile(member).read()
            expected = manifest["files"][member.name]
            assert len(data) == expected["bytes"]
            assert hashlib.sha256(data).hexdigest() == expected["sha256"]
            payload[member.name] = data
    destination.mkdir()
    for name, data in payload.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)


if __name__ == "__main__":
    main()
