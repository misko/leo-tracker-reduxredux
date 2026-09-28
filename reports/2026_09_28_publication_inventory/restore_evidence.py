"""Verify published evidence and optionally restore oversized original files."""

import argparse
import gzip
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def digest(stream):
    result = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        result.update(block)
    return result.hexdigest()


def safe_path(name):
    path = (ROOT / name).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError(f"Path outside checkout: {name}")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    count = archives = 0
    for row in json.loads((HERE / "manifest.json").read_text()):
        if "published_path" not in row:
            continue
        path = safe_path(row["published_path"])
        with path.open("rb") as stream:
            assert digest(stream) == row.get("published_sha256", row["sha256"]), path
        count += 1
        if row["status"] != "gzip-restorable":
            continue
        archives += 1
        with gzip.open(path, "rb") as stream:
            assert digest(stream) == row["sha256"], path
        if not args.restore:
            continue
        target = safe_path(row["path"])
        if target.exists():
            with target.open("rb") as stream:
                if digest(stream) != row["sha256"]:
                    raise FileExistsError(f"Refusing to overwrite different evidence: {target}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile() as temporary:
            with gzip.open(path, "rb") as stream:
                shutil.copyfileobj(stream, temporary)
            temporary.seek(0)
            with target.open("xb") as stream:
                shutil.copyfileobj(temporary, stream)
    print(f"Verified {count} published files and {archives} lossless archives")


if __name__ == "__main__":
    main()
