"""Qualify exact output on one of two pinned detached tmpfs members, without timing."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
import subprocess
import sys

from leo.storage.short_window import ShortWindowReader

from .legacy_block_seek import read_rows
from .zstd_literal_pair import Authority, Decoder, HERE, digest, plan
from .zstd_structure import inspect


CASES = {
    "DS30-0008": (
        Path("/dev/shm/leo-seekable-member-0008-case1/fast8-auto-20261113-075937-d9ab96ee-1-lower-segment-00000000"),
        ("5ffe3ed98feb37f7f7ada44dbf34d2af9d3fcadce567fd3cdbb7e31965a02759",
         "556772d5619b710cae8030050b8f8a4a7b18f4b196e57cddc14562c8ca73404a",
         "9bd62a272cc90d7b1abbb6ac2424317a599b9f92fca5287ed0999fd1e6b1e802",
         "758d22d502ba1e0688f3dfb2528549eadd187f33021598179e9fab308e9a89b6"), (390, 1, 1),
    ),
    "DS30-0016": (
        Path("/dev/shm/leo-v3-guarded-selective-0016-stage01/fast8-auto-20261113-112146-b04f5461-1-lower")
        / "fast8-auto-20261113-112146-b04f5461-1-lower-segment-00000000",
        ("1530e4a7376f569f52d2b41dfdfc732489b036df73a8cff9b0feabecbc8cb3cc",
         "4773bee9d16a0291338408540c4b4e83c6ce960bb2ed01ef1e5e65a25d38ea4a",
         "dfe2b6d4971a48811462a2ad1f97e85a7574fa949c0b8f10fe4222e0ab20c609",
         "defed2edfa130b9c1cbee028b9c5daa3700265a9bc2ecc1d0b5105fc67089b43"), (391, 0, 0),
    ),
}
FILES = ("manifest.json", "iq-000000.ci16.zst", "windows-000000.jsonl")


def resident(paths):
    for path in paths:
        if path.resolve(strict=True) != path or not path.is_file() or path.stat().st_dev != Path("/dev/shm").stat().st_dev:
            raise ValueError("Require literal, private tmpfs fixture files")
    command = ["/usr/bin/fincore", "--json", "--bytes", "--output", "RES,PAGES,SIZE,FILE"]
    entries = json.loads(subprocess.check_output([*command, *paths]))["fincore"]
    if {Path(row["file"]) for row in entries} != set(paths) or any(row["res"] < row["size"] for row in entries):
        raise ValueError("The existing detached sources must already be fully resident")
    return entries


def restrict_payloads(expected):
    def audit(event, arguments):
        if event != "open" or isinstance(arguments[0], int):
            return
        source = Path(os.fsdecode(arguments[0])).absolute()
        if source.is_relative_to("/srv/bulk") or source.is_relative_to("/mnt/qnap01"):
            raise PermissionError("Backing archives are unavailable for this check")
        if source.suffix in {".zst", ".ci16", ".tle"} and source not in expected:
            raise PermissionError("Only the one detached wave member is enrolled")
    sys.addaudithook(audit)


def check(case, decoder, native_pin):
    cpus = os.sched_getaffinity(0)
    if len(cpus) != 1 or 2 in cpus or os.getpriority(os.PRIO_PROCESS, 0) < 15:
        raise ValueError("Correctness only, using one nonbenchmark CPU at nice 15")
    source, pins, expected_work = CASES[case]
    paths = tuple(source / name for name in FILES)
    before = resident(paths)
    restrict_payloads(paths)
    usage = getrusage(RUSAGE_SELF)
    reader = ShortWindowReader(source)
    chunk = reader.manifest.chunks[0]
    if (chunk.chunk_index, chunk.first_sequence, chunk.window_count, chunk.payload_relative_path,
            chunk.index_relative_path) != (0, 0, 64, FILES[1], FILES[2]):
        raise ValueError("Only the first signed detached member is enrolled")
    actual_pins = reader.manifest_sha256, chunk.compressed_sha256, chunk.index_sha256, chunk.uncompressed_sha256
    if actual_pins != tuple("sha256:" + value for value in pins):
        raise ValueError("Detached manifest or member digests differ from the archived pins")
    rows = read_rows(reader, chunk)
    receipt = Authority(chunk.compressed_bytes, chunk.compressed_sha256, chunk.uncompressed_bytes,
                        chunk.uncompressed_sha256, tuple((row.payload_bytes, row.iq_sha256) for row in rows))
    encoded = reader._member(chunk.payload_relative_path, chunk.compressed_bytes, chunk.compressed_sha256)
    control, _ = decoder.verified(encoded, receipt)
    candidate, counts = decoder.verified(encoded, receipt, paired=True)
    expected = {name: value for name, value in zip(("pair_count", "singletons", "mixed_blocks"), expected_work, strict=True)}
    if candidate != control or counts["route"] != "paired" or any(counts[k] != v for k, v in expected.items()):
        raise ValueError(f"Exact bytes or planned branch counts differ: {counts}")
    del control
    at = 0
    count = 0
    for item, row in zip(reader.windows(start_sequence=0, stop_sequence=64), rows, strict=True):
        whole = memoryview(item.samples).cast("B")
        if item.index != row or whole != candidate[at:at + len(whole)]:
            raise ValueError("The installed manifest reader and paired lane order differ")
        at += len(whole)
        count += 1
    if at != len(candidate) or count != 64:
        raise ValueError("The paired and installed readers disagree on complete coverage")
    final = getrusage(RUSAGE_SELF)
    after = resident(paths)
    if final.ru_inblock - usage.ru_inblock:
        raise ValueError("Unexpected block input during the resident check")
    return dict(case=case, source=str(source), immutable_encoded_snapshot=True, pinned_original=list(actual_pins),
                installed_reader_sha256=digest(Path(sys.modules[ShortWindowReader.__module__].__file__).read_bytes()),
                native_candidate_sha256=native_pin, source_sha256=digest((HERE / "zstd_literal_pair.c").read_bytes()),
                ordered_window_pins_sha256=digest("\n".join(row.iq_sha256 for row in rows).encode()),
                decoded_sha256="sha256:" + sha256(candidate).hexdigest(), verified_windows=count, same_all_bytes=True,
                structure=inspect(encoded, len(candidate)), paired=counts,
                mixed_ordinal=[i for i, row in enumerate(plan(encoded, len(candidate))) if row[-1]],
                residency_before=before, residency_after=after, ru_inblock=0, max_rss_kib=final.ru_maxrss,
                controlled_clock=False, affinity=sorted(cpus))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("library", type=Path)
    parser.add_argument("native_pin")
    args = parser.parse_args()
    print(json.dumps(check(args.case, Decoder(args.library, args.native_pin), args.native_pin), sort_keys=True, indent=2))
