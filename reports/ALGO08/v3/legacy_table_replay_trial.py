"""Qualify exact table restoration on only the last staged DS30-0016 member."""

import argparse
from contextlib import ExitStack
import ctypes as ct
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import numpy as np

from leo.contracts.digests import sha256_digest
from leo.storage.short_window import ShortWindowReader

from . import legacy_block_seek as core, sparse_cold_input as release
from .future_capture_storage import SOURCE
from .legacy_block_exception import SelectiveException, encode_sidecar, exception_layout, open_sidecar
from .seekable_member_trial import clock, elapsed
from .zstd_physical_structure import view_for

SCOPE = SimpleNamespace(
    path=SOURCE.with_name(SOURCE.name[:-1] + "1"),
    manifest="sha256:48c9225baa0327877da41508a17ccca3175808670a174470142ecf228e1cc2a3",
)
PINS = (
    "sha256:b9b5e3e65e0d0088a5714489ea6ad0bdf97a0c1f20d61e95cc5cfcf7e0cd0a2d",
    "sha256:81f21f5fdf4119e8655e7f875808489178ab8a8bf2b603e715e2814778cfefde",
    "sha256:249a85538688dfeae65e9c2f5ab07555d7ee1e088f750aff77984170a2132c4f",
)
MEMBER = 4


def open_selective(reader, chunk, sidecar, pin, binary):
    return SelectiveException(core, reader, chunk, sidecar, pin, binary, replay_table=True)


def forced_check(reader, chunk, sidecar, pin, binary, windows, owner, consumer):
    participant = open_selective(reader, chunk, sidecar, pin, binary)
    try:
        start, length = participant.blocks[consumer][2:4]
        output = np.empty(length, dtype=np.uint8)
        attempted = binary.legacy_span(
            participant.context, participant.pointer, len(participant.frame), participant.native_blocks,
            len(participant.blocks), owner, participant.blocks[owner][2], 1,
            output.ctypes.data, ct.byref(participant.counts))
        if attempted:
            raise ValueError("native output exposed the synthetic table owner")
        participant.decode(start, length, output.ctypes.data)
        wanted = bytearray()
        for window in windows:
            offset = window.index.payload_offset_bytes
            begin, end = max(offset, start), min(offset + window.index.payload_bytes, start + length)
            if begin < end:
                raw = memoryview(window.samples.reshape(-1)).cast("B")
                wanted.extend(raw[begin - offset:end - offset])
        if (memoryview(output) != wanted or participant.counts.requested_blocks != 1
                or binary.legacy_origin_replays(participant.context) != 1):
            raise ValueError("independent dependent block failed exact original parity")
        result = dict(owner=owner, consumer=consumer, returned_sha256=sha256_digest(wanted),
                      owner_refused_native_output=True, table_replays=1, counts=participant.counts.report())
    finally:
        participant.close()
    participant = open_selective(reader, chunk, sidecar, pin, binary)
    try:
        for row, stock in zip(participant.rows, windows, strict=True):
            if row != stock.index or not np.array_equal(participant.read(row, full=True), stock.samples):
                raise ValueError("exception reader changed a complete stock-authenticated visit")
        full = dict(checked=len(windows), reads=dict(participant.reads),
                    table_replays=binary.legacy_origin_replays(participant.context))
    finally:
        participant.close()
    return result, full


