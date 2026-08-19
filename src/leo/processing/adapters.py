"""Concrete adapters connecting processing ports to recording and artifact stores."""

from __future__ import annotations

import hashlib
import io
import os
import stat
import time
import weakref
from collections import OrderedDict
from collections.abc import Buffer, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol, cast
from urllib.parse import unquote, urlsplit

import numpy as np
import zstandard as zstd
from pydantic import JsonValue, ValidationError

from leo.artifacts import AnalysisArtifactStore
from leo.catalog import CaptureRecordingIdentity, CatalogRepository, RunExecutionInfo
from leo.contracts.digests import canonical_digest, sha256_digest
from leo.contracts.radio import IqBlockMetadataV1
from leo.contracts.recording import RecordingChunkV1, RecordingManifestV1
from leo.contracts.states import ContinuityStatus
from leo.domain.iq import IqBlock
from leo.pipeline import (
    IqReader,
    ProductReader,
    ProductRequirement,
    RawIntegrityAttestationV1,
    RawStreamIntegrityV1,
    ScopeIdentityV1,
    ScopeKind,
    UpstreamJsonProduct,
)
from leo.storage import PinnedLocalRoot, RecordingStore, parse_recording_bundle_uri
from leo.storage.errors import BundleCorruptionError
from leo.storage.writer import PublishedBundle


class InputManifestMismatchError(RuntimeError):
    """The recording at a catalog URI is not the run's pinned input."""


class IqReaderProvider(Protocol):
    def open(self, execution: RunExecutionInfo, scope_key: str) -> IqReader: ...

    def open_scope(self, execution: RunExecutionInfo, scope: ScopeIdentityV1) -> IqReader: ...

    def verify_integrity(self, identity: CaptureRecordingIdentity) -> RawIntegrityAttestationV1: ...

    def verified_manifest(self, attestation_digest: str) -> RecordingManifestV1: ...

    def close(self) -> None: ...


