"""Verify archive and restore absent metadata only; refuse conflicting content."""

import argparse
import hashlib
import json
import tarfile
from pathlib import Path, PurePosixPath

from run import digest

HERE = Path(__file__).resolve().parent


def unpack(destination, *, here=HERE):
    receipt = json.loads((here / "METADATA_ARCHIVE.json").read_text())
    archive_path = here / receipt["archive"]
    if digest(archive_path) != receipt["sha256"]:
        raise ValueError("archive digest mismatch")
    found = set()
    for writing in (False, True):
        with tarfile.open(archive_path, "r|gz") as archive:
            for member in archive:
                relative = PurePosixPath(member.name)
                if (
                    not member.isfile()
                    or relative.is_absolute()
                    or ".." in relative.parts
                    or member.name not in receipt["files"]
                ):
                    raise ValueError("unsafe archive member")
                if not writing:
                    if member.name in found:
                        raise ValueError("duplicate archive member")
                    found.add(member.name)
                data = archive.extractfile(member).read()
                expected = receipt["files"][member.name]["sha256"]
                if hashlib.sha256(data).hexdigest() != expected:
                    raise ValueError("member digest mismatch")
                target = destination / member.name
                if any(p.is_symlink() for p in (target, *target.parents)):
                    raise ValueError("symlink target rejected")
                if target.exists():
                    if not target.is_file() or digest(target) != expected:
                        raise ValueError("existing metadata conflict")
                elif writing:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open("xb") as stream:
                        stream.write(data)
        if not writing and found != set(receipt["files"]):
            raise ValueError("archive membership differs")
    return len(found)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, default=HERE)
    args = parser.parse_args()
    print(unpack(args.destination))
