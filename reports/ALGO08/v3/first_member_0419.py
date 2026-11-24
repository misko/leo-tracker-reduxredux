"""Observe the first signed DS30-0419 member's residency without reading IQ."""

import argparse
import errno
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import subprocess
from time import time_ns

from tools.pipeline_eval.qualification.cache_residency import load_query, pages


SAVED = Path("/dev/shm/leo-v3-nomination-handoff-0419-local01")
REQUEST_PIN = "333faaee6e48085385db617e6422c08d58aed3c99baa74c9119cd3fc09dd7614"
INVENTORY_PIN = "bc869c479a0e5c0d4fc4e7b1b19032d3e131c4f741c4910317e8cede3e133256"
CACHE = Path("/tmp/leo-algo08v2-2x-bench/ds30-cache-residency.so")
CACHE_PIN = "4f10e0a2e23121e184ee7d37767f55c29fefc158f4182a2dd99c4268ff2ce6ab"
SPOOL = Path("/srv/postgres-nvme/fast-scan-recordings")
TMPFS = Path("/dev/shm")
FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


def authenticate(data, pin):
    if sha256(data).hexdigest() != pin.removeprefix("sha256:"):
        raise ValueError("Signed admission metadata changed")
    return data


def metadata(path, pin, limit):
    with os.fdopen(os.open(path, FLAGS), "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
            raise ValueError("Invalid first-member metadata extent")
        content = stream.read(limit + 1)
        if len(content) != info.st_size:
            raise ValueError("Metadata changed during read")
        return authenticate(content, pin)


def select_first(request, inventory, *, case="DS30-0419", inventory_pin=INVENTORY_PIN):
    if (request["case"] != case or request["inventory"] != "sha256:" + inventory_pin
            or inventory["window_count"] != request["issued"] or not inventory["segments"]):
        raise ValueError("Require the originally signed inventory for the enrolled case")
    first = inventory["segments"][0]
    folder = Path(first["path"])
    if (folder.parent != Path(request["recording"]) or first["scope"] != "segment-00000000"
            or request["manifests"][0] != [str(folder / "manifest.json"), first["manifest_digest"]]):
        raise ValueError("First enrolled original segment differs")
    return folder, first


def bound_index(folder, first):
    manifest = json.loads(metadata(folder / "manifest.json", first["manifest_digest"], 256_000))
    if manifest["window_count"] != first["windows"] or not manifest["chunks"]:
        raise ValueError("Manifest does not describe the first signed segment")
    chunk = manifest["chunks"][0]
    if (chunk["chunk_index"] != 0 or chunk["first_sequence"] != 0
            or not 0 < chunk["window_count"] <= 64 or not 0 < chunk["compressed_bytes"] <= 120_000_000
            or any(Path(chunk[key]).name != chunk[key] for key in ("payload_relative_path", "index_relative_path"))):
        raise ValueError("Require the first bounded original payload and index")
    index = metadata(folder / chunk["index_relative_path"], chunk["index_sha256"], 2_000_000)
    rows = [json.loads(line) for line in index.splitlines()]
    offset = 0
    for sequence, row in enumerate(rows):
        if (row["sequence"] != sequence or row["payload_offset_bytes"] != offset
                or row["payload_bytes"] < 0):
            raise ValueError("First signed member changed raw visit order or extent")
        offset += row["payload_bytes"]
    if (len(index), len(rows), offset) != (chunk["index_bytes"], chunk["window_count"], chunk["uncompressed_bytes"]):
        raise ValueError("First signed index fails exact row and byte coverage")
    return chunk, rows


def payload_cache(path, length, query, page_size):
    fd = os.open(path, FLAGS)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size != length:
            raise ValueError("Selected original payload extent changed")
        cached, failure = None, None
        started = time_ns()
        try:
            cached = query(fd, length)
        except OSError as error:
            failure = errno.errorcode.get(error.errno, str(error.errno))
        return dict(path=str(path), device=info.st_dev, inode=info.st_ino, stat_blocks=info.st_blocks,
                    bytes=length, file_pages=pages(length, page_size), cached_pages=cached, cache_error=failure,
                    started_unix_ns=started, ended_unix_ns=time_ns())
    finally:
        os.close(fd)


def tmpfs_candidates(segment, signed, member):
    search = subprocess.run(["find", str(TMPFS), "-xdev", "-type", "d", "-name", segment.name],
                            check=False, capture_output=True, text=True, timeout=20)
    result = []
    for path in map(Path, sorted(search.stdout.splitlines())):
        if not path.is_relative_to(TMPFS) or path.resolve(strict=True) != path:
            continue
        try:
            actual, _ = bound_index(path, signed)
            content = path / member["payload_relative_path"]
            info = content.stat(follow_symlinks=False)
            if (actual != member or info.st_dev != TMPFS.stat().st_dev or stat.S_ISLNK(info.st_mode)
                    or not stat.S_ISREG(info.st_mode) or info.st_size != member["compressed_bytes"]):
                continue
        except (OSError, ValueError):
            continue
        result.append(str(path))
    return dict(method="exact segment basename on the tmpfs device, signed manifest and first index only",
                matched=result, find_exit=search.returncode, search_error_count=len(search.stderr.splitlines()))


def run(output):
    opened = time_ns()
    request = json.loads(metadata(SAVED / "request.json", REQUEST_PIN, 96_000))
    inventory = json.loads(metadata(SAVED / "inventory.json", INVENTORY_PIN, 96_000))
    segment, first = select_first(request, inventory)
    if segment.resolve(strict=True) != segment:
        raise ValueError("The first signed original segment traverses an unexpected device alias")
    chunk, rows = bound_index(segment, first)
    payload = segment / chunk["payload_relative_path"]
    if payload.resolve(strict=True) != payload:
        raise ValueError("The first signed payload traverses an unexpected alias")
    authenticate(CACHE.read_bytes(), CACHE_PIN)
    cache = payload_cache(payload, chunk["compressed_bytes"], load_query(CACHE), os.sysconf("SC_PAGE_SIZE"))
    spool_recording = SPOOL / segment.parent.name
    spool = dict(path=str(spool_recording), symlink=spool_recording.is_symlink(),
                 resolves_to=str(spool_recording.resolve()), exists=spool_recording.exists())
    mount = json.loads(subprocess.check_output(
        ["findmnt", "--json", "-o", "SOURCE,FSTYPE,TARGET,MAJ:MIN", "-T", str(payload)]))["filesystems"]
    copies = tmpfs_candidates(segment, first, chunk)
    reason = "tmpfs_candidate_needs_complete_payload_authentication" if copies["matched"] else (
        "cache_only_copy_not_qualified" if cache["cached_pages"] == cache["file_pages"] else
        "original_first_payload_cache_observation_unavailable" if cache["cached_pages"] is None else
        "original_first_payload_not_fully_resident")
    report = dict(case="DS30-0419", session=request["session"], original_inventory=request["inventory"],
                  signed_inventory_segments=len(inventory["segments"]), first_segment=first,
                  member=chunk, signed_rows=len(rows), original_recording_authority=request["raw_authority"],
                  cache=cache, cache_observer_sha256=CACHE_PIN, mount=mount, nominal_spool=spool, tmpfs=copies,
                  disposition="deferred", reason=reason, nowait_attempted=False, payload_data_bytes_read=0,
                  waveform_bytes_staged=0, benchmark_children=0, new_rf=0, started_unix_ns=opened,
                  ended_unix_ns=time_ns(), uid=os.getuid(), kernel_release=os.uname().release)
    with output.open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
