"""Inspect one resident signed physical frame, or reconstruct one physical fixture."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from . import sparse_cold_input as release
from .full_short_cold import check_machine
from .warm_six_prefetch import ColdPage
from .zstd_structure import inspect
from .zstd_structure_trial import HeldReads, READER_SHA


PHYSICAL = Path("/var/tmp/leo-full-short-DS30-0016-pair/request.json")
PHYSICAL_SHA = "d58723098826fc7e1478f92880dffdb500bcb3f5225b4d64a4b2949cfbceab06"
WEAK = Path("/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_20_single_scan_glrt/satellite-reference.zip")
WEAK_SHA = "0f025d0f5c80f5425a3c6fa90bc77a0e5628eb8cf7bc7ac7dab7fdd6c1d2e9d9"
WRITER_SHA = "86de05d4e62356a3c7a87caaa91e9fcd5495b064468b632fa26c8fd514fa5aa1"


def view_for(root, names, query):
    from tools.pipeline_eval.qualification.cache_residency import cache_snapshot

    fs = subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root], text=True).strip()
    plan = [(root, name, (root / name).stat().st_size) for name in names]
    snapshot = cache_snapshot(plan, os.sysconf("SC_PAGE_SIZE"), query)
    data = dict(filesystem=fs, members={name: size for _, name, size in plan}, snapshot=snapshot)
    if snapshot["observed_members"] != len(names) or snapshot["cached_pages"] != snapshot["observed_file_pages"]:
        data["stop"] = "incomplete residency before content read"
        return data, None
    view = HeldReads(root, fs, query)
    data["descriptor_pages"] = view.pages
    return data, view


def original(query):
    from leo.storage import short_window

    release.verified(Path(short_window.__file__), READER_SHA)
    pin = json.loads(release.verified(PHYSICAL, PHYSICAL_SHA))["inventory_pins"][0]
    manifest = Path(pin["path"])
    names = ("manifest.json", "windows-000000.jsonl", "iq-000000.ci16.zst")
    data, view = view_for(manifest.parent, names, query)
    data.update(source=str(manifest), request_sha256=PHYSICAL_SHA, original=True)
    if view is None:
        return data
    try:
        with patch.object(short_window.ScannerIqStore, "_read_regular", staticmethod(view.read)):
            reader = short_window.ShortWindowReader(manifest.parent)
            chunk = reader.manifest.chunks[0]
            if (reader.manifest_sha256 != pin["sha256"] or chunk.chunk_index != 0 or chunk.first_sequence != 0
                    or chunk.index_relative_path != names[1] or chunk.payload_relative_path != names[2]
                    or chunk.window_count != 64 or chunk.uncompressed_bytes != 102400000):
                raise ValueError("Unexpected first member of signed original")
            reader._member(chunk.index_relative_path, chunk.index_bytes, chunk.index_sha256)
            frame = reader._member(chunk.payload_relative_path, chunk.compressed_bytes, chunk.compressed_sha256)
    except ColdPage as error:
        data["stop"] = str(error)
        return data
    data.update(manifest_sha256=reader.manifest_sha256, chunk=chunk.model_dump(mode="json"),
                structure=inspect(frame, chunk.uncompressed_bytes))
    return data


def reconstruct(clips, output, writer, zstd):
    archive_writer = writer(output / "reconstructed.ci16.zst.partial", level=1)
    digests, decoded = [], sha256()
    for row, iq in clips:
        payload = memoryview(iq.reshape(-1)).cast("B")
        decoded.update(payload)
        archive_writer.write(payload)
        digests.append(dict(case=row["case"], visit=row["visit"], sha256=row["sha256"], raw_bytes=len(payload)))
    path, count, digest = archive_writer.finish()
    frame = release.verified(path, digest)
    if len(frame) != count:
        raise ValueError("Reconstructed frame extent mismatch")
    with zstd.ZstdDecompressor().stream_reader(frame) as stream:
        for row in digests:
            if sha256(stream.read(row["raw_bytes"])).hexdigest() != row["sha256"].removeprefix("sha256:"):
                raise ValueError("Reconstructed frame failed per-window bit comparison")
        if stream.read(1):
            raise ValueError("Unexpected trailing decoded bytes")
    return dict(compressed_sha256=digest, decoded_sha256=decoded.hexdigest(), visits=digests,
                structure=inspect(frame, sum(row["raw_bytes"] for row in digests)))


def weak(query):
    from leo.storage import writer
    from tools.pipeline_eval.variants.experimental.receiver_benchmark import read_archive

    release.verified(Path(writer.__file__), WRITER_SHA)
    data, view = view_for(WEAK.parent, (WEAK.name,), query)
    data.update(source=str(WEAK), source_sha256=WEAK_SHA, original=False)
    if view is None:
        return data
    start_cpu, start_wall = process_time_ns(), perf_counter_ns()
    try:
        blob = view.read(WEAK, 22425953)
    except ColdPage as error:
        data["stop"] = str(error)
        return data
    if sha256(blob).hexdigest() != WEAK_SHA:
        raise ValueError("Unexpected physical weak fixture digest")
    clips = list(read_archive(BytesIO(blob), 18))
    if len(clips) != 18:
        raise ValueError("The fixed physical weak archive must supply 18 visits")
    read_cpu, read_wall = process_time_ns(), perf_counter_ns()
    with TemporaryDirectory(dir="/dev/shm", prefix="leo-zstd-physical-") as path:
        data.update(reconstruct(clips, Path(path), writer._CompressedFileWriter, writer.zstd))
    data.update(staging_cpu_ns=read_cpu-start_cpu, staging_wall_ns=read_wall-start_wall,
                reconstruction_cpu_ns=process_time_ns()-read_cpu, reconstruction_wall_ns=perf_counter_ns()-read_wall,
                writer_sha256=WRITER_SHA, codec=list(writer.zstd.ZSTD_VERSION))
    return data


def main():
    from tools.pipeline_eval.qualification.cache_residency import load_query

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", choices=("original", "weak"))
    args = parser.parse_args()
    machine = check_machine()
    release.verified(release.CACHE_LIBRARY, release.CACHE_SHA)
    query = load_query(release.CACHE_LIBRARY)
    transfer = (original if args.source == "original" else weak)(query)
    print(json.dumps(dict(machine=machine, transfer=transfer, source_sha256=sha256(Path(__file__).read_bytes()).hexdigest()),
                     indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
