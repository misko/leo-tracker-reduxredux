"""Bind first-use maps to the normal, complete original receiver traversal."""

from contextlib import ExitStack, closing, contextmanager, nullcontext
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.storage.errors import BundleCorruptionError
from leo.storage.short_window import ShortWindowReader
from leo.storage.writer import _fsync_directory

from . import legacy_block_input as port, legacy_block_multi as multi, legacy_fused_map as fused
from . import legacy_block_seek as legacy
from .legacy_block_seek import clock, elapsed


@contextmanager
def borrow_snapshot(reader, chunk, encoded):
    original = ShortWindowReader._member
    supplied = False

    def borrowed(source, name, size, pin):
        nonlocal supplied
        if source is reader and name == chunk.payload_relative_path:
            if (size, pin) != (len(encoded), chunk.compressed_sha256) or supplied:
                raise BundleCorruptionError("Replay requested a different original compressed member")
            supplied = True
            return encoded
        return original(source, name, size, pin)

    with patch.object(ShortWindowReader, "_member", borrowed):
        yield
    if not supplied:
        raise BundleCorruptionError("The same authenticated compressed member was not consumed")


def reopen(member, expected, raw, codec, replay):
    """Reopen with the same authenticated snapshot, without a second payload read."""
    with borrow_snapshot(member.reader, member.chunk, member.compressed), closing(
        codec.Selective(member.reader, member.chunk, raw, expected["map_sha256"], replay)
    ) as reopened:
        if tuple(reopened.rows) != member.rows:
            raise BundleCorruptionError("Replay map did not reopen the original member and signed rows")
        proof = reopened.read(reopened.rows[0], full=False)
        pin = sha256_digest(memoryview(proof.reshape(-1)).cast("B"))
        if pin != member.prefixes[0]:
            raise BundleCorruptionError("Reopened map changed its verified prefix")
        return dict(prefix_bytes=proof.nbytes, prefix_sha256=pin,
                    original_encoded_reused=len(member.compressed))


def member_windows(source, chunk, declared, name, history, hasher, replay, hashes):
    """Yield one complete installed-source member and return its verified map evidence."""
    from leo.scanner.fast_scan_analysis import VerifiedFastWindow

    reader = source.reader
    if (chunk not in reader.manifest.chunks or chunk.first_sequence < source.start_sequence
            or chunk.first_sequence + chunk.window_count > source.stop_sequence):
        raise BundleCorruptionError("First-use member lies outside the declared original source slice")
    member, reason, snapshots = None, None, []
    try:
        with legacy.one_member(reader.path, chunk, snapshots=snapshots):
            member = fused.FusedMember(reader, chunk, history, hasher, allow_literal=True)
    except multi.UnsupportedExceptionLayout as error:
        reason = str(error)
    if len(snapshots) > 1:
        raise BundleCorruptionError("First-use reader authenticated the same compressed member repeatedly")
    snapshot = borrow_snapshot(reader, chunk, snapshots[0]) if member is None and snapshots else nullcontext()
    check = closing(member) if member is not None else nullcontext()
    with check, snapshot:
        count = 0
        windows = member.windows() if member is not None else port.stock_scope(reader, chunk)
        with closing(windows):
            for window in windows:
                index = window.index
                if index.sequence != chunk.first_sequence + count:
                    raise BundleCorruptionError("First-use reader changed signed window order")
                count += 1
                hashes.append(index.iq_sha256)
                yield VerifiedFastWindow(index.sequence, index.iq_sha256, index.acquisition,
                                         source.targets[index.target_id], window.samples,
                                         sample_rate_hz=reader.manifest.sample_rate_hz)
        if count != chunk.window_count:
            raise BundleCorruptionError("First-use reader did not exhaust the original member")
        observed = dict(port.member_identity(reader, chunk), map=None, map_kind="ordinary", map_sha256=None)
        if member is None:
            check_expected(declared, observed)
            return dict(observed, fallback=reason, map_bytes=0), None
        began = clock()
        try:
            raw, pin = member.sidecar()
        except legacy.UnsupportedLayout as error:
            check_expected(declared, observed)
            return dict(observed, verified_without_map=str(error), map_bytes=0, **member.audit()), None
        kind = "exception" if member.exceptions else "literal"
        observed.update(map=name, map_kind=kind, map_sha256=pin)
        check_expected(declared, observed)
        serialization = elapsed(began)
        began = clock()
        proof = reopen(member, observed, raw, multi if member.exceptions else legacy, replay)
        return dict(observed, map_bytes=len(raw), proof=proof, map_serialize=serialization,
                    map_reopen=elapsed(began), **member.audit()), raw


