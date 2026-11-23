"""Compare an authenticated DS30 member with a new seekable view in tmpfs."""

import argparse
import json
import resource
from collections import Counter
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from types import SimpleNamespace

import numpy as np

from . import full_short_cold as signed
from . import seekable_member as seek
from . import sparse_cold_input as frozen
from .mixed_aperture_receiver import MixedApertureDetector, NativePath, StereoSchedule, strongest
from .zstd_physical_structure import view_for
from .zstd_structure_trial import MEMBER_SHA, PHYSICAL, PHYSICAL_SHA

ORDERS = (("original", "seekable"), ("seekable", "original"))
SOURCE_FILES = ("manifest.json", "windows-000000.jsonl", "iq-000000.ci16.zst")
RING_UNCOMPRESSED = "sha256:758d22d502ba1e0688f3dfb2528549eadd187f33021598179e9fab308e9a89b6"


def clock():
    return perf_counter_ns(), process_time_ns(), resource.getrusage(resource.RUSAGE_SELF).ru_inblock


def elapsed(start):
    return dict(zip(("wall_ns", "cpu_ns", "input_blocks"),
                    (end - begin for begin, end in zip(start, clock(), strict=True)), strict=True))


def stage(output, output_receipt):
    from tools.pipeline_eval.qualification.cache_residency import load_query

    entry = json.loads(frozen.verified(PHYSICAL, PHYSICAL_SHA))["entry"]
    original = Path(entry["path"])
    frozen.verified(frozen.CACHE_LIBRARY, frozen.CACHE_SHA)
    query = load_query(frozen.CACHE_LIBRARY)
    state, view = view_for(original, SOURCE_FILES, query)
    state["source"] = str(original)
    state["authority"] = PHYSICAL_SHA
    if view is None:
        signed.freeze(output_receipt, state)
        raise ValueError("The exact previously staged DS30 member is no longer fully resident")
    local = output / original.name
    local.mkdir()
    start = clock()
    manifest_bytes = view.read(original / SOURCE_FILES[0], seek.MAX_METADATA)
    seek.check(manifest_bytes, entry["manifest_digest"])
    manifest = seek.ShortWindowManifestV2.model_validate_json(manifest_bytes)
    chunk = manifest.chunks[0]
    if (chunk.index_relative_path, chunk.payload_relative_path, chunk.compressed_sha256,
            chunk.uncompressed_sha256) != (
        SOURCE_FILES[1], SOURCE_FILES[2], MEMBER_SHA, RING_UNCOMPRESSED,
    ):
        raise ValueError("Staged manifest does not identify the frozen dense member")
    index = view.read(original / chunk.index_relative_path, chunk.index_bytes)
    payload = view.read(original / chunk.payload_relative_path, chunk.compressed_bytes)
    seek.check(index, chunk.index_sha256)
    seek.check(payload, chunk.compressed_sha256)
    for name, data in zip(SOURCE_FILES, (manifest_bytes, index, payload), strict=True):
        seek.write(local / name, data)
    state["timing"] = elapsed(start)
    state["no_blocking_payload_fallback"] = True
    signed.freeze(output_receipt, state)
    return dict(entry, path=str(local))


def mixed_call(engine, window):
    from tools.pipeline_eval.qualification.blind_compact_run import _probe, factor_candidate

    target, acquisition = window.target, window.acquisition
    center = target["rf_center_hz"] - target["lnb_lo_hz"] - acquisition["actual_if_center_hz"]
    selected = []
    for lane in (0, 1):
        measured, _ = engine.run(window.samples, lane, center)
        candidates = [factor_candidate(rank, epoch, status="complete", offset=offset, cfo=hz,
                        exact=exact, control=roll, margin=exact-roll)
                      for rank, epoch, offset, hz, exact, roll in measured]
        factor = strongest(candidates)
        selected.append(_probe(window, lane, [] if factor is None else [factor]))
    return selected


def window_from(row, target, samples):
    return SimpleNamespace(sequence=row.sequence, acquisition=row.acquisition, target=target,
                           sample_rate_hz=10_000_000, receiver_ids=(0, 1), samples=samples)


