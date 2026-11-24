"""Verify no-plan replay custody on the resident original first DS30-0169 member."""

import argparse
from contextlib import ExitStack, closing
import json
import os
from pathlib import Path
import subprocess
from unittest.mock import patch

import numpy as np

from leo.contracts.digests import canonical_digest, sha256_digest
from leo.storage.errors import BundleCorruptionError
from leo.storage.fast_scan import FastSegmentSource
from leo.storage.short_window import ShortWindowReader
from tools.pipeline_eval.qualification.cache_residency import load_query
from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes

from . import legacy_block_input as port, legacy_block_multi as multi, legacy_block_seek as core
from . import legacy_first_map_input as first, legacy_fused_map as fused, sparse_cold_input as release
from .full_short_run import EIGHT_MS_SHA
from .legacy_fused_map_trial import analyze
from .mixed_aperture_receiver import INSTALLED_SHA, PILOT_SHA, NativePath
from .receiver_ceiling_0169 import INVENTORY, INVENTORY_PIN, first_member
from .seekable_eight_raw import HELD, HELD_NAMED, HELD_SHA, SHORT
from .zstd_physical_structure import view_for

SCHEMA = "private-algo08-legacy-map-single-original-member-v1"


def admit():
    scope = json.loads(release.verified(HELD, HELD_SHA))
    enrollment = json.loads(release.verified(INVENTORY, INVENTORY_PIN))
    named = json.loads(release.verified(HELD.parent / "1-stock.json", HELD_NAMED["1-stock.json"]))
    local = Path(scope["entry"]["path"])
    chunk = scope["member"]
    if (scope["entry"] != dict(enrollment["segments"][0], path=str(local))
            or canonical_digest(enrollment) != "sha256:" + INVENTORY_PIN
            or not local.is_relative_to("/dev/shm") or local.resolve(strict=True) != local):
        raise ValueError("The bounded resident copy must match the previously signed inventory")
    files = {"manifest.json": 6812, chunk["index_relative_path"]: chunk["index_bytes"],
             chunk["payload_relative_path"]: chunk["compressed_bytes"]}
    if any((local / name).resolve(strict=True) != local / name or (local / name).stat().st_size != size
           for name, size in files.items()):
        raise ValueError("The staged declared member file extents changed")
    release.verified(release.CACHE_LIBRARY, release.CACHE_SHA)
    cache, view = view_for(local, files, load_query(release.CACHE_LIBRARY))
    if view is None or cache["filesystem"] != "tmpfs":
        raise ValueError("The exact original member is unavailable in resident tmpfs")
    source = FastSegmentSource(scope["entry"], start_sequence=0, stop_sequence=64)
    original = first_member(source.reader.manifest)
    expected = named["packet"]["source"]["raw_recording_authority_digest"]
    if (original.model_dump(mode="json") != chunk or len(named["iq"]) != 64
            or port.raw_authority("sha256:" + INVENTORY_PIN, named["iq"]) != expected):
        raise ValueError("The original member differs from the authenticated ordinary reference")
    return source, original, named["iq"], expected, cache


def compare_produced(source, chunk, ordinary, history, replay, hasher, natives):
    hashes, selected = [], {}
    began = core.clock()
    words = first.member_windows(source, chunk, port.member_identity(source.reader, chunk), port.map_name(0),
                                 history, hasher, replay, hashes)

    def visits():
        selected["count"] = 0
        while True:
            try:
                row = next(words)
            except StopIteration as done:
                selected["map"], selected["data"] = done.value
                return
            original = ordinary[selected["count"]]
            if (row.sequence != original.index.sequence or row.iq_sha256 != original.index.iq_sha256
                    or not np.array_equal(row.samples, original.samples)):
                raise BundleCorruptionError("Fresh producer changed an original index or CI16 word")
            selected["count"] += 1
            yield original.index, row.samples

    with closing(words):
        factors, _ = analyze(source.reader, chunk, visits(), natives)
    return selected["map"], selected["data"], hashes, factors, core.elapsed(began)


def compare_replay(reader, chunk, raw, row, replay, ordinary):
    if raw is None:
        return None
    codec = multi if row["map_kind"] == "exception" else core
    began = core.clock()
    with closing(codec.Selective(reader, chunk, raw, row["map_sha256"], replay)) as select:
        for full in (True, False):
            for index, w in zip(select.rows, ordinary, strict=True):
                wanted = w.samples if full else w.samples[:80_000]
                if index != w.index or not np.array_equal(select.read(index, full=full), wanted):
                    raise BundleCorruptionError("Independent fresh map replay changed a stock sample span")
        return dict(full=len(ordinary), prefix=len(ordinary), requested_decode=select.counts.report(),
                    clock=core.elapsed(began))


