"""Build and consume optional visit maps on an unchanged signed recording."""

import json
from collections import Counter
from contextlib import ExitStack, closing, contextmanager
from copy import copy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from leo.contracts.digests import canonical_digest, canonical_json_bytes, sha256_digest
from leo.storage.errors import BundleCorruptionError
from leo.storage.short_window import ShortWindowReader

from . import legacy_block_seek as legacy
from .seekable_member_trial import clock, elapsed

SCHEMA = "private-algo08-legacy-map-custody-v1"
MAX_CUSTODY = 256_000


def checked_file(path, pin, limit):
    if path.resolve(strict=True) != path or path.stat().st_dev != Path("/dev/shm").stat().st_dev:
        raise ValueError("The map file must be a direct tmpfs path")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit or sha256_digest(data) != pin:
        raise BundleCorruptionError("The detached map file differs from its external pin")
    return data


def stock_scope(reader, chunk):
    return reader.windows(
        start_sequence=chunk.first_sequence, stop_sequence=chunk.first_sequence + chunk.window_count
    )


def prepare_member(reader, chunk, codec=legacy):
    """Release every ordinary hash and build metadata from its very same input buffer."""
    start = clock()
    snapshots, hashes, prefixes, costs = [], [], [], Counter()
    blocks, reason = None, None
    with (
        codec.one_member(reader.path, chunk, snapshots=snapshots),
        closing(stock_scope(reader, chunk)) as windows,
    ):
        for sequence, window in enumerate(windows, chunk.first_sequence):
            if window.index.sequence != sequence:
                raise BundleCorruptionError("Ordinary preparation changed signed visit order")
            if not hashes:
                census_start = clock()
                if len(snapshots) != 1:
                    raise BundleCorruptionError("Expected one authenticated encoded snapshot")
                try:
                    blocks = codec.block_map(snapshots[0], chunk.uncompressed_bytes)
                except codec.UnsupportedLayout as error:
                    reason = str(error)
                costs.update(elapsed(census_start))
            hashes.append(window.index.iq_sha256)
            if blocks is not None:
                prefix_start = clock()
                raw = memoryview(window.samples.reshape(-1)).cast("B")
                prefixes.append(sha256_digest(raw[: codec.PREFIX_BYTES]))
                costs.update(elapsed(prefix_start))
    if len(hashes) != chunk.window_count or len(snapshots) != 1:
        raise BundleCorruptionError(
            "Ordinary preparation did not finish the signed complete member"
        )
    map_start = clock()
    data = (
        None
        if blocks is None
        else canonical_json_bytes(
            dict(
                schema=codec.SCHEMA,
                **codec.identity(reader, chunk),
                blocks=blocks,
                prefixes=prefixes,
            )
        )
    )
    costs.update(elapsed(map_start))
    if data is not None and len(data) > codec.MAX_MAP:
        raise ValueError("Detached member map exceeds its codec bound")
    return (
        data,
        hashes,
        dict(
            full=elapsed(start),
            incremental=dict(costs),
            unsupported=reason,
            indexed_blocks=0 if blocks is None else len(blocks),
        ),
    )


def ordered_members(inventory):
    for entry in inventory["segments"]:
        reader = ShortWindowReader(Path(entry["path"]))
        if (
            reader.manifest_sha256 != entry["manifest_digest"]
            or reader.manifest.window_count != entry["windows"]
        ):
            raise BundleCorruptionError("Ordinary recording inventory changed")
        yield from ((reader, chunk) for chunk in reader.manifest.chunks)


def member_identity(reader, chunk):
    return dict(
        **legacy.identity(reader, chunk),
        first_sequence=chunk.first_sequence,
        windows=chunk.window_count,
        encoded=chunk.compressed_bytes,
        decoded=chunk.uncompressed_bytes,
    )


def map_name(ordinal):
    return f"member-{ordinal:06d}.json"


def all_parts(plan, session, digest, inventory):
    if (plan["schema"], plan["session"], plan["inventory"], plan["windows"]) != (
        SCHEMA,
        session,
        digest,
        inventory["window_count"],
    ):
        raise BundleCorruptionError("Map custody does not bind the original ordinary inventory")
    parts = {}
    for ordinal, ((reader, chunk), row) in enumerate(
        zip(ordered_members(inventory), plan["members"], strict=True)
    ):
        observed = member_identity(reader, chunk)
        if any(row[key] != value for key, value in observed.items()):
            raise BundleCorruptionError("Map custody differs from the signed ordered member")
        if row["map"] not in (None, map_name(ordinal)) or bool(row["map"]) != bool(
            row["map_sha256"]
        ):
            raise ValueError("Map custody describes an ambiguous optional member map")
        parts[reader.manifest_sha256, chunk.chunk_index] = row
    return parts


