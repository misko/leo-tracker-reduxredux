"""Inspection, reconciliation, verification, and exact reads for recording bundles."""

from __future__ import annotations

import hashlib
import io
import os
import re
import stat
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import numpy.typing as npt
import zstandard as zstd
from pydantic import ValidationError

from leo.contracts.digests import sha256_digest
from leo.contracts.radio import IqBlockMetadataV1
from leo.contracts.recording import (
    CompressionSettingsV1,
    RecordingChunkV1,
    RecordingManifestV1,
    RecordingStreamV1,
)
from leo.contracts.states import ContinuityStatus
from leo.domain.iq import IqBlock
from leo.storage.errors import (
    BundleCorruptionError,
    BundleNotFoundError,
    PathConfinementError,
)
from leo.storage.uri import BulkUriResolver, confined_path
from leo.storage.writer import FailureInjector, PublishedBundle, RecordingBundleWriter

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_MANIFEST_BYTES = 16 * 1024 * 1024
_VERIFY_BUFFER_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class VerificationReport:
    session_id: str
    chunk_count: int
    compressed_bytes: int
    uncompressed_bytes: int
    timeline_count: int


@dataclass(frozen=True, slots=True)
class ReconcileIssue:
    path: Path
    error: str


@dataclass(frozen=True, slots=True)
class ReconcileReport:
    committed: tuple[PublishedBundle, ...]
    issues: tuple[ReconcileIssue, ...]


