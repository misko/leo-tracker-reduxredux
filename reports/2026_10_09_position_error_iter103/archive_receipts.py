"""Deterministically archive persisted receipts; preserve every raw local file."""

import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    paths = [HERE / "result.json", HERE / "fresh-calibration.json"]
    paths += sorted((HERE / "stages").glob("*.json"))
    payload = {str(path.relative_to(HERE)): path.read_bytes() for path in paths}
    archive = HERE / "receipts.tar.gz"
    with (
        archive.open("wb") as stream,
        gzip.GzipFile(fileobj=stream, mode="wb", mtime=0, filename="") as compressed,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as tar,
    ):
        for name, data in sorted(payload.items()):
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            tar.addfile(info, io.BytesIO(data))
    manifest = dict(
        archive_sha256=digest(archive.read_bytes()),
        files={
            name: dict(sha256=digest(data), bytes=len(data))
            for name, data in sorted(payload.items())
        },
    )
    with tarfile.open(archive, "r:gz") as tar:
        assert sorted(tar.getnames()) == sorted(payload)
        for member in tar.getmembers():
            assert member.isfile()
            data = tar.extractfile(member).read()
            assert data == payload[member.name]
    for path in paths:
        assert path.read_bytes() == payload[str(path.relative_to(HERE))]
    manifest["readback_verified"] = True
    manifest["raw_local_files_preserved"] = True
    (HERE / "receipts-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
