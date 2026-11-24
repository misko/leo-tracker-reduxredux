"""Prove exact independent spans on the original resident DS30-0008 member."""

import argparse
import gzip
import json
import os
from pathlib import Path
import subprocess
from unittest.mock import patch

from leo.contracts.digests import sha256_digest
from leo.storage import short_window
from leo.storage.errors import BundleCorruptionError

from . import legacy_block_seek as core, sparse_cold_input as release
from .legacy_block_exception import PREFIX, SelectiveException, encode_sidecar, open_sidecar, overlaps
from .seekable_member_trial import clock, elapsed
from .zstd_physical_structure import view_for
from .zstd_structure_trial import HeldReads
from .zstd_wide_huffman import DENSE_PINS, DENSE_SOURCE, NAMES, huffman_blocks


HERE = Path(__file__).resolve().parent
SCOPE = HERE / "measurements/zstd-wide-huffman-0008-scope.json.gz"
SCOPE_PIN = "d0f18a12ed2e149e01902f1713bf95954ed5dd949fd208fe4da45b99b7711791"
ORDERS = (("stock", "exception"), ("exception", "stock"))


def source(query):
    exposure, view = view_for(DENSE_SOURCE, NAMES, query)
    if view is None or exposure["filesystem"] != "tmpfs" or DENSE_SOURCE.resolve(strict=True) != DENSE_SOURCE:
        raise ValueError("The original signed dense member was not already resident in local tmpfs")
    return exposure, view


def verified_reader():
    reader = short_window.ShortWindowReader(DENSE_SOURCE)
    chunk = reader.manifest.chunks[0]
    if (reader.manifest_sha256, chunk.compressed_sha256, chunk.index_sha256, chunk.uncompressed_sha256) != DENSE_PINS:
        raise ValueError("Original dense source pins changed")
    if chunk.first_sequence != 0 or chunk.window_count != 64 or chunk.uncompressed_bytes != 102_400_000:
        raise ValueError("Only the original complete first dense member is enrolled")
    return reader, chunk


def workload(reader, windows):
    from .future_capture_storage import qualified
    from .mixed_aperture_receiver import StereoSchedule

    schedule = StereoSchedule(full_coverage=True)
    targets = {row["target_id"]: row for row in reader.manifest.configuration["targets"]}
    requests = []
    for window in windows:
        row = window.index
        if not qualified(row.acquisition):
            requests.append(None)
            continue
        _, detector = schedule.visit("lower", targets[row.target_id], row.acquisition)
        requests.append(detector == "full")
    return requests


def measure(mode, query, path, pin, library, binary, original, requests, *, exact=False):
    """Time fresh resident attachment and reading with no numerical detector work."""
    view = HeldReads(DENSE_SOURCE, "tmpfs", query)
    started = clock()
    with patch.object(short_window.ScannerIqStore, "_read_regular", staticmethod(view.read)):
        reader, chunk = verified_reader()
        manifest = elapsed(started)
        if mode == "stock":
            count = 0
            for seen, expected, full in zip(reader.windows(stop_sequence=64), original, requests, strict=True):
                if seen.index != expected.index:
                    raise ValueError("Stock index order changed")
                if full is not None:
                    count += seen.index.payload_bytes if full else min(seen.index.payload_bytes, PREFIX)
            return dict(timing=elapsed(started), manifest=manifest, returned_bytes=count,
                        encoded_authenticated_bytes=chunk.compressed_bytes, decoded_bytes=chunk.uncompressed_bytes,
                        original_residence=view.pages)
        stage = clock()
        raw = path.read_bytes()
        side_read = elapsed(stage)
        active = SelectiveException(core, reader, chunk, raw, pin, binary)
        attached = elapsed(started)
        try:
            stage = clock()
            for row, expected, full in zip(active.rows, original, requests, strict=True):
                if row != expected.index:
                    raise ValueError("Independent span reader reordered the original signed opportunities")
                if full is not None:
                    current = active.read(row, full=full)
                    if exact and not (current == (expected.samples if full else expected.samples[:80_000])).all():
                        raise ValueError("The composed CI16 words differ from released stock")
            request_clock = elapsed(stage)
        finally:
            active.close()
        counts = active.counts.report()
        return dict(timing=elapsed(started), attached=attached, manifest=manifest, binary=str(library),
                    sidecar_read=side_read, sidecar_bytes=len(raw), metadata=active.metadata,
                    complete_encoded_auth=active.authentication, structure_and_native_context=active.setup,
                    requested_span_and_hash=request_clock, encoded_authenticated_bytes=chunk.compressed_bytes,
                    original_residence=view.pages, requests=dict(active.reads), decode=counts,
                    decoded_bytes=counts["requested_decoded"]+counts["dependency_decoded"])


def damage(query, frame, index, ordinal, path, pin, binary):
    view = HeldReads(DENSE_SOURCE, "tmpfs", query)
    raw = path.read_bytes()
    with patch.object(short_window.ScannerIqStore, "_read_regular", staticmethod(view.read)):
        reader, chunk = verified_reader()
        changed = bytearray(raw)
        changed[-1] ^= 1
        try:
            SelectiveException(core, reader, chunk, bytes(changed), pin, binary)
        except core.MapError as error:
            map_error = str(error)
        else:
            raise ValueError("Changed exception escaped its detached pin")
    corrupt_at = index[ordinal][0] + index[ordinal][1] // 2
    altered = bytearray(frame)
    altered[corrupt_at] ^= 1
    payload = reader.path / chunk.payload_relative_path

    def changed_read(path, limit):
        return bytes(altered) if path == payload else view.read(path, limit)

    rejected = {}
    with patch.object(short_window.ScannerIqStore, "_read_regular", staticmethod(changed_read)):
        for label in ("stock", "exception"):
            try:
                if label == "stock":
                    next(reader.windows(stop_sequence=64))
                else:
                    SelectiveException(core, reader, chunk, raw, pin, binary)
            except BundleCorruptionError as error:
                rejected[label] = str(error)
            else:
                raise ValueError("A mutation to intentionally skipped compressed bytes escaped authentication")
    return dict(detached_map=map_error, original_encoded_byte=corrupt_at, before_any_visit=rejected)


