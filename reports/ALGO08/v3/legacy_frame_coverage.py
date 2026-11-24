"""Classify existing signed Zstandard members without decoding signal samples."""

import json
import mmap
import os
from hashlib import sha256
from pathlib import Path
import subprocess

from .history_risk_0016_raw import RECORDING, STAGE
from .owned_capture_0016 import MANIFESTS, checked
from .visit_frame_recording_0016 import resident_path
from .zstd_structure import MAX_BLOCK, inspect, literal_section


def exception_dependencies(blocks):
    """Count zero-sequence consumers of a table introduced in a match block."""
    exceptions = []
    owner = None
    for index, (is_new, count) in enumerate(blocks):
        if is_new:
            owner = None
        if count:
            row = dict(block=index, new_table=is_new, dependent_literal_blocks=0)
            exceptions.append(row)
            if is_new:
                owner = row
        elif owner is not None:
            owner["dependent_literal_blocks"] += 1
    return exceptions


def classify(frame, decoded_bytes):
    spans = []
    info = inspect(frame, decoded_bytes, block_spans=spans)
    compressed = info["block_counts"].get("compressed", 0)
    exceptional = compressed - info["zero_sequence_blocks"]
    profile = (info["checksum"] and frame[4] & 3 == 0 and compressed > 0
               and info["block_counts"] == {"compressed": compressed}
               and info["huffman_streams"] == {"4": compressed}
               and set(info["literal_counts"]) <= {"huffman_new", "huffman_reused"}
               and max(len(frame), decoded_bytes) < 2**32)
    kind = "other"
    if profile:
        kind = "match_blocks" if exceptional else "literal_only"
    dependencies = []
    if profile and exceptional:
        view = memoryview(frame)
        dependencies = exception_dependencies(
            (literal_section(view[start:start + length])[0] == "huffman_new", count)
            for start, length, _, count in spans)
    return dict(kind=kind, compressed_blocks=compressed, match_blocks=exceptional,
                match_bytes=info["match_bytes"], sequence_count=info["sequences"],
                exception_byte_ceiling=exceptional * MAX_BLOCK if profile else None,
                exception_dependencies=dependencies)


def census(recording, manifest_pins):
    device = Path("/dev/shm").stat().st_dev
    resident_path(recording, device)
    manifests = sorted(recording.glob("*/manifest.json"))
    if len(manifests) != len(manifest_pins):
        raise ValueError("Incomplete manifest roster")
    rows = []
    for path, (pin, visits, chunks) in zip(manifests, manifest_pins, strict=True):
        manifest = json.loads(checked(resident_path(path, device), pin))
        members = manifest["chunks"]
        if len(members) != chunks or sum(m["window_count"] for m in members) != visits:
            raise ValueError("Manifest coverage differs from the signed roster")
        for member in members:
            name = member["payload_relative_path"]
            if Path(name).name != name:
                raise ValueError("Expected a direct member of the signed segment")
            payload = resident_path(path.parent / name, device)
            size = member["compressed_bytes"]
            pages = int(subprocess.check_output(["fincore", "-n", "-o", "PAGES", payload], text=True))
            if pages * os.sysconf("SC_PAGE_SIZE") < size or payload.stat().st_size != size:
                raise ValueError("Compressed payload is incomplete or cold")
            with payload.open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as frame:
                if "sha256:" + sha256(frame).hexdigest() != member["compressed_sha256"]:
                    raise ValueError("Compressed payload digest differs from its signed manifest")
                result = classify(frame, member["uncompressed_bytes"])
            rows.append(dict(segment=path.parent.name, member=name, manifest_sha256=pin,
                             compressed_sha256=member["compressed_sha256"], compressed_bytes=size,
                             windows=member["window_count"], decoded_bytes=member["uncompressed_bytes"], **result))
    return rows


if __name__ == "__main__":
    if os.sched_getaffinity(0) != {2}:
        raise SystemExit("Use the shared Gauss CPU 2 slot")
    print(json.dumps(census(STAGE / RECORDING.name, MANIFESTS), indent=2))
