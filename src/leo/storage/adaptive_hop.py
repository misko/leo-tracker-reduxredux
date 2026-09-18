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
from collections.abc import Iterator
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, ClassVar, Literal, Self

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
from leo.scanner.host_adaptive import (
    HostAdaptiveHopPlanV2,
    HostAdaptiveHopPlanV3,
    HostAdaptiveHopReceiptV2,
    HostAdaptiveHopReceiptV3,
    HostAdaptiveHopReceiptV4,
    HostAdaptiveHopReceiptV5,
)
from leo.scanner.host_adaptive_ports import HostAdaptiveHopVisitBlock
from leo.scanner.persistent_hop import PersistentHopUtcTimingAuthorityV1
from leo.scanner.single_rx import SingleRxHopTimingV2, SingleRxHopTimingV3
from leo.storage.errors import BundleCorruptionError, BundleNotFoundError, BundleStateError
from leo.storage.persistent_hop import PersistentHopQueueTelemetryV1
from leo.storage.pinned import PinnedLocalRoot
from leo.storage.writer import _CompressedFileWriter

if TYPE_CHECKING:
    from leo.storage.adaptive_hop_queue import QueuedAdaptiveHopSessionWriter

_NAMESPACE = "scanner-adaptive-recordings"
_SPOOL_NAMESPACE = "scanner-adaptive-spool"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_MANIFEST_BYTES = 32 * 1024 * 1024
_MANIFEST_INDEX_PREFIX_BYTES = 512 * 1024
_MAX_CHUNK_BYTES = 64 * 1024 * 1024
_FINALIZED_UTC_NS = re.compile(rb'"finalized_utc_ns":([0-9]{1,20})')
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
    _bytes_per_sample: ClassVar[int] = 8
    _visits_per_chunk: ClassVar[int] = 8
    _timing_model: ClassVar[type[PersistentHopUtcTimingAuthorityV1]] = (
        PersistentHopUtcTimingAuthorityV1
    )
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
            self._timing_model.model_validate(self.timing.model_dump())
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
                or (index < len(self.chunks) - 1 and chunk.visit_count != self._visits_per_chunk)
                or next_visit + chunk.visit_count > receipt.complete_visit_count
                or chunk.sample_count != chunk.visit_count * g.valid_visit_samples
                or chunk.uncompressed_bytes != chunk.sample_count * self._bytes_per_sample
            ):
                raise ValueError("adaptive IQ chunks disagree with actual valid visits")
            next_visit += chunk.visit_count
            next_sample += chunk.sample_count
            compressed += chunk.compressed_bytes
        if (
            next_visit != receipt.complete_visit_count
            or next_sample != receipt.valid_sample_count
            or self.total_sample_count != next_sample
            or self.uncompressed_bytes != next_sample * self._bytes_per_sample
            or self.compressed_bytes != compressed
        ):
            raise ValueError("adaptive IQ manifest accounting is incomplete")
        if not self.chunks and self.uncompressed_sha256 != sha256_digest(b""):
            raise ValueError("adaptive empty IQ digest is not reproducible")
        return self


class HostAdaptiveHopIqChunkV2(AdaptiveHopIqChunkV1):
    schema_version: Literal[2] = 2  # type: ignore[assignment]
    sample_count: Annotated[int, Field(strict=True, gt=0, le=9_600_000)]


class HostAdaptiveHopIqManifestV2(AdaptiveHopIqManifestV1):
    schema_version: Literal[2] = 2  # type: ignore[assignment]
    _bytes_per_sample: ClassVar[int] = 4
    _timing_model: ClassVar[type[PersistentHopUtcTimingAuthorityV1]] = SingleRxHopTimingV2
    receipt: HostAdaptiveHopReceiptV2
    timing: SingleRxHopTimingV2 | None
    chunks: Annotated[tuple[HostAdaptiveHopIqChunkV2, ...], Field(max_length=313)]


class HostAdaptiveHopIqChunkV3(HostAdaptiveHopIqChunkV2):
    schema_version: Literal[3] = 3  # type: ignore[assignment]
    chunk_index: Annotated[int, Field(strict=True, ge=0, le=624)]
    visit_count: Annotated[int, Field(strict=True, ge=1, le=4)]


