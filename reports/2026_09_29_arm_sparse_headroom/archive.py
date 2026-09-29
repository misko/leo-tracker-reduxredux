"""Archive measured JSON, compiler profiles and selected oracle rows; never IQ."""

import argparse
import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path

from execute import HERE, digest, save


def main(args):
    panel = json.loads((HERE / "panel.json").read_text())
    keys = {
        (v["context"]["session_id"], v["context"]["visit_index"])
        for v in panel["selected"] + panel["compatibility"]
    }
    reference = []
    for line in args.baseline.open():
        row = json.loads(line)
        c = row["context"]
        if (
            (c["session_id"], c["visit_index"]) in keys
            and row["method"] == "original"
            and row["repeat"] == 0
        ):
            assert row["status"] == "ok"
            reference.append(line.encode())
    assert len(reference) == len(keys) == 176
    entries = {"original-selected.jsonl": b"".join(reference)}
    for folder in sorted((HERE / "local").iterdir()):
        if not folder.is_dir():
            continue
        for path in sorted(folder.iterdir()):
            if path.is_file() and (
                path.suffix in {".json", ".jsonl", ".tsv"} or path.name == "profiles.tar"
            ):
                entries[str(path.relative_to(HERE))] = path.read_bytes()
    target = HERE / "evidence.tar.gz"
    with (
        target.open("wb") as stream,
        gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as zipped,
        tarfile.open(fileobj=zipped, mode="w") as archive,
    ):
        for name, payload in sorted(entries.items()):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(payload))
    save(
        HERE / "evidence-manifest.json",
        {
            "archive_sha256": digest(target),
            "full_reference_sha256": digest(args.baseline),
            "files": {k: hashlib.sha256(v).hexdigest() for k, v in sorted(entries.items())},
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    main(parser.parse_args())