def run(root):
    from tools.pipeline_eval.qualification.cache_residency import load_query

    policy = subprocess.check_output(("ionice", "-p", str(os.getpid())), text=True).strip()
    if (root.parent.resolve() != Path("/dev/shm") or os.sched_getaffinity(0) != {2}
            or os.getpriority(os.PRIO_PROCESS, 0) != 15 or policy != "best-effort: prio 7"):
        raise ValueError("Use the low-priority single CPU 2 Gauss slot and a fresh tmpfs directory")
    archived = json.loads(gzip.decompress(release.verified(SCOPE, SCOPE_PIN)))
    release.verified(release.CACHE_LIBRARY, release.CACHE_SHA)
    query = load_query(release.CACHE_LIBRARY)
    stage = clock()
    residence, view = source(query)
    residency_clock = elapsed(stage)
    root.mkdir(mode=0o700)
    stage = clock()
    library = root / "legacy-block-seek.so"
    build = core.build(library)
    binary = core.load(library)
    build_clock = elapsed(stage)
    stage = clock()
    with patch.object(short_window.ScannerIqStore, "_read_regular", staticmethod(view.read)):
        reader, chunk = verified_reader()
        original = tuple(reader.windows(stop_sequence=64))
    trusted_decode_clock = elapsed(stage)
    frame = view.files[DENSE_SOURCE / chunk.payload_relative_path]
    if (tuple(window.index.iq_sha256 for window in original) != tuple(archived["window_iq_sha256"])
            or list(DENSE_PINS) != archived["pins"]):
        raise ValueError("The released read changed the complete archived authority")
    stage = clock()
    encoded = encode_sidecar(core, reader, chunk, frame, original)
    pin = sha256_digest(encoded)
    sidecar_seal = elapsed(stage)
    side = root / "exception.map"
    stage = clock()
    with side.open("xb") as write:
        write.write(encoded)
        write.flush()
        os.fsync(write.fileno())
    directory = os.open(root, os.O_DIRECTORY | os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    sidecar_write = elapsed(stage)
    archive_structure, groups, huffman, _ = huffman_blocks(frame, chunk.uncompressed_bytes)
    if (archive_structure != archived["structure"] or groups != archived["groups"] or huffman != archived["huffman"]):
        raise ValueError("Current exact HUF map disagrees with the previously sealed ordinal census")
    document, material = open_sidecar(core, reader, chunk, encoded, pin)
    ordinal = document["ordinal"]
    entry = document["blocks"][ordinal]
    windows = []
    for index, window in enumerate(original):
        low, high = overlaps(entry, window.index.payload_offset_bytes, window.index.payload_bytes)
        if low < high:
            windows.append(index)
    requests = workload(reader, original)
    if ordinal != 311 or windows != [25] or requests[25] is not False:
        raise ValueError("The enrolled mixed-aperture schedule differs from the frozen exception witness")
    ready = []
    for order in ORDERS:
        ready.append({mode: measure(mode, query, side, pin, library, binary, original, requests) for mode in order})
    exact_scheduled = measure("exception", query, side, pin, library, binary, original, requests, exact=True)
    proof = measure("exception", query, side, pin, library, binary, original, [True]*len(requests), exact=True)
    if (exact_scheduled["requests"].get("exception_visits", 0) or proof["requests"]["exception_visits"] != 1
            or proof["requests"]["exception_bytes"] != len(material)):
        raise ValueError("The sparse exception should be skipped for the real schedule and read once for all full visits")
    rejected = damage(query, frame, document["blocks"], ordinal, side, pin, binary)
    receipt = dict(case="DS30-0008", pins=DENSE_PINS, no_backing=True, scope_sha256=SCOPE_PIN, original=archive_structure,
        residency=residence, residency_clock=residency_clock, source=str(DENSE_SOURCE), trial_sources={
            name: sha256_digest((HERE / name).read_bytes()) for name in ("legacy_block_exception.py",
                "legacy_block_exception_trial.py", "legacy_block_seek.c", "legacy_block_seek.py")},
        build=build, build_clock=build_clock, trusted_whole_decode=trusted_decode_clock, sidecar_seal=sidecar_seal,
        sidecar_write=sidecar_write, sidecar=dict(digest=pin, bytes=len(encoded), raw_exception_bytes=len(material),
            exact_decoded_exception_sha256=document["exact_decoded_exception_sha256"], ordinal=ordinal, entry=entry,
            retained_requests=len(requests), original_full_visits=sum(item is True for item in requests),
            original_short_visits=sum(item is False for item in requests), touched_visits=windows,
            original_table_owner_consumers=sum(block[4] == ordinal for block in document["blocks"][ordinal+1:])),
        orders=ORDERS, ready=ready, scheduled_exact_word_check=exact_scheduled, forced_full_exact_word_check=proof,
        mutations_rejected=rejected, cold_disk_timed=False)
    with (root / "result.json").open("x") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("root", type=Path)
    run(command.parse_args().root)
