"""Crash-safe, bounded-memory storage for persistent scanner-hop sessions."""

from __future__ import annotations

import hashlib
import os
import queue
import re
import stat
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal, Self
from uuid import uuid4

import numpy as np
import numpy.typing as npt
import zstandard as zstd
from pydantic import Field, model_validator

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.contracts.recording import CompressionSettingsV1
from leo.domain.iq import receiver_major_complex_to_ci16
from leo.scanner.models import ScannerModel
from leo.scanner.persistent_hop import (
    PersistentHopPlanV1,
    PersistentHopSessionReceiptV1,
    PersistentHopVisitV1,
)
from leo.scanner.persistent_hop_ports import PersistentHopVisitBlock
from leo.storage.errors import BundleCorruptionError, BundleNotFoundError, BundleStateError
from leo.storage.uri import BulkUriResolver, confined_path
from leo.storage.writer import _CompressedFileWriter, _fsync_directory, _mkdir_durable

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_MANIFEST_BYTES = 32 * 1024 * 1024
_READ_BUFFER_BYTES = 1024 * 1024


class PersistentHopIqChunkV1(ScannerModel):
    """One independently decompressible sweep-sized IQ shard."""

    schema_version: Literal[1] = 1
    chunk_index: Annotated[int, Field(ge=0)]
    sweep_index: Annotated[int, Field(ge=0)]
    first_visit_index: Annotated[int, Field(ge=0)]
    visit_count: Annotated[int, Field(ge=1, le=8)]
    sample_start: Annotated[int, Field(ge=0)]
    sample_count: Annotated[int, Field(gt=0)]
    relative_path: Annotated[
        str,
        Field(pattern=r"^iq-sweep-[0-9]{6}\.ci16\.zst$"),
    ]
    uncompressed_bytes: Annotated[int, Field(gt=0)]
    compressed_bytes: Annotated[int, Field(gt=0)]
    uncompressed_sha256: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    compressed_sha256: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]


class PersistentHopQueueTelemetryV1(ScannerModel):
    """Bounded host-pipeline pressure observed while draining the radio."""

    schema_version: Literal[1] = 1
    capacity_visits: Annotated[int, Field(gt=0)]
    high_water_visits: Annotated[int, Field(ge=0)]
    enqueue_failure_count: Annotated[int, Field(ge=0)] = 0
    maximum_enqueue_wait_ns: Annotated[int, Field(ge=0)] = 0
    maximum_writer_service_ns: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def _high_water_fits(self) -> Self:
        if self.high_water_visits > self.capacity_visits:
            raise ValueError("persistent-hop queue high-water exceeds capacity")
        return self