class Samples:
    """Preserve admitted sample geometry until the native schedule chooses an aperture."""

    dtype = np.dtype("<i2")
    flags = SimpleNamespace(c_contiguous=True)

    def __init__(self, member, row, counts, costs):
        self.shape = (row.sample_count, 2, 2)
        self.member, self.row = member, row
        self.counts, self.costs = counts, costs
        self.array, self.full = None, None

    def realize(self, full):
        if self.array is None:
            started = clock()
            self.array = self.member.read(self.row, full=full)
            self.costs.update(elapsed(started))
            self.full = full
            self.counts["full" if full else "prefix"] += 1
            self.counts["committed_bytes"] += self.array.nbytes
        elif self.full != full:
            raise ValueError("A signed visit must keep its declared aperture across antennas")
        return self.array


def mixed_windows(source, ordinary, parts, folder, binary, audit, codec=legacy):
    if source.start_sequence or source.stop_sequence != source.reader.manifest.window_count:
        raise ValueError("Detached maps require a complete original segment")
    seen = 0
    for chunk in source.reader.manifest.chunks:
        row = parts[source.reader.manifest_sha256, chunk.chunk_index]
        issued = 0
        if row["map"] is None:
            narrowed = copy(source)
            narrowed.start_sequence = chunk.first_sequence
            narrowed.stop_sequence = chunk.first_sequence + chunk.window_count
            with closing(ordinary(narrowed)) as stream:
                for window in stream:
                    issued += 1
                    yield window
            lane = dict(kind="ordinary", committed_bytes=chunk.uncompressed_bytes)
        else:
            start = clock()
            data = checked_file(folder / row["map"], row["map_sha256"], codec.MAX_MAP)
            table_open = elapsed(start)
            counts, costs = Counter(), Counter()
            with closing(
                codec.Selective(source.reader, chunk, data, row["map_sha256"], binary)
            ) as member:
                for index in member.rows:
                    words = Samples(member, index, counts, costs)
                    issued += 1
                    yield SimpleNamespace(
                        sequence=index.sequence,
                        iq_sha256=index.iq_sha256,
                        acquisition=index.acquisition,
                        target=source.targets[index.target_id],
                        samples=words,
                        sample_rate_hz=source.reader.manifest.sample_rate_hz,
                    )
                lane = dict(
                    kind="map",
                    committed_bytes=counts["committed_bytes"],
                    counts=dict(counts),
                    spans=member.counts.report(),
                    map_file=table_open,
                    auth=member.authentication,
                    metadata=member.metadata,
                    setup=member.setup,
                    span_decode=dict(costs),
                )
            del member, words
        if issued != chunk.window_count:
            raise BundleCorruptionError("Original member did not emit its complete visit sequence")
        seen += issued
        audit.append(dict(row, authenticated_encoded_bytes=chunk.compressed_bytes, **lane))
    if seen != source.stop_sequence:
        raise BundleCorruptionError("Mixed reader missed an original visit")


@contextmanager
def binding(boot, plan, folder, binary, audit, *, codec=legacy):
    from mixed_aperture_receiver import NativePath

    staged = boot.staged_scanner
    members = audit["members"] = []
    ports = ExitStack()

    def prepare(sources, detector=None):
        scan = staged(sources, detector=detector)
        if detector is None:
            return scan
        source, acquire, run = scan.FastSegmentSource, scan.acquire, NativePath.run
        stock, parts = source.windows, None

        def materialize(engine, words, lane, centre):
            if isinstance(words, Samples):
                if engine.maximum not in (1, 2):
                    raise ValueError("Legacy block selection requires the signed 20/8 ms detector")
                words = words.realize(engine.maximum == 2)
            return run(engine, words, lane, centre)

        def windows(item):
            return (
                stock(item)
                if parts is None
                else mixed_windows(item, stock, parts, folder, binary, members, codec)
            )

        def checked(session, digest, inventory, assets):
            nonlocal parts
            parts = all_parts(plan, session, digest, inventory)

            try:
                with patch.object(NativePath, "run", materialize):
                    result = acquire(session, digest, inventory, assets)
                observed = [(row["manifest_sha256"], row["chunk_index"]) for row in members]
                if result["source"]["raw_recording_authority_digest"] != plan[
                    "raw_authority"
                ] or observed != list(parts):
                    raise BundleCorruptionError(
                        "Original raw authority or exact member traversal changed"
                    )
                return result
            finally:
                parts = None

        # The existing bounded lookahead wraps this port, so both raw arms retain it.
        ports.enter_context(patch.object(source, "windows", windows))
        scan.acquire = checked
        return scan

    with ports, patch.object(boot, "staged_scanner", prepare):
        yield


def raw_authority(inventory, hashes):
    return canonical_digest([inventory, hashes])


def load_custody(path, digest):
    return json.loads(checked_file(path, digest, MAX_CUSTODY))
