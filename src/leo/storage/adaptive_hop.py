"""Immutable actual-visit IQ bundles, explicitly separate from fixed sweeps.

Directories are exclusively reserved before acquisition. An atomic, no-replace
manifest is the publication point; failed/unpublished directories are retained.
All IO is anchored to no-follow directory descriptors beneath a pre-created
local root. Readers never create paths and never need radio or PPU imports.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import re
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal, Self

import numpy as np
import numpy.typing as npt
import zstandard as zstd
from pydantic import Field, model_validator

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.contracts.recording import CompressionSettingsV1
from leo.domain.iq import receiver_major_complex_to_ci16
from leo.scanner.adaptive_hop import (
    AdaptiveHopPlanV1,
    AdaptiveHopReceiptV1,
    AdaptiveHopVisitV1,
    AdaptiveModel,
    Counter,
    SessionId,
)
from leo.scanner.adaptive_hop_ports import AdaptiveHopVisitBlock
from leo.scanner.persistent_hop import PersistentHopUtcTimingAuthorityV1
from leo.storage.errors import BundleCorruptionError, BundleNotFoundError, BundleStateError
from leo.storage.persistent_hop import PersistentHopQueueTelemetryV1
from leo.storage.pinned import PinnedLocalRoot
from leo.storage.writer import _CompressedFileWriter

if TYPE_CHECKING:
    from leo.storage.adaptive_hop_queue import QueuedAdaptiveHopSessionWriter

_NAMESPACE = "scanner-adaptive-recordings"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_MANIFEST_BYTES = 32 * 1024 * 1024
_MAX_CHUNK_BYTES = 64 * 1024 * 1024
Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]


class AdaptiveHopIqChunkV1(AdaptiveModel):
    """Up to eight chronological visits, with no implied channel coverage."""

    schema_version: Literal[1] = 1
    chunk_index: Annotated[int, Field(strict=True, ge=0, le=312)]
    first_visit_index: Annotated[int, Field(strict=True, ge=0, lt=2500)]
    visit_count: Annotated[int, Field(strict=True, ge=1, le=8)]
    sample_start: Counter
    sample_count: Annotated[int, Field(strict=True, gt=0, le=4_800_000)]
    relative_path: Annotated[str, Field(pattern=r"^iq-block-[0-9]{6}\.ci16\.zst$")]
    uncompressed_bytes: Annotated[int, Field(strict=True, gt=0, le=_MAX_CHUNK_BYTES)]
    compressed_bytes: Annotated[int, Field(strict=True, gt=0, le=_MAX_CHUNK_BYTES)]
    uncompressed_sha256: Digest
    compressed_sha256: Digest


class AdaptiveHopIqManifestV1(AdaptiveModel):
    schema_version: Literal[1] = 1
    kind: Literal["starlink_adaptive_hop_iq"] = "starlink_adaptive_hop_iq"
    session_id: SessionId
    created_utc_ns: Counter
    finalized_utc_ns: Counter
    receipt: AdaptiveHopReceiptV1
    timing: PersistentHopUtcTimingAuthorityV1 | None
    sample_format: Literal["ci16_le"] = "ci16_le"
    sample_layout: Literal["sample_receiver_iq"] = "sample_receiver_iq"
    chunks: Annotated[tuple[AdaptiveHopIqChunkV1, ...], Field(max_length=313)]
    total_sample_count: Counter
    uncompressed_bytes: Counter
    compressed_bytes: Counter
    uncompressed_sha256: Digest
    compression: CompressionSettingsV1
    queue_telemetry: PersistentHopQueueTelemetryV1 | None = None

    @model_validator(mode="after")
    def _manifest_is_complete(self) -> Self:
        receipt = self.receipt
        g = receipt.plan.geometry
        CompressionSettingsV1.model_validate(self.compression.model_dump())
        if self.queue_telemetry is not None:
            PersistentHopQueueTelemetryV1.model_validate(self.queue_telemetry.model_dump())
            if self.queue_telemetry.enqueue_failure_count:
                raise ValueError("adaptive publication cannot hide exhausted storage queues")
        if self.finalized_utc_ns < self.created_utc_ns or self.session_id != receipt.session_id:
            raise ValueError("adaptive IQ identity or finalization time is inconsistent")
        if self.timing is None:
            if receipt.events:
                raise ValueError("adaptive received events require a UTC timing authority")
        else:
            PersistentHopUtcTimingAuthorityV1.model_validate(self.timing.model_dump())
            if (
                self.timing.session_id != self.session_id
                or self.timing.sample_rate_hz != g.sample_rate_hz
                or self.timing.session_start_device_sample_counter != receipt.terminal.first_counter
            ):
                raise ValueError("adaptive UTC authority does not bind this source")
        next_visit = next_sample = compressed = 0
        for index, chunk in enumerate(self.chunks):
            if (
                chunk.chunk_index != index
                or chunk.first_visit_index != next_visit
                or chunk.sample_start != next_sample
                or chunk.relative_path != f"iq-block-{index:06d}.ci16.zst"
                or (index < len(self.chunks) - 1 and chunk.visit_count != 8)
                or next_visit + chunk.visit_count > receipt.complete_visit_count
                or chunk.sample_count != chunk.visit_count * g.valid_visit_samples
                or chunk.uncompressed_bytes != chunk.sample_count * 8
            ):
                raise ValueError("adaptive IQ chunks disagree with actual valid visits")
            next_visit += chunk.visit_count
            next_sample += chunk.sample_count
            compressed += chunk.compressed_bytes
        if (
            next_visit != receipt.complete_visit_count
            or next_sample != receipt.valid_sample_count
            or self.total_sample_count != next_sample
            or self.uncompressed_bytes != next_sample * 8
            or self.compressed_bytes != compressed
        ):
            raise ValueError("adaptive IQ manifest accounting is incomplete")
        if not self.chunks and self.uncompressed_sha256 != sha256_digest(b""):
            raise ValueError("adaptive empty IQ digest is not reproducible")
        return self


class _ManifestSeal(AdaptiveModel):
    manifest: AdaptiveHopIqManifestV1
    sha256: Digest

    @model_validator(mode="after")
    def _digest_matches(self) -> Self:
        if self.sha256 != sha256_digest(
            canonical_json_bytes(self.manifest.model_dump(mode="json"))
        ):
            raise ValueError("adaptive manifest digest mismatch")
        return self


@dataclass(frozen=True, slots=True)
class PublishedAdaptiveHopIqSession:
    session_id: str
    manifest: AdaptiveHopIqManifestV1
    manifest_sha256: str


def _identifier(session_id: str) -> None:
    if not isinstance(session_id, str) or not _IDENTIFIER.fullmatch(session_id):
        raise ValueError("adaptive session ID is unsafe")


def _rename_noreplace(directory_fd: int, source: bytes, destination: bytes) -> None:
    # The pinned /proc/self/fd store is Linux-owned. renameat2 is the atomic
    # no-replace publication primitive; link/unlink would leave a two-link
    # manifest after a crash, rejected by our single-link immutable reader.
    library = ctypes.CDLL(None, use_errno=True)
    rename = library.renameat2
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(directory_fd, source, directory_fd, destination, 1) != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), os.fsdecode(destination))


def _read_regular(directory: PinnedLocalRoot, name: str, maximum: int) -> bytes:
    descriptor = os.open(
        name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory.fileno()
    )
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > maximum:
            raise BundleCorruptionError("adaptive file is not a bounded single-link regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            payload = stream.read(maximum + 1)
        after = os.fstat(descriptor)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_nlink")
        if (
            len(payload) != before.st_size
            or len(payload) > maximum
            or any(getattr(before, field) != getattr(after, field) for field in fields)
        ):
            raise BundleCorruptionError("adaptive file changed during read")
        return payload
    finally:
        os.close(descriptor)


class AdaptiveHopIqStore:
    def __init__(self, root: Path, *, read_only: bool = False) -> None:
        self._root = PinnedLocalRoot(root)
        self._read_only = read_only

    def close(self) -> None:
        self._root.close()

    def begin_queued(
        self, session_id: str, plan: AdaptiveHopPlanV1, *, capacity_visits: int = 8
    ) -> QueuedAdaptiveHopSessionWriter:
        from leo.storage.adaptive_hop_queue import QueuedAdaptiveHopSessionWriter

        if type(capacity_visits) is not int or not 1 <= capacity_visits <= 64:
            raise ValueError("adaptive storage queue capacity must be within 1..64")
        writer = self.begin(session_id, plan)
        try:
            return QueuedAdaptiveHopSessionWriter(writer, capacity_visits=capacity_visits)
        except BaseException:
            writer.abort()
            raise

    def begin(self, session_id: str, plan: AdaptiveHopPlanV1) -> AdaptiveHopSessionWriter:
        if self._read_only:
            raise BundleStateError("adaptive IQ store is read-only")
        _identifier(session_id)
        plan = AdaptiveHopPlanV1.model_validate(plan)
        namespace = self._root.child(_NAMESPACE, create=True)
        try:
            os.fsync(self._root.fileno())
            # Existing incomplete or published sessions cannot be overwritten.
            os.mkdir(session_id, mode=0o750, dir_fd=namespace.fileno())
            os.fsync(namespace.fileno())
            directory = namespace.child(session_id)
        finally:
            namespace.close()
        try:
            return AdaptiveHopSessionWriter(directory, session_id, plan)
        except BaseException:
            directory.close()
            raise

    def _session(self, session_id: str) -> PinnedLocalRoot:
        _identifier(session_id)
        try:
            namespace = self._root.child(_NAMESPACE)
        except ValueError as error:
            # PinnedLocalRoot deliberately wraps openat errors. Preserve a
            # genuinely missing namespace without masking a symlink/refusal.
            if isinstance(error.__cause__, FileNotFoundError):
                raise BundleNotFoundError(
                    f"adaptive recording does not exist: {session_id}"
                ) from error
            raise
        try:
            os.stat(session_id, dir_fd=namespace.fileno(), follow_symlinks=False)
        except FileNotFoundError as error:
            raise BundleNotFoundError(f"adaptive recording does not exist: {session_id}") from error
        finally:
            namespace.close()
        return self._root.child(_NAMESPACE, session_id)

    def inspect(self, session_id: str) -> PublishedAdaptiveHopIqSession:
        directory = None
        try:
            directory = self._session(session_id)
            seal = _ManifestSeal.model_validate_json(
                _read_regular(directory, "manifest.json", _MAX_MANIFEST_BYTES)
            )
            if seal.manifest.session_id != session_id:
                raise BundleCorruptionError("adaptive manifest changed session identity")
            return PublishedAdaptiveHopIqSession(session_id, seal.manifest, seal.sha256)
        except FileNotFoundError as error:
            raise BundleNotFoundError(f"adaptive recording is unpublished: {session_id}") from error
        except (OSError, ValueError) as error:
            raise BundleCorruptionError(
                f"cannot read adaptive recording {session_id}: {error}"
            ) from error
        finally:
            if directory is not None:
                directory.close()

    def contains_session(self, session_id: str) -> bool:
        """Includes reserved/unpublished sessions; never authorizes overwriting."""
        try:
            directory = self._session(session_id)
        except BundleNotFoundError:
            return False
        directory.close()
        return True

    def session_ids(self) -> tuple[str, ...]:
        # Do not turn unreadable or corrupt *published* records into an empty
        # history. Directory discovery ignores only uncommitted manifest absence.
        try:
            os.stat(_NAMESPACE, dir_fd=self._root.fileno(), follow_symlinks=False)
        except FileNotFoundError:
            return ()
        namespace = self._root.child(_NAMESPACE)
        try:
            output = []
            for name in sorted(os.listdir(namespace.fileno())):
                if not _IDENTIFIER.fullmatch(name):
                    continue
                info = os.stat(name, dir_fd=namespace.fileno(), follow_symlinks=False)
                if not stat.S_ISDIR(info.st_mode):
                    raise BundleCorruptionError("adaptive session path is not a directory")
                try:
                    self.inspect(name)
                except BundleNotFoundError:
                    continue
                output.append(name)
            return tuple(output)
        finally:
            namespace.close()

    def read_chunk_ci16(
        self, session: PublishedAdaptiveHopIqSession, chunk_index: int
    ) -> tuple[tuple[AdaptiveHopVisitV1, ...], npt.NDArray[np.int16]]:
        with self.reader(session.session_id, expected=session) as reader:
            return reader.read_chunk_ci16(chunk_index)

    def read_visit_ci16(
        self, session: PublishedAdaptiveHopIqSession, visit_index: int
    ) -> tuple[AdaptiveHopVisitV1, npt.NDArray[np.int16]]:
        with self.reader(session.session_id, expected=session) as reader:
            return reader.read_visit_ci16(visit_index)

    def reader(
        self, session_id: str, *, expected: PublishedAdaptiveHopIqSession | None = None
    ) -> AdaptiveHopIqReader:
        session = self.inspect(session_id)
        if expected is not None and expected != session:
            raise BundleCorruptionError("adaptive IQ handle differs from published manifest")
        return AdaptiveHopIqReader(self._session(session_id), session)

    def verify(self, session_id: str) -> PublishedAdaptiveHopIqSession:
        with self.reader(session_id) as reader:
            digest = hashlib.sha256()
            for index in range(len(reader.session.manifest.chunks)):
                _, values = reader.read_chunk_ci16(index)
                digest.update(memoryview(values).cast("B"))
            if f"sha256:{digest.hexdigest()}" != reader.session.manifest.uncompressed_sha256:
                raise BundleCorruptionError("adaptive session IQ digest mismatch")
            return reader.session


class AdaptiveHopIqReader:
    """One verified immutable manifest, one cached IQ chunk, one pinned directory.

    Arrays already returned are immutable verified snapshots; a caller retaining
    them owns that memory. New reads outside the cache still verify exact hashes.
    """

    def __init__(self, directory: PinnedLocalRoot, session: PublishedAdaptiveHopIqSession):
        self._directory = directory
        self.session = session
        self._visits = session.manifest.receipt.visits
        self._cached_index: int | None = None
        self._cached_values: npt.NDArray[np.int16] | None = None

    def __enter__(self) -> Self:
        self._directory.assert_open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._cached_index = None
        self._cached_values = None
        self._directory.close()

    def read_chunk_ci16(
        self, chunk_index: int
    ) -> tuple[tuple[AdaptiveHopVisitV1, ...], npt.NDArray[np.int16]]:
        self._directory.assert_open()
        if type(chunk_index) is not int or not 0 <= chunk_index < len(self.session.manifest.chunks):
            raise ValueError("adaptive IQ chunk does not exist")
        chunk = self.session.manifest.chunks[chunk_index]
        visits = self._visits[chunk.first_visit_index : chunk.first_visit_index + chunk.visit_count]
        if self._cached_index == chunk_index:
            assert self._cached_values is not None
            return visits, self._cached_values
        try:
            payload = _read_regular(self._directory, chunk.relative_path, chunk.compressed_bytes)
        except (OSError, ValueError) as error:
            raise BundleCorruptionError(f"cannot read adaptive IQ: {error}") from error
        if (
            len(payload) != chunk.compressed_bytes
            or sha256_digest(payload) != chunk.compressed_sha256
        ):
            raise BundleCorruptionError("adaptive compressed digest mismatch")
        try:
            parameters = zstd.get_frame_parameters(payload)
            if (
                parameters.content_size not in (zstd.CONTENTSIZE_UNKNOWN, chunk.uncompressed_bytes)
                or parameters.window_size > _MAX_CHUNK_BYTES
            ):
                raise BundleCorruptionError("adaptive frame declares an invalid expansion bound")
            raw = zstd.ZstdDecompressor(max_window_size=_MAX_CHUNK_BYTES).decompress(
                payload,
                max_output_size=chunk.uncompressed_bytes,
                allow_extra_data=False,
            )
        except zstd.ZstdError as error:
            raise BundleCorruptionError(
                f"adaptive bounded decompression failed: {error}"
            ) from error
        if len(raw) != chunk.uncompressed_bytes or sha256_digest(raw) != chunk.uncompressed_sha256:
            raise BundleCorruptionError("adaptive uncompressed size/digest mismatch")
        values = np.frombuffer(raw, dtype="<i2").reshape(chunk.sample_count, 2, 2)
        self._cached_index = chunk_index
        self._cached_values = values
        return visits, values

    def read_visit_ci16(self, visit_index: int) -> tuple[AdaptiveHopVisitV1, npt.NDArray[np.int16]]:
        if type(visit_index) is not int or not 0 <= visit_index < len(self._visits):
            raise ValueError("adaptive IQ visit does not exist")
        visits, values = self.read_chunk_ci16(visit_index // 8)
        local = visit_index % 8
        count = visits[local].valid_sample_count
        return visits[local], values[local * count : (local + 1) * count]


class AdaptiveHopSessionWriter:
    def __init__(self, directory: PinnedLocalRoot, session_id: str, plan: AdaptiveHopPlanV1):
        self._directory = directory
        self._session_id = session_id
        self._plan = plan
        self._created_ns = time.time_ns()
        self._closed = False
        self._failed = False
        self._visits: list[AdaptiveHopVisitV1] = []
        self._chunks: list[AdaptiveHopIqChunkV1] = []
        self._compressed: _CompressedFileWriter | None = None
        self._chunk_visits = 0
        self._chunk_digest = hashlib.sha256()
        self._digest = hashlib.sha256()

    def _require_open(self) -> None:
        if self._closed or self._failed:
            raise BundleStateError("adaptive IQ writer is closed or failed")

    def append(self, block: AdaptiveHopVisitBlock) -> None:
        self._require_open()
        try:
            visit = AdaptiveHopVisitV1.model_validate(block.evidence)
            g = self._plan.geometry
            e = visit.event
            if (
                e.visit_index != len(self._visits)
                or e.target != g.profiles[e.target_index].target
                or e.decision.mode != self._plan.policy.mode
                or e.decision.generation != self._plan.policy.generation
                or e.valid_start_counter != e.transition_after_counter + g.transition_guard_samples
                or visit.valid_sample_count != g.valid_visit_samples
                or block.receiver_ids != g.receiver_ids
                or (
                    self._visits
                    and (
                        e.from_profile_index != self._visits[-1].event.target_index
                        or e.invalid_start_counter != self._visits[-1].valid_end_counter_exclusive
                    )
                )
            ):
                raise ValueError("adaptive IQ visit differs from plan or source order")
            ci16 = receiver_major_complex_to_ci16(block.samples.T, 2, visit.valid_sample_count)
            if self._compressed is None:
                name = f"iq-block-{len(self._chunks):06d}.ci16.zst.partial"
                self._compressed = _CompressedFileWriter(self._directory.io_root / name, level=3)
            payload = memoryview(ci16).cast("B")
            self._compressed.write(payload)
            self._chunk_digest.update(payload)
            self._digest.update(payload)
            self._visits.append(visit)
            self._chunk_visits += 1
            if self._chunk_visits == 8:
                self._finish_chunk()
        except BaseException:
            self._failed = True
            raise

    def _finish_chunk(self) -> None:
        if self._compressed is None:
            return
        _, compressed_bytes, compressed_digest = self._compressed.finish()
        count = self._chunk_visits
        first = len(self._visits) - count
        dwell = self._plan.geometry.valid_visit_samples
        index = len(self._chunks)
        self._chunks.append(
            AdaptiveHopIqChunkV1(
                chunk_index=index,
                first_visit_index=first,
                visit_count=count,
                sample_start=first * dwell,
                sample_count=count * dwell,
                relative_path=f"iq-block-{index:06d}.ci16.zst",
                uncompressed_bytes=count * dwell * 8,
                compressed_bytes=compressed_bytes,
                uncompressed_sha256=f"sha256:{self._chunk_digest.hexdigest()}",
                compressed_sha256=compressed_digest,
            )
        )
        self._compressed = None
        self._chunk_visits = 0
        self._chunk_digest = hashlib.sha256()

    def finish(
        self,
        receipt: AdaptiveHopReceiptV1,
        *,
        timing: PersistentHopUtcTimingAuthorityV1 | None,
        queue_telemetry: PersistentHopQueueTelemetryV1 | None = None,
    ) -> PublishedAdaptiveHopIqSession:
        self._require_open()
        try:
            receipt = AdaptiveHopReceiptV1.model_validate(receipt)
            if (
                receipt.session_id != self._session_id
                or receipt.plan != self._plan
                or receipt.visits != tuple(self._visits)
            ):
                raise ValueError("adaptive IQ receipt disagrees with written actual visits")
            self._finish_chunk()
            manifest = AdaptiveHopIqManifestV1(
                session_id=self._session_id,
                created_utc_ns=self._created_ns,
                finalized_utc_ns=time.time_ns(),
                receipt=receipt,
                timing=timing,
                chunks=tuple(self._chunks),
                total_sample_count=receipt.valid_sample_count,
                uncompressed_bytes=receipt.valid_sample_count * 8,
                compressed_bytes=sum(c.compressed_bytes for c in self._chunks),
                uncompressed_sha256=f"sha256:{self._digest.hexdigest()}",
                compression=CompressionSettingsV1(
                    policy_id="adaptive-eight-visit-chunks-v1",
                    level=3,
                    target_uncompressed_bytes=self._plan.geometry.valid_visit_samples * 8 * 8,
                ),
                queue_telemetry=queue_telemetry,
            )
            digest = sha256_digest(canonical_json_bytes(manifest.model_dump(mode="json")))
            payload = canonical_json_bytes(
                _ManifestSeal(manifest=manifest, sha256=digest).model_dump(mode="json")
            )
            if len(payload) > _MAX_MANIFEST_BYTES:
                raise ValueError("adaptive manifest exceeds bounded reader capacity")
            self._publish_manifest(payload)
            self._closed = True
            self._directory.close()
            return PublishedAdaptiveHopIqSession(self._session_id, manifest, digest)
        except BaseException:
            self._failed = True
            raise

    def _publish_manifest(self, payload: bytes) -> None:
        fd = self._directory.fileno()
        descriptor = os.open(
            "manifest.json.partial",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o640,
            dir_fd=fd,
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _rename_noreplace(fd, b"manifest.json.partial", b"manifest.json")
        os.fsync(fd)

    def abort(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self._compressed is not None:
                self._compressed.abort()
        finally:
            self._directory.close()
