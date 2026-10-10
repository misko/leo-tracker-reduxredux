"""Deterministic metadata archive; preserve originals and verify streamed contents."""

import gzip
import hashlib
import tarfile
from pathlib import Path

from run import digest, write_new

HERE = Path(__file__).resolve().parent


def main():
    files = [HERE / "inventory.json", HERE / "resources.json"]
    for name in ("metadata", "metadata-v2", "metadata-v3"):
        files.extend(sorted((HERE / name).glob("*.json")))
    manifest = {
        str(p.relative_to(HERE)): {"sha256": digest(p), "bytes": p.stat().st_size} for p in files
    }
    target = HERE / "metadata.tar.gz"
    with (
        target.open("xb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w|") as archive,
    ):
        for path in sorted(files):
            info = tarfile.TarInfo(str(path.relative_to(HERE)))
            info.size = path.stat().st_size
            info.mode = 0o644
            with path.open("rb") as stream:
                archive.addfile(info, stream)
    found = set()
    with tarfile.open(target, "r|gz") as archive:
        for member in archive:
            if not member.isfile() or member.name not in manifest or member.name in found:
                raise ValueError("unexpected archive member")
            found.add(member.name)
            content = archive.extractfile(member).read()
            if hashlib.sha256(content).hexdigest() != manifest[member.name]["sha256"]:
                raise ValueError("archive digest mismatch")
    if found != set(manifest):
        raise ValueError("archive membership differs")
    write_new(
        HERE / "METADATA_ARCHIVE.json",
        {
            "archive": target.name,
            "sha256": digest(target),
            "bytes": target.stat().st_size,
            "raw_bytes": sum(v["bytes"] for v in manifest.values()),
            "files": manifest,
            "verification": "every decompressed member digest checked; originals preserved",
            "iq_reads": 0,
        },
    )


if __name__ == "__main__":
    main()
