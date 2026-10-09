"""Verify full archive before writing; never overwrite differing files or follow links."""

import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent


def restore(destination, here=HERE):
    destination, here = Path(destination).absolute(), Path(here)
    manifest = json.loads((here / "results-receipts-manifest.json").read_text())
    archive = here / "results-receipts.tar.gz"
    if archive.exists():
        compressed = archive.read_bytes()
    else:
        parts = []
        for part in manifest["parts"]:
            name = PurePosixPath(part["name"])
            assert len(name.parts) == 1 and not name.is_absolute() and name.name not in (".", "..")
            data = (here / part["name"]).read_bytes()
            assert len(data) == part["bytes"] and hashlib.sha256(data).hexdigest() == part["sha256"]
            parts.append(data)
        compressed = b"".join(parts)
    assert len(compressed) == manifest["archive_bytes"]
    assert hashlib.sha256(compressed).hexdigest() == manifest["archive_sha256"]
    payload = {}
    with tarfile.open(fileobj=io.BytesIO(compressed), mode="r:gz") as tar:
        assert len(tar.getmembers()) == len(manifest["files"])
        for member in tar.getmembers():
            name = PurePosixPath(member.name)
            assert member.isfile() and not name.is_absolute() and ".." not in name.parts
            assert name.parts[0] in ("results", "attempts", "controller-claims")
            assert len(name.parts) >= 2 and name.suffix == ".json"
            assert member.name in manifest["files"] and member.name not in payload
            data = tar.extractfile(member).read()
            expected = manifest["files"][member.name]
            assert (
                len(data) == expected["bytes"]
                and hashlib.sha256(data).hexdigest() == expected["sha256"]
            )
            row = json.loads(data)
            assert row["protocol_sha256"] == manifest["protocol_sha256"]
            target = destination / member.name
            assert not any(p.is_symlink() for p in (target, *target.parents))
            if target.exists():
                assert target.is_file() and target.read_bytes() == data, "Existing file differs"
            payload[member.name] = data
    for name, data in payload.items():
        target = destination / name
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
    return len(payload)


if __name__ == "__main__":
    print("Verified/restored", restore(sys.argv[1]), "files")
