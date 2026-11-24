"""Prove the direct packed producer's authority boundary on one owned North member."""

import argparse
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess

from . import sparse_cold_input as release
from .eight_ms_primary import write
from .scout_readout_trial import check_machine


HERE = Path(__file__).resolve().parent
SOURCE = Path("/tmp/leo-regional-qZJKBw4W/public/0abe7b4514be674d9f5388e3")
MANIFEST = "0205ca2d10c1282f6c782c93a32d2bff1ae8a7b39ff959c93b4ca3613f0f07eb"
PROTOCOL = HERE / "north-owned-capture-protocol.md"
SCHEMAS = {"ordinary": "private-owned-capture-zstandard-v1", "packed": "private-owned-capture-packed-ci16-v1"}


def commitment(kind, archive_pin, record, count):
    """Bind only what this writer itself produced from the owned raw words."""
    if kind not in SCHEMAS or not count or not record["bytes"]:
        raise ValueError("Incomplete owned capture authority")
    return dict(schema=SCHEMAS[kind], archive_root_sha256=archive_pin,
                indexes_sha256=record["index_sha256"], logical_decoded_sha256=record["decoded_sha256"],
                emitted_objects=record["bytes"], windows=count)


def load_commitment(path, expected, kind):
    if kind not in SCHEMAS:
        raise ValueError("Unknown producer custody schema")
    value = json.loads(release.verified(path, expected))
    if value["schema"] != SCHEMAS[kind] or value["windows"] <= 0:
        raise ValueError("Captured authority does not identify the requested representation")
    return value


def resident(path, files):
    from tools.pipeline_eval.qualification.cache_residency import cache_snapshot, load_query
    from north_held_anchor_pair import require_resident, tmpfs

    tmpfs(path)
    release.verified(release.CACHE_LIBRARY, release.CACHE_SHA)
    observed = cache_snapshot([(path, key, size) for key, size in files.items()],
                              os.sysconf("SC_PAGE_SIZE"), load_query(release.CACHE_LIBRARY))
    require_resident(observed)
    return observed


