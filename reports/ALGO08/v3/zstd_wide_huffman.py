"""Time and census installed Huffman decode on the original resident DS30-0016 member."""

import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
from statistics import median
import subprocess
from unittest.mock import patch

from . import sparse_cold_input as release
from .zstd_physical_structure import view_for
from .zstd_structure import inspect, literal_section
from .zstd_structure_trial import BUNDLED_SHA, READER_SHA, Samples, locations, timed_reads


HERE = Path(__file__).resolve().parent
RECORDING = "fast8-auto-20261113-112146-b04f5461-1-lower"
SOURCE = Path("/dev/shm/leo-v3-guarded-selective-0016-stage01") / RECORDING / (RECORDING + "-segment-00000000")
PINS = (
    "sha256:1530e4a7376f569f52d2b41dfdfc732489b036df73a8cff9b0feabecbc8cb3cc",
    "sha256:4773bee9d16a0291338408540c4b4e83c6ce960bb2ed01ef1e5e65a25d38ea4a",
    "sha256:dfe2b6d4971a48811462a2ad1f97e85a7574fa949c0b8f10fe4222e0ab20c609",
    "sha256:defed2edfa130b9c1cbee028b9c5daa3700265a9bc2ecc1d0b5105fc67089b43",
)
DENSE_SOURCE = Path("/dev/shm/leo-seekable-member-0008-case1/fast8-auto-20261113-075937-d9ab96ee-1-lower-segment-00000000")
DENSE_PINS = (
    "sha256:5ffe3ed98feb37f7f7ada44dbf34d2af9d3fcadce567fd3cdbb7e31965a02759",
    "sha256:556772d5619b710cae8030050b8f8a4a7b18f4b196e57cddc14562c8ca73404a",
    "sha256:9bd62a272cc90d7b1abbb6ac2424317a599b9f92fca5287ed0999fd1e6b1e802",
    "sha256:758d22d502ba1e0688f3dfb2528549eadd187f33021598179e9fab308e9a89b6",
)
CASES = {"DS30-0016": (SOURCE, PINS), "DS30-0008": (DENSE_SOURCE, DENSE_PINS)}
NAMES = ("manifest.json", "windows-000000.jsonl", "iq-000000.ci16.zst")
WIDTHS = (12, 14, 16)
REPEATS = 16
DENSE_CALLS = 6_772