def run(root):
    setting = subprocess.check_output(("ionice", "-p", str(os.getpid())), text=True).strip()
    if (root.parent.resolve() != Path("/dev/shm") or os.sched_getaffinity(0) != {2}
            or os.getpriority(os.PRIO_PROCESS, 0) != 15 or setting != "best-effort: prio 7"
            or not Path(ShortWindowReader.windows.__code__.co_filename).is_relative_to(release.RELEASE)):
        raise ValueError("Use the shared CPU2 Gauss slot and exact installed stock storage")
    source, chunk, expected, raw_authority, residence = admit()
    reader = source.reader
    root.mkdir(mode=0o700)
    lib, seek = root / "history.so", root / "replay.so"
    build = dict(history=fused.build(lib), replay=core.build(seek))
    history, replay = fused.load(lib), core.load(seek)
    spec = json.loads(release.verified(release.PAYLOAD / "spec.json", release.SPEC_SHA))
    ingress = release.frozen_function(spec, "receiver_ingress.py", "compressed_input_buffer")
    hasher, full = release.PAYLOAD / "paired-sha256.so", release.PAYLOAD / "receiver.so"
    release.verified(hasher, spec["paired_sha256"]["sha256"])
    release.verified(full, INSTALLED_SHA)
    release.verified(SHORT, EIGHT_MS_SHA)
    pilot = np.frombuffer(release.verified(release.RELEASE / "assets/lower.f32", PILOT_SHA["lower"]), dtype="<f4")
    with ExitStack() as stack:
        natives = {mode: NativePath(path, pilot, mode) for mode, path in (("full", full), ("short_primary", SHORT))}
        for engine in natives.values():
            stack.callback(engine.close)
        with core.one_member(reader.path, chunk), ingress(), paired_decoded_hashes(hasher):
            began = core.clock()
            stock = tuple(port.stock_scope(reader, chunk))
            stock_time = core.elapsed(began)
            if [window.index.iq_sha256 for window in stock] != expected:
                raise BundleCorruptionError("Installed stock changed the frozen original first-member hashes")
            baseline, _ = analyze(reader, chunk, ((window.index, window.samples) for window in stock), natives)
            row, raw, hashes, factors, producer_time = compare_produced(
                source, chunk, stock, history, replay, hasher, natives)
            if (hashes != expected or port.raw_authority("sha256:" + INVENTORY_PIN, hashes) != raw_authority
                    or baseline != factors or factors["lanes"] != 102
                    or factors["visits"].get("invalid") != 13):
                raise BundleCorruptionError("Fresh member changed the existing original authority or native evidence")
            confirmed = compare_replay(reader, chunk, raw, row, replay, stock)

    opened = []

    def forbidden(_reader, name, *_options):
        opened.append(name)
        raise ValueError("A following member reached its opener despite the first-member gate")

    following = reader.manifest.chunks[1]
    with patch.object(ShortWindowReader, "_member", forbidden):
        try:
            next(first.member_windows(source, following, {}, "forbidden", history, hasher, replay, []))
        except BundleCorruptionError as error:
            boundary = str(error)
        else:
            raise ValueError("The enrolled prefix accepted a following member")
    if opened:
        raise ValueError("Member exclusion did not precede storage access")
    plan = dict(schema=SCHEMA, original_inventory_sha256="sha256:" + INVENTORY_PIN,
                original_manifest_sha256=reader.manifest_sha256, scope_sha256="sha256:" + HELD_SHA,
                raw_authority=raw_authority, windows=64, members=[{key: row[key] for key in (
                    *port.member_identity(reader, chunk), "map", "map_kind", "map_sha256")}])
    bundle = root / "fresh"
    pin = first.publish_bundle(bundle, plan, {} if raw is None else {row["map"]: raw})
    if sha256_digest((bundle / "custody.json").read_bytes()) != pin or (
        raw is not None and sha256_digest((bundle / row["map"]).read_bytes()) != row["map_sha256"]
    ):
        raise ValueError("Durable freshly pinned member bundle changed")
    record = dict(case="DS30-0169", scope="only the signed original first member", source=str(reader.path),
                  resident=residence, prior_maps_read=0, plan=plan, pin=pin, evidence=factors,
                  producer=row, replay=confirmed, stock_verification=stock_time,
                  producer_with_native_and_word_comparison=producer_time, native_build=build,
                  following_guard=boundary, later_member_opens=opened)
    with (root / "result.json").open("x") as stream:
        json.dump(record, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    run(parser.parse_args().out)
