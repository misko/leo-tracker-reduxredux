"""Completion-gated deterministic raw parity archive; originals preserved."""

import gzip
import json
import tarfile
import tempfile
from pathlib import Path

from archive_inputs import digest, restore
from report_parity import summarize

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def prepare_files(here, root):
    path = here / "parity-protocol.json"
    plan = json.loads(path.read_text())
    protocol_sha = digest(path.read_bytes())
    for relative, expected in {**plan["sources"], **plan["inputs"]}.items():
        if digest((root / relative).read_bytes()) != expected:
            raise ValueError("Frozen input/source mismatch")
    if len(plan["members"]) != 193:
        raise ValueError("Full193 authority required")
    receipts, files = {}, []
    for binding in plan["members"]:
        label = binding["label"]
        if Path(label).name != label:
            raise ValueError("Unsafe member label")
        result = here / "parity-results" / (label + ".json")
        claim = result.with_suffix(".claim.json")
        for artifact in (result, claim):
            value = json.loads(artifact.read_text())
            if value["label"] != label or value["protocol_sha256"] != protocol_sha:
                raise ValueError("Foreign result/claim")
            files.append(artifact)
        receipts[label] = json.loads(result.read_text())
    summarize(plan["members"], receipts)
    if set((here / "parity-results").glob("*.json")) != set(files):
        raise ValueError("Unbound extra raw receipt")
    return protocol_sha, sorted(files)


def create(here=HERE, root=ROOT):
    protocol_sha, paths = prepare_files(here, root)
    files = {
        str(p.relative_to(here)): dict(bytes=p.stat().st_size, sha256=digest(p.read_bytes()))
        for p in paths
    }
    target = here / "parity-results.tar.gz"
    with (
        target.open("xb") as raw,
        gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as gz,
        tarfile.open(fileobj=gz, mode="w|") as archive,
    ):
        for path in paths:
            info = tarfile.TarInfo(str(path.relative_to(here)))
            info.size, info.mode = path.stat().st_size, 0o644
            with path.open("rb") as stream:
                archive.addfile(info, stream)
    manifest = dict(
        protocol_sha256=protocol_sha,
        files=files,
        archive_sha256=digest(target.read_bytes()),
        archive_bytes=target.stat().st_size,
    )
    with tempfile.TemporaryDirectory() as directory:
        restore(target, manifest, directory)
    with (here / "PARITY_RESULT_ARCHIVE.json").open("x") as stream:
        json.dump(manifest, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return manifest


if __name__ == "__main__":
    print(json.dumps(create()))
