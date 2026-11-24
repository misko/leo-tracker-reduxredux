"""Price the native signed CI16 operations on two existing resident members."""

import argparse
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
from statistics import median
import subprocess
from tempfile import TemporaryDirectory
from time import process_time_ns
from types import SimpleNamespace
from unittest.mock import patch

from .ci16_packing import Packing, SOURCE as LEGACY
from .direct_packed_capture import Capture, PREFIX, write_capture
from .north_direct_multichunk import MANIFEST, SOURCE, checked_lease, require_tmpfs
from .seekable_eight_raw import clocks, elapsed
from .seekable_member import digest


BUILD = ("cc", "-std=c11", "-O3", "-fPIC", "-shared", "-mssse3", "-Wall", "-Wextra", "-Werror")
DENSE = Path("/dev/shm/leo-seekable-member-0008-case1/fast8-auto-20261113-075937-d9ab96ee-1-lower-segment-00000000")
DENSE_MANIFEST = "5ffe3ed98feb37f7f7ada44dbf34d2af9d3fcadce567fd3cdbb7e31965a02759"
SOURCES = {"North": (SOURCE, MANIFEST), "DS30-0008": (DENSE, DENSE_MANIFEST)}
GROUPED = LEGACY.with_name("ci16_grouped.c")
OPERATIONS = ("ci16_occupied_bits", "ci16_pack", "ci16_unpack")
ORDERS = {"North": ("legacy", "grouped", "grouped", "legacy"),
          "DS30-0008": ("grouped", "legacy", "legacy", "grouped")}


class GroupedPacking(Packing):
    """The experimental binary can use the same wire format with distinct source provenance."""

    def programme(self):
        base = super().programme()
        return base | {"grouped_source_sha256": sha256(GROUPED.read_bytes()).hexdigest()}


def inputs(case):
    from leo.storage.short_window import ShortWindowReader
    from tools.pipeline_eval.qualification.cache_residency import cache_snapshot, load_query

    from .sparse_cold_input import CACHE_LIBRARY, CACHE_SHA, verified

    path, manifest = SOURCES[case]
    require_tmpfs(path)
    if path.resolve(strict=True) != path:
        raise ValueError("Expected a literal original resident input path")
    source = ShortWindowReader(path)
    chunk = source.manifest.chunks[0]
    if source.manifest_sha256 != "sha256:"+manifest or (chunk.first_sequence, chunk.window_count) != (0, 64):
        raise ValueError("The original staged member or its chronological scope changed")
    members = {chunk.index_relative_path: (chunk.index_bytes, chunk.index_sha256),
               chunk.payload_relative_path: (chunk.compressed_bytes, chunk.compressed_sha256)}
    files = [(path, name, amount) for name, (amount, _) in members.items()]
    verified(CACHE_LIBRARY, CACHE_SHA)
    state = cache_snapshot(files, os.sysconf("SC_PAGE_SIZE"), load_query(CACHE_LIBRARY))
    if state["unavailable"] or state["observed_members"] != 2 or state["cached_pages"] != state["observed_file_pages"]:
        raise ValueError("The selected first member is not fully resident")
    opened = Counter()
    original = ShortWindowReader._member

    def first_only(reader, name, size, pin):
        if reader.path != path or members.get(name) != (size, pin) or name in opened:
            raise ValueError("Read outside the one signed member")
        data = original(reader, name, size, pin)
        opened[name] += len(data)
        return data

    with patch.object(ShortWindowReader, "_member", first_only):
        owned = tuple(source.windows(stop_sequence=64))
    if len(owned) != 64 or any(w.samples.shape != (200_000, 2, 2) or w.samples.flags.writeable for w in owned):
        raise ValueError("Expected sixty-four immutable complete stereo windows")
    return source.manifest, chunk, owned, dict(path=str(path), manifest=source.manifest_sha256, resident=state,
                                              opened=dict(opened), member=chunk.model_dump(mode="json"))


def make(source, binary, isa=BUILD):
    subprocess.run([*isa, str(source), "-o", str(binary)], check=True)
    return dict(source_sha256=sha256(source.read_bytes()).hexdigest(), binary_sha256=sha256(binary.read_bytes()).hexdigest(),
                source=str(source), binary=str(binary), compiler=list(isa))


def native_profile(codec, owned):
    operations = {}

    def timer(name, function):
        total, widths = Counter(), Counter()
        operations[name] = (total, widths)

        def run(*args):
            start = process_time_ns()
            result = function(*args)
            cpu = process_time_ns()-start
            total["calls"] += 1
            total["cpu_ns"] += cpu
            if name != "ci16_occupied_bits":
                widths[str(args[2])] += cpu
            return result

        return run

    codec.blocks.clear()
    encoded = sha256()
    with patch.multiple(codec.library, **{name: timer(name, getattr(codec.library, name)) for name in OPERATIONS}):
        for window in owned:
            for part in (window.samples[:PREFIX], window.samples[PREFIX:]):
                raw = memoryview(part).cast("B")
                stored = codec.compress(raw)
                if codec.decode(stored, len(raw)) != raw:
                    raise ValueError("Codec failed to recover an original block")
                encoded.update(stored)
    return dict(operations={name: dict(counts) | {"cpu_by_width_ns": dict(widths)}
                            for name, (counts, widths) in operations.items()}, widths=codec.counts(),
                ordered_encoded_sha256="sha256:"+encoded.hexdigest())