def test_source_window(window):
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import valid_window_support

    if (window.target["edge"] != "lower" or not valid_window_support(
        window.acquisition, 10_000_000, (seek.SAMPLES, 2, 2), (0, 1), FastScanPolicyV2(),
    )):
        raise ValueError("Pinned trial expects admitted lower-edge visits")


def consume(mode, receiver, source, sidecar, pin, short_binary, spec):
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import FastSegmentSource
    from tools.pipeline_eval.qualification.blind_compact_run import detector
    from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes

    binary = frozen.PAYLOAD / "receiver.so"
    pilot = frozen.RELEASE / "assets/lower.f32"
    ingress = frozen.frozen_function(spec, "receiver_ingress.py", "compressed_input_buffer")
    hasher = frozen.PAYLOAD / "paired-sha256.so"
    probes, modes = [], Counter()
    native_cpu = native_wall = 0
    start = clock()
    with ExitStack() as stack:
        if receiver == "named":
            callback = stack.enter_context(
                detector("cancellation", "lower", binary=binary, pilot=pilot),
            )
        elif mode == "original":
            engine = MixedApertureDetector(short_binary, signed.SHORT_SHA, full_coverage=True)
            callback = stack.enter_context(
                engine.detector("cancellation", "lower", binary=binary, pilot=pilot),
            )
        else:
            schedule = StereoSchedule(full_coverage=True)
            pilot_bytes = frozen.verified(pilot, signed.PILOT_SHA["lower"])
            asset = np.frombuffer(pilot_bytes, dtype="<f4")
            engines = {}
            for name, library in (("full", binary), ("short_primary", short_binary)):
                engines[name] = NativePath(library, asset, name)
                stack.callback(engines[name].close)

        if mode == "original":
            stack.enter_context(ingress())
            stack.enter_context(paired_decoded_hashes(hasher))
            raw_source = FastSegmentSource(source, stop_sequence=frozen.WINDOWS_PER_MEMBER)
            chunk = raw_source.reader.manifest.chunks[0]
            for verified in raw_source.windows():
                window = window_from(verified, verified.target, verified.samples)
                test_source_window(window)
                work = clock()
                probes.extend(callback(window))
                used = elapsed(work)
                native_cpu += used["cpu_ns"]
                native_wall += used["wall_ns"]
            if receiver == "mixed":
                modes.update(engine.visits)
            else:
                modes["full"] = len(probes) // 2
            header_size = (Path(source["path"]) / "manifest.json").stat().st_size
            counts = dict(payload_bytes=chunk.compressed_bytes,
                          decoded_bytes=chunk.uncompressed_bytes,
                          metadata_bytes=chunk.index_bytes + header_size, frames=1,
                          full_checks=chunk.window_count, original_member_checked=True)
        else:
            reader = stack.enter_context(seek.open_member(sidecar, pin))
            targets = {row["target_id"]: row for row in reader.manifest.configuration["targets"]}
            whole = sha256() if receiver == "named" else None
            for row in reader.rows:
                target = targets[row.target_id]
                aperture = "full"
                if receiver == "mixed":
                    _, aperture = schedule.visit("lower", target, row.acquisition)
                modes[aperture] += 1
                raw = reader.read(row.sequence, full=aperture == "full")
                if whole is not None:
                    whole.update(raw)
                values = np.frombuffer(raw, dtype="<i2").reshape(-1, 2, 2)
                window = window_from(row, target, values)
                test_source_window(window)
                work = clock()
                if receiver == "mixed":
                    probes.extend(mixed_call(engines[aperture], window))
                else:
                    probes.extend(callback(window))
                used = elapsed(work)
                native_cpu += used["cpu_ns"]
                native_wall += used["wall_ns"]
            if whole is not None and "sha256:" + whole.hexdigest() != RING_UNCOMPRESSED:
                raise ValueError("The exact named replay must verify the whole decoded member")
            counts = dict(reader.counts(), original_member_checked=whole is not None)
    spent = elapsed(start)
    return dict(mode=mode, receiver=receiver, timing=spent, native_callback_cpu_ns=native_cpu,
                native_callback_wall_ns=native_wall, visits=dict(modes), reads=counts,
                selected=sum(len(row["candidates"]) for row in probes),
                probes_sha256=canonical_digest(probes), probes=len(probes))


