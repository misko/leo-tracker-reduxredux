"""Observe only the first original member of the two combined blind solver cases."""

import argparse
import json
import os
from pathlib import Path
import stat
import subprocess

from reports.ALGO08.v3.first_member_0419 import (
    CACHE, CACHE_PIN, SPOOL, bound_index, metadata, payload_cache, select_first,
)
from tools.pipeline_eval.qualification.cache_residency import load_query


CASES = {
    "DS30-0163": ("/dev/shm/leo-v3-ds30-0163-ready01",
                  "654bb406870bd97ac6b1854f312b0dae54e8405d6fda81c2ee135c61e41fcae9",
                  "d30888ead13433a1194dec7286e2a71af3d4d78876733eadd8becc06c7121ddd"),
    "DS30-0173": ("/dev/shm/leo-v3-combined-0173-blind01-ready",
                  "04e96eedcc0d356bd4456341de227f9c8d3f226adb851d3ab586331003cbaea3",
                  "b509df18a0649101840de09bb0e5bc46bbf22af4bcbacee9db13eaad3ae1eca4"),
}
POLICY = "first signed segment and first signed payload only, no waveform reads or copies"


def direct_matches(segment, signed, member):
    mt = (Path("/tmp"), Path("/dev/shm"))
    search = subprocess.run(
        ["find", "-P", *map(str, mt), "-xdev", "-maxdepth", "5", "-type", "d", "-name", segment.name],
        capture_output=True, text=True, timeout=15, check=False)
    spool = SPOOL / segment.parent.name
    candidates = {Path(line) for line in search.stdout.splitlines()}
    if (spool / segment.name).is_dir() and spool.resolve() == spool:
        candidates.add(spool / segment.name)
    matches = []
    for folder in sorted(candidates):
        if folder.resolve() != folder or folder.stat().st_dev == segment.stat().st_dev:
            continue
        try:
            checked, _ = bound_index(folder, signed)
            info = (folder / member["payload_relative_path"]).stat(follow_symlinks=False)
            if checked == member and stat.S_ISREG(info.st_mode) and info.st_size == member["compressed_bytes"]:
                matches.append(dict(path=str(folder), device=info.st_dev, bytes=info.st_size))
        except (OSError, ValueError):
            continue
    return dict(matches=matches, searched_tmpfs_roots=[str(path) for path in mt], search_depth=5,
                find_exit=search.returncode, find_errors=len(search.stderr.splitlines()), spool=str(spool),
                spool_exists=spool.exists(), spool_redirects=spool.resolve() != spool)


def observe(case, pins, query):
    source, request_pin, inventory_pin = pins
    root = Path(source)
    req = json.loads(metadata(root / "request.json", request_pin, 96_000))
    inv = json.loads(metadata(root / "inventory.json", inventory_pin, 96_000))
    segment, signed = select_first(req, inv, case=case, inventory_pin=inventory_pin)
    member, rows = bound_index(segment, signed)
    payload = segment / member["payload_relative_path"]
    if payload.resolve(strict=True) != payload:
        raise ValueError("Original selected member traverses an unexpected alias")
    cache = payload_cache(payload, member["compressed_bytes"], query, os.sysconf("SC_PAGE_SIZE"))
    copies = direct_matches(segment, signed, member)
    return dict(case=case, policy=POLICY, session=req["session"], request_sha256=request_pin,
                inventory_sha256=inventory_pin, original_raw_authority=req["raw_authority"],
                signed_first_segment=signed, first_member=member, signed_rows=len(rows), cache=cache,
                copies=copies, cache_complete=cache["cached_pages"] == cache["file_pages"],
                payload_reads=0, copies_started=0, workers=0)


def execute(path):
    metadata(CACHE, CACHE_PIN, 80_000)
    query = load_query(CACHE)
    data = {"policy": POLICY, "cache_observer_sha256": CACHE_PIN,
            "cases": [observe(case, pins, query) for case, pins in CASES.items()]}
    with path.open("x") as stream:
        json.dump(data, stream, sort_keys=True, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    execute(parser.parse_args().receipt)
