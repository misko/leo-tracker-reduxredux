"""Archive only terminal replay data, preserving originals and every failed row."""

import gzip
import hashlib
import json
import tarfile
from pathlib import Path

from report import summarize
from run import digest, write_new

HERE = Path(__file__).resolve().parent


def main():
    plan = json.loads((HERE / "protocol.json").read_text())
    summary, _ = summarize(plan)
    if not summary["coverage_complete"]:
        raise ValueError("all members must be terminal before archiving")
    files = []
    for member in plan["members"]:
        label = member["label"]
        files.extend(
            HERE / "results" / label / name
            for name in ("started.json", "rows.jsonl", "result.json")
        )
        files.extend(
            HERE / "controller-claims" / (label + suffix) for suffix in (".json", ".exit.json")
        )
    manifest = {
        str(p.relative_to(HERE)): {"bytes": p.stat().st_size, "sha256": digest(p)} for p in files
    }
    target = HERE / "results.tar.gz"
    with (
        target.open("xb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w|") as archive,
    ):
        for path in sorted(files):
            member = tarfile.TarInfo(str(path.relative_to(HERE)))
            member.size, member.mode = path.stat().st_size, 0o644
            with path.open("rb") as stream:
                archive.addfile(member, stream)
    found = set()
    with tarfile.open(target, "r|gz") as archive:
        for member in archive:
            if not member.isfile() or member.name not in manifest or member.name in found:
                raise ValueError("unexpected result archive member")
            found.add(member.name)
            if (
                hashlib.sha256(archive.extractfile(member).read()).hexdigest()
                != manifest[member.name]["sha256"]
            ):
                raise ValueError("result archive mismatch")
    if found != set(manifest):
        raise ValueError("archive coverage differs")
    write_new(
        HERE / "RESULT_ARCHIVE.json",
        {
            "archive": target.name,
            "sha256": digest(target),
            "bytes": target.stat().st_size,
            "protocol_sha256": digest(HERE / "protocol.json"),
            "files": manifest,
            "raw_bytes": sum(row["bytes"] for row in manifest.values()),
            "verification": "all terminal metadata/window IDs and archive digests checked; "
            "originals retained",
        },
    )


if __name__ == "__main__":
    main()