class HostAdaptiveHopIqManifestV3(HostAdaptiveHopIqManifestV2):
    schema_version: Literal[3] = 3  # type: ignore[assignment]
    _visits_per_chunk: ClassVar[int] = 4
    _timing_model: ClassVar[type[PersistentHopUtcTimingAuthorityV1]] = SingleRxHopTimingV3
    receipt: HostAdaptiveHopReceiptV3
    timing: SingleRxHopTimingV3 | None
    chunks: Annotated[tuple[HostAdaptiveHopIqChunkV3, ...], Field(max_length=625)]


class HostAdaptiveHopIqManifestV4(HostAdaptiveHopIqManifestV3):
    schema_version: Literal[4] = 4  # type: ignore[assignment]
    receipt: HostAdaptiveHopReceiptV4


class HostAdaptiveHopIqManifestV5(HostAdaptiveHopIqManifestV2):
    schema_version: Literal[5] = 5  # type: ignore[assignment]
    receipt: HostAdaptiveHopReceiptV5


class _ManifestSeal(AdaptiveModel):
    manifest: Annotated[
        AdaptiveHopIqManifestV1
        | HostAdaptiveHopIqManifestV2
        | HostAdaptiveHopIqManifestV3
        | HostAdaptiveHopIqManifestV4
        | HostAdaptiveHopIqManifestV5,
        Field(discriminator="schema_version"),
    ]
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


def _read_regular_prefix(
    directory: PinnedLocalRoot, name: str, *, maximum: int, prefix_bytes: int
) -> bytes:
    descriptor = os.open(
        name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory.fileno()
    )
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > maximum:
            raise BundleCorruptionError("adaptive file is not a bounded single-link regular file")
        payload = os.read(descriptor, min(before.st_size, prefix_bytes))
        after = os.fstat(descriptor)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_nlink")
        if any(getattr(before, field) != getattr(after, field) for field in fields):
            raise BundleCorruptionError("adaptive file changed during indexed read")
        return payload
    finally:
        os.close(descriptor)


def _copy_regular_verified(
    source: PinnedLocalRoot,
    destination: PinnedLocalRoot,
    name: str,
    *,
    maximum: int,
    expected_size: int,
    expected_digest: str,
) -> None:
    source_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=source.fileno())
    destination_fd = -1
    try:
        before = os.fstat(source_fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size != expected_size
            or before.st_size > maximum
        ):
            raise BundleCorruptionError("adaptive spool file is not the sealed regular file")
        destination_fd = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o640,
            dir_fd=destination.fileno(),
        )
        digest = hashlib.sha256()
        copied = 0
        while True:
            payload = os.read(source_fd, min(4 * 1024 * 1024, maximum + 1 - copied))
            if not payload:
                break
            copied += len(payload)
            if copied > maximum:
                raise BundleCorruptionError("adaptive spool file exceeds its manifest bound")
            digest.update(payload)
            view = memoryview(payload)
            while view:
                written = os.write(destination_fd, view)
                if written <= 0:
                    raise OSError("adaptive RAID copy made no progress")
                view = view[written:]
        after = os.fstat(source_fd)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_nlink")
        if (
            copied != expected_size
            or f"sha256:{digest.hexdigest()}" != expected_digest
            or any(getattr(before, field) != getattr(after, field) for field in fields)
        ):
            raise BundleCorruptionError("adaptive spool file changed or failed digest verification")
        os.fsync(destination_fd)
    except BaseException:
        if destination_fd >= 0:
            os.close(destination_fd)
            destination_fd = -1
        with suppress(FileNotFoundError):
            os.unlink(name, dir_fd=destination.fileno())
        raise
    finally:
        if destination_fd >= 0:
            os.close(destination_fd)
        os.close(source_fd)