class PersistentHopIqSessionManifestV1(ScannerModel):
    """Immutable storage index for all valid IQ from one hopping session."""

    schema_version: Literal[1] = 1
    kind: Literal["starlink_persistent_hop_iq"] = "starlink_persistent_hop_iq"
    session_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
    created_utc_ns: Annotated[int, Field(ge=0)]
    finalized_utc_ns: Annotated[int, Field(ge=0)]
    plan: PersistentHopPlanV1
    receipt: PersistentHopSessionReceiptV1
    receiver_ids: tuple[int, ...]
    sample_format: Literal["ci16_le"] = "ci16_le"
    sample_layout: Literal["sample_receiver_iq"] = "sample_receiver_iq"
    chunks: tuple[PersistentHopIqChunkV1, ...]
    total_sample_count: Annotated[int, Field(ge=0)]
    uncompressed_bytes: Annotated[int, Field(ge=0)]
    compressed_bytes: Annotated[int, Field(ge=0)]
    uncompressed_sha256: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    compression: CompressionSettingsV1
    queue_telemetry: PersistentHopQueueTelemetryV1 | None = None

    @model_validator(mode="after")
    def _content_is_closed(self) -> Self:
        if self.finalized_utc_ns < self.created_utc_ns:
            raise ValueError("persistent-hop IQ finalization precedes creation")
        if self.session_id != self.receipt.session_id or self.plan != self.receipt.plan:
            raise ValueError("persistent-hop IQ identity or plan disagrees with receipt")
        if self.receiver_ids != self.plan.receiver_ids:
            raise ValueError("persistent-hop IQ receiver IDs disagree with plan")

        next_visit = 0
        next_sample = 0
        compressed_bytes = 0
        for index, chunk in enumerate(self.chunks):
            if (
                chunk.chunk_index != index
                or chunk.sweep_index != index
                or chunk.first_visit_index != next_visit
                or chunk.sample_start != next_sample
                or chunk.relative_path != f"iq-sweep-{index:06d}.ci16.zst"
            ):
                raise ValueError("persistent-hop IQ chunks are not contiguous and canonical")
            visits = self.receipt.visits[next_visit : next_visit + chunk.visit_count]
            if len(visits) != chunk.visit_count:
                raise ValueError("persistent-hop IQ chunk references absent visits")
            if any(visit.sweep_index != chunk.sweep_index for visit in visits):
                raise ValueError("persistent-hop IQ chunk crosses a sweep boundary")
            expected_samples = sum(visit.valid_sample_count for visit in visits)
            if chunk.sample_count != expected_samples:
                raise ValueError("persistent-hop IQ chunk sample count disagrees with visits")
            if chunk.uncompressed_bytes != expected_samples * len(self.receiver_ids) * 4:
                raise ValueError("persistent-hop IQ chunk byte count disagrees with geometry")
            next_visit += chunk.visit_count
            next_sample += chunk.sample_count
            compressed_bytes += chunk.compressed_bytes
        if next_visit != len(self.receipt.visits):
            raise ValueError("persistent-hop IQ chunks omit receipt visits")
        if (
            next_sample != self.receipt.valid_sample_count
            or self.total_sample_count != next_sample
            or self.uncompressed_bytes != next_sample * len(self.receiver_ids) * 4
            or self.compressed_bytes != compressed_bytes
        ):
            raise ValueError("persistent-hop IQ terminal accounting disagrees with chunks")
        return self


@dataclass(frozen=True, slots=True)
class PublishedPersistentHopIqSession:
    session_id: str
    path: Path
    uri: str
    manifest: PersistentHopIqSessionManifestV1
    manifest_sha256: str


class PersistentHopStoredCi16Reader:
    """Read valid-only CI16 by the manifest's compact payload coordinate."""

    def __init__(
        self,
        store: PersistentHopIqStore,
        session: PublishedPersistentHopIqSession,
    ) -> None:
        self._store = store
        self._session = session

    @property
    def sample_count(self) -> int:
        return self._session.manifest.total_sample_count

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        return self._session.manifest.receiver_ids

    def read_valid_ci16(
        self,
        sample_start: int,
        sample_count: int,
    ) -> npt.NDArray[np.int16]:
        if sample_start < 0 or sample_count <= 0:
            raise ValueError("persistent-hop valid CI16 range is invalid")
        sample_end = sample_start + sample_count
        if sample_end > self.sample_count:
            raise ValueError("persistent-hop valid CI16 range exceeds the session")

        pieces: list[npt.NDArray[np.int16]] = []
        covered = sample_start
        for chunk in self._session.manifest.chunks:
            chunk_end = chunk.sample_start + chunk.sample_count
            if chunk_end <= sample_start:
                continue
            if chunk.sample_start >= sample_end:
                break
            _visits, values = self._store.read_sweep_ci16(
                self._session,
                chunk.sweep_index,
            )
            local_start = max(sample_start, chunk.sample_start) - chunk.sample_start
            local_end = min(sample_end, chunk_end) - chunk.sample_start
            if chunk.sample_start + local_start != covered:
                raise BundleCorruptionError("persistent-hop valid CI16 range has a gap")
            pieces.append(values[local_start:local_end])
            covered += local_end - local_start
        if covered != sample_end:
            raise BundleCorruptionError("persistent-hop valid CI16 range is incomplete")
        output = np.ascontiguousarray(np.concatenate(pieces, axis=0), dtype="<i2")
        output.setflags(write=False)
        return output