def ceiling(root):
    legacy = root/"legacy.so"
    build = make(LEGACY, legacy)
    result = {}
    for case in SOURCES:
        _, _, owned, source = inputs(case)
        codec = Packing(legacy)
        rounds = [native_profile(codec, owned) for _ in range(3)]
        if len({row["ordered_encoded_sha256"] for row in rounds}) != 1:
            raise ValueError("Repeated codec calls changed the original wire")
        result[case] = dict(source=source, rounds=rounds,
                            native_cpu_ns={name: median(row["operations"][name]["cpu_ns"] for row in rounds)
                                           for name in OPERATIONS})
    return dict(legacy=build, cases=result)


def capture_readback(path, header, original, owned, codec):
    started = clocks()
    pin, result = write_capture(path, header, owned, (64,), codec)
    writer = elapsed(started)
    captured = clocks()
    source = Capture(path, pin, codec)
    _, _, inventory = source.inventory(path)
    segment, = inventory["segments"]
    hashes = [item.iq_sha256 for item in source.segment(segment).windows()]
    paid = elapsed(started)
    reader = elapsed(captured)
    member, = result["chunks"]
    sealed, = source.audit
    if (hashes != [item.index.iq_sha256 for item in owned] or member["index_sha256"] != original.index_sha256
            or sealed["original_decoded_sha256"] != original.uncompressed_sha256 or sealed["encoded_blocks"] != 128
            or sealed["checks"]["full_checks"] != 64 or sealed["checks"]["decoded_bytes"] != original.uncompressed_bytes):
        raise ValueError("The private first readback differs from the complete signed original")
    return dict(writer=writer, reader=reader, total=paid, readback=sealed, identity=pin, seek_sha256=member["seek_sha256"],
                bytes=sum(file.stat().st_size for file in path.rglob("*") if file.is_file()))


def synthetic_widths(codecs):
    import numpy as np

    random = np.random.default_rng(223)
    results = {}
    for width in range(1, 17):
        half = 1 << (width-1)
        block = random.integers(-half, half, (200_000, 2, 2), dtype="<i2")
        block[0, 0] = [-half, half-1]
        owned = [SimpleNamespace(samples=block)]
        runs = {name: native_profile(codec, owned) for name, codec in codecs.items()}
        if any(row["widths"] != [{"width": width, "shift": 0, "blocks": 2}] for row in runs.values()):
            raise ValueError("The synthetic benchmark missed an intended width")
        if len({row["ordered_encoded_sha256"] for row in runs.values()}) != 1:
            raise ValueError("The grouped codec changed the v1 bytes")
        results[width] = runs
    return results


def compare(root):
    paths = {name: root/(name+".so") for name in ("legacy", "grouped")}
    builds = {name: make(source, paths[name]) for name, source in (("legacy", LEGACY), ("grouped", GROUPED))}
    codecs = {"legacy": Packing(paths["legacy"]), "grouped": GroupedPacking(paths["grouped"])}
    results = {}
    for case, order in ORDERS.items():
        header, original, owned, source = inputs(case)
        profiles = [(name, native_profile(codecs[name], owned)) for name in order]
        if len({row["ordered_encoded_sha256"] for _, row in profiles}) != 1:
            raise ValueError("Matched native profiles disagree on the ordered encoded blocks")
        order_to_capture = tuple(dict.fromkeys(order))
        with TemporaryDirectory(dir=root, prefix=case+"-") as temporary:
            verified = {name: capture_readback(Path(temporary)/name, header, original, owned, codecs[name])
                        for name in order_to_capture}
        if len({row["seek_sha256"] for row in verified.values()}) != 1:
            raise ValueError("The emitted members differ on exact bytes or metadata")
        results[case] = dict(source=source, native_rounds=profiles, first_use=verified, first_use_order=order_to_capture)
    return dict(builds=builds, cases=results, synthetic_widths=synthetic_widths(codecs))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    cli.add_argument("--compare", action="store_true")
    args = cli.parse_args()
    checked_lease()
    priority = subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True)
    if (args.root.parent.resolve() != Path("/dev/shm") or os.sched_getaffinity(0) != {2}
            or os.getpriority(os.PRIO_PROCESS, 0) < 15 or "prio 7" not in priority):
        raise ValueError("Use one dedicated Gauss core and a fresh tmpfs root")
    args.root.mkdir()
    data = compare(args.root) if args.compare else ceiling(args.root)
    with (args.root/("compare.json" if args.compare else "ceiling.json")).open("x") as stream:
        json.dump(data, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
