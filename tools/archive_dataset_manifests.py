"""Publish exact dataset-authority bytes in bounded, lossless Git-sized files."""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PART_BYTES = 40 * 1024**2


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024**2), b""):
            h.update(block)
    return h.hexdigest()


def archive(source, stem, directory):
    """Preserve bytes exactly; no JSON normalization or membership rewriting."""
    temporary = directory / (stem + ".original")
    if source.startswith("git:"):
        _, revision, path = source.split(":", 2)
        with temporary.open("wb") as handle:
            subprocess.run(["git", "show", f"{revision}:{path}"], stdout=handle, check=True)
        original = temporary
    else:
        original = Path(source)
    digest, size = sha(original), original.stat().st_size
    target = directory / stem
    if size <= 1024**2:
        shutil.copyfile(original, target)
        parts, encoding = [target], "identity"
    else:
        target = target.with_name(target.name + ".zst")
        subprocess.run(["zstd", "-q", "-f", "-8", "-T2", str(original), "-o", str(target)],
                       check=True)
        if target.stat().st_size <= PART_BYTES:
            parts = [target]
        else:
            parts = []
            with target.open("rb") as handle:
                index = 0
                while block := handle.read(PART_BYTES):
                    part = target.with_name(target.name + f".part{index:03d}")
                    part.write_bytes(block)
                    parts.append(part)
                    index += 1
            target.unlink()
        encoding = "zstd" if len(parts) == 1 else "concatenated-zstd-parts"
    temporary.unlink(missing_ok=True)
    return dict(source=source, original_sha256=digest, original_bytes=size, encoding=encoding,
                parts=[dict(path=p.name, sha256=sha(p), bytes=p.stat().st_size) for p in parts])


def verify_entry(entry, directory):
    parts = [directory / p["path"] for p in entry["parts"]]
    for part, record in zip(parts, entry["parts"], strict=True):
        if sha(part) != record["sha256"] or part.stat().st_size != record["bytes"]:
            raise ValueError("published part changed")
    h, count = hashlib.sha256(), 0
    if entry["encoding"] == "identity":
        with parts[0].open("rb") as handle:
            for block in iter(lambda: handle.read(1024**2), b""):
                h.update(block)
                count += len(block)
    else:
        # Split files are a single stream, not independent zstd frames.
        if len(parts) > 1:
            proc = subprocess.Popen(["zstd", "-q", "-d", "-c"], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE)
            import threading

            def feed():
                try:
                    for part in parts:
                        with part.open("rb") as handle:
                            shutil.copyfileobj(handle, proc.stdin)
                finally:
                    proc.stdin.close()

            thread = threading.Thread(target=feed)
            thread.start()
        else:
            proc = subprocess.Popen(["zstd", "-q", "-d", "-c", str(parts[0])],
                                    stdout=subprocess.PIPE)
        for block in iter(lambda: proc.stdout.read(1024**2), b""):
            h.update(block)
            count += len(block)
        if len(parts) > 1:
            thread.join()
        if proc.wait():
            raise ValueError("lossless archive decompression failed")
    if (h.hexdigest(), count) != (entry["original_sha256"], entry["original_bytes"]):
        raise ValueError("archive does not recover original authority bytes")


def run(output, extra):
    output.mkdir(parents=True, exist_ok=True)
    inventory = json.loads((ROOT / "reports/2026_10_18_ds_dataset_inventory/inventory.json")
                           .read_text())
    destination = output / "catalogue.json"
    records = json.loads(destination.read_text())["authorities"] if destination.exists() else []
    entries = [(r["dataset"], r["source"]) for r in inventory["datasets"]]
    entries += extra
    entries += [("DS3-inference", "git:75b76f66974c78588c6599822e8007aaa767466b:"
                                  "reports/2026_09_24_ds3_all_captures/inference-manifest.json")]
    for name, source in entries:
        old = next((r for r in records if r["dataset"] == name), None)
        if old:
            verify_entry(old, output)
            continue
        record = dict(dataset=name, **archive(source, f"{name}.manifest.json", output))
        verify_entry(record, output)
        records.append(record)
        destination.write_text(json.dumps(dict(
            schema="lossless-dataset-authority-archive/v1", authorities=records,
            not_located=["DS14", "DS15", "DS19"],
            scope=("All located primary membership authorities, DS2 revision, "
                   "DS3 inference authority"),
            IQ_included=False, all_archives_roundtrip_verified=True), indent=2) + "\n")
        print(name, record["original_bytes"], sum(p["bytes"] for p in record["parts"]),
              flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--extra", nargs=2, action="append", default=[], metavar=("ID", "PATH"))
    a = p.parse_args()
    run(a.output, a.extra)