class AdaptiveHopIqStore:
    def __init__(
        self,
        root: Path,
        *,
        read_only: bool = False,
        spool_root: Path | None = None,
        defer_spool_transfer: bool = False,
    ) -> None:
        self._root = PinnedLocalRoot(root)
        self._read_only = read_only
        self._spool_root = None if read_only or spool_root is None else PinnedLocalRoot(spool_root)
        self._defer_spool_transfer = defer_spool_transfer
        if self._spool_root is not None and not defer_spool_transfer:
            try:
                self.recover_spooled_sessions()
            except BaseException:
                self._spool_root.close()
                self._root.close()
                raise

    def close(self) -> None:
        if self._spool_root is not None:
            self._spool_root.close()
        self._root.close()

    def begin_queued(
        self, session_id: str, plan: AdaptiveHopPlanV1, *, capacity_visits: int = 8
    ) -> QueuedAdaptiveHopSessionWriter:
        from leo.storage.adaptive_hop_queue import QueuedAdaptiveHopSessionWriter

        if type(capacity_visits) is not int or not 1 <= capacity_visits <= 256:
            raise ValueError("adaptive storage queue capacity must be within 1..256")
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
        plan_model = (
            HostAdaptiveHopPlanV3
            if isinstance(plan, HostAdaptiveHopPlanV3)
            else HostAdaptiveHopPlanV2
            if isinstance(plan, HostAdaptiveHopPlanV2)
            else AdaptiveHopPlanV1
        )
        plan = plan_model.model_validate(plan.model_dump())
        if self.contains_session(session_id):
            raise FileExistsError(session_id)
        write_root = self._spool_root or self._root
        namespace_name = _SPOOL_NAMESPACE if self._spool_root is not None else _NAMESPACE
        namespace = write_root.child(namespace_name, create=True)
        try:
            os.fsync(write_root.fileno())
            # Existing incomplete or published sessions cannot be overwritten.
            os.mkdir(session_id, mode=0o750, dir_fd=namespace.fileno())
            os.fsync(namespace.fileno())
            directory = namespace.child(session_id)
        finally:
            namespace.close()
        try:
            writer = AdaptiveHopSessionWriter(directory, session_id, plan)
            if self._spool_root is None:
                return writer
            return _SpoolingAdaptiveHopSessionWriter(writer, self, session_id)
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
            return self._spooled_session_exists(session_id)
        directory.close()
        return True

    def _spooled_session_exists(self, session_id: str) -> bool:
        _identifier(session_id)
        if self._spool_root is None:
            return False
        try:
            namespace = self._spool_root.child(_SPOOL_NAMESPACE)
        except ValueError as error:
            if isinstance(error.__cause__, FileNotFoundError):
                return False
            raise
        try:
            info = os.stat(session_id, dir_fd=namespace.fileno(), follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode):
                raise BundleCorruptionError("adaptive spool session is not a directory")
            return True
        except FileNotFoundError:
            return False
        finally:
            namespace.close()

    def recover_spooled_sessions(self) -> tuple[str, ...]:
        """Publish sealed NVMe sessions left by a stopped transfer.

        Unsealed acquisition evidence remains untouched and continues to reserve
        its session ID. A destination becomes discoverable only after every
        manifest-bound file has been copied and verified.
        """
        if self._read_only or self._spool_root is None:
            return ()
        try:
            namespace = self._spool_root.child(_SPOOL_NAMESPACE)
        except ValueError as error:
            if isinstance(error.__cause__, FileNotFoundError):
                return ()
            raise
        try:
            names = tuple(sorted(os.listdir(namespace.fileno())))
        finally:
            namespace.close()
        recovered: list[str] = []
        for name in names:
            if not _IDENTIFIER.fullmatch(name):
                continue
            source = self._spool_root.child(_SPOOL_NAMESPACE, name)
            try:
                try:
                    os.stat("manifest.json", dir_fd=source.fileno(), follow_symlinks=False)
                except FileNotFoundError:
                    continue
            finally:
                source.close()
            self._transfer_spooled_session(name)
            recovered.append(name)
        return tuple(recovered)

    def _transfer_spooled_session(self, session_id: str) -> PublishedAdaptiveHopIqSession:
        assert self._spool_root is not None
        source = self._spool_root.child(_SPOOL_NAMESPACE, session_id)
        try:
            manifest_payload = _read_regular(source, "manifest.json", _MAX_MANIFEST_BYTES)
            seal = _ManifestSeal.model_validate_json(manifest_payload)
            if seal.manifest.session_id != session_id:
                raise BundleCorruptionError("adaptive spool changed session identity")
            expected_files = {"manifest.json"}
            expected_files.update(chunk.relative_path for chunk in seal.manifest.chunks)
            actual_files = set(os.listdir(source.fileno()))
            if actual_files != expected_files:
                raise BundleCorruptionError("adaptive spool contains files outside its manifest")

            try:
                published = self.inspect(session_id)
            except BundleNotFoundError:
                published = None
            if published is not None:
                if published.manifest_sha256 != seal.sha256:
                    raise BundleStateError("adaptive RAID destination conflicts with sealed spool")
                self._remove_spooled_session(session_id, expected_files)
                return published

            destination_namespace = self._root.child(_NAMESPACE, create=True)
            staging_name = f".transfer-{session_id}.partial"
            try:
                os.fsync(self._root.fileno())
                try:
                    os.mkdir(staging_name, mode=0o750, dir_fd=destination_namespace.fileno())
                except FileExistsError:
                    self._remove_staging(destination_namespace, staging_name)
                    os.mkdir(staging_name, mode=0o750, dir_fd=destination_namespace.fileno())
                staging = destination_namespace.child(staging_name)
                try:
                    for chunk in seal.manifest.chunks:
                        _copy_regular_verified(
                            source,
                            staging,
                            chunk.relative_path,
                            maximum=chunk.compressed_bytes,
                            expected_size=chunk.compressed_bytes,
                            expected_digest=chunk.compressed_sha256,
                        )
                    _copy_regular_verified(
                        source,
                        staging,
                        "manifest.json",
                        maximum=_MAX_MANIFEST_BYTES,
                        expected_size=len(manifest_payload),
                        expected_digest=sha256_digest(manifest_payload),
                    )
                    os.fsync(staging.fileno())
                except BaseException:
                    staging.close()
                    self._remove_staging(destination_namespace, staging_name)
                    raise
                else:
                    staging.close()
                _rename_noreplace(
                    destination_namespace.fileno(),
                    os.fsencode(staging_name),
                    os.fsencode(session_id),
                )
                os.fsync(destination_namespace.fileno())
            finally:
                destination_namespace.close()
        finally:
            source.close()
        published = self.inspect(session_id)
        if published.manifest_sha256 != seal.sha256:
            raise BundleCorruptionError("adaptive RAID publication differs from sealed spool")
        self._remove_spooled_session(session_id, expected_files)
        return published

    def _remove_staging(self, namespace: PinnedLocalRoot, name: str) -> None:
        directory = namespace.child(name)
        try:
            for member in os.listdir(directory.fileno()):
                info = os.stat(member, dir_fd=directory.fileno(), follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise BundleCorruptionError("adaptive transfer staging is unsafe")
                os.unlink(member, dir_fd=directory.fileno())
        finally:
            directory.close()
        os.rmdir(name, dir_fd=namespace.fileno())
        os.fsync(namespace.fileno())

    def _remove_spooled_session(self, session_id: str, names: set[str]) -> None:
        assert self._spool_root is not None
        namespace = self._spool_root.child(_SPOOL_NAMESPACE)
        try:
            directory = namespace.child(session_id)
            try:
                if set(os.listdir(directory.fileno())) != names:
                    raise BundleCorruptionError("adaptive spool changed before cleanup")
                for name in names:
                    os.unlink(name, dir_fd=directory.fileno())
                os.fsync(directory.fileno())
            finally:
                directory.close()
            os.rmdir(session_id, dir_fd=namespace.fileno())
            os.fsync(namespace.fileno())
        finally:
            namespace.close()

    def session_ids(self) -> tuple[str, ...]:
        return tuple(session.session_id for session in self.iter_sessions())

    def history_index(self) -> tuple[tuple[int, str], ...]:
        """Return immutable publication keys without parsing every multi-megabyte receipt."""
        try:
            os.stat(_NAMESPACE, dir_fd=self._root.fileno(), follow_symlinks=False)
        except FileNotFoundError:
            return ()
        namespace = self._root.child(_NAMESPACE)
        try:
            index: list[tuple[int, str]] = []
            for name in sorted(os.listdir(namespace.fileno())):
                if not _IDENTIFIER.fullmatch(name):
                    continue
                info = os.stat(name, dir_fd=namespace.fileno(), follow_symlinks=False)
                if not stat.S_ISDIR(info.st_mode):
                    raise BundleCorruptionError("adaptive session path is not a directory")
                directory = namespace.child(name)
                try:
                    try:
                        prefix = _read_regular_prefix(
                            directory,
                            "manifest.json",
                            maximum=_MAX_MANIFEST_BYTES,
                            prefix_bytes=_MANIFEST_INDEX_PREFIX_BYTES,
                        )
                    except FileNotFoundError:
                        continue
                finally:
                    directory.close()
                matches = _FINALIZED_UTC_NS.findall(prefix)
                if len(matches) != 1:
                    raise BundleCorruptionError(
                        "adaptive manifest lacks one bounded finalization index"
                    )
                index.append((int(matches[0]), name))
            return tuple(sorted(index, reverse=True))
        finally:
            namespace.close()

    def iter_sessions(self) -> Iterator[PublishedAdaptiveHopIqSession]:
        """Validate one published manifest at a time; retain no growing IQ inventory."""
        # Do not turn unreadable or corrupt *published* records into an empty
        # history. Directory discovery ignores only uncommitted manifest absence.
        try:
            os.stat(_NAMESPACE, dir_fd=self._root.fileno(), follow_symlinks=False)
        except FileNotFoundError:
            return
        namespace = self._root.child(_NAMESPACE)
        try:
            for name in sorted(os.listdir(namespace.fileno())):
                if not _IDENTIFIER.fullmatch(name):
                    continue
                info = os.stat(name, dir_fd=namespace.fileno(), follow_symlinks=False)
                if not stat.S_ISDIR(info.st_mode):
                    raise BundleCorruptionError("adaptive session path is not a directory")
                try:
                    session = self.inspect(name)
                except BundleNotFoundError:
                    continue
                yield session
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
        receivers = len(self.session.manifest.receipt.plan.geometry.receiver_ids)
        values = np.frombuffer(raw, dtype="<i2").reshape(chunk.sample_count, receivers, 2)
        self._cached_index = chunk_index
        self._cached_values = values
        return visits, values

    def read_visit_ci16(self, visit_index: int) -> tuple[AdaptiveHopVisitV1, npt.NDArray[np.int16]]:
        if type(visit_index) is not int or not 0 <= visit_index < len(self._visits):
            raise ValueError("adaptive IQ visit does not exist")
        visits_per_chunk = self.session.manifest._visits_per_chunk
        visits, values = self.read_chunk_ci16(visit_index // visits_per_chunk)
        local = visit_index % visits_per_chunk
        count = visits[local].valid_sample_count
        return visits[local], values[local * count : (local + 1) * count]


class AdaptiveHopSessionWriter:
    def __init__(self, directory: PinnedLocalRoot, session_id: str, plan: AdaptiveHopPlanV1):
        self._directory = directory
        self._session_id = session_id
        self._plan = plan
        self._receiver_count = len(plan.geometry.receiver_ids)
        self._bytes_per_sample = self._receiver_count * 4
        self._host_adaptive_version = (
            plan.schema_version if isinstance(plan, HostAdaptiveHopPlanV2) else 0
        )
        self._visits_per_chunk = 4 if self._host_adaptive_version == 3 else 8
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

    def append(self, block: AdaptiveHopVisitBlock | HostAdaptiveHopVisitBlock) -> None:
        self._require_open()
        try:
            visit = AdaptiveHopVisitV1.model_validate(block.evidence)
            g = self._plan.geometry
            e = visit.event
            if (
                (
                    e.visit_index != len(self._visits)
                    if not isinstance(self._plan, HostAdaptiveHopPlanV2)
                    else bool(self._visits) and e.visit_index <= self._visits[-1].event.visit_index
                )
                or e.target != g.profiles[e.target_index].target
                or e.decision.mode != self._plan.policy.mode
                or e.decision.generation != self._plan.policy.generation
                or e.valid_start_counter != e.transition_after_counter + g.transition_guard_samples
                or visit.valid_sample_count != g.valid_visit_samples
                or block.receiver_ids != g.receiver_ids
                or (
                    self._visits
                    and not isinstance(self._plan, HostAdaptiveHopPlanV2)
                    and (
                        e.from_profile_index != self._visits[-1].event.target_index
                        or e.invalid_start_counter != self._visits[-1].valid_end_counter_exclusive
                    )
                )
            ):
                raise ValueError("adaptive IQ visit differs from plan or source order")
            ci16 = receiver_major_complex_to_ci16(
                block.samples.T, self._receiver_count, visit.valid_sample_count
            )
            if self._compressed is None:
                name = f"iq-block-{len(self._chunks):06d}.ci16.zst.partial"
                self._compressed = _CompressedFileWriter(self._directory.io_root / name, level=3)
            payload = memoryview(ci16).cast("B")
            self._compressed.write(payload)
            self._chunk_digest.update(payload)
            self._digest.update(payload)
            self._visits.append(visit)
            self._chunk_visits += 1
            if self._chunk_visits == self._visits_per_chunk:
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
        chunk_model = (
            HostAdaptiveHopIqChunkV3
            if self._host_adaptive_version == 3
            else HostAdaptiveHopIqChunkV2
            if self._host_adaptive_version == 2
            else AdaptiveHopIqChunkV1
        )
        self._chunks.append(
            chunk_model(
                chunk_index=index,
                first_visit_index=first,
                visit_count=count,
                sample_start=first * dwell,
                sample_count=count * dwell,
                relative_path=f"iq-block-{index:06d}.ci16.zst",
                uncompressed_bytes=count * dwell * self._bytes_per_sample,
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
            receipt_model = (
                HostAdaptiveHopReceiptV5
                if getattr(receipt, "schema_version", None) == 5
                else HostAdaptiveHopReceiptV4
                if getattr(receipt, "schema_version", None) == 4
                else HostAdaptiveHopReceiptV3
                if self._host_adaptive_version == 3
                else HostAdaptiveHopReceiptV2
                if self._host_adaptive_version == 2
                else AdaptiveHopReceiptV1
            )
            receipt = receipt_model.model_validate(receipt.model_dump())
            if (
                receipt.session_id != self._session_id
                or receipt.plan != self._plan
                or receipt.visits != tuple(self._visits)
            ):
                raise ValueError("adaptive IQ receipt disagrees with written actual visits")
            self._finish_chunk()
            manifest_model: type[AdaptiveHopIqManifestV1] = (
                HostAdaptiveHopIqManifestV5
                if getattr(receipt, "schema_version", None) == 5
                else HostAdaptiveHopIqManifestV4
                if getattr(receipt, "schema_version", None) == 4
                else HostAdaptiveHopIqManifestV3
                if self._host_adaptive_version == 3
                else HostAdaptiveHopIqManifestV2
                if self._host_adaptive_version == 2
                else AdaptiveHopIqManifestV1
            )
            manifest = manifest_model(
                session_id=self._session_id,
                created_utc_ns=self._created_ns,
                finalized_utc_ns=time.time_ns(),
                receipt=receipt,
                timing=timing,
                chunks=tuple(self._chunks),
                total_sample_count=receipt.valid_sample_count,
                uncompressed_bytes=receipt.valid_sample_count * self._bytes_per_sample,
                compressed_bytes=sum(c.compressed_bytes for c in self._chunks),
                uncompressed_sha256=f"sha256:{self._digest.hexdigest()}",
                compression=CompressionSettingsV1(
                    policy_id=(
                        "adaptive-four-visit-chunks-v1"
                        if self._visits_per_chunk == 4
                        else "adaptive-eight-visit-chunks-v1"
                    ),
                    level=3,
                    target_uncompressed_bytes=(
                        self._plan.geometry.valid_visit_samples
                        * self._visits_per_chunk
                        * self._bytes_per_sample
                    ),
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


class _SpoolingAdaptiveHopSessionWriter(AdaptiveHopSessionWriter):
    """Seal on the capture filesystem, then atomically publish a verified RAID copy."""

    def __init__(
        self, writer: AdaptiveHopSessionWriter, store: AdaptiveHopIqStore, session_id: str
    ) -> None:
        self._writer = writer
        self._store = store
        self._session_id = session_id

    def append(self, block: AdaptiveHopVisitBlock | HostAdaptiveHopVisitBlock) -> None:
        self._writer.append(block)

    def finish(
        self,
        receipt: AdaptiveHopReceiptV1,
        *,
        timing: PersistentHopUtcTimingAuthorityV1 | None,
        queue_telemetry: PersistentHopQueueTelemetryV1 | None = None,
    ) -> PublishedAdaptiveHopIqSession:
        sealed = self._writer.finish(receipt, timing=timing, queue_telemetry=queue_telemetry)
        if self._store._defer_spool_transfer:
            return sealed
        return self._store._transfer_spooled_session(self._session_id)

    def abort(self) -> None:
        self._writer.abort()