@dataclass(slots=True)
class _OpenSweep:
    writer: _CompressedFileWriter
    sweep_index: int
    first_visit_index: int
    visit_count: int
    sample_start: int
    sample_count: int
    uncompressed_bytes: int
    digest: Any


class PersistentHopSessionWriter:
    """Append valid visits while retaining at most one sweep of writer state."""

    def __init__(
        self,
        store: PersistentHopIqStore,
        session_id: str,
        plan: PersistentHopPlanV1,
        compression: CompressionSettingsV1,
    ) -> None:
        self._store = store
        self.session_id = session_id
        self.plan = plan
        self.compression = compression
        self._spool_path = store.spool_root / (
            f"{session_id}.{os.getpid()}.{uuid4().hex}.persistent-hop.partial"
        )
        self._spool_path.mkdir(exist_ok=False)
        _fsync_directory(store.spool_root)
        self._created_utc_ns = time.time_ns()
        self._visits: list[PersistentHopVisitV1] = []
        self._chunks: list[PersistentHopIqChunkV1] = []
        self._current: _OpenSweep | None = None
        self._total_samples = 0
        self._uncompressed_digest = hashlib.sha256()
        self._closed = False

    def append(self, block: PersistentHopVisitBlock) -> None:
        if self._closed:
            raise BundleStateError("persistent-hop session writer is closed")
        evidence = block.evidence
        expected_index = len(self._visits)
        expected_profile = self.plan.profiles[expected_index % len(self.plan.profiles)]
        if (
            evidence.visit_index != expected_index
            or evidence.sweep_index != expected_index // len(self.plan.profiles)
            or evidence.target_index != expected_profile.target_index
            or evidence.fastlock_profile_index != expected_profile.fastlock_profile_index
            or evidence.target != expected_profile.target
            or evidence.valid_sample_count != self.plan.valid_visit_samples
            or block.receiver_ids != self.plan.receiver_ids
        ):
            raise ValueError("persistent-hop IQ block disagrees with the ordered plan")
        if self._current is None or self._current.sweep_index != evidence.sweep_index:
            self._finish_current_sweep()
            name = f"iq-sweep-{evidence.sweep_index:06d}.ci16.zst"
            self._current = _OpenSweep(
                writer=_CompressedFileWriter(
                    self._spool_path / f"{name}.partial",
                    level=self.compression.level,
                ),
                sweep_index=evidence.sweep_index,
                first_visit_index=expected_index,
                visit_count=0,
                sample_start=self._total_samples,
                sample_count=0,
                uncompressed_bytes=0,
                digest=hashlib.sha256(),
            )
        assert self._current is not None
        ci16 = receiver_major_complex_to_ci16(
            np.asarray(block.samples).T,
            len(block.receiver_ids),
            evidence.valid_sample_count,
        )
        payload = memoryview(ci16).cast("B")
        self._current.writer.write(payload)
        self._current.digest.update(payload)
        self._uncompressed_digest.update(payload)
        self._current.visit_count += 1
        self._current.sample_count += evidence.valid_sample_count
        self._current.uncompressed_bytes += payload.nbytes
        self._total_samples += evidence.valid_sample_count
        self._visits.append(evidence)

    def finish(
        self,
        receipt: PersistentHopSessionReceiptV1,
        *,
        queue_telemetry: PersistentHopQueueTelemetryV1 | None = None,
    ) -> PublishedPersistentHopIqSession:
        if self._closed:
            raise BundleStateError("persistent-hop session writer is closed")
        if (
            receipt.session_id != self.session_id
            or receipt.plan != self.plan
            or receipt.visits != tuple(self._visits)
        ):
            raise ValueError("persistent-hop receipt disagrees with appended IQ")
        self._finish_current_sweep()
        manifest = PersistentHopIqSessionManifestV1(
            session_id=self.session_id,
            created_utc_ns=self._created_utc_ns,
            finalized_utc_ns=max(self._created_utc_ns, time.time_ns()),
            plan=self.plan,
            receipt=receipt,
            receiver_ids=self.plan.receiver_ids,
            chunks=tuple(self._chunks),
            total_sample_count=self._total_samples,
            uncompressed_bytes=self._total_samples * len(self.plan.receiver_ids) * 4,
            compressed_bytes=sum(chunk.compressed_bytes for chunk in self._chunks),
            uncompressed_sha256=f"sha256:{self._uncompressed_digest.hexdigest()}",
            compression=self.compression,
            queue_telemetry=queue_telemetry,
        )
        payload = canonical_json_bytes(manifest.model_dump(mode="json"))
        partial_manifest = self._spool_path / "manifest.json.partial"
        with partial_manifest.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(partial_manifest, self._spool_path / "manifest.json")
        _fsync_directory(self._spool_path)

        created = datetime.fromtimestamp(self._created_utc_ns / 1_000_000_000, tz=UTC)
        parent = (
            self._store.bundles_root
            / f"{created.year:04d}"
            / f"{created.month:02d}"
            / f"{created.day:02d}"
        )
        _mkdir_durable(parent, stop=self._store.bundles_root)
        destination = parent / self.session_id
        if destination.exists():
            raise FileExistsError(f"persistent-hop IQ session already exists: {destination}")
        os.rename(self._spool_path, destination)
        _fsync_directory(parent)
        self._closed = True
        return PublishedPersistentHopIqSession(
            session_id=self.session_id,
            path=destination,
            uri=self._store.resolver.uri_for(destination),
            manifest=manifest,
            manifest_sha256=sha256_digest(payload),
        )

    def abort(self) -> None:
        """Close the current compressor and preserve unpublished evidence."""

        if self._closed:
            return
        if self._current is not None:
            self._current.writer.abort()
        self._closed = True

    def _finish_current_sweep(self) -> None:
        current = self._current
        if current is None:
            return
        path, compressed_bytes, compressed_sha256 = current.writer.finish()
        self._chunks.append(
            PersistentHopIqChunkV1(
                chunk_index=len(self._chunks),
                sweep_index=current.sweep_index,
                first_visit_index=current.first_visit_index,
                visit_count=current.visit_count,
                sample_start=current.sample_start,
                sample_count=current.sample_count,
                relative_path=path.name,
                uncompressed_bytes=current.uncompressed_bytes,
                compressed_bytes=compressed_bytes,
                uncompressed_sha256=f"sha256:{current.digest.hexdigest()}",
                compressed_sha256=compressed_sha256,
            )
        )
        self._current = None