class RecordingStore:
    """Own the public recording namespace beneath one local bulk root."""

    def __init__(
        self,
        root: Path,
        *,
        failure_injector: FailureInjector | None = None,
    ) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.root = root.resolve(strict=True)
        self.spool_root = self.root / "spool"
        self.recordings_root = self.root / "recordings"
        self.spool_root.mkdir(exist_ok=True)
        self.recordings_root.mkdir(exist_ok=True)
        if os.stat(self.spool_root).st_dev != os.stat(self.recordings_root).st_dev:
            raise ValueError("spool and recording roots must share one filesystem")
        self.resolver = BulkUriResolver(self.root)
        self._failure_injector = failure_injector

    @classmethod
    def open_read_only(cls, root: Path) -> RecordingStore:
        """Open an existing store without creating or changing filesystem objects.

        Qualification auditors use the ordinary inspection and digest-verification
        implementation, but must not acquire the writer's create-on-open behavior.
        """

        canonical = root.resolve(strict=True)
        if not canonical.is_dir():
            raise ValueError("recording-store root is not a directory")
        spool_root = canonical / "spool"
        recordings_root = canonical / "recordings"
        if not spool_root.is_dir() or not recordings_root.is_dir():
            raise ValueError("existing recording store requires spool and recordings directories")
        if os.stat(spool_root).st_dev != os.stat(recordings_root).st_dev:
            raise ValueError("spool and recording roots must share one filesystem")

        store = cls.__new__(cls)
        store.root = canonical
        store.spool_root = spool_root
        store.recordings_root = recordings_root
        store.resolver = BulkUriResolver(canonical, create=False)
        store._failure_injector = None
        return store

    def begin(
        self,
        session_id: str,
        compression: CompressionSettingsV1,
        *,
        failure_injector: FailureInjector | None = None,
    ) -> RecordingBundleWriter:
        return RecordingBundleWriter(
            self.root,
            session_id=session_id,
            compression=compression,
            resolver=self.resolver,
            failure_injector=(
                self._failure_injector if failure_injector is None else failure_injector
            ),
        )

    def resolve_uri(self, uri: str, *, must_exist: bool = True) -> Path:
        return self.resolver.resolve(uri, must_exist=must_exist)

    def reader(
        self,
        bundle: PublishedBundle | str,
        stream_id: str,
        *,
        verify: bool = True,
    ) -> RecordingIqReader:
        inspected = self.inspect(bundle) if isinstance(bundle, str) else bundle
        return RecordingIqReader(self, inspected, stream_id, verify=verify)

    def inspect(self, session_id: str) -> PublishedBundle:
        if not _IDENTIFIER.fullmatch(session_id):
            raise ValueError("session ID is not one safe persisted identifier")
        matches = tuple(self.recordings_root.glob(f"*/*/*/{session_id}"))
        if not matches:
            raise BundleNotFoundError(f"recording session does not exist: {session_id}")
        if len(matches) > 1:
            raise BundleCorruptionError(f"recording session appears more than once: {session_id}")
        return self._inspect_path(matches[0])

    def inspect_uri(self, uri: str) -> PublishedBundle:
        path = self.resolver.resolve(uri, must_exist=True)
        try:
            relative = path.relative_to(self.recordings_root)
        except ValueError as error:
            raise PathConfinementError("URI does not identify a recording bundle") from error
        if len(relative.parts) != 4 or not path.is_dir():
            raise PathConfinementError("URI must identify one dated recording directory")
        return self._inspect_path(path)

    def reconcile(self) -> ReconcileReport:
        committed: list[PublishedBundle] = []
        issues: list[ReconcileIssue] = []
        for path in sorted(self.recordings_root.glob("*/*/*/*")):
            try:
                committed.append(self._inspect_path(path))
            except (OSError, RecordingStoreInspectionError, ValidationError) as error:
                issues.append(ReconcileIssue(path=path, error=f"{type(error).__name__}: {error}"))
        return ReconcileReport(committed=tuple(committed), issues=tuple(issues))

    def verify(self, bundle: PublishedBundle | str) -> VerificationReport:
        inspected = self.inspect(bundle) if isinstance(bundle, str) else bundle
        chunk_count = 0
        compressed_bytes = 0
        uncompressed_bytes = 0
        timeline_count = 0
        for stream in inspected.manifest.streams:
            for chunk in stream.chunks:
                self._decompress_chunk(inspected.path, stream, chunk, verify=True)
                chunk_count += 1
                compressed_bytes += chunk.compressed_bytes
                uncompressed_bytes += chunk.uncompressed_bytes
            if stream.timeline_relative_path is not None:
                timeline = _bundle_file(inspected.path, stream.timeline_relative_path)
                _verify_file_digest(timeline, stream.timeline_sha256)
                timeline_count += 1
        return VerificationReport(
            session_id=inspected.session_id,
            chunk_count=chunk_count,
            compressed_bytes=compressed_bytes,
            uncompressed_bytes=uncompressed_bytes,
            timeline_count=timeline_count,
        )

    def read_ci16(
        self,
        bundle: PublishedBundle | str,
        stream_id: str,
        sample_start: int,
        sample_count: int,
        *,
        receiver_ids: tuple[int, ...] | None = None,
        verify: bool = True,
    ) -> npt.NDArray[np.int16]:
        inspected = self.inspect(bundle) if isinstance(bundle, str) else bundle
        stream = _manifest_stream(inspected.manifest, stream_id)
        if sample_start < 0 or sample_count < 0:
            raise ValueError("sample range cannot be negative")
        sample_end = sample_start + sample_count
        if sample_end > stream.captured_sample_count:
            raise ValueError("sample range exceeds the captured stream")
        storage_settings = stream.applied_settings or stream.requested_settings
        actual_receivers = storage_settings.receiver_ids
        selected = actual_receivers if receiver_ids is None else receiver_ids
        if not selected or len(set(selected)) != len(selected):
            raise ValueError("selected receivers must be non-empty and unique")
        try:
            receiver_columns = tuple(actual_receivers.index(receiver) for receiver in selected)
        except ValueError as error:
            raise ValueError("selected receiver is absent from the stream") from error
        if sample_count == 0:
            return np.empty((0, len(selected), 2), dtype="<i2")

        pieces: list[npt.NDArray[np.int16]] = []
        for chunk in stream.chunks:
            chunk_end = chunk.sample_start + chunk.sample_count
            overlap_start = max(sample_start, chunk.sample_start)
            overlap_end = min(sample_end, chunk_end)
            if overlap_start >= overlap_end:
                continue
            payload = self._decompress_chunk(inspected.path, stream, chunk, verify=verify)
            values = np.frombuffer(payload, dtype="<i2").reshape(
                chunk.sample_count,
                len(actual_receivers),
                2,
            )
            local_start = overlap_start - chunk.sample_start
            local_end = overlap_end - chunk.sample_start
            pieces.append(values[local_start:local_end, receiver_columns, :].copy())
        if not pieces or sum(piece.shape[0] for piece in pieces) != sample_count:
            raise BundleCorruptionError("chunk inventory did not cover the requested sample range")
        if len(pieces) == 1:
            return pieces[0]
        return np.concatenate(pieces, axis=0, dtype=np.dtype("<i2"))

    def _inspect_path(self, path: Path) -> PublishedBundle:
        try:
            bundle_path = confined_path(self.recordings_root, path, must_exist=True)
        except (FileNotFoundError, PathConfinementError) as error:
            raise RecordingStoreInspectionError(str(error)) from error
        if not bundle_path.is_dir():
            raise RecordingStoreInspectionError("recording bundle path is not a directory")
        manifest_path = _bundle_file(bundle_path, "manifest.json")
        size = manifest_path.stat().st_size
        if size <= 0 or size > _MAX_MANIFEST_BYTES:
            raise RecordingStoreInspectionError("recording manifest size is invalid")
        payload = manifest_path.read_bytes()
        try:
            manifest = RecordingManifestV1.model_validate_json(payload)
        except ValidationError as error:
            raise RecordingStoreInspectionError(
                f"recording manifest is invalid: {error}"
            ) from error
        if manifest.session_id != bundle_path.name:
            raise RecordingStoreInspectionError("manifest session ID disagrees with its directory")
        try:
            created = datetime.fromtimestamp(
                manifest.created_utc_ns // 1_000_000_000,
                tz=UTC,
            )
        except (OSError, OverflowError, ValueError) as error:
            raise RecordingStoreInspectionError(
                "manifest creation time is outside the supported UTC range"
            ) from error
        expected_date = (f"{created.year:04d}", f"{created.month:02d}", f"{created.day:02d}")
        relative = bundle_path.relative_to(self.recordings_root)
        if relative.parts[:3] != expected_date or len(relative.parts) != 4:
            raise RecordingStoreInspectionError("recording directory date disagrees with manifest")
        for stream in manifest.streams:
            for chunk in stream.chunks:
                chunk_path = _bundle_file(bundle_path, chunk.relative_path)
                if not _is_regular_file(chunk_path):
                    raise RecordingStoreInspectionError(
                        f"chunk is not a regular file: {chunk_path}"
                    )
                if chunk_path.stat().st_size != chunk.compressed_bytes:
                    raise RecordingStoreInspectionError(
                        f"compressed chunk size disagrees with manifest: {chunk_path}"
                    )
            if stream.timeline_relative_path is not None:
                timeline = _bundle_file(bundle_path, stream.timeline_relative_path)
                if not _is_regular_file(timeline):
                    raise RecordingStoreInspectionError(
                        f"timeline is not a regular file: {timeline}"
                    )
        return PublishedBundle(
            session_id=manifest.session_id,
            path=bundle_path,
            uri=self.resolver.uri_for(bundle_path),
            manifest=manifest,
            manifest_sha256=sha256_digest(payload),
        )

    def _decompress_chunk(
        self,
        bundle_path: Path,
        stream: RecordingStreamV1,
        chunk: RecordingChunkV1,
        *,
        verify: bool,
    ) -> bytes:
        path = _bundle_file(bundle_path, chunk.relative_path)
        try:
            compressed = path.read_bytes()
        except OSError as error:
            raise BundleCorruptionError(f"cannot read compressed chunk {path}: {error}") from error
        if len(compressed) != chunk.compressed_bytes:
            raise BundleCorruptionError(f"compressed chunk size mismatch: {path}")
        if verify and sha256_digest(compressed) != chunk.compressed_sha256:
            raise BundleCorruptionError(f"compressed chunk digest mismatch: {path}")
        try:
            payload = zstd.ZstdDecompressor().decompress(
                compressed,
                max_output_size=chunk.uncompressed_bytes,
            )
        except zstd.ZstdError as error:
            raise BundleCorruptionError(f"cannot decompress chunk {path}: {error}") from error
        if len(payload) != chunk.uncompressed_bytes:
            raise BundleCorruptionError(f"uncompressed chunk size mismatch: {path}")
        if verify and sha256_digest(payload) != chunk.uncompressed_sha256:
            raise BundleCorruptionError(f"uncompressed chunk digest mismatch: {path}")
        settings = stream.applied_settings
        if settings is None:
            raise BundleCorruptionError("stored IQ stream has no applied radio settings")
        expected_bytes = chunk.sample_count * len(settings.receiver_ids) * 4
        if len(payload) != expected_bytes:
            raise BundleCorruptionError(f"chunk sample geometry mismatch: {path}")
        return payload