class RecordingIqReaderProvider:
    """Resolve one job scope to a real compressed recording stream."""

    _MAX_RETAINED_BUNDLES = 8

    def __init__(
        self,
        recordings: RecordingStore,
        *,
        verify: bool = True,
        allow_unpinned_integrity_for_tests: bool = False,
    ) -> None:
        self._recordings = recordings
        self._verify = verify
        self._allow_unpinned_integrity_for_tests = allow_unpinned_integrity_for_tests
        self._capabilities: OrderedDict[
            tuple[str, str], _VerifiedBundleCapability
        ] = OrderedDict()
        self._attestation_keys: OrderedDict[str, tuple[str, str]] = OrderedDict()

    @property
    def recordings(self) -> RecordingStore:
        return self._recordings

    @property
    def verifies_digests(self) -> bool:
        return self._verify

    def open(self, execution: RunExecutionInfo, scope_key: str) -> IqReader:
        bundle = self._recordings.inspect_uri(execution.bundle_uri)
        if bundle.manifest_sha256 != execution.input_manifest_digest:
            raise InputManifestMismatchError(
                "recording manifest digest disagrees with analysis run input: "
                f"{bundle.manifest_sha256} != {execution.input_manifest_digest}"
            )
        return self._recordings.reader(bundle, scope_key, verify=self._verify)

    def open_scope(self, execution: RunExecutionInfo, scope: ScopeIdentityV1) -> IqReader:
        if scope.kind is not ScopeKind.RECEIVER_PATH:
            raise ValueError("only receiver_path scopes may open raw IQ")
        if scope.stream_id is None or scope.receiver_id is None:
            raise ValueError("receiver_path scope is incomplete")
        capability = self._typed_capability(execution)
        capability.assert_bound()
        capability.acquire()
        try:
            source = _VerifiedRecordingIqReader(capability, scope.stream_id)
            return _LeasedIqReader(_ReceiverPathReader(source, scope.receiver_id), capability)
        except Exception:
            capability.release()
            raise

    def verify_integrity(self, identity: CaptureRecordingIdentity) -> RawIntegrityAttestationV1:
        if (
            self._recordings.pinned_root_identity is None
            and not self._allow_unpinned_integrity_for_tests
        ):
            raise RuntimeError(
                "typed run creation requires a pinned recording-store integrity authority"
            )
        key = (identity.session_id, identity.manifest_digest)
        capability = self._capabilities.get(key)
        if capability is None:
            capability = self._open_verified_capability(identity)
            for old_key in tuple(self._capabilities):
                if old_key[0] == identity.session_id and old_key != key:
                    self._capabilities.pop(old_key).request_close()
            self._retain_capability(key, capability)
        else:
            _verify_capability_bytes(capability)
            self._capabilities.move_to_end(key)
        bundle = capability.bundle
        streams = []
        for stream in sorted(bundle.manifest.streams, key=lambda item: item.stream_id):
            inventory = [
                {
                    "chunk_index": chunk.chunk_index,
                    "sample_start": chunk.sample_start,
                    "sample_count": chunk.sample_count,
                    "digest": chunk.compressed_sha256,
                }
                for chunk in stream.chunks
            ]
            uncompressed_inventory = [
                {
                    "chunk_index": chunk.chunk_index,
                    "sample_start": chunk.sample_start,
                    "sample_count": chunk.sample_count,
                    "digest": chunk.uncompressed_sha256,
                }
                for chunk in stream.chunks
            ]
            streams.append(
                RawStreamIntegrityV1(
                    stream_id=stream.stream_id,
                    chunk_count=len(stream.chunks),
                    compressed_closure_digest=canonical_digest(inventory),
                    uncompressed_closure_digest=canonical_digest(uncompressed_inventory),
                )
            )
        attestation = RawIntegrityAttestationV1(
            session_id=identity.session_id,
            manifest_digest=identity.manifest_digest,
            streams=tuple(streams),
            verifier_version="recording-store-full-v1",
            verified_utc_ns=time.time_ns(),
        )
        self._attestation_keys[attestation.attestation_digest] = key
        self._attestation_keys.move_to_end(attestation.attestation_digest)
        while len(self._attestation_keys) > 64:
            self._attestation_keys.popitem(last=False)
        return attestation

    def verified_manifest(self, attestation_digest: str) -> RecordingManifestV1:
        key = self._attestation_keys.get(attestation_digest)
        capability = None if key is None else self._capabilities.get(key)
        if capability is None:
            raise InputManifestMismatchError("raw-integrity capability is not retained")
        capability.assert_bound()
        return capability.bundle.manifest

    def _typed_capability(self, execution: RunExecutionInfo) -> _VerifiedBundleCapability:
        digest = execution.raw_integrity_attestation_digest
        document = execution.raw_integrity_attestation
        if digest is None or document is None:
            raise InputManifestMismatchError(
                "typed IQ access requires a persisted raw-integrity attestation"
            )
        attestation = RawIntegrityAttestationV1.model_validate(document)
        if (
            attestation.attestation_digest != digest
            or attestation.session_id != execution.session_id
            or attestation.manifest_digest != execution.input_manifest_digest
        ):
            raise InputManifestMismatchError("persisted raw-integrity attestation is invalid")
        key = (execution.session_id, execution.input_manifest_digest)
        capability = self._capabilities.get(key)
        if capability is not None:
            capability.assert_bound()
            self._capabilities.move_to_end(key)
            return capability

        # Worker restarts intentionally lose process-local descriptors. Re-establish
        # them only by repeating the full verification and comparing the immutable
        # byte closure to the persisted attestation; a database document alone is
        # never treated as a read capability.
        identity = CaptureRecordingIdentity(
            session_id=execution.session_id,
            bundle_uri=execution.bundle_uri,
            manifest_digest=execution.input_manifest_digest,
        )
        capability = self._open_verified_capability(identity)
        bundle = capability.bundle
        current_streams = _stream_integrities(bundle)
        if current_streams != attestation.streams:
            capability.close()
            raise InputManifestMismatchError("recording byte closure changed after run creation")
        self._retain_capability(key, capability)
        self._attestation_keys[digest] = key
        return capability

    def _retain_capability(
        self, key: tuple[str, str], capability: _VerifiedBundleCapability
    ) -> None:
        self._capabilities[key] = capability
        self._capabilities.move_to_end(key)
        while len(self._capabilities) > self._MAX_RETAINED_BUNDLES:
            evicted_key, evicted = self._capabilities.popitem(last=False)
            for digest, mapped_key in tuple(self._attestation_keys.items()):
                if mapped_key == evicted_key:
                    self._attestation_keys.pop(digest)
            evicted.request_close()

    def close(self) -> None:
        capabilities = {id(item): item for item in self._capabilities.values()}
        for capability in capabilities.values():
            capability.request_close()
        self._capabilities.clear()
        self._attestation_keys.clear()

    def _open_verified_capability(
        self, identity: CaptureRecordingIdentity
    ) -> _VerifiedBundleCapability:
        uri_session = parse_recording_bundle_uri(identity.bundle_uri)
        if uri_session != identity.session_id:
            raise InputManifestMismatchError("recording URI session disagrees with catalog")
        try:
            namespace = self._recordings.recording_namespace_capability()
        except RuntimeError:
            if not self._allow_unpinned_integrity_for_tests:
                raise
            namespace = PinnedLocalRoot(self._recordings.recordings_root)
        raw_parts = urlsplit(identity.bundle_uri).path.removeprefix("/").split("/")
        parts = tuple(unquote(item) for item in raw_parts)
        try:
            directory = namespace.child(*parts)
        finally:
            namespace.close()
        manifest_file: _PinnedFile | None = None
        capability: _VerifiedBundleCapability | None = None
        try:
            manifest_file = _PinnedFile.open_at(directory, "manifest.json")
            payload = _read_bounded(manifest_file, maximum_bytes=16 * 1024 * 1024)
            manifest = RecordingManifestV1.model_validate_json(payload)
            manifest_digest = sha256_digest(payload)
            if (
                manifest.session_id != identity.session_id
                or manifest_digest != identity.manifest_digest
            ):
                raise InputManifestMismatchError(
                    "recording manifest identity disagrees with catalog"
                )
            bundle = PublishedBundle(
                session_id=manifest.session_id,
                path=directory.io_root,
                uri=identity.bundle_uri,
                manifest=manifest,
                manifest_sha256=manifest_digest,
            )
            capability = _VerifiedBundleCapability.pin(bundle, directory)
            directory = None  # type: ignore[assignment]
            retained_manifest = _read_bounded(
                capability.file("manifest.json"), maximum_bytes=16 * 1024 * 1024
            )
            if sha256_digest(retained_manifest) != manifest_digest:
                raise InputManifestMismatchError("manifest changed while acquiring capability")
            _verify_capability_bytes(capability)
            capability.assert_bound()
            return capability
        except Exception:
            if capability is not None:
                capability.close()
            if directory is not None:
                directory.close()
            raise
        finally:
            if manifest_file is not None:
                manifest_file.close()