def run(root):
    from tools.pipeline_eval.qualification.cache_residency import load_query
    from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes

    from .full_short_run import EIGHT_MS_SHA
    from .mixed_aperture_receiver import INSTALLED_SHA, PILOT_SHA, NativePath
    from .seekable_eight_raw import SHORT

    io = subprocess.check_output(("ionice", "-p", str(os.getpid())), text=True).strip()
    if (root.parent.resolve() != Path("/dev/shm") or os.sched_getaffinity(0) != {2}
            or os.getpriority(os.PRIO_PROCESS, 0) != 15 or io != "best-effort: prio 7"
            or not Path(ShortWindowReader.windows.__code__.co_filename).is_relative_to(release.RELEASE)):
        raise ValueError("require isolated tmpfs, installed stock and the shared CPU2 Gauss lock")
    release.verified(release.CACHE_LIBRARY, release.CACHE_SHA)
    reader = ShortWindowReader(SCOPE.path)
    chunk = reader.manifest.chunks[MEMBER]
    if ((chunk.compressed_sha256, chunk.index_sha256, chunk.uncompressed_sha256) != PINS
            or reader.manifest_sha256 != SCOPE.manifest or chunk.first_sequence != 256
            or chunk.window_count != 40 or chunk.compressed_bytes != 49_036_352
            or chunk.uncompressed_bytes != 64_000_000 or chunk.index_bytes != 108_240):
        raise ValueError("last original manifest and member identity changed")
    names = ("manifest.json", chunk.index_relative_path, chunk.payload_relative_path)
    if any((SCOPE.path / name).resolve(strict=True) != SCOPE.path / name for name in names):
        raise ValueError("original scoped paths must stay in the staged segment")
    residence, view = view_for(SCOPE.path, names, load_query(release.CACHE_LIBRARY))
    if view is None or residence["filesystem"] != "tmpfs":
        raise ValueError("last original member must already be resident")
    spec = json.loads(release.verified(release.PAYLOAD / "spec.json", release.SPEC_SHA))
    ingress = release.frozen_function(spec, "receiver_ingress.py", "compressed_input_buffer")
    hasher = release.PAYLOAD / "paired-sha256.so"
    release.verified(hasher, spec["paired_sha256"]["sha256"])
    full = release.PAYLOAD / "receiver.so"
    release.verified(full, INSTALLED_SHA)
    release.verified(SHORT, EIGHT_MS_SHA)
    pilot = np.frombuffer(release.verified(release.RELEASE / "assets/lower.f32", PILOT_SHA["lower"]), dtype="<f4")
    root.mkdir(mode=0o700)
    library = root / "legacy-block-seek.so"
    build = core.build(library)
    binary = core.load(library)
    began = clock()
    snapshots = []
    with core.one_member(SCOPE.path, chunk, snapshots=snapshots), ingress(), paired_decoded_hashes(hasher):
        windows = tuple(reader.windows(start_sequence=chunk.first_sequence,
                                       stop_sequence=chunk.first_sequence + chunk.window_count))
    authority = elapsed(began)
    frame, = snapshots
    start = clock()
    sidecar = encode_sidecar(core, reader, chunk, frame, windows, replay_table=True)
    pin = sha256_digest(sidecar)
    side = root / "exception.map"
    with side.open("xb") as write:
        write.write(sidecar)
        write.flush()
        os.fsync(write.fileno())
    map_clock = elapsed(start)
    build_and_verify = elapsed(began)
    blocks, owner, seed = exception_layout(frame, chunk.uncompressed_bytes)
    dependents = [index for index, block in enumerate(blocks) if index > owner and block[4] == owner]
    if owner != 232 or dependents != [233] or seed is None or blocks[owner][3] - seed[2] != 7:
        raise ValueError("exception and dependent differ from the earlier frozen original census")
    del frame, snapshots
    metadata, retained = open_sidecar(core, reader, chunk, sidecar, pin)
    with core.one_member(SCOPE.path, chunk), ingress(), paired_decoded_hashes(hasher):
        forced, all_full = forced_check(reader, chunk, sidecar, pin, binary, windows, owner, dependents[0])
    with ExitStack() as stack:
        natives = {name: NativePath(path, pilot, name) for name, path in (
            ("full", full), ("short_primary", SHORT))}
        for engine in natives.values():
            stack.callback(engine.close)
        with core.one_member(SCOPE.path, chunk), ingress(), paired_decoded_hashes(hasher):
            parity, proof, participant, uses = core.measure(
                "selective", SCOPE, natives, side, pin, binary, windows, verify_words=True,
                member_index=MEMBER, open_selective=open_selective)
            if participant is None:
                raise ValueError("declined the frozen last original member")
            witness = core.missing_block(participant, uses)
        del participant
        ready = []
        for order in core.ORDERS:
            result = {}
            for label in order:
                with core.one_member(SCOPE.path, chunk), ingress(), paired_decoded_hashes(hasher):
                    timing, seen, selected, _ = core.measure(
                        label, SCOPE, natives, side, pin, binary, windows,
                        member_index=MEMBER, open_selective=open_selective)
                del selected
                if seen != proof or timing["actual_reader"] != label:
                    raise ValueError("true last-member signed acquisition changed or fell back")
                result[label] = timing
            ready.append(result)
    refusal = core.corruption(reader, chunk, SCOPE, sidecar, pin, binary, witness, ingress,
                             open_selective=open_selective)
    result = dict(
        source=str(SCOPE.path), manifest_sha256=SCOPE.manifest, chunk=chunk.model_dump(mode="json"),
        residence=residence, io_policy=io, sidecar_sha256=pin, sidecar_bytes=len(sidecar),
        exception_sha256=metadata["exact_decoded_exception_sha256"], exception_bytes=len(retained),
        block=blocks[owner], tables=dict(owner=owner, consumers=dependents, seed=seed),
        forced_consumer=forced, scheduled_exact=parity, forced_all_full=all_full, evidence=proof,
        stock_authority=authority, sidecar_creation=map_clock, verification_through_map=build_and_verify,
        build=build, orders=core.ORDERS, schedule_scope="fresh last-member-only per original recipe",
        ready=ready, corruption=refusal, receiver_sha256=INSTALLED_SHA, short_sha256=EIGHT_MS_SHA,
    )
    with (root / "result.json").open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    run(parser.parse_args().out)
