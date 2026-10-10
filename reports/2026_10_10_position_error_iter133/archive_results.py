"""Completion-gated deterministic raw receipt archive; originals remain untouched."""

import gzip
import hashlib
import json
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TERMINAL = ("complete", "failed", "attempt-failed", "model-integrity-failed")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare_files(here, root):
    protocol = here / "protocol.json"
    plan = json.loads(protocol.read_text())
    if len(plan["members"]) != 12 or len({m["label"] for m in plan["members"]}) != 12:
        raise ValueError("Expected all twelve frozen members")
    for group in ("sources", "inputs"):
        for name, expected in plan[group].items():
            if digest(root / name) != expected:
                raise ValueError("Frozen binding changed: " + name)
    protocol_digest = digest(protocol)
    files = []
    for member in plan["members"]:
        label = member["label"]
        if Path(label).name != label:
            raise ValueError("Unsafe member label")
        terminal = here / "results" / (label + ".json")
        claim = terminal.with_suffix(".claim.json")
        for path in (terminal, claim):
            receipt = json.loads(path.read_text())
            if receipt["label"] != label or receipt["protocol_sha256"] != protocol_digest:
                raise ValueError("Foreign result or claim")
        if json.loads(terminal.read_text())["status"] not in TERMINAL:
            raise ValueError("Not terminal: " + label)
        files.extend((terminal, claim))
    if set((here / "results").glob("*.json")) != set(files):
        raise ValueError("Unbound extra result files")
    return protocol_digest, sorted(files)


def create(here=HERE, root=ROOT):
    protocol_digest, files = prepare_files(here, root)
    manifest = {
        str(path.relative_to(here)): dict(bytes=path.stat().st_size, sha256=digest(path))
        for path in files
    }
    target = here / "results.tar.gz"
    with (
        target.open("xb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w|") as archive,
    ):
        for path in files:
            member = tarfile.TarInfo(str(path.relative_to(here)))
            member.size, member.mode = path.stat().st_size, 0o644
            with path.open("rb") as stream:
                archive.addfile(member, stream)
    found = set()
    with tarfile.open(target, "r|gz") as archive:
        for member in archive:
            if not member.isfile() or member.name not in manifest or member.name in found:
                raise ValueError("Unexpected archive member")
            found.add(member.name)
            payload = archive.extractfile(member).read()
            if (
                len(payload) != manifest[member.name]["bytes"]
                or hashlib.sha256(payload).hexdigest() != manifest[member.name]["sha256"]
            ):
                raise ValueError("Archived bytes differ")
    if found != set(manifest):
        raise ValueError("Archive coverage differs")
    result = dict(
        archive=target.name,
        sha256=digest(target),
        bytes=target.stat().st_size,
        protocol_sha256=protocol_digest,
        files=manifest,
        raw_bytes=sum(value["bytes"] for value in manifest.values()),
        verification=(
            "12 terminal results +12 exclusive claims; "
            "full readback byte/hash parity; originals preserved"
        ),
    )
    with (here / "RESULT_ARCHIVE.json").open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return result


if __name__ == "__main__":
    create()
