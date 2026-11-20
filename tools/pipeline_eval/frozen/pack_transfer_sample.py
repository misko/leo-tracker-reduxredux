"""Package public tracks and orbit catalogues for the deterministic transfer16 roster."""

import argparse
import hashlib
import io
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .. import corpus
from ..__main__ import references, write


def pack(public_root, output):
    _, selected = references("transfer16", None)
    _, hashes = corpus._selection("transfer124")
    inputs = corpus._index(corpus._read_frozen("inputs.jsonl", hashes))
    files = {}
    for case in selected:
        item = inputs[case["id"]]
        tree = public_root / item["blind_tree"]
        for key, folder, suffix in [
            ("observation", "observations", ".json"),
            ("catalog", "orbits", ".tle"),
        ]:
            locator = item[key]
            digest = locator["sha256"] if isinstance(locator, dict) else locator
            name = digest + suffix
            files[name] = tree / folder / name
    compressed = io.BytesIO()
    with ZipFile(compressed, "w") as archive:
        for name, path in sorted(files.items()):
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != Path(name).stem:
                raise ValueError(f"public sample differs from its frozen input: {path}")
            # Fixed entry metadata makes rebuilding the archive independent of local mtimes.
            archive.writestr(ZipInfo(name), raw, compress_type=ZIP_DEFLATED, compresslevel=9)
    write(output, compressed.getvalue())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-root", type=Path, default=corpus.DEFAULT_BLIND)
    parser.add_argument("--out", type=Path, default=corpus.TRANSFER_SAMPLE)
    args = parser.parse_args()
    pack(args.public_root, args.out)