def first_windows(source, parts, history, hasher, replay, pending, audit, hashes):
    if source.start_sequence or source.stop_sequence != source.reader.manifest.window_count:
        raise ValueError("First-use maps require the complete original segment")
    for chunk in source.reader.manifest.chunks:
        identity = source.reader.manifest_sha256, chunk.chunk_index
        declared = parts[identity]
        name = port.map_name(len(audit))
        if name in pending:
            raise BundleCorruptionError("Original first-use acquisition repeated a member")
        evidence, raw = yield from member_windows(source, chunk, declared, name, history, hasher, replay, hashes)
        if raw is not None:
            pending[name] = raw
        audit.append(evidence)


def check_expected(declared, observed):
    if any(observed[key] != value for key, value in declared.items()):
        raise BundleCorruptionError("First-use member differs from declared original or independently sealed replay")


def map_names(plan):
    return [row["map"] for row in plan["members"] if row["map"] is not None]


@contextmanager
def binding(boot, expected, history, hasher, replay, pending, audit):
    staged = boot.staged_scanner
    with ExitStack() as stack:
        def prepare(sources, detector=None):
            scan = staged(sources, detector=detector)
            if detector is None:
                return scan
            source, acquire = scan.FastSegmentSource, scan.acquire
            stock, parts, hashes = source.windows, None, []

            def windows(item):
                return stock(item) if parts is None else first_windows(
                    item, parts, history, hasher, replay, pending, audit["members"], hashes)

            def checked(session, digest, inventory, assets):
                nonlocal parts
                if audit["members"] or pending or hashes:
                    raise ValueError("First-use authority requires one complete acquisition")
                if expected is None:
                    parts = {(reader.manifest_sha256, chunk.chunk_index): port.member_identity(reader, chunk)
                             for reader, chunk in port.ordered_members(inventory)}
                else:
                    parts = port.all_parts(expected, session, digest, inventory)
                try:
                    result = acquire(session, digest, inventory, assets)
                    observed = [(row["manifest_sha256"], row["chunk_index"]) for row in audit["members"]]
                    raw = port.raw_authority(digest, hashes)
                    plan = dict(schema=port.SCHEMA, session=session, inventory=digest, windows=len(hashes),
                                raw_authority=raw, members=[
                                    {key: row[key] for key in (*parts[identity], "map", "map_kind", "map_sha256")}
                                    for identity, row in zip(observed, audit["members"], strict=True)])
                    if (observed != list(parts) or list(pending) != map_names(plan)
                            or len(hashes) != inventory["window_count"]
                            or result["source"]["raw_recording_authority_digest"] != raw
                            or expected is not None and expected != plan):
                        raise BundleCorruptionError("The fused path did not finish the original signed receiver")
                    audit["verified_plan"] = plan
                    audit["finished_raw_authority"] = raw
                    return result
                except BaseException:
                    pending.clear()
                    audit["members"].clear()
                    hashes.clear()
                    raise
                finally:
                    parts = None

            stack.enter_context(patch.object(source, "windows", windows))
            scan.acquire = checked
            return scan

        audit["members"] = []
        stack.enter_context(patch.object(boot, "staged_scanner", prepare))
        yield


def publish_bundle(path, plan, pending):
    if list(pending) != map_names(plan):
        raise BundleCorruptionError("Cannot publish an incomplete ordered map bundle")
    if path.exists():
        raise FileExistsError(path)
    with TemporaryDirectory(prefix=".legacy-first-maps-", dir=path.parent) as temp:
        private = Path(temp)
        for row in plan["members"]:
            if row["map"] is None:
                continue
            raw = pending[row["map"]]
            if sha256_digest(raw) != row["map_sha256"]:
                raise BundleCorruptionError("Map changed between successful receiver and publication")
            fused.publish(private / row["map"], raw)
        custody = canonical_json_bytes(plan)
        fused.publish(private / "custody.json", custody)
        os.rename(private, path)
        _fsync_directory(path.parent)
    return sha256_digest(custody)