class RecordingStoreInspectionError(BundleCorruptionError):
    pass


class RecordingIqReader:
    """Bounded reader that structurally implements the analyzer ``IqReader`` port."""

    def __init__(
        self,
        store: RecordingStore,
        bundle: PublishedBundle,
        stream_id: str,
        *,
        verify: bool,
    ) -> None:
        self._store = store
        self._bundle = bundle
        self._stream = _manifest_stream(bundle.manifest, stream_id)
        self._verify = verify

    @property
    def sample_rate_hz(self) -> int:
        settings = self._stream.applied_settings or self._stream.requested_settings
        return settings.sample_rate_hz

    @property
    def center_frequency_hz(self) -> int:
        settings = self._stream.applied_settings or self._stream.requested_settings
        return settings.center_frequency_hz

    @property
    def sample_count(self) -> int:
        return self._stream.captured_sample_count

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        settings = self._stream.applied_settings or self._stream.requested_settings
        return settings.receiver_ids

    def read(
        self,
        sample_start: int,
        sample_count: int,
        *,
        receiver_ids: tuple[int, ...] | None = None,
    ) -> npt.NDArray[np.int16]:
        return self._store.read_ci16(
            self._bundle,
            self._stream.stream_id,
            sample_start,
            sample_count,
            receiver_ids=receiver_ids,
            verify=self._verify,
        )

    def iter_blocks(self, *, block_samples: int) -> Iterator[IqBlock]:
        """Yield original refill evidence, splitting oversized refills if necessary."""

        if block_samples <= 0:
            raise ValueError("block_samples must be positive")
        timeline = self._timeline_metadata()
        chunk_index = 0
        chunk_values: npt.NDArray[np.int16] | None = None
        chunk: RecordingChunkV1 | None = None
        expected_start = 0
        for metadata in timeline:
            if metadata.radio_id != self._stream.radio.radio_id:
                raise BundleCorruptionError("timeline radio ID disagrees with its stream")
            if metadata.receiver_ids != self.receiver_ids:
                raise BundleCorruptionError("timeline receiver IDs disagree with its stream")
            if metadata.session_sample_start != expected_start:
                raise BundleCorruptionError("timeline sample coordinates are not contiguous")
            expected_start += metadata.sample_count

            while chunk is None or metadata.session_sample_start >= (
                chunk.sample_start + chunk.sample_count
            ):
                if chunk_index >= len(self._stream.chunks):
                    raise BundleCorruptionError("timeline extends beyond the chunk inventory")
                chunk = self._stream.chunks[chunk_index]
                payload = self._store._decompress_chunk(
                    self._bundle.path,
                    self._stream,
                    chunk,
                    verify=self._verify,
                )
                chunk_values = np.frombuffer(payload, dtype="<i2").reshape(
                    chunk.sample_count,
                    len(self.receiver_ids),
                    2,
                )
                chunk_index += 1
            assert chunk is not None and chunk_values is not None
            metadata_end = metadata.session_sample_start + metadata.sample_count
            if (
                metadata.session_sample_start < chunk.sample_start
                or metadata_end > chunk.sample_start + chunk.sample_count
            ):
                raise BundleCorruptionError("one timeline refill crosses a shard boundary")
            local_start = metadata.session_sample_start - chunk.sample_start
            for offset in range(0, metadata.sample_count, block_samples):
                count = min(block_samples, metadata.sample_count - offset)
                values = chunk_values[local_start + offset : local_start + offset + count].copy()
                derived = _slice_metadata(metadata, offset=offset, sample_count=count)
                yield IqBlock(samples=values, metadata=derived)
        if expected_start != self.sample_count:
            raise BundleCorruptionError("timeline does not cover the captured sample count")

    def _timeline_metadata(self) -> Iterator[IqBlockMetadataV1]:
        relative_path = self._stream.timeline_relative_path
        if relative_path is None:
            raise BundleCorruptionError("data stream has no timeline")
        path = _bundle_file(self._bundle.path, relative_path)
        if self._verify:
            _verify_file_digest(path, self._stream.timeline_sha256)
        try:
            with (
                path.open("rb") as source,
                zstd.ZstdDecompressor().stream_reader(source) as decompressed,
                io.TextIOWrapper(decompressed, encoding="utf-8") as text,
            ):
                for line_number, line in enumerate(text, start=1):
                    if not line.strip():
                        raise BundleCorruptionError(
                            f"timeline contains an empty record at line {line_number}"
                        )
                    try:
                        yield IqBlockMetadataV1.model_validate_json(line)
                    except ValidationError as error:
                        raise BundleCorruptionError(
                            f"timeline record {line_number} is invalid: {error}"
                        ) from error
        except (OSError, UnicodeError, zstd.ZstdError) as error:
            raise BundleCorruptionError(f"cannot read timeline {path}: {error}") from error


