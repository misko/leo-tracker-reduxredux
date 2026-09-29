"""Package measured outputs and selected reference rows, never private IQ."""

import argparse
import gzip
import io
import json
import tarfile
from pathlib import Path

from experiment import HERE, save, sha


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    panel = json.loads((HERE / "panel.json").read_text())
    keys = {(c["context"]["session_id"], c["context"]["visit_index"]) for c in panel["selected"]}
    reference = []
    for line in args.baseline.open():
        row = json.loads(line)
        context = row["context"]
        if (
            (context["session_id"], context["visit_index"]) in keys
            and row["method"] == "original"
            and row["repeat"] == 0
        ):
            assert row["status"] == "ok"
            reference.append(line.encode())
    assert len(reference) == len(keys) == 56
    entries = {
        "original-selected.jsonl": b"".join(reference),
        "build-receipt.json": args.receipt.read_bytes(),
    }
    entries.update({"arm/" + p.name: p.read_bytes() for p in sorted(args.cohort.glob("*.json"))})
    archive = HERE / "evidence.tar.gz"
    with (
        archive.open("wb") as stream,
        gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as zipped,
        tarfile.open(fileobj=zipped, mode="w") as bundle,
    ):
        for name, payload in sorted(entries.items()):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mode = 0o644
            bundle.addfile(info, io.BytesIO(payload))
    import hashlib

    save(
        HERE / "evidence-manifest.json",
        {
            "archive_sha256": sha(archive),
            "full_original_baseline_sha256": sha(args.baseline),
            "files": {
                name: hashlib.sha256(payload).hexdigest()
                for name, payload in sorted(entries.items())
            },
        },
    )
    (HERE / "build-receipt.json").write_bytes(args.receipt.read_bytes())


if __name__ == "__main__":
    main()