def table_extent(src):
    if not src:
        raise ValueError("Missing Huffman weight descriptor")
    first = src[0]
    size = 1 + ((first - 127 + 1) // 2 if first >= 128 else first)
    if not 1 < size < len(src):
        raise ValueError("Incomplete Huffman table or bitstream")
    return size


def huffman_blocks(frame, decoded_bytes):
    spans = []
    structure = inspect(frame, decoded_bytes, block_spans=spans)
    view = memoryview(frame)
    groups, rows = [], []
    stats = Counter()
    for pos, length, original_decoded, sequences in spans:
        lit, header, encoded, decoded, lanes = literal_section(view[pos:pos + length])
        if decoded != original_decoded:
            raise ValueError("Block literal extent changed")
        if lit == "huffman_new":
            weights = view[pos + header:pos + header + encoded]
            extent = table_extent(weights)
            groups.append(dict(offset=pos + header, bytes=extent, sha256=sha256(weights[:extent]).hexdigest(),
                               blocks=0, four_stream_blocks=0, four_stream_literals=0))
        if lanes:
            group = groups[-1]
            group["blocks"] += 1
            group["four_stream_blocks"] += lanes == 4
            group["four_stream_literals"] += decoded if lanes == 4 else 0
            stats[f"huffman{lanes}_with{'out' if not sequences else ''}_sequences_blocks"] += 1
            stats[f"huffman{lanes}_with{'out' if not sequences else ''}_sequences_literals"] += decoded
            rows.append(dict(offset=pos + header, encoded=encoded, decoded=decoded, group=len(groups) - 1,
                             streams=lanes, sequences=sequences, new=lit == "huffman_new"))
    return structure, groups, rows, dict(stats)


def admit(case):
    import zstandard.backend_c as cext
    from leo.storage import short_window
    from tools.pipeline_eval.qualification.cache_residency import load_query

    source, pins = CASES[case]
    if (os.sched_getaffinity(0) != {2} or source.resolve(strict=True) != source
            or source.stat().st_dev != Path("/dev/shm").stat().st_dev):
        raise ValueError("Expected the local original stage and the shared CPU2 slot")
    release.verified(Path(cext.__file__), BUNDLED_SHA)
    release.verified(Path(short_window.__file__), READER_SHA)
    release.verified(release.CACHE_LIBRARY, release.CACHE_SHA)
    query = load_query(release.CACHE_LIBRARY)
    admitted, view = view_for(source, NAMES, query)
    if view is None or admitted["filesystem"] != "tmpfs":
        raise ValueError("The original member is not fully resident on tmpfs")
    with patch.object(short_window.ScannerIqStore, "_read_regular", staticmethod(view.read)):
        reader = short_window.ShortWindowReader(source)
        member = reader.manifest.chunks[0]
        if (reader.manifest_sha256, member.compressed_sha256, member.index_sha256, member.uncompressed_sha256) != pins:
            raise ValueError("The original member binding differs from the frozen one")
        windows = tuple(row.index.iq_sha256 for row in reader.windows(stop_sequence=64))
    if len(windows) != 64 or member.window_count != 64 or member.first_sequence != 0:
        raise ValueError("Expected one complete first physical member")
    return short_window, cext, reader, member, view, windows, admitted


def run(root, case):
    short_window, cext, reader, member, view, windows, admitted = admit(case)
    frame = view.files[reader.path / member.payload_relative_path]
    structure, groups, rows, eligibility = huffman_blocks(frame, member.uncompressed_bytes)

    root.mkdir()
    library = root / "pc.so"
    subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-O2", "-shared", "-fPIC",
                    str(HERE / "zstd_decoder_pc.c"), "-o", str(library)], check=True)
    before = [timed_reads(short_window, reader, view, windows) for _ in range(2)]
    sampler = Samples(library)
    sampler.start()
    try:
        profiled = [timed_reads(short_window, reader, view, windows, sampler) for _ in range(REPEATS)]
    finally:
        pcs, overruns = sampler.stop()
    after = [timed_reads(short_window, reader, view, windows) for _ in range(2)]
    profile = locations(Path(cext.__file__), pcs)
    if profile["total"] < 250:
        raise ValueError("Insufficient actual decoder samples")
    counts = Counter(group["sha256"] for group in groups)
    median_ms = median(row["decode_cpu_ns"] for row in before + after) / 1e6
    names = profile["symbols"]
    loops = sum(value for key, value in names.items()
                if "HUF_decompress4X" in key and "internal_fast_c_loop" in key)
    result = dict(case=case, source=str(reader.path), pins=CASES[case][1], member=member.model_dump(mode="json"), cache=admitted,
                  window_iq_sha256=windows, structure=structure, groups=groups, eligibility=eligibility, huffman=rows,
                  tables=dict(new=len(groups), distinct=len(counts), longest=max(g["blocks"] for g in groups),
                              table_bytes={bits: 4*(1 << bits) for bits in WIDTHS}),
                  before=before, after=after, profiled=profiled, pc=profile, sampler_overruns=overruns,
                  pricing=dict(median_read_ms=median_ms, fast_loop_fraction=loops / profile["total"],
                               observed_share_fast_loop_ms=median_ms * loops / profile["total"],
                               one_second_dense_ms_per_member=64_000 / DENSE_CALLS),
                  sources={name: sha256((HERE / name).read_bytes()).hexdigest() for name in
                           ("zstd_decoder_pc.c", "zstd_structure.py", "zstd_structure_trial.py", "zstd_wide_huffman.py")})
    with (root / "scope.json.gz").open("xb") as out:
        out.write(gzip.compress(json.dumps(result, sort_keys=True, separators=(",", ":")).encode(), mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--case", choices=tuple(CASES), default="DS30-0016")
    args = parser.parse_args()
    run(args.root, args.case)
