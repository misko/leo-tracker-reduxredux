"""Read existing runtime bundles; export unique ELF objects without executing them."""
import hashlib
import io
import json
import tarfile
from pathlib import Path

import zstandard

BASE = Path(__file__).resolve().parent
SOURCE = BASE.parents[3] / "starlink_firmware/apk_fw_v1/local/firmware"


def run():
    out = BASE / "local/binaries"
    out.mkdir(parents=True, exist_ok=True)
    objects, aliases, scripts, containers = {}, [], [], []
    for family in ("catson", "catapult"):
        path = SOURCE / f"sw_update_{family}-runtime.sxv"
        raw = path.read_bytes()
        inventory = json.loads((SOURCE / f"sw_update_{family}-runtime-inventory.json").read_text())
        row, = [r for r in inventory if r["path"] == "/runtime.tar.zst"]
        start = raw.index(b"-rom1fs-") + row["offset"]
        compressed = raw[start:start + row["size"]]
        assert hashlib.sha256(compressed).hexdigest() == row["sha256"]
        containers.append(dict(family=family, path=str(path),
                               sha256=hashlib.sha256(raw).hexdigest(),
                               archive_sha256=row["sha256"]))
        with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(compressed)) as reader:  # noqa: SIM117
            with tarfile.open(fileobj=reader, mode="r|") as archive:
                for entry in archive:
                    if entry.issym() or entry.islnk():
                        aliases.append(dict(family=family, path=entry.name, target=entry.linkname))
                    if not entry.isfile():
                        continue
                    stream = archive.extractfile(entry)
                    prefix = stream.read(4)
                    if prefix == b"\x7fELF":
                        data = prefix + stream.read()
                        digest = hashlib.sha256(data).hexdigest()
                        location = dict(family=family, path=entry.name)
                        if digest not in objects:
                            filename = (family + "--" +
                                        entry.name.removeprefix("./").replace("/", "--"))
                            (out / filename).write_bytes(data)
                            objects[digest] = dict(file=filename, sha256=digest, bytes=len(data),
                                                   locations=[])
                        objects[digest]["locations"].append(location)
                    elif prefix.startswith(b"#!"):
                        scripts.append(dict(family=family, path=entry.name, bytes=entry.size))
    result = dict(containers=containers, objects=list(objects.values()), aliases=aliases,
                  scripts=scripts, limitation="Runtime ELF inventory, including shared objects. "
                  "Scripts and symlinks listed separately. Opaque MCU images/S-records are "
                  "not claimed disassembled. Third-party package authenticity unverified.")
    (BASE / "local/corpus.json").write_text(json.dumps(result, indent=2) + "\n")
    print(len(objects), "unique ELF objects;", sum(len(r["locations"]) for r in objects.values()),
          "archive occurrences;", len(scripts), "scripts;", len(aliases), "aliases")


if __name__ == "__main__":
    run()