def arbitrary(source, sidecar, pin, spec):
    from leo.storage.short_window import ShortWindowReader
    from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes

    ingress = frozen.frozen_function(spec, "receiver_ingress.py", "compressed_input_buffer")
    hasher = frozen.PAYLOAD / "paired-sha256.so"
    visit = 37
    begin = clock()
    with ingress(), paired_decoded_hashes(hasher):
        source_reader = ShortWindowReader(Path(source["path"]))
        window, = source_reader.windows(start_sequence=visit, stop_sequence=visit + 1)
        raw = memoryview(window.samples).cast("B")
    original = elapsed(begin)
    rows = {}
    for full in (True, False):
        start = clock()
        with seek.open_member(sidecar, pin) as reader:
            replay = reader.read(visit, full=full)
            reads = reader.counts()
        timing = elapsed(start)
        if raw[:len(replay)] != replay:
            raise ValueError("Arbitrary seek does not reproduce the original window bytes")
        aperture = "full" if full else "short"
        rows[aperture] = dict(timing=timing, reads=reads, sha256=seek.digest(replay))
    return dict(visit=visit, original=original, seek=rows)


def trial(output, short_binary):
    import zstandard

    from leo.storage.short_window import ShortWindowReader
    from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes

    machine = signed.check_machine()
    if output.parent.resolve() != Path("/dev/shm"):
        raise ValueError("Use only a fresh tmpfs output directory")
    spec = json.loads(frozen.verified(frozen.PAYLOAD / "spec.json", frozen.SPEC_SHA))
    frozen.verified(frozen.PAYLOAD / "receiver.so", spec["detector_sha256"])
    frozen.verified(frozen.PAYLOAD / "paired-sha256.so", spec["paired_sha256"]["sha256"])
    frozen.verified(frozen.RELEASE / "assets/lower.f32", signed.PILOT_SHA["lower"])
    frozen.verified(short_binary, signed.SHORT_SHA)
    output.mkdir(mode=0o700)
    source = stage(output, output / "staged.json")
    sidecar = output / "seekable"
    ingress = frozen.frozen_function(spec, "receiver_ingress.py", "compressed_input_buffer")
    costs = Counter()
    begin = clock()
    with ingress(), paired_decoded_hashes(frozen.PAYLOAD / "paired-sha256.so"):
        source_reader = ShortWindowReader(Path(source["path"]))
        pin = seek.create(source_reader, 0, sidecar, costs=costs)
    conversion = elapsed(begin) | dict(costs)
    begin = clock()
    with seek.open_member(sidecar, pin) as reader:
        original_seal = reader.verify_all()
        verified = reader.counts()
        chunk = reader.chunk.model_dump(mode="json")
    readback = elapsed(begin) | verified
    sizes = {path.name: path.stat().st_size for path in sidecar.iterdir()}
    results = {}
    for receiver in ("mixed", "named"):
        rows = [consume(mode, receiver, source, sidecar, pin, short_binary, spec)
                for arm in ORDERS for mode in arm]
        if len({(r["probes_sha256"], r["probes"], r["selected"], tuple(sorted(r["visits"].items())))
                for r in rows}) != 1:
            raise ValueError("Seekable and original native receiver witnesses differ")
        results[receiver] = rows
    seek_test = arbitrary(source, sidecar, pin, spec)
    signed.freeze(output / "result.json", dict(
        machine=machine, source=source, original_member=chunk, sidecar_pin=pin, storage_bytes=sizes,
        attachment_name="private future format, outside original DS30 benchmarking",
        conversion=conversion, readback=readback, full_decoded_original_seal=original_seal,
        arbitrary=seek_test, receivers=results, orders=ORDERS,
        zstd=list(zstandard.ZSTD_VERSION), short_binary_sha256=signed.SHORT_SHA,
        runtime_spec_sha256=frozen.SPEC_SHA, code={p.name: sha256(p.read_bytes()).hexdigest()
              for p in (Path(__file__), Path(seek.__file__))},
    ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("short_binary", type=Path)
    args = parser.parse_args()
    trial(args.output, args.short_binary)
