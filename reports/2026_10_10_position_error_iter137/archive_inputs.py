"""Deterministic input archive and safe hash-verified restoration."""

import gzip
import hashlib
import json
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def restore(archive_path, manifest, destination):
    destination = Path(destination)
    if digest(Path(archive_path).read_bytes()) != manifest["archive_sha256"]:
        raise ValueError("Archive hash mismatch")
    found = set()
    with tarfile.open(archive_path, "r|gz") as archive:
        for member in archive:
            name = member.name
            if (
                name not in manifest["files"]
                or name in found
                or not member.isfile()
                or Path(name).is_absolute()
                or ".." in Path(name).parts
            ):
                raise ValueError("Unsafe/unbound archive member")
            data = archive.extractfile(member).read()
            expected = manifest["files"][name]
            if len(data) != expected["bytes"] or digest(data) != expected["sha256"]:
                raise ValueError("Member hash mismatch")
            output = destination / name
            output.parent.mkdir(parents=True, exist_ok=True)
            if output.exists():
                if output.read_bytes() != data:
                    raise ValueError("Existing input differs; refuse overwrite")
            else:
                with output.open("xb") as stream:
                    stream.write(data)
            found.add(name)
    if found != set(manifest["files"]):
        raise ValueError("Incomplete archive membership")


def create(here=HERE):
    members = json.loads((here / "parity-bindings.json").read_text())["members"]
    if len(members) != 193 or len({m["label"] for m in members}) != 193:
        raise ValueError("Wrong input membership")
    paths = [
        here / group / (m["label"] + ".json")
        for m in members
        for group in ("selected", "documents")
    ]
    paths.sort()
    files = {
        str(p.relative_to(here)): dict(bytes=p.stat().st_size, sha256=digest(p.read_bytes()))
        for p in paths
    }
    target = here / "parity-inputs.tar.gz"
    with (
        target.open("xb") as raw,
        gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as gz,
        tarfile.open(fileobj=gz, mode="w|") as archive,
    ):
        for path in paths:
            info = tarfile.TarInfo(str(path.relative_to(here)))
            info.size = path.stat().st_size
            info.mode = 0o644
            with path.open("rb") as stream:
                archive.addfile(info, stream)
    manifest = dict(
        files=files, archive_sha256=digest(target.read_bytes()), archive_bytes=target.stat().st_size
    )
    with (here / "PARITY_INPUT_ARCHIVE.json").open("x") as stream:
        json.dump(manifest, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return manifest


if __name__ == "__main__":
    import tempfile

    manifest = create()
    with tempfile.TemporaryDirectory() as directory:
        restore(HERE / "parity-inputs.tar.gz", manifest, directory)
    print(
        json.dumps(
            dict(
                files=len(manifest["files"]),
                bytes=manifest["archive_bytes"],
                sha256=manifest["archive_sha256"],
            )
        )
    )