class QueuedPersistentHopSessionWriter:
    """Move CI16 conversion and compression off the radio-drain thread."""

    _STOP = object()

    def __init__(
        self,
        writer: PersistentHopSessionWriter,
        *,
        capacity_visits: int = 8,
    ) -> None:
        if capacity_visits <= 0:
            raise ValueError("persistent-hop queue capacity must be positive")
        self._writer = writer
        self._capacity = capacity_visits
        self._queue: queue.Queue[PersistentHopVisitBlock | object] = queue.Queue(
            maxsize=capacity_visits
        )
        self._high_water = 0
        self._enqueue_failures = 0
        self._maximum_enqueue_wait_ns = 0
        self._maximum_writer_service_ns = 0
        self._error: BaseException | None = None
        self._closed = False
        self._worker = threading.Thread(
            target=self._run,
            name=f"leo-hop-store-{writer.session_id}",
            daemon=True,
        )
        self._worker.start()

    @property
    def telemetry(self) -> PersistentHopQueueTelemetryV1:
        return PersistentHopQueueTelemetryV1(
            capacity_visits=self._capacity,
            high_water_visits=self._high_water,
            enqueue_failure_count=self._enqueue_failures,
            maximum_enqueue_wait_ns=self._maximum_enqueue_wait_ns,
            maximum_writer_service_ns=self._maximum_writer_service_ns,
        )

    def append(self, block: PersistentHopVisitBlock) -> None:
        if self._closed:
            raise BundleStateError("queued persistent-hop writer is closed")
        self._raise_worker_error()
        started = time.perf_counter_ns()
        self._put(block)
        self._maximum_enqueue_wait_ns = max(
            self._maximum_enqueue_wait_ns,
            time.perf_counter_ns() - started,
        )
        self._high_water = max(self._high_water, self._queue.qsize())

    def finish(
        self,
        receipt: PersistentHopSessionReceiptV1,
    ) -> PublishedPersistentHopIqSession:
        if self._closed:
            raise BundleStateError("queued persistent-hop writer is closed")
        try:
            self._put(self._STOP)
            self._worker.join()
            self._raise_worker_error()
            published = self._writer.finish(receipt, queue_telemetry=self.telemetry)
        except Exception:
            self._writer.abort()
            self._closed = True
            raise
        self._closed = True
        return published

    def abort(self) -> None:
        if self._closed:
            return
        if self._worker.is_alive():
            with suppress(Exception):
                self._put(self._STOP)
            self._worker.join()
        self._writer.abort()
        self._closed = True

    def _put(self, item: PersistentHopVisitBlock | object) -> None:
        while True:
            self._raise_worker_error()
            try:
                self._queue.put(item, timeout=0.1)
                return
            except queue.Full:
                self._enqueue_failures += 1

    def _run(self) -> None:
        try:
            while True:
                item = self._queue.get()
                try:
                    if item is self._STOP:
                        return
                    started = time.perf_counter_ns()
                    self._writer.append(item)  # type: ignore[arg-type]
                    self._maximum_writer_service_ns = max(
                        self._maximum_writer_service_ns,
                        time.perf_counter_ns() - started,
                    )
                finally:
                    self._queue.task_done()
        except BaseException as error:
            self._error = error

    def _raise_worker_error(self) -> None:
        if self._error is not None:
            raise BundleStateError(
                f"persistent-hop storage worker failed: {type(self._error).__name__}: {self._error}"
            ) from self._error