def _manifest_stream(manifest: RecordingManifestV1, stream_id: str) -> RecordingStreamV1:
    matches = tuple(stream for stream in manifest.streams if stream.stream_id == stream_id)
    if len(matches) != 1:
        raise BundleNotFoundError(f"manifest has no unique stream {stream_id!r}")
    return matches[0]


def _slice_metadata(
    metadata: IqBlockMetadataV1,
    *,
    offset: int,
    sample_count: int,
) -> IqBlockMetadataV1:
    document = metadata.model_dump(mode="json")
    document.update(
        {
            "sample_count": sample_count,
            "session_sample_start": metadata.session_sample_start + offset,
            "device_sample_counter": (
                None
                if metadata.device_sample_counter is None
                else metadata.device_sample_counter + offset
            ),
        }
    )
    if offset:
        document.update(
            {
                "continuity": ContinuityStatus.CONTIGUOUS.value,
                "missing_samples_before": 0,
                "overflow_observed": False,
                "hardware_metadata": {
                    **metadata.hardware_metadata,
                    "storage_subblock_offset": offset,
                },
            }
        )
    return IqBlockMetadataV1.model_validate(document)


def _bundle_file(bundle_path: Path, relative_path: str) -> Path:
    try:
        path = confined_path(bundle_path, bundle_path / relative_path, must_exist=True)
    except (FileNotFoundError, PathConfinementError) as error:
        raise RecordingStoreInspectionError(
            f"bundle file is absent or escapes its recording: {relative_path}"
        ) from error
    if not _is_regular_file(path):
        raise RecordingStoreInspectionError(f"bundle object is not a regular file: {path}")
    return path


def _is_regular_file(path: Path) -> bool:
    try:
        return stat.S_ISREG(os.lstat(path).st_mode)
    except FileNotFoundError:
        return False


def _verify_file_digest(path: Path, expected: str | None) -> None:
    if expected is None:
        raise BundleCorruptionError(f"file has no declared digest: {path}")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while payload := stream.read(_VERIFY_BUFFER_BYTES):
                digest.update(payload)
    except OSError as error:
        raise BundleCorruptionError(f"cannot verify file {path}: {error}") from error
    actual = f"sha256:{digest.hexdigest()}"
    if actual != expected:
        raise BundleCorruptionError(f"file digest mismatch: {path}")
