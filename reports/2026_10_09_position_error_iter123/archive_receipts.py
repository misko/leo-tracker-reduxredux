"""Deterministic report-owned archive; verifies bytes without deleting raw receipts."""

import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    plan = json.loads((HERE / "protocol.json").read_text())
    for group in ("source_sha256", "input_sha256"):
        for name, expected in plan[group].items():
            if sha((ROOT / name).read_bytes()) != expected:
                raise ValueError("frozen closure mismatch: " + name)
    files = sorted((HERE / "results").rglob("*.json"))
    contents = {}
    archive = HERE / "raw-receipts.tar.gz"
    with archive.open("xb") as output:
        with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as tar:
                for path in files:
                    name = str(path.relative_to(HERE))
                    data = path.read_bytes()
                    contents[name] = dict(sha256=sha(data), bytes=len(data))
                    info = tarfile.TarInfo(name)
                    info.size, info.mode, info.mtime = len(data), 0o644, 0
                    tar.addfile(info, io.BytesIO(data))
    readback = {}
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            if (
                not member.isfile()
                or not member.name.startswith("results/")
                or ".." in Path(member.name).parts
                or member.name in readback
            ):
                raise ValueError("unsafe archive member")
            data = tar.extractfile(member).read()
            readback[member.name] = dict(sha256=sha(data), bytes=len(data))
    if readback != contents:
        raise ValueError("archive readback differs")
    artifacts = {
        path.name: sha(path.read_bytes())
        for path in (
            HERE / "DOWNSTREAM_SUMMARY.json",
            HERE / "downstream-comparison.png",
            HERE / "RESULTS.md",
            HERE / "report_downstream.py",
            HERE / "publish_downstream.py",
            HERE / "archive_receipts.py",
        )
    }
    result = dict(
        protocol_file_sha256=sha((HERE / "protocol.json").read_bytes()),
        frozen_sources_verified=len(plan["source_sha256"]),
        frozen_inputs_verified=len(plan["input_sha256"]),
        raw_files=contents,
        raw_bytes=sum(row["bytes"] for row in contents.values()),
        archive_sha256=sha(archive.read_bytes()),
        archive_bytes=archive.stat().st_size,
        archive_readback_verified=True,
        artifacts_sha256=artifacts,
        raw_files_preserved=True,
    )
    with (HERE / "DOWNSTREAM_INTEGRITY.json").open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