class PersistentHopIqStore:
    """Own immutable persistent-hop IQ sessions below one local bulk root."""

    def __init__(self, root: Path) -> None:
        if root == Path("/mnt/qnap01") or str(root).startswith("/mnt/qnap01/"):
            raise ValueError("persistent-hop IQ cannot be written beneath QNAP")
        root.mkdir(parents=True, exist_ok=True)
        self.root = root.resolve(strict=True)
        self.spool_root = self.root / "spool"
        self.bundles_root = self.root / "scanner-hop-recordings"
        self.spool_root.mkdir(exist_ok=True)
        self.bundles_root.mkdir(exist_ok=True)
        if os.stat(self.spool_root).st_dev != os.stat(self.bundles_root).st_dev:
            raise ValueError("persistent-hop spool and bundle roots must share one filesystem")
        self.resolver = BulkUriResolver(
            self.root,
            allowed_namespaces=("scanner-hop-recordings",),
        )

    def begin(
        self,
        session_id: str,
        plan: PersistentHopPlanV1,
        *,
        compression: CompressionSettingsV1 | None = None,
    ) -> PersistentHopSessionWriter:
        if not _IDENTIFIER.fullmatch(session_id):
            raise ValueError("persistent-hop session ID is not safe")
        selected = compression or CompressionSettingsV1(policy_id="zstd-128m-v1")
        return PersistentHopSessionWriter(self, session_id, plan, selected)

    def begin_queued(
        self,
        session_id: str,
        plan: PersistentHopPlanV1,
        *,
        compression: CompressionSettingsV1 | None = None,
        capacity_visits: int = 8,
    ) -> QueuedPersistentHopSessionWriter:
        return QueuedPersistentHopSessionWriter(
            self.begin(session_id, plan, compression=compression),
            capacity_visits=capacity_visits,
        )

    def inspect(self, session_id: str) -> PublishedPersistentHopIqSession:
        if not _IDENTIFIER.fullmatch(session_id):
            raise ValueError("persistent-hop session ID is not safe")
        matches = tuple(self.bundles_root.glob(f"*/*/*/{session_id}"))
        if not matches:
            raise BundleNotFoundError(f"persistent-hop IQ session does not exist: {session_id}")
        if len(matches) != 1:
            raise BundleCorruptionError(
                f"persistent-hop IQ session appears more than once: {session_id}"
            )
        path = confined_path(self.bundles_root, matches[0], must_exist=True)
        payload = self._read_regular(path / "manifest.json", _MAX_MANIFEST_BYTES)
        try:
            manifest = PersistentHopIqSessionManifestV1.model_validate_json(payload)
        except Exception as error:
            raise BundleCorruptionError(f"invalid persistent-hop IQ manifest: {error}") from error
        if manifest.session_id != session_id:
            raise BundleCorruptionError("persistent-hop manifest session ID disagrees with path")
        return PublishedPersistentHopIqSession(
            session_id=session_id,
            path=path,
            uri=self.resolver.uri_for(path),
            manifest=manifest,
            manifest_sha256=sha256_digest(payload),
        )

    def read_sweep_ci16(
        self,
        session: PublishedPersistentHopIqSession | str,
        sweep_index: int,
        *,
        verify: bool = True,
    ) -> tuple[tuple[PersistentHopVisitV1, ...], npt.NDArray[np.int16]]:
        inspected = self.inspect(session) if isinstance(session, str) else session
        try:
            chunk = inspected.manifest.chunks[sweep_index]
        except IndexError as error:
            raise KeyError(f"persistent-hop sweep does not exist: {sweep_index}") from error
        path = confined_path(inspected.path, inspected.path / chunk.relative_path, must_exist=True)
        compressed = self._read_regular(path, chunk.compressed_bytes)
        if len(compressed) != chunk.compressed_bytes:
            raise BundleCorruptionError("persistent-hop compressed byte count changed")
        if verify and sha256_digest(compressed) != chunk.compressed_sha256:
            raise BundleCorruptionError("persistent-hop compressed digest mismatch")
        try:
            with zstd.ZstdDecompressor().stream_reader(compressed) as reader:
                raw = reader.read(chunk.uncompressed_bytes + 1)
        except zstd.ZstdError as error:
            raise BundleCorruptionError(f"persistent-hop decompression failed: {error}") from error
        if len(raw) != chunk.uncompressed_bytes:
            raise BundleCorruptionError("persistent-hop uncompressed byte count changed")
        if verify and sha256_digest(raw) != chunk.uncompressed_sha256:
            raise BundleCorruptionError("persistent-hop uncompressed digest mismatch")
        values = np.frombuffer(raw, dtype="<i2").reshape(
            chunk.sample_count,
            len(inspected.manifest.receiver_ids),
            2,
        )
        values.setflags(write=False)
        start = chunk.first_visit_index
        visits = inspected.manifest.receipt.visits[start : start + chunk.visit_count]
        return visits, values

    def valid_ci16_reader(
        self,
        session: PublishedPersistentHopIqSession | str,
    ) -> PersistentHopStoredCi16Reader:
        inspected = self.inspect(session) if isinstance(session, str) else session
        return PersistentHopStoredCi16Reader(self, inspected)

    @staticmethod
    def _read_regular(path: Path, maximum_bytes: int) -> bytes:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise BundleCorruptionError("persistent-hop bundle member is not one regular file")
            if before.st_size > maximum_bytes:
                raise BundleCorruptionError(
                    "persistent-hop bundle member exceeds its declared bound"
                )
            chunks: list[bytes] = []
            remaining = maximum_bytes + 1
            while remaining:
                chunk = os.read(descriptor, min(_READ_BUFFER_BYTES, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            after = os.fstat(descriptor)
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ):
                raise BundleCorruptionError("persistent-hop bundle member changed while reading")
            return b"".join(chunks)
        finally:
            os.close(descriptor)
