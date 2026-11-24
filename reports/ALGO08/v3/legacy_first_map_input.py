"""Bind first-use maps to the normal, complete original receiver traversal."""

from contextlib import ExitStack, closing, contextmanager
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.storage.errors import BundleCorruptionError
from leo.storage.short_window import ShortWindowReader
from leo.storage.writer import _fsync_directory

from . import legacy_block_input as port, legacy_fused_map as fused
from .legacy_block_seek import clock, elapsed


def reopen(member, expected, raw, codec, replay):
    """Reopen with the same authenticated snapshot, without a second payload read."""
    original = ShortWindowReader._member
    reader, chunk = member.reader, member.chunk
    supplied = 0

    def borrowed(source, name, size, pin):
        nonlocal supplied
        if source is reader and name == chunk.payload_relative_path:
            if (size, pin) != (len(member.compressed), chunk.compressed_sha256) or supplied:
                raise BundleCorruptionError("Replay requested a different original compressed member")
            supplied += 1
            return member.compressed
        return original(source, name, size, pin)

    with patch.object(ShortWindowReader, "_member", borrowed), closing(
        codec.Selective(reader, chunk, raw, expected["map_sha256"], replay)
    ) as reopened:
        if supplied != 1 or tuple(reopened.rows) != member.rows:
            raise BundleCorruptionError("Replay map did not reopen the original member and signed rows")
        proof = reopened.read(reopened.rows[0], full=False)
        pin = sha256_digest(memoryview(proof.reshape(-1)).cast("B"))
        if pin != member.prefixes[0]:
            raise BundleCorruptionError("Reopened map changed its verified prefix")
        return dict(prefix_bytes=proof.nbytes, prefix_sha256=pin,
                    original_encoded_reused=len(member.compressed))


def first_windows(source, parts, history, hasher, codec, replay, pending, audit):
    from leo.scanner.fast_scan_analysis import VerifiedFastWindow

    if source.start_sequence or source.stop_sequence != source.reader.manifest.window_count:
        raise ValueError("First-use maps require the complete original segment")
    for chunk in source.reader.manifest.chunks:
        identity = source.reader.manifest_sha256, chunk.chunk_index
        expected = parts[identity]
        if expected["map"] in pending:
            raise BundleCorruptionError("Original first-use acquisition repeated a member")
        with closing(fused.FusedMember(source.reader, chunk, history, hasher, allow_literal=True)) as member:
            for window in member.windows():
                index = window.index
                yield VerifiedFastWindow(index.sequence, index.iq_sha256, index.acquisition,
                                         source.targets[index.target_id], window.samples,
                                         sample_rate_hz=source.reader.manifest.sample_rate_hz)
            began = clock()
            raw, pin = member.sidecar()
            kind = "exception" if member.exceptions else "literal"
            if (pin, kind) != (expected["map_sha256"], expected["map_kind"]):
                raise BundleCorruptionError("Fused map disagrees with the independently sealed replay map")
            serialization = elapsed(began)
            began = clock()
            proof = reopen(member, expected, raw, codec, replay)
            pending[expected["map"]] = raw
            audit.append(dict(expected, map_bytes=len(raw), proof=proof, map_serialize=serialization,
                              map_reopen=elapsed(began), **member.audit()))


@contextmanager
def binding(boot, plan, history, hasher, codec, replay, pending, audit):
    staged = boot.staged_scanner
    with ExitStack() as stack:
        def prepare(sources, detector=None):
            scan = staged(sources, detector=detector)
            if detector is None:
                return scan
            source, acquire = scan.FastSegmentSource, scan.acquire
            stock, parts = source.windows, None

            def windows(item):
                return stock(item) if parts is None else first_windows(
                    item, parts, history, hasher, codec, replay, pending, audit["members"])

            def checked(session, digest, inventory, assets):
                nonlocal parts
                parts = port.all_parts(plan, session, digest, inventory)
                try:
                    result = acquire(session, digest, inventory, assets)
                    observed = [(row["manifest_sha256"], row["chunk_index"]) for row in audit["members"]]
                    if (observed != list(parts) or list(pending) != [row["map"] for row in plan["members"]]
                            or result["source"]["raw_recording_authority_digest"] != plan["raw_authority"]):
                        raise BundleCorruptionError("The fused path did not finish the original signed receiver")
                    audit["finished_raw_authority"] = plan["raw_authority"]
                    return result
                finally:
                    parts = None

            stack.enter_context(patch.object(source, "windows", windows))
            scan.acquire = checked
            return scan

        audit["members"] = []
        stack.enter_context(patch.object(boot, "staged_scanner", prepare))
        yield


def publish_bundle(path, plan, pending):
    if list(pending) != [row["map"] for row in plan["members"]]:
        raise BundleCorruptionError("Cannot publish an incomplete ordered map bundle")
    if path.exists():
        raise FileExistsError(path)
    with TemporaryDirectory(prefix=".legacy-first-maps-", dir=path.parent) as temp:
        private = Path(temp)
        for row in plan["members"]:
            raw = pending[row["map"]]
            if sha256_digest(raw) != row["map_sha256"]:
                raise BundleCorruptionError("Map changed between successful receiver and publication")
            fused.publish(private / row["map"], raw)
        custody = canonical_json_bytes(plan)
        fused.publish(private / "custody.json", custody)
        os.rename(private, path)
        _fsync_directory(path.parent)
    return sha256_digest(custody)