def run(root):
    from ci16_packing import Packing, SOURCE as PACKING_SOURCE
    from eight_first_use import bound_capture
    from leo.contracts.digests import canonical_digest, canonical_json_bytes
    from leo.storage.fast_scan import FastScanStore, FastSegmentSource
    from leo.storage.short_window import ShortWindowReader
    from leo.storage.writer import _fsync_directory
    from packed_combined_input import admit
    from seekable_eight_raw import BUILD, PREFIX, clocks, elapsed, original_member_only
    import seekable_member as seek
    from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes

    host = check_machine()
    if root.parent.resolve() != Path("/dev/shm") or SOURCE.resolve(strict=True) != SOURCE:
        raise ValueError("Only the existing local North source and a fresh tmpfs output are admitted")
    source = ShortWindowReader(SOURCE)
    if source.manifest_sha256 != "sha256:" + MANIFEST or source.manifest.window_count != 1200:
        raise ValueError("The committed North source changed")
    original = source.manifest.chunks[0].model_dump(mode="json")
    if len(source.manifest.chunks) != 19 or original["window_count"] != 64:
        raise ValueError("The original complete first member changed")
    files = {"manifest.json": (SOURCE / "manifest.json").stat().st_size,
             original["index_relative_path"]: original["index_bytes"],
             original["payload_relative_path"]: original["compressed_bytes"]}
    before = resident(SOURCE, files)
    spec = json.loads(release.verified(release.PAYLOAD / "spec.json", release.SPEC_SHA))
    hashlib_library = release.PAYLOAD / "paired-sha256.so"
    release.verified(hashlib_library, spec["paired_sha256"]["sha256"])
    ingress = release.frozen_function(spec, "receiver_ingress.py", "compressed_input_buffer")
    root.mkdir()
    codec_path = root / "packing.so"
    setup = clocks()
    subprocess.run([*BUILD, str(PACKING_SOURCE), "-o", str(codec_path)], check=True)
    codec = Packing(codec_path)
    capture, writer_pin = bound_capture()
    setup_clock = elapsed(setup)

    began = clocks()
    opened = Counter()
    with (original_member_only(dict(path=str(SOURCE)), original, opened),
          ingress(), paired_decoded_hashes(hashlib_library)):
        windows = tuple(source.windows(stop_sequence=64))
    owned = elapsed(began)
    if (len(windows) != 64 or opened != {name: size for name, size in files.items() if name != "manifest.json"}
            or any(window.samples.flags.writeable or window.samples.shape != (200_000, 2, 2) for window in windows)):
        raise ValueError("The fixture must own one complete immutable signed first member")
    expected = canonical_digest([window.index.model_dump(mode="json") for window in windows])
    results = {}
    ordinary_source = ordinary_chunk = None
    for kind in ("ordinary", "packed"):
        output = root / kind
        began = clocks()
        captured, pin, record = capture(output, "ordinary" if kind == "ordinary" else "packed-ci16",
                                       source.manifest, windows, codec=codec if kind == "packed" else None,
                                       prefix_samples=PREFIX)
        document = commitment(kind, pin, record, len(windows))
        sealed = canonical_json_bytes(document)
        seek.write(output / "capture-authority.json", sealed)
        _fsync_directory(output)
        capture_cpu = elapsed(began)
        first = clocks()
        binding = load_commitment(output / "capture-authority.json", seek.digest(sealed), kind)
        if binding["emitted_objects"] != {p.name: p.stat().st_size for p in captured.iterdir()}:
            raise ValueError("The emitted representation differs from its own capture authority")
        if kind == "ordinary":
            _, _, inventory = FastScanStore(output).inventory(captured, verify_windows=False)
            ordinary_source = FastSegmentSource(inventory["segments"][0])
            ordinary_chunk, = ordinary_source.reader.manifest.chunks
            with ingress(), paired_decoded_hashes(hashlib_library):
                rows = [window.index.model_dump(mode="json") for window in ordinary_source.reader.windows()]
            readback_digest = ordinary_chunk.uncompressed_sha256
            scope = dict(windows=len(rows), encoded_bytes=ordinary_chunk.compressed_bytes,
                         decoded_bytes=ordinary_chunk.uncompressed_bytes, native_inventory=True)
        else:
            with seek.open_member(captured, binding["archive_root_sha256"], codec=codec, prefix_samples=PREFIX) as packed:
                packed.verify_encoded()
                readback_digest = packed.verify_all()
                rows = [row.model_dump(mode="json") for row in packed.rows]
                scope = dict(packed.counts(), encoded_blocks=packed.verified_encoded_frames,
                             own_manifest_sha256=packed.manifest_sha256,
                             own_encoded_prefix_sha256=packed.chunk.compressed_sha256)
            # The exact first readback clock ends before checking consumer compatibility.
        first_use = elapsed(began)
        readback = elapsed(first)
        if (canonical_digest(rows) != expected or binding["indexes_sha256"] != original["index_sha256"]
                or readback_digest != original["uncompressed_sha256"]
                or binding["logical_decoded_sha256"] != readback_digest):
            raise ValueError("The independent captures disagreed on North logical words or chronology")
        if kind == "packed":
            try:
                FastScanStore(output).inventory(captured, verify_windows=False)
            except (ValueError, OSError) as error:
                scope["ordinary_inventory_declined"] = str(error)
            with seek.open_member(captured, pin, codec=codec, prefix_samples=PREFIX) as packed:
                try:
                    admit(packed, ordinary_source, ordinary_chunk)
                except ValueError as error:
                    scope["packed_map_to_independent_ordinary_declined"] = str(error)
            if ("ordinary_inventory_declined" not in scope
                    or "packed_map_to_independent_ordinary_declined" not in scope):
                raise ValueError("The existing input authority boundary changed")
        results[kind] = dict(custody=binding, custody_sha256=seek.digest(sealed), capture=capture_cpu,
                             first_full_readback=readback, writer_through_readback=first_use,
                             scope=scope, writer=record)
    write(root / "result.json", dict(host=host, original=original, original_staged_path=str(SOURCE),
         original_manifest_sha256=source.manifest_sha256, original_members=19, original_visits=1200,
         source_reads=dict(opened), source_residency_before=before, source_residency_after=resident(SOURCE, files),
         original_owned_hydration=owned, shared_setup=setup_clock, original_index_rows_sha256=expected,
         codec=codec.programme(), writer_sha256=writer_pin, paired=results, full_publication_run=False,
         protocol_sha256=sha256(PROTOCOL.read_bytes()).hexdigest(), source_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