@dataclass(slots=True)
class _PinnedFile:
    label: str
    parent: PinnedLocalRoot
    name: str
    descriptor: int
    identity: tuple[int, int, int]

    @classmethod
    def open_at(cls, bundle: PinnedLocalRoot, relative_path: str) -> _PinnedFile:
        parts = Path(relative_path).parts
        if (
            not parts
            or Path(relative_path).is_absolute()
            or any(part in {"", ".", ".."} for part in parts)
        ):
            raise InputManifestMismatchError("verified input path is unsafe")
        parent = bundle.clone() if len(parts) == 1 else bundle.child(*parts[:-1])
        try:
            descriptor = os.open(
                parts[-1],
                os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                dir_fd=parent.fileno(),
            )
        except Exception:
            parent.close()
            raise
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            os.close(descriptor)
            parent.close()
            raise InputManifestMismatchError(
                f"verified input is not a regular file: {relative_path}"
            )
        return cls(
            relative_path,
            parent,
            parts[-1],
            descriptor,
            (metadata.st_dev, metadata.st_ino, metadata.st_size),
        )

    def assert_bound(self) -> None:
        descriptor_metadata = os.fstat(self.descriptor)
        try:
            path_metadata = os.stat(
                self.name,
                dir_fd=self.parent.fileno(),
                follow_symlinks=False,
            )
        except OSError as error:
            raise InputManifestMismatchError(f"verified input disappeared: {self.label}") from error
        current = (path_metadata.st_dev, path_metadata.st_ino, path_metadata.st_size)
        retained = (
            descriptor_metadata.st_dev,
            descriptor_metadata.st_ino,
            descriptor_metadata.st_size,
        )
        if (
            current != self.identity
            or retained != self.identity
            or not stat.S_ISREG(path_metadata.st_mode)
        ):
            raise InputManifestMismatchError(f"verified input binding changed: {self.label}")

    def close(self) -> None:
        os.close(self.descriptor)
        self.parent.close()

    def open_reader(self) -> io.BufferedReader:
        """Duplicate the retained descriptor; never reopen the mutable pathname."""
        self.assert_bound()
        descriptor = os.dup(self.descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        return cast(io.BufferedReader, os.fdopen(descriptor, "rb"))


def _read_bounded(pinned: _PinnedFile, *, maximum_bytes: int) -> bytes:
    pinned.assert_bound()
    if pinned.identity[2] <= 0 or pinned.identity[2] > maximum_bytes:
        raise InputManifestMismatchError(f"verified input size is invalid: {pinned.label}")
    with pinned.open_reader() as source:
        payload = source.read(maximum_bytes + 1)
    pinned.assert_bound()
    if len(payload) != pinned.identity[2]:
        raise InputManifestMismatchError(f"verified input changed while reading: {pinned.label}")
    return payload


@dataclass(slots=True)
class _VerifiedBundleCapability:
    bundle: PublishedBundle
    directory: PinnedLocalRoot
    files: tuple[_PinnedFile, ...]
    active_readers: int = 0
    close_requested: bool = False

    @classmethod
    def pin(cls, bundle: PublishedBundle, directory: PinnedLocalRoot) -> _VerifiedBundleCapability:
        paths = ["manifest.json"]
        for stream in bundle.manifest.streams:
            paths.extend(chunk.relative_path for chunk in stream.chunks)
            if stream.timeline_relative_path is not None:
                paths.append(stream.timeline_relative_path)
        opened: list[_PinnedFile] = []
        try:
            opened.extend(_PinnedFile.open_at(directory, path) for path in paths)
            capability = cls(bundle=bundle, directory=directory, files=tuple(opened))
            capability.assert_bound()
            return capability
        except Exception:
            for item in opened:
                item.close()
            directory.close()
            raise

    def assert_bound(self) -> None:
        self.directory.assert_open()
        for item in self.files:
            item.assert_bound()

    def close(self) -> None:
        for item in self.files:
            item.close()
        self.directory.close()

    def acquire(self) -> None:
        if self.close_requested:
            raise RuntimeError("verified recording capability is closing")
        self.assert_bound()
        self.active_readers += 1

    def release(self) -> None:
        if self.active_readers <= 0:
            raise RuntimeError("verified recording capability reader count underflow")
        self.active_readers -= 1
        if self.close_requested and self.active_readers == 0:
            self.close()

    def request_close(self) -> None:
        self.close_requested = True
        if self.active_readers == 0:
            self.close()

    def file(self, relative_path: str) -> _PinnedFile:
        matches = tuple(item for item in self.files if item.label == relative_path)
        if len(matches) != 1:
            raise InputManifestMismatchError(
                f"file is absent from verified capability: {relative_path}"
            )
        return matches[0]


class _VerifiedRecordingIqReader:
    """Recording reader whose data source is exclusively the retained verified FDs."""

    def __init__(self, capability: _VerifiedBundleCapability, stream_id: str) -> None:
        self._capability = capability
        streams = tuple(
            item for item in capability.bundle.manifest.streams if item.stream_id == stream_id
        )
        if len(streams) != 1:
            raise ValueError(f"verified manifest has no unique stream {stream_id!r}")
        self._stream = streams[0]

    @property
    def sample_rate_hz(self) -> int:
        self._capability.assert_bound()
        return (self._stream.applied_settings or self._stream.requested_settings).sample_rate_hz

    @property
    def center_frequency_hz(self) -> int:
        self._capability.assert_bound()
        return (
            self._stream.applied_settings or self._stream.requested_settings
        ).center_frequency_hz

    @property
    def sample_count(self) -> int:
        self._capability.assert_bound()
        return self._stream.captured_sample_count

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        self._capability.assert_bound()
        return (self._stream.applied_settings or self._stream.requested_settings).receiver_ids

    def iter_blocks(self, *, block_samples: int) -> Iterable[IqBlock]:
        if block_samples <= 0:
            raise ValueError("block_samples must be positive")
        timeline = self._timeline_metadata()
        chunk_index = 0
        chunk_stream: _RetainedChunkStream | None = None
        chunk: RecordingChunkV1 | None = None
        expected_start = 0
        try:
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
                    if chunk_stream is not None:
                        chunk_stream.finish()
                    if chunk_index >= len(self._stream.chunks):
                        raise BundleCorruptionError("timeline extends beyond chunk inventory")
                    chunk = self._stream.chunks[chunk_index]
                    chunk_stream = _RetainedChunkStream(
                        self._capability.file(chunk.relative_path),
                        chunk,
                        receiver_count=len(self.receiver_ids),
                    )
                    chunk_index += 1
                assert chunk is not None and chunk_stream is not None
                metadata_end = metadata.session_sample_start + metadata.sample_count
                if (
                    metadata.session_sample_start < chunk.sample_start
                    or metadata_end > chunk.sample_start + chunk.sample_count
                ):
                    raise BundleCorruptionError("one timeline refill crosses a shard boundary")
                for offset in range(0, metadata.sample_count, block_samples):
                    count = min(block_samples, metadata.sample_count - offset)
                    yield IqBlock(
                        samples=chunk_stream.read_samples(count),
                        metadata=_slice_metadata(metadata, offset=offset, sample_count=count),
                    )
            if chunk_stream is not None:
                chunk_stream.finish()
                chunk_stream = None
            if expected_start != self.sample_count:
                raise BundleCorruptionError("timeline does not cover captured sample count")
        finally:
            if chunk_stream is not None:
                chunk_stream.close()

    def _timeline_metadata(self) -> Iterable[IqBlockMetadataV1]:
        relative_path = self._stream.timeline_relative_path
        expected_digest = self._stream.timeline_sha256
        if relative_path is None or expected_digest is None:
            raise BundleCorruptionError("data stream has no verified timeline")
        pinned = self._capability.file(relative_path)
        raw = pinned.open_reader()
        digest_source = _DigestingReader(raw)
        try:
            with (
                zstd.ZstdDecompressor().stream_reader(
                    cast(BinaryIO, digest_source), closefd=False
                ) as decompressed,
                io.TextIOWrapper(decompressed, encoding="utf-8") as text_source,
            ):
                for line_number, line in enumerate(text_source, start=1):
                    try:
                        yield IqBlockMetadataV1.model_validate_json(line)
                    except ValidationError as error:
                        raise BundleCorruptionError(
                            f"timeline record {line_number} is invalid"
                        ) from error
            while digest_source.read(1024 * 1024):
                pass
            if digest_source.digest != expected_digest:
                raise BundleCorruptionError("retained timeline digest mismatch")
            pinned.assert_bound()
        except (UnicodeError, zstd.ZstdError) as error:
            raise BundleCorruptionError("cannot read retained timeline") from error
        finally:
            raw.close()


class _DigestingReader(io.RawIOBase):
    def __init__(self, source: io.BufferedReader) -> None:
        super().__init__()
        self._source = source
        self._digest = hashlib.sha256()

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        payload = self._source.read(size)
        self._digest.update(payload)
        return payload

    def readinto(self, buffer: Buffer) -> int:
        count = self._source.readinto(buffer)
        if count:
            self._digest.update(memoryview(buffer)[:count])
        return 0 if count is None else count

    @property
    def digest(self) -> str:
        return f"sha256:{self._digest.hexdigest()}"


class _RetainedChunkStream:
    def __init__(
        self,
        pinned: _PinnedFile,
        chunk: RecordingChunkV1,
        *,
        receiver_count: int,
    ) -> None:
        self._pinned = pinned
        self._chunk = chunk
        self._receiver_count = receiver_count
        self._raw = pinned.open_reader()
        self._compressed = _DigestingReader(self._raw)
        self._decompressed = zstd.ZstdDecompressor().stream_reader(
            cast(BinaryIO, self._compressed), closefd=False
        )
        self._uncompressed_digest = hashlib.sha256()
        self._uncompressed_bytes = 0
        self._finished = False

    def read_samples(self, sample_count: int) -> np.ndarray:
        required = sample_count * self._receiver_count * 4
        payload = bytearray()
        while len(payload) < required:
            part = self._decompressed.read(min(1024 * 1024, required - len(payload)))
            if not part:
                raise BundleCorruptionError("retained chunk ended before its sample inventory")
            payload.extend(part)
            self._uncompressed_digest.update(part)
            self._uncompressed_bytes += len(part)
        return np.frombuffer(payload, dtype="<i2").reshape(sample_count, self._receiver_count, 2)

    def finish(self) -> None:
        if self._finished:
            return
        extra = self._decompressed.read(1)
        if extra:
            raise BundleCorruptionError("retained chunk exceeds its sample inventory")
        while self._compressed.read(1024 * 1024):
            pass
        if (
            self._uncompressed_bytes != self._chunk.uncompressed_bytes
            or f"sha256:{self._uncompressed_digest.hexdigest()}" != self._chunk.uncompressed_sha256
            or self._compressed.digest != self._chunk.compressed_sha256
        ):
            raise BundleCorruptionError("retained chunk digest or size mismatch")
        self._pinned.assert_bound()
        self._finished = True
        self.close()

    def close(self) -> None:
        self._decompressed.close()
        self._raw.close()


def _verify_capability_bytes(capability: _VerifiedBundleCapability) -> None:
    manifest_payload = _read_bounded(
        capability.file("manifest.json"), maximum_bytes=16 * 1024 * 1024
    )
    if sha256_digest(manifest_payload) != capability.bundle.manifest_sha256:
        raise InputManifestMismatchError("retained manifest digest changed")
    for stream in capability.bundle.manifest.streams:
        if stream.captured_sample_count:
            for _block in _VerifiedRecordingIqReader(capability, stream.stream_id).iter_blocks(
                block_samples=262_144
            ):
                pass
    capability.assert_bound()


def _slice_metadata(
    metadata: IqBlockMetadataV1, *, offset: int, sample_count: int
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


def _stream_integrities(bundle: PublishedBundle) -> tuple[RawStreamIntegrityV1, ...]:
    streams = []
    for stream in sorted(bundle.manifest.streams, key=lambda item: item.stream_id):
        streams.append(
            RawStreamIntegrityV1(
                stream_id=stream.stream_id,
                chunk_count=len(stream.chunks),
                compressed_closure_digest=canonical_digest(
                    [
                        {
                            "chunk_index": chunk.chunk_index,
                            "sample_start": chunk.sample_start,
                            "sample_count": chunk.sample_count,
                            "digest": chunk.compressed_sha256,
                        }
                        for chunk in stream.chunks
                    ]
                ),
                uncompressed_closure_digest=canonical_digest(
                    [
                        {
                            "chunk_index": chunk.chunk_index,
                            "sample_start": chunk.sample_start,
                            "sample_count": chunk.sample_count,
                            "digest": chunk.uncompressed_sha256,
                        }
                        for chunk in stream.chunks
                    ]
                ),
            )
        )
    return tuple(streams)


class _ReceiverPathReader:
    def __init__(self, source: IqReader, receiver_id: int) -> None:
        if receiver_id not in source.receiver_ids:
            raise ValueError(f"receiver {receiver_id} is absent from the selected stream")
        self._source = source
        self._receiver_id = receiver_id
        self._column = source.receiver_ids.index(receiver_id)

    @property
    def sample_rate_hz(self) -> int:
        return self._source.sample_rate_hz

    @property
    def center_frequency_hz(self) -> int:
        return self._source.center_frequency_hz

    @property
    def sample_count(self) -> int:
        return self._source.sample_count

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        return (self._receiver_id,)

    def iter_blocks(self, *, block_samples: int) -> Iterable[IqBlock]:
        for block in self._source.iter_blocks(block_samples=block_samples):
            samples = np.ascontiguousarray(block.samples[:, self._column : self._column + 1, :])
            yield IqBlock(
                samples=samples,
                metadata=block.metadata.model_copy(update={"receiver_ids": self.receiver_ids}),
            )


class _LeasedIqReader:
    __slots__ = ("_source", "_finalizer", "__weakref__")

    def __init__(self, source: IqReader, capability: _VerifiedBundleCapability) -> None:
        self._source = source
        self._finalizer = weakref.finalize(self, capability.release)

    @property
    def sample_rate_hz(self) -> int:
        return self._source.sample_rate_hz

    @property
    def center_frequency_hz(self) -> int:
        return self._source.center_frequency_hz

    @property
    def sample_count(self) -> int:
        return self._source.sample_count

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        return self._source.receiver_ids

    def iter_blocks(self, *, block_samples: int) -> Iterable[IqBlock]:
        yield from self._source.iter_blocks(block_samples=block_samples)

    def close(self) -> None:
        self._finalizer()


class CatalogArtifactProductReader(ProductReader):
    """Read registered upstream JSON products for one run/scope."""

    def __init__(
        self,
        catalog: CatalogRepository,
        artifacts: AnalysisArtifactStore,
        *,
        run_id: str,
        scope_key: str,
        job_id: int | None = None,
    ) -> None:
        self._catalog = catalog
        self._artifacts = artifacts
        self._run_id = run_id
        self._scope_key = scope_key
        self._job_id = job_id
        self._consumed_product_ids: set[int] = set()

    @property
    def consumed_product_ids(self) -> tuple[int, ...]:
        return tuple(sorted(self._consumed_product_ids))

    def read_json(self, requirement: ProductRequirement) -> dict[str, JsonValue] | None:
        snapshot = self._catalog.run_seal_snapshot(self._run_id)
        authorized = None
        if self._job_id is not None:
            authorized = self._catalog.authorized_job_input_products(self._job_id)
        if requirement.producer_stage_key is not None:
            authorized_nodes = (
                {node_id for node_id, _ in authorized if node_id is not None}
                if authorized is not None
                else set()
            )
            jobs = tuple(
                job
                for job in snapshot.jobs
                if job.stage_key == requirement.producer_stage_key
                and (
                    (
                        requirement.producer_node_id is not None
                        and getattr(job, "node_id", None) == requirement.producer_node_id
                    )
                    or (
                        requirement.producer_node_id is None
                        and (
                            getattr(job, "node_id", None) in authorized_nodes
                            or job.scope_key == self._scope_key
                        )
                    )
                )
            )
            if len(jobs) != 1:
                raise ValueError(
                    f"required producer job is absent or ambiguous for {self._scope_key}: "
                    f"{requirement.producer_stage_key}"
                )
            job = jobs[0]
            if job.state != "succeeded" or (
                requirement.required_status is not None
                and job.outcome != requirement.required_status.value
            ):
                raise ValueError(
                    f"required producer job is not complete for {self._scope_key}: "
                    f"{requirement.producer_stage_key}"
                )
        candidates = (
            tuple(product for _, product in authorized)
            if authorized is not None
            else snapshot.products
        )
        matches = tuple(
            product
            for product in candidates
            if (
                product.run_id == self._run_id
                and product.kind == requirement.kind
                and (authorized is not None or product.scope_key == self._scope_key)
                and product.schema_version in requirement.accepted_schema_versions
                and (
                    requirement.producer_stage_key is None
                    or product.stage_key == requirement.producer_stage_key
                )
                and (
                    requirement.required_role is None
                    or product.role == requirement.required_role.value
                )
                and (
                    requirement.required_status is None
                    or product.status == requirement.required_status.value
                )
                and (not requirement.require_available or product.available)
                and (
                    requirement.producer_node_id is None
                    or authorized is not None
                    and any(
                        node_id == requirement.producer_node_id
                        and authorized_product.product_id == product.product_id
                        for node_id, authorized_product in authorized
                    )
                )
            )
        )
        for version in requirement.accepted_schema_versions:
            candidates = tuple(item for item in matches if item.schema_version == version)
            if len(candidates) > 1:
                raise ValueError(
                    f"required product is ambiguous for {self._scope_key}: "
                    f"{requirement.kind} v{version}"
                )
            if candidates:
                selected = candidates[0]
                document = self._artifacts.read_json(selected.logical_uri, selected.digest)
                self._consumed_product_ids.add(selected.product_id)
                return document
        if requirement.required:
            raise KeyError(f"required product is absent for {self._scope_key}: {requirement.kind}")
        return None

    def read_json_many(
        self,
        requirement: ProductRequirement,
        *,
        producer_node_ids: tuple[str, ...],
    ) -> tuple[UpstreamJsonProduct, ...]:
        if self._job_id is None:
            raise ValueError("bounded fan-in requires a typed persisted job plan")
        if (
            not producer_node_ids
            or len(producer_node_ids) > 64
            or tuple(sorted(producer_node_ids)) != producer_node_ids
            or len(set(producer_node_ids)) != len(producer_node_ids)
        ):
            raise ValueError("producer node IDs must be non-empty, unique, bounded and ordered")
        authorized = self._catalog.authorized_job_input_products(self._job_id)
        authorized_nodes = tuple(sorted({node for node, _ in authorized if node is not None}))
        if authorized_nodes != producer_node_ids:
            raise ValueError("fan-in nodes do not equal the exact required dependency inventory")

        output = []
        for node_id in producer_node_ids:
            matches = tuple(
                product
                for producer_node, product in authorized
                if producer_node == node_id
                and product.kind == requirement.kind
                and product.schema_version in requirement.accepted_schema_versions
                and (
                    requirement.producer_stage_key is None
                    or product.stage_key == requirement.producer_stage_key
                )
                and (
                    requirement.required_role is None
                    or product.role == requirement.required_role.value
                )
                and (
                    requirement.required_status is None
                    or product.status == requirement.required_status.value
                )
                and (not requirement.require_available or product.available)
            )
            selected = None
            for version in requirement.accepted_schema_versions:
                candidates = tuple(
                    product for product in matches if product.schema_version == version
                )
                if len(candidates) > 1:
                    raise ValueError(f"fan-in product is ambiguous for producer node {node_id}")
                if candidates:
                    selected = candidates[0]
                    break
            if selected is None:
                raise KeyError(f"fan-in product is absent for producer node {node_id}")
            if selected.scope is None:
                raise ValueError(f"fan-in producer node {node_id} has no typed scope")
            document = self._artifacts.read_json(selected.logical_uri, selected.digest)
            self._consumed_product_ids.add(selected.product_id)
            output.append(
                UpstreamJsonProduct(
                    producer_node_id=node_id,
                    producer_scope=selected.scope,
                    product_digest=selected.digest,
                    document=document,
                )
            )
        return tuple(output)
