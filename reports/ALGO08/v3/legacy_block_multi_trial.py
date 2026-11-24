"""Verify multiple exceptions on one original resident DS30-0016 member."""

import argparse
import json
import os
from pathlib import Path
import subprocess
from unittest.mock import patch

from leo.contracts.digests import sha256_digest
from leo.storage import short_window

from . import legacy_block_multi as multi, legacy_block_seek as core, sparse_cold_input as release
from .future_capture_storage import ORIGINAL
from .seekable_member_trial import clock, elapsed
from .zstd_physical_structure import view_for
from .zstd_structure_trial import HeldReads


HERE = Path(__file__).resolve().parent
CENSUS = Path("/dev/shm/leo-original-frame-coverage-0016-02.json")
CENSUS_PIN = "f7f570de3511e871cacb7eb2e5cc121f01b9d17f3ab11d37314cc5409caff8e4"
ORDINAL = 3
NAMES = ("manifest.json", "windows-000003.jsonl", "iq-000003.ci16.zst")


def held(view):
    def read(path, limit):
        if path.parent != ORIGINAL.path or path.name not in NAMES:
            raise ValueError("Only the enrolled member and original manifest are readable")
        return view.read(path, limit)

    return patch.object(short_window.ScannerIqStore, "_read_regular", staticmethod(read))


def verified_reader(census):
    reader = short_window.ShortWindowReader(ORIGINAL.path)
    chunk = reader.manifest.chunks[ORDINAL]
    if (reader.manifest_sha256 != ORIGINAL.manifest or census["manifest_sha256"] != ORIGINAL.manifest[7:]
            or (chunk.index_relative_path, chunk.payload_relative_path) != NAMES[1:]
            or chunk.compressed_sha256 != census["compressed_sha256"] or chunk.compressed_bytes != census["compressed_bytes"]
            or chunk.window_count != 64 or chunk.first_sequence != 192 or chunk.uncompressed_bytes != 102_400_000):
        raise ValueError("The original three-match physical member changed")
    return reader, chunk


def run(root):
    from tools.pipeline_eval.qualification.cache_residency import load_query

    setting = subprocess.check_output(("ionice", "-p", str(os.getpid())), text=True).strip()
    if (root.parent.resolve() != Path("/dev/shm") or os.sched_getaffinity(0) != {2}
            or os.getpriority(os.PRIO_PROCESS, 0) != 15 or setting != "best-effort: prio 7"):
        raise ValueError("Use the shared single-core Gauss slot and fresh tmpfs output")
    census = json.loads(release.verified(CENSUS, CENSUS_PIN))[ORDINAL]
    release.verified(release.CACHE_LIBRARY, release.CACHE_SHA)
    query = load_query(release.CACHE_LIBRARY)
    stage = clock()
    cache, view = view_for(ORIGINAL.path, NAMES, query)
    preflight = elapsed(stage)
    if view is None or cache["filesystem"] != "tmpfs" or ORIGINAL.path.resolve(strict=True) != ORIGINAL.path:
        raise ValueError("The original physical member is not already fully resident in the private stage")
    root.mkdir(mode=0o700)
    stage = clock()
    native_path = root / "legacy-block-seek.so"
    build = core.build(native_path)
    decoder, history = core.load(native_path), multi.load_history()
    build_time = elapsed(stage)

    stage = clock()
    with held(view):
        reader, chunk = verified_reader(census)
        windows = tuple(reader.windows(start_sequence=192, stop_sequence=256))
    stock = elapsed(stage)
    frame = view.files[reader.path / chunk.payload_relative_path]
    stage = clock()
    with held(view):
        sidecar = multi.seal(reader, chunk, frame, windows, history=history)
    creation = elapsed(stage)
    pin = sha256_digest(sidecar)
    header, material = multi.trusted_header(reader, chunk, sidecar, pin)
    if [row[0] for row in header["exceptions"]] != [120, 135, 676]:
        raise ValueError("Actual three exception ordinals disagree with the sealed census")
    side_path = root / "exceptions.map"
    stage = clock()
    with side_path.open("xb") as stream:
        stream.write(sidecar)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    write = elapsed(stage)

    comparisons = {}
    for operation, full in (("prefix", False), ("full", True)):
        start = clock()
        view = HeldReads(ORIGINAL.path, "tmpfs", query)
        with held(view):
            origin, chunk = verified_reader(census)
            readonly = multi.Selective(origin, chunk, side_path.read_bytes(), pin, decoder)
        attachment = elapsed(start)
        start = clock()
        try:
            for row, window in zip(readonly.rows, windows, strict=True):
                selected = readonly.read(row, full=full)
                expectation = window.samples if full else window.samples[:80_000]
                if row != window.index or not (selected == expectation).all():
                    raise ValueError("One issued selective request changed original words or chronology")
        finally:
            readonly.close()
        comparisons[operation] = dict(metadata=readonly.metadata, authentication=readonly.authentication,
            initial_construction=readonly.setup, attachment=attachment, original_pages=view.pages,
            decode_hash_and_word_comparison=elapsed(start), requests=dict(readonly.requests), native=readonly.counts.report(),
            new_exception_table_consumer=readonly.owner)
    if (comparisons["full"]["requests"]["exception_bytes"] != len(material)
            or comparisons["full"]["requests"]["full"] != 64 or comparisons["prefix"]["requests"]["prefix"] != 64):
        raise ValueError("All three original exceptions and all 128 requested views must actually be verified")
    report = dict(case="DS30-0016", member_global_index=ORDINAL, source=str(ORIGINAL.path), no_backing=True,
        census_sha256=CENSUS_PIN, census=census, cache=cache, metadata_admission=preflight, build=build,
        build_and_load=build_time, history_sha256=multi.ZSTD_PIN, binding={key: header[key] for key in multi.core.identity(reader, chunk)},
        stock_drain=stock, independent_native_decode_and_seal=creation, detached_write_sync=write, sidecar=dict(
            bytes=len(sidecar), exception_bytes=len(material), sha256=pin, emergency_footprint_ceiling=multi.MAX_SIDECAR,
            exceptions=[dict(ordinal=i, block=header["blocks"][i], sha256=hash_) for i, hash_ in header["exceptions"]]),
        users=comparisons, source_sha256={name: sha256_digest((HERE / name).read_bytes()) for name in
            ("legacy_block_multi.py", "legacy_block_multi_trial.py", "legacy_block_seek.py", "legacy_block_seek.c")})
    with (root / "result.json").open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    run(cli.parse_args().root)
