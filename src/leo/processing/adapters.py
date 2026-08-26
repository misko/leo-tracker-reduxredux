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
from leo.catalog import (
    CaptureRecordingIdentity,
    CatalogProductRecord,
    CatalogRepository,
    RunExecutionInfo,
)
from leo.contracts.continuity import IqGapMapV1
from leo.contracts.digests import Sha256Digest, canonical_digest, sha256_digest
from leo.contracts.radio import IqBlockMetadataV1, parse_iq_block_metadata_json
from leo.contracts.rate_analysis import VerifiedIqGapMapEvidenceV1
from leo.contracts.recording import (
    DeviceAxisRecordingChunkV1,
    RecordingChunkV1,
    RecordingManifestV1,
    RecordingManifestV3,
    RecordingStreamV1,
    RecordingStreamV2,
    RecordingStreamV3,
    parse_recording_manifest_json,
)
from leo.contracts.states import ContinuityStatus
from leo.contracts.validity import (
    ContinuitySegmentV1,
    DeviceAxisContentKind,
    ValidityInventoryV1,
)
from leo.domain.gap_map import IqContinuityEvidenceError, build_iq_gap_map
from leo.domain.iq import IqBlock
from leo.domain.validity import build_validity_inventory_v1
from leo.pipeline import (
    GapAwareIqReader,
    IqReader,
    ProductReader,
    ProductRequirement,
    RawIntegrityAttestationV1,
    RawStreamIntegrityV1,
    ScopeIdentityV1,
    ScopeKind,
    StageOutcome,
    UpstreamJsonProduct,
    ValidityAwareIqReader,
)
from leo.processing.continuity import (
    PhysicalDeviceIqBlock,
    V2ValidityAwareIqReader,
    V3ValidityAwareIqReader,
)
from leo.storage import PinnedLocalRoot, RecordingStore, parse_recording_bundle_uri
from leo.storage.errors import BundleCorruptionError
from leo.storage.writer import PublishedBundle

_MAX_VERIFIED_RECORDING_BYTES = 8 * 1024**4
_MAX_TYPED_IQ_BLOCK_SAMPLES = 1_048_576


class InputManifestMismatchError(RuntimeError):
    """The recording at a catalog URI is not the run's pinned input."""


@dataclass(frozen=True, slots=True)
class VerifiedHistoricalV2NativeStreamEvidence:
    """Attestation-bound digests for one verified packed historical V2 stream."""

    raw_integrity_attestation_digest: Sha256Digest
    stream_id: str
    selected_stream_digest: Sha256Digest
    uncompressed_chunk_closure_digest: Sha256Digest
    validity_inventory: ValidityInventoryV1
    observed_iq_digest: Sha256Digest
    logical_iq_digest: Sha256Digest


class IqReaderProvider(Protocol):
    def open(self, execution: RunExecutionInfo, scope_key: str) -> IqReader: ...

    def open_scope(self, execution: RunExecutionInfo, scope: ScopeIdentityV1) -> IqReader: ...

    def open_validity_scope(
        self, execution: RunExecutionInfo, scope: ScopeIdentityV1
    ) -> ValidityAwareIqReader: ...

    def verify_integrity(self, identity: CaptureRecordingIdentity) -> RawIntegrityAttestationV1: ...

    def verified_manifest(
        self, attestation_digest: str
    ) -> RecordingManifestV1 | RecordingManifestV3: ...

    def verified_validity_inventory(
        self, attestation_digest: str, stream_id: str
    ) -> ValidityInventoryV1: ...

    def verified_historical_v2_native_stream_evidence(
        self, attestation_digest: str, stream_id: str
    ) -> VerifiedHistoricalV2NativeStreamEvidence: ...

    def close(self) -> None: ...


class ValidityAwareIqReaderProvider(Protocol):
    """Additive provider seam for logical device-axis IQ analysis."""

    def open_validity_scope(
        self, execution: RunExecutionInfo, scope: ScopeIdentityV1
    ) -> ValidityAwareIqReader: ...

    def verified_validity_inventory(
        self, attestation_digest: str, stream_id: str
    ) -> ValidityInventoryV1: ...

    def verified_historical_v2_native_stream_evidence(
        self, attestation_digest: str, stream_id: str
    ) -> VerifiedHistoricalV2NativeStreamEvidence: ...


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
        self._capabilities: OrderedDict[tuple[str, str], _VerifiedBundleCapability] = OrderedDict()
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
        stream = _capability_stream(capability, scope.stream_id)
        if isinstance(stream, RecordingStreamV3):
            raise ValueError("V3 IQ requires explicit validity-aware device-axis access")
        capability.assert_bound()
        capability.acquire()
        try:
            source = _VerifiedRecordingIqReader(capability, scope.stream_id)
            return _LeasedIqReader(_ReceiverPathReader(source, scope.receiver_id), capability)
        except Exception:
            capability.release()
            raise

    def open_validity_scope(
        self, execution: RunExecutionInfo, scope: ScopeIdentityV1
    ) -> ValidityAwareIqReader:
        """Open one verified V2-synthesized or V3-physical mandatory-validity path."""

        if scope.kind is not ScopeKind.RECEIVER_PATH:
            raise ValueError("only receiver_path scopes may open validity-aware IQ")
        if scope.stream_id is None or scope.receiver_id is None:
            raise ValueError("receiver_path scope is incomplete")
        capability = self._typed_capability(execution)
        stream = _capability_stream(capability, scope.stream_id)
        if isinstance(stream, RecordingStreamV3):
            capability.assert_bound()
            capability.acquire()
            v3_source: _VerifiedV3DeviceAxisSource | None = None
            try:
                v3_source = _VerifiedV3DeviceAxisSource(
                    capability,
                    stream,
                    receiver_id=scope.receiver_id,
                )
                return V3ValidityAwareIqReader(v3_source)
            except Exception:
                if v3_source is None:
                    capability.release()
                else:
                    v3_source.close()
                raise

        source = self.open_scope(execution, scope)
        try:
            return V2ValidityAwareIqReader(cast(GapAwareIqReader, source))
        except Exception:
            close = getattr(source, "close", None)
            if callable(close):
                close()
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
        for stream in sorted(_recording_streams(bundle.manifest), key=lambda item: item.stream_id):
            inventory = [
                {
                    "chunk_index": chunk.chunk_index,
                    "sample_start": _chunk_axis_start(chunk),
                    "sample_count": chunk.sample_count,
                    "digest": chunk.compressed_sha256,
                }
                for chunk in stream.chunks
            ]
            uncompressed_inventory = [
                {
                    "chunk_index": chunk.chunk_index,
                    "sample_start": _chunk_axis_start(chunk),
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

    def verified_manifest(
        self, attestation_digest: str
    ) -> RecordingManifestV1 | RecordingManifestV3:
        key = self._attestation_keys.get(attestation_digest)
        capability = None if key is None else self._capabilities.get(key)
        if capability is None:
            raise InputManifestMismatchError("raw-integrity capability is not retained")
        capability.assert_bound()
        return capability.bundle.manifest

    def verified_validity_inventory(
        self, attestation_digest: str, stream_id: str
    ) -> ValidityInventoryV1:
        """Return rebuilt validity under one retained raw-integrity authority."""

        key = self._attestation_keys.get(attestation_digest)
        capability = None if key is None else self._capabilities.get(key)
        if capability is None:
            raise InputManifestMismatchError("raw-integrity capability is not retained")
        stream = _capability_stream(capability, stream_id)
        evidence = _VerifiedRecordingIqReader(capability, stream.stream_id).gap_map_evidence()
        if isinstance(stream, RecordingStreamV2):
            return build_validity_inventory_v1(evidence.gap_map)
        if not isinstance(stream, RecordingStreamV3):
            raise ValueError("verified validity requires a V2 or V3 stream")
        return _verified_v3_inventory(
            capability,
            stream,
            gap_evidence=evidence,
        )

    def verified_historical_v2_native_stream_evidence(
        self,
        attestation_digest: str,
        stream_id: str,
    ) -> VerifiedHistoricalV2NativeStreamEvidence:
        """Hash the verified packed and synthesized V2 axes in canonical CI16 order."""

        key = self._attestation_keys.get(attestation_digest)
        capability = None if key is None else self._capabilities.get(key)
        if capability is None:
            raise InputManifestMismatchError("raw-integrity capability is not retained")
        capability.assert_bound()
        stream = _capability_stream(capability, stream_id)
        if not isinstance(stream, RecordingStreamV2):
            raise ValueError("historical V2 native evidence requires a V2 stream")
        source = _VerifiedRecordingIqReader(capability, stream.stream_id)
        gap_map = source.gap_map_evidence().gap_map
        if gap_map.capture_start_overflow or gap_map.terminal_rejected_refill is not None:
            raise BundleCorruptionError(
                "historical V2 native evidence forbids overflow or rejected refill evidence"
            )
        reader = V2ValidityAwareIqReader(source)
        observed_digest = hashlib.sha256()
        logical_digest = hashlib.sha256()
        observed_samples = 0
        logical_samples = 0
        try:
            for block in reader.iter_masked_blocks(block_samples=_MAX_TYPED_IQ_BLOCK_SAMPLES):
                payload = memoryview(block.samples).cast("B")
                logical_digest.update(payload)
                logical_samples += block.sample_count
                if np.all(block.valid_samples):
                    observed_digest.update(payload)
                    observed_samples += block.sample_count
                elif np.any(block.valid_samples):
                    raise BundleCorruptionError(
                        "historical V2 synthesized digest block has mixed validity"
                    )
        finally:
            reader.close()
        validity = build_validity_inventory_v1(gap_map)
        if (
            observed_samples != validity.observed_sample_count
            or logical_samples != validity.logical_sample_count
        ):
            raise BundleCorruptionError("historical V2 synthesized digest counts do not close")
        observed_iq_digest = f"sha256:{observed_digest.hexdigest()}"
        logical_iq_digest = f"sha256:{logical_digest.hexdigest()}"
        if validity.missing_sample_count:
            if observed_iq_digest == logical_iq_digest:
                raise BundleCorruptionError("gapped V2 logical IQ digest aliases observed IQ")
        elif observed_iq_digest != logical_iq_digest:
            raise BundleCorruptionError("lossless V2 logical and observed IQ digests differ")
        raw_stream = next(
            (
                item
                for item in _stream_integrities(capability.bundle)
                if item.stream_id == stream_id
            ),
            None,
        )
        if raw_stream is None:
            raise BundleCorruptionError("historical V2 raw stream closure is absent")
        return VerifiedHistoricalV2NativeStreamEvidence(
            raw_integrity_attestation_digest=attestation_digest,
            stream_id=stream_id,
            selected_stream_digest=canonical_digest(stream.model_dump(mode="json")),
            uncompressed_chunk_closure_digest=raw_stream.uncompressed_closure_digest,
            validity_inventory=validity,
            observed_iq_digest=observed_iq_digest,
            logical_iq_digest=logical_iq_digest,
        )

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
            manifest = parse_recording_manifest_json(payload)
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
    bundle: PinnedLocalRoot
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
        descriptor = -1
        try:
            descriptor = os.open(
                parts[-1],
                os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                dir_fd=parent.fileno(),
            )
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise InputManifestMismatchError(
                    f"verified input is not a regular file: {relative_path}"
                )
            return cls(
                relative_path,
                bundle,
                (metadata.st_dev, metadata.st_ino, metadata.st_size),
            )
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            parent.close()

    def assert_bound(self) -> None:
        with self.open_reader():
            pass

    def close(self) -> None:
        return

    def open_reader(self) -> io.BufferedReader:
        """Open one bounded child through the retained bundle directory capability."""

        parts = Path(self.label).parts
        parent = self.bundle.clone() if len(parts) == 1 else self.bundle.child(*parts[:-1])
        descriptor = -1
        try:
            descriptor = os.open(
                parts[-1],
                os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                dir_fd=parent.fileno(),
            )
            metadata = os.fstat(descriptor)
            current = (metadata.st_dev, metadata.st_ino, metadata.st_size)
            if current != self.identity or not stat.S_ISREG(metadata.st_mode):
                raise InputManifestMismatchError(f"verified input binding changed: {self.label}")
            source = cast(io.BufferedReader, os.fdopen(descriptor, "rb"))
            descriptor = -1
            return source
        except OSError as error:
            raise InputManifestMismatchError(
                f"verified input binding changed or became unsafe: {self.label}"
            ) from error
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            parent.close()


def _read_bounded(pinned: _PinnedFile, *, maximum_bytes: int) -> bytes:
    if pinned.identity[2] <= 0 or pinned.identity[2] > maximum_bytes:
        raise InputManifestMismatchError(f"verified input size is invalid: {pinned.label}")
    with pinned.open_reader() as source:
        payload = source.read(maximum_bytes + 1)
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
            if isinstance(stream, (RecordingStreamV2, RecordingStreamV3)) and (
                stream.gap_map_relative_path is not None
            ):
                paths.append(stream.gap_map_relative_path)
            if isinstance(stream, RecordingStreamV3):
                paths.append(stream.validity_inventory_relative_path)
        if len(paths) > 16_384 or len(set(paths)) != len(paths):
            directory.close()
            raise InputManifestMismatchError("recording file inventory is duplicate or unbounded")
        opened: list[_PinnedFile] = []
        try:
            opened.extend(_PinnedFile.open_at(directory, path) for path in paths)
            compressed_bytes = sum(item.identity[2] for item in opened)
            uncompressed_bytes = sum(
                chunk.uncompressed_bytes
                for stream in bundle.manifest.streams
                for chunk in stream.chunks
            )
            if (
                compressed_bytes > _MAX_VERIFIED_RECORDING_BYTES
                or uncompressed_bytes > _MAX_VERIFIED_RECORDING_BYTES
            ):
                raise InputManifestMismatchError("recording file inventory exceeds 8 TiB")
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

    def close(self) -> None:
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
        self._verified_timeline_cache: tuple[IqBlockMetadataV1, ...] | None = None

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
        if isinstance(self._stream, RecordingStreamV3):
            return self._stream.logical_sample_count
        return self._stream.captured_sample_count

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        self._capability.assert_bound()
        return (self._stream.applied_settings or self._stream.requested_settings).receiver_ids

    def iter_blocks(self, *, block_samples: int) -> Iterable[IqBlock]:
        if isinstance(self._stream, RecordingStreamV3):
            raise ValueError("V3 IQ requires explicit validity-aware device-axis iteration")
        yield from self.iter_stored_blocks(
            stored_sample_start=0,
            sample_count=self.sample_count,
            block_samples=block_samples,
        )

    def iter_stored_blocks(
        self,
        *,
        stored_sample_start: int,
        sample_count: int,
        block_samples: int,
    ) -> Iterable[IqBlock]:
        """Read one packed-IQ range while opening only intersecting verified shards."""

        if isinstance(self._stream, RecordingStreamV3):
            raise ValueError("V3 IQ has no mask-blind packed-IQ range")
        if not 0 < block_samples <= _MAX_TYPED_IQ_BLOCK_SAMPLES:
            raise ValueError(f"block_samples must be in [1, {_MAX_TYPED_IQ_BLOCK_SAMPLES}]")
        if stored_sample_start < 0 or sample_count <= 0:
            raise ValueError("stored IQ range requires a non-negative start and positive count")
        stored_sample_stop = stored_sample_start + sample_count
        if stored_sample_stop > self.sample_count:
            raise ValueError("stored IQ range exceeds the packed observed span")

        timeline = self._verified_timeline()
        range_cursor = stored_sample_start
        chunk_stream: _RetainedChunkStream | None = None
        try:
            for chunk in self._stream.chunks:
                chunk_start = chunk.sample_start
                chunk_stop = chunk_start + chunk.sample_count
                selected_start = max(stored_sample_start, chunk_start)
                selected_stop = min(stored_sample_stop, chunk_stop)
                if selected_start >= selected_stop:
                    continue
                if selected_start != range_cursor:
                    raise BundleCorruptionError("selected IQ shards do not cover the stored range")

                chunk_stream = _RetainedChunkStream(
                    self._capability.file(chunk.relative_path),
                    chunk,
                    receiver_count=len(self.receiver_ids),
                )
                chunk_stream.skip_samples(selected_start - chunk_start)
                chunk_cursor = selected_start
                for metadata in timeline:
                    metadata_start = metadata.session_sample_start
                    metadata_stop = metadata_start + metadata.sample_count
                    overlap_start = max(selected_start, metadata_start)
                    overlap_stop = min(selected_stop, metadata_stop)
                    if overlap_start >= overlap_stop:
                        continue
                    if overlap_start != chunk_cursor:
                        raise BundleCorruptionError(
                            "verified timeline does not cover the selected IQ range"
                        )
                    for position in range(overlap_start, overlap_stop, block_samples):
                        offset = position - metadata_start
                        count = min(block_samples, overlap_stop - position)
                        assert chunk_stream is not None
                        samples = chunk_stream.read_samples(count)
                        chunk_cursor += count
                        range_cursor += count
                        yield IqBlock(
                            samples=samples,
                            metadata=_slice_metadata(
                                metadata,
                                offset=offset,
                                sample_count=count,
                            ),
                        )
                if chunk_cursor != selected_stop:
                    raise BundleCorruptionError(
                        "verified timeline ended before the selected IQ range"
                    )
                chunk_stream.skip_samples(chunk_stop - selected_stop)
                chunk_stream.finish()
                chunk_stream = None
            if range_cursor != stored_sample_stop:
                raise BundleCorruptionError("IQ shards ended before the selected stored range")
        finally:
            if chunk_stream is not None:
                chunk_stream.close()

    def iter_timeline_metadata(self) -> Iterable[IqBlockMetadataV1]:
        """Yield verified refill metadata without opening retained IQ chunks."""

        yield from self._verified_timeline()

    def gap_map_evidence(self) -> VerifiedIqGapMapEvidenceV1:
        """Verify persisted bytes and rebuild them from the retained timeline."""

        stream = self._stream
        if not isinstance(stream, (RecordingStreamV2, RecordingStreamV3)):
            raise BundleCorruptionError("legacy recording has no counter-authoritative gap map")
        relative_path = stream.gap_map_relative_path
        expected_digest = stream.gap_map_sha256
        timeline_digest = stream.timeline_sha256
        if relative_path is None or expected_digest is None or timeline_digest is None:
            raise BundleCorruptionError("V2 data stream has no gap-map evidence")
        payload = _read_bounded(
            self._capability.file(relative_path),
            maximum_bytes=16 * 1024 * 1024,
        )
        if sha256_digest(payload) != expected_digest:
            raise BundleCorruptionError("retained gap-map digest mismatch")
        try:
            stored = IqGapMapV1.model_validate_json(payload)
            rebuilt = build_iq_gap_map(
                stream_id=stream.stream_id,
                timeline_sha256=timeline_digest,
                timeline=self._verified_timeline(),
                continuity=stream.continuity,
            )
        except (ValidationError, IqContinuityEvidenceError) as error:
            raise BundleCorruptionError(f"gap-map evidence is invalid: {error}") from error
        if stored != rebuilt:
            raise BundleCorruptionError(
                "persisted gap map disagrees with its retained verified timeline"
            )
        return VerifiedIqGapMapEvidenceV1(
            persisted_sha256=expected_digest,
            gap_map=stored,
        )

    def _verified_timeline(self) -> tuple[IqBlockMetadataV1, ...]:
        cached = self._verified_timeline_cache
        if cached is not None:
            return cached
        timeline = tuple(self._timeline_metadata())
        expected_start = 0
        chunk_index = 0
        for metadata in timeline:
            if metadata.radio_id != self._stream.radio.radio_id:
                raise BundleCorruptionError("timeline radio ID disagrees with its stream")
            if metadata.receiver_ids != self.receiver_ids:
                raise BundleCorruptionError("timeline receiver IDs disagree with its stream")
            if metadata.session_sample_start != expected_start:
                raise BundleCorruptionError("timeline sample coordinates are not contiguous")
            metadata_stop = metadata.session_sample_start + metadata.sample_count
            if isinstance(self._stream, RecordingStreamV3):
                expected_start = metadata_stop
                continue
            while (
                chunk_index < len(self._stream.chunks)
                and metadata.session_sample_start
                >= self._stream.chunks[chunk_index].sample_start
                + self._stream.chunks[chunk_index].sample_count
            ):
                chunk_index += 1
            if chunk_index >= len(self._stream.chunks):
                raise BundleCorruptionError("timeline extends beyond chunk inventory")
            chunk = self._stream.chunks[chunk_index]
            if (
                metadata.session_sample_start < chunk.sample_start
                or metadata_stop > chunk.sample_start + chunk.sample_count
            ):
                raise BundleCorruptionError("one timeline refill crosses a shard boundary")
            expected_start = metadata_stop
        expected_sample_count = (
            self._stream.observed_sample_count
            if isinstance(self._stream, RecordingStreamV3)
            else self.sample_count
        )
        if expected_start != expected_sample_count:
            raise BundleCorruptionError("timeline does not cover captured sample count")
        self._verified_timeline_cache = timeline
        return timeline

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
                        yield parse_iq_block_metadata_json(line)
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
        chunk: RecordingChunkV1 | DeviceAxisRecordingChunkV1,
        *,
        receiver_count: int,
    ) -> None:
        self._pinned = pinned
        self._chunk = chunk
        self._receiver_count = receiver_count
        self._requires_zero = (
            isinstance(chunk, DeviceAxisRecordingChunkV1)
            and chunk.content_kind is DeviceAxisContentKind.ZERO_FILL
        )
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
            if self._requires_zero and any(part):
                raise BundleCorruptionError("retained V3 zero-fill chunk contains observed bytes")
            payload.extend(part)
            self._uncompressed_digest.update(part)
            self._uncompressed_bytes += len(part)
        return np.frombuffer(payload, dtype="<i2").reshape(sample_count, self._receiver_count, 2)

    def skip_samples(self, sample_count: int) -> None:
        """Consume and attest samples without materializing an ndarray."""

        if sample_count < 0:
            raise ValueError("retained chunk skip count cannot be negative")
        remaining = sample_count * self._receiver_count * 4
        while remaining:
            part = self._decompressed.read(min(1024 * 1024, remaining))
            if not part:
                raise BundleCorruptionError("retained chunk ended before its sample inventory")
            if self._requires_zero and any(part):
                raise BundleCorruptionError("retained V3 zero-fill chunk contains observed bytes")
            self._uncompressed_digest.update(part)
            self._uncompressed_bytes += len(part)
            remaining -= len(part)

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


class _VerifiedV3DeviceAxisSource:
    """Retained-FD physical V3 source available only to the validity adapter."""

    def __init__(
        self,
        capability: _VerifiedBundleCapability,
        stream: RecordingStreamV3,
        *,
        receiver_id: int,
    ) -> None:
        stream_receiver_ids = stream.applied_settings.receiver_ids
        if receiver_id not in stream_receiver_ids:
            raise ValueError(f"receiver {receiver_id} is absent from the selected stream")
        evidence_reader = _VerifiedRecordingIqReader(capability, stream.stream_id)
        gap_evidence = evidence_reader.gap_map_evidence()
        inventory = _verified_v3_inventory(
            capability,
            stream,
            gap_evidence=gap_evidence,
        )
        self._capability = capability
        self._stream = stream
        self._receiver_id = receiver_id
        self._receiver_column = stream_receiver_ids.index(receiver_id)
        self._inventory = inventory
        self._gap_evidence = gap_evidence
        self._timeline = tuple(evidence_reader.iter_timeline_metadata())
        self._finalizer = weakref.finalize(self, capability.release)

    @property
    def sample_rate_hz(self) -> int:
        self._assert_open()
        return self._stream.applied_settings.sample_rate_hz

    @property
    def center_frequency_hz(self) -> int:
        self._assert_open()
        return self._stream.applied_settings.center_frequency_hz

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        self._assert_open()
        return (self._receiver_id,)

    @property
    def validity_inventory(self) -> ValidityInventoryV1:
        self._assert_open()
        return self._inventory

    @property
    def verified_gap_map_evidence(self) -> VerifiedIqGapMapEvidenceV1:
        self._assert_open()
        return self._gap_evidence

    def iter_physical_device_blocks(
        self,
        *,
        device_sample_start: int,
        sample_count: int,
        block_samples: int,
    ) -> Iterable[PhysicalDeviceIqBlock]:
        yield from self._iter_physical_range(
            device_sample_start=device_sample_start,
            sample_count=sample_count,
            block_samples=block_samples,
            device_breakpoints=(),
        )

    def iter_observed_segment_blocks(
        self,
        segment: ContinuitySegmentV1,
        *,
        block_samples: int,
    ) -> Iterable[IqBlock]:
        self._assert_open()
        if (
            segment.segment_index >= len(self._inventory.segments)
            or self._inventory.segments[segment.segment_index] != segment
            or segment.observed_sample_count <= 0
        ):
            raise ValueError("observed V3 segment is absent from verified validity")
        stored_start = segment.stored_sample_start
        stored_stop = segment.stored_sample_stop
        timeline = tuple(
            metadata
            for metadata in self._timeline
            if metadata.session_sample_start < stored_stop
            and metadata.session_sample_start + metadata.sample_count > stored_start
        )
        stored_cursor = stored_start
        device_breakpoints: list[int] = []
        for metadata in timeline:
            overlap_start = max(stored_start, metadata.session_sample_start)
            overlap_stop = min(
                stored_stop,
                metadata.session_sample_start + metadata.sample_count,
            )
            if overlap_start != stored_cursor:
                raise BundleCorruptionError("V3 timeline does not cover an observed segment")
            stored_cursor = overlap_stop
            device_breakpoints.append(segment.device_sample_start + overlap_stop - stored_start)
        if stored_cursor != stored_stop:
            raise BundleCorruptionError("V3 timeline ended before an observed segment")

        metadata_index = 0
        returned = 0
        for physical in self._iter_physical_range(
            device_sample_start=segment.device_sample_start,
            sample_count=segment.observed_sample_count,
            block_samples=block_samples,
            device_breakpoints=tuple(device_breakpoints),
        ):
            if (
                physical.content_kind is not DeviceAxisContentKind.OBSERVED
                or physical.continuity_segment_index != segment.segment_index
            ):
                raise BundleCorruptionError("V3 observed segment includes physical zero fill")
            packed_start = (
                segment.stored_sample_start
                + physical.device_sample_start
                - segment.device_sample_start
            )
            while (
                metadata_index < len(timeline)
                and packed_start
                >= timeline[metadata_index].session_sample_start
                + timeline[metadata_index].sample_count
            ):
                metadata_index += 1
            if metadata_index >= len(timeline):
                raise BundleCorruptionError("V3 observed IQ extends beyond its timeline")
            metadata = timeline[metadata_index]
            metadata_stop = metadata.session_sample_start + metadata.sample_count
            if (
                packed_start < metadata.session_sample_start
                or packed_start + physical.sample_count > metadata_stop
            ):
                raise BundleCorruptionError("V3 observed block crosses timeline evidence")
            derived = _slice_metadata(
                metadata,
                offset=packed_start - metadata.session_sample_start,
                sample_count=physical.sample_count,
            ).model_copy(update={"receiver_ids": self.receiver_ids})
            yield IqBlock(samples=physical.samples, metadata=derived)
            returned += physical.sample_count
        if returned != segment.observed_sample_count:
            raise BundleCorruptionError("V3 physical segment ended before validity evidence")

    def close(self) -> None:
        self._finalizer()

    def _iter_physical_range(
        self,
        *,
        device_sample_start: int,
        sample_count: int,
        block_samples: int,
        device_breakpoints: tuple[int, ...],
    ) -> Iterable[PhysicalDeviceIqBlock]:
        self._assert_open()
        if not 0 < block_samples <= _MAX_TYPED_IQ_BLOCK_SAMPLES:
            raise ValueError(f"block_samples must be in [1, {_MAX_TYPED_IQ_BLOCK_SAMPLES}]")
        if device_sample_start < 0 or sample_count <= 0:
            raise ValueError("physical V3 range requires a non-negative start and positive count")
        device_sample_stop = device_sample_start + sample_count
        if device_sample_stop > self._inventory.logical_sample_count:
            raise ValueError("physical V3 range exceeds the logical device span")
        if tuple(sorted(set(device_breakpoints))) != device_breakpoints or any(
            boundary <= device_sample_start or boundary > device_sample_stop
            for boundary in device_breakpoints
        ):
            raise ValueError("physical V3 range breakpoints are not canonical")

        cursor = device_sample_start
        breakpoint_index = 0
        chunk_stream: _RetainedChunkStream | None = None
        try:
            for chunk in self._stream.chunks:
                chunk_start = chunk.device_sample_start
                chunk_stop = chunk_start + chunk.sample_count
                selected_start = max(device_sample_start, chunk_start)
                selected_stop = min(device_sample_stop, chunk_stop)
                if selected_start >= selected_stop:
                    continue
                if selected_start != cursor:
                    raise BundleCorruptionError("V3 chunks do not cover the physical range")
                chunk_stream = _RetainedChunkStream(
                    self._capability.file(chunk.relative_path),
                    chunk,
                    receiver_count=len(self._stream.applied_settings.receiver_ids),
                )
                chunk_stream.skip_samples(selected_start - chunk_start)
                while cursor < selected_stop:
                    while (
                        breakpoint_index < len(device_breakpoints)
                        and device_breakpoints[breakpoint_index] <= cursor
                    ):
                        breakpoint_index += 1
                    next_breakpoint = (
                        device_breakpoints[breakpoint_index]
                        if breakpoint_index < len(device_breakpoints)
                        else selected_stop
                    )
                    count = min(block_samples, selected_stop - cursor, next_breakpoint - cursor)
                    if count <= 0:
                        raise BundleCorruptionError("V3 physical range could not advance")
                    full_samples = chunk_stream.read_samples(count)
                    samples = np.ascontiguousarray(
                        full_samples[:, self._receiver_column : self._receiver_column + 1, :]
                    )
                    yield PhysicalDeviceIqBlock(
                        samples=samples,
                        device_sample_start=cursor,
                        receiver_ids=self.receiver_ids,
                        content_kind=chunk.content_kind,
                        continuity_segment_index=chunk.continuity_segment_index,
                    )
                    cursor += count
                chunk_stream.skip_samples(chunk_stop - selected_stop)
                chunk_stream.finish()
                chunk_stream = None
            if cursor != device_sample_stop:
                raise BundleCorruptionError("V3 chunks ended before the physical range")
        finally:
            if chunk_stream is not None:
                chunk_stream.close()

    def _assert_open(self) -> None:
        if not self._finalizer.alive:
            raise RuntimeError("verified V3 device-axis source is closed")
        self._capability.assert_bound()


def _verified_v3_inventory(
    capability: _VerifiedBundleCapability,
    stream: RecordingStreamV3,
    *,
    gap_evidence: VerifiedIqGapMapEvidenceV1,
) -> ValidityInventoryV1:
    payload = _read_bounded(
        capability.file(stream.validity_inventory_relative_path),
        maximum_bytes=16 * 1024 * 1024,
    )
    if sha256_digest(payload) != stream.validity_inventory_sha256:
        raise BundleCorruptionError("retained validity-inventory digest mismatch")
    try:
        stored = ValidityInventoryV1.model_validate_json(payload)
        rebuilt = build_validity_inventory_v1(gap_evidence.gap_map)
    except (ValidationError, IqContinuityEvidenceError) as error:
        raise BundleCorruptionError(f"validity inventory is invalid: {error}") from error
    if stored != rebuilt:
        raise BundleCorruptionError(
            "persisted validity inventory disagrees with retained counter evidence"
        )
    if (
        stored.logical_sample_count != stream.logical_sample_count
        or stored.observed_sample_count != stream.observed_sample_count
        or stored.missing_sample_count != stream.zero_fill_sample_count
    ):
        raise BundleCorruptionError("V3 validity counts disagree with its manifest stream")
    _verify_v3_chunk_inventory(stream, stored)
    return stored


def _verify_v3_chunk_inventory(
    stream: RecordingStreamV3,
    validity: ValidityInventoryV1,
) -> None:
    run_index = 0
    device_cursor = 0
    for chunk in stream.chunks:
        while (
            run_index < len(validity.runs)
            and device_cursor == validity.runs[run_index].device_sample_stop
        ):
            run_index += 1
        if run_index >= len(validity.runs):
            raise BundleCorruptionError("V3 chunk inventory exceeds validity evidence")
        run = validity.runs[run_index]
        chunk_stop = chunk.device_sample_start + chunk.sample_count
        if (
            chunk.device_sample_start != device_cursor
            or chunk.device_sample_start < run.device_sample_start
            or chunk_stop > run.device_sample_stop
            or chunk.content_kind is not run.content_kind
            or chunk.continuity_segment_index != run.continuity_segment_index
        ):
            raise BundleCorruptionError("V3 chunk inventory disagrees with validity runs")
        device_cursor = chunk_stop
    while (
        run_index < len(validity.runs)
        and device_cursor == validity.runs[run_index].device_sample_stop
    ):
        run_index += 1
    if run_index != len(validity.runs) or device_cursor != validity.logical_sample_count:
        raise BundleCorruptionError("V3 chunks do not close the validity inventory")


def _verify_v3_stream_bytes(
    capability: _VerifiedBundleCapability,
    stream: RecordingStreamV3,
) -> None:
    logical_digest = hashlib.sha256()
    observed_digest = hashlib.sha256()
    for chunk in stream.chunks:
        retained = _RetainedChunkStream(
            capability.file(chunk.relative_path),
            chunk,
            receiver_count=len(stream.applied_settings.receiver_ids),
        )
        try:
            remaining = chunk.sample_count
            while remaining:
                count = min(262_144, remaining)
                samples = retained.read_samples(count)
                payload = memoryview(samples).cast("B")
                logical_digest.update(payload)
                if chunk.content_kind is DeviceAxisContentKind.OBSERVED:
                    observed_digest.update(payload)
                remaining -= count
            retained.finish()
        finally:
            retained.close()
    if (
        f"sha256:{logical_digest.hexdigest()}" != stream.logical_iq_sha256
        or f"sha256:{observed_digest.hexdigest()}" != stream.observed_iq_sha256
    ):
        raise BundleCorruptionError("retained V3 aggregate IQ digest mismatch")
    evidence_reader = _VerifiedRecordingIqReader(capability, stream.stream_id)
    gap_evidence = evidence_reader.gap_map_evidence()
    _verified_v3_inventory(capability, stream, gap_evidence=gap_evidence)


def _verify_capability_bytes(capability: _VerifiedBundleCapability) -> None:
    manifest_payload = _read_bounded(
        capability.file("manifest.json"), maximum_bytes=16 * 1024 * 1024
    )
    if sha256_digest(manifest_payload) != capability.bundle.manifest_sha256:
        raise InputManifestMismatchError("retained manifest digest changed")
    for stream in capability.bundle.manifest.streams:
        if isinstance(stream, RecordingStreamV3):
            _verify_v3_stream_bytes(capability, stream)
            continue
        reader = _VerifiedRecordingIqReader(capability, stream.stream_id)
        if stream.captured_sample_count:
            for _block in reader.iter_blocks(block_samples=262_144):
                pass
        if isinstance(stream, RecordingStreamV2) and stream.gap_map_relative_path is not None:
            reader.gap_map_evidence()
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
    return type(metadata).model_validate(document)


def _stream_integrities(bundle: PublishedBundle) -> tuple[RawStreamIntegrityV1, ...]:
    streams = []
    for stream in sorted(_recording_streams(bundle.manifest), key=lambda item: item.stream_id):
        streams.append(
            RawStreamIntegrityV1(
                stream_id=stream.stream_id,
                chunk_count=len(stream.chunks),
                compressed_closure_digest=canonical_digest(
                    [
                        {
                            "chunk_index": chunk.chunk_index,
                            "sample_start": _chunk_axis_start(chunk),
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
                            "sample_start": _chunk_axis_start(chunk),
                            "sample_count": chunk.sample_count,
                            "digest": chunk.uncompressed_sha256,
                        }
                        for chunk in stream.chunks
                    ]
                ),
            )
        )
    return tuple(streams)


def _chunk_axis_start(chunk: RecordingChunkV1 | DeviceAxisRecordingChunkV1) -> int:
    return (
        chunk.device_sample_start
        if isinstance(chunk, DeviceAxisRecordingChunkV1)
        else chunk.sample_start
    )


def _recording_streams(
    manifest: RecordingManifestV1 | RecordingManifestV3,
) -> tuple[RecordingStreamV1 | RecordingStreamV3, ...]:
    return cast(tuple[RecordingStreamV1 | RecordingStreamV3, ...], manifest.streams)


def _capability_stream(
    capability: _VerifiedBundleCapability,
    stream_id: str,
) -> RecordingStreamV1 | RecordingStreamV3:
    matches = tuple(
        stream for stream in capability.bundle.manifest.streams if stream.stream_id == stream_id
    )
    if len(matches) != 1:
        raise ValueError(f"verified manifest has no unique stream {stream_id!r}")
    return matches[0]


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
            yield self._select_receiver(block)

    def iter_stored_blocks(
        self,
        *,
        stored_sample_start: int,
        sample_count: int,
        block_samples: int,
    ) -> Iterable[IqBlock]:
        method = getattr(self._source, "iter_stored_blocks", None)
        if not callable(method):
            raise ValueError("selected IQ reader has no bounded stored-range access")
        for block in method(
            stored_sample_start=stored_sample_start,
            sample_count=sample_count,
            block_samples=block_samples,
        ):
            yield self._select_receiver(cast(IqBlock, block))

    def gap_map_evidence(self) -> VerifiedIqGapMapEvidenceV1:
        method = getattr(self._source, "gap_map_evidence", None)
        if not callable(method):
            raise ValueError("selected IQ reader has no verified gap-map evidence")
        return cast(VerifiedIqGapMapEvidenceV1, method())

    def _select_receiver(self, block: IqBlock) -> IqBlock:
        samples = np.ascontiguousarray(block.samples[:, self._column : self._column + 1, :])
        return IqBlock(
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

    def iter_stored_blocks(
        self,
        *,
        stored_sample_start: int,
        sample_count: int,
        block_samples: int,
    ) -> Iterable[IqBlock]:
        method = getattr(self._source, "iter_stored_blocks", None)
        if not callable(method):
            raise ValueError("selected IQ reader has no bounded stored-range access")
        yield from method(
            stored_sample_start=stored_sample_start,
            sample_count=sample_count,
            block_samples=block_samples,
        )

    def gap_map_evidence(self) -> VerifiedIqGapMapEvidenceV1:
        method = getattr(self._source, "gap_map_evidence", None)
        if not callable(method):
            raise ValueError("selected IQ reader has no verified gap-map evidence")
        return cast(VerifiedIqGapMapEvidenceV1, method())

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
        scope: ScopeIdentityV1 | None = None,
    ) -> None:
        self._catalog = catalog
        self._artifacts = artifacts
        self._run_id = run_id
        self._scope_key = scope_key
        self._job_id = job_id
        self._scope = scope
        self._consumed_product_ids: set[int] = set()

    @property
    def consumed_product_ids(self) -> tuple[int, ...]:
        return tuple(sorted(self._consumed_product_ids))

    def after_fork(self) -> None:
        self._catalog.dispose_inherited_connections_after_fork()

    def read_subject_binding(self) -> dict[str, JsonValue]:
        if self._scope is None:
            raise ValueError("subject binding requires a typed persisted scope")
        return cast(
            dict[str, JsonValue],
            self._catalog.run_subject_binding(self._run_id, self._scope).document,
        )

    def read_json(self, requirement: ProductRequirement) -> dict[str, JsonValue] | None:
        selected = self._select_one(requirement)
        if selected is None:
            return None
        _, product = selected
        document = self._artifacts.read_json(product.logical_uri, product.digest)
        self._consumed_product_ids.add(product.product_id)
        return document

    def read_json_bound(self, requirement: ProductRequirement) -> UpstreamJsonProduct | None:
        selected = self._select_one(requirement)
        if selected is None:
            return None
        node_id, product = selected
        if node_id is None or product.scope is None:
            raise ValueError("bound product requires an exact typed producer node and scope")
        document = self._artifacts.read_json(product.logical_uri, product.digest)
        self._consumed_product_ids.add(product.product_id)
        return UpstreamJsonProduct(
            producer_node_id=node_id,
            producer_scope=product.scope,
            outcome=StageOutcome(product.status),
            product_digest=product.digest,
            document=document,
            membership=cast(dict[str, JsonValue], product.summary),
        )

    def _select_one(
        self,
        requirement: ProductRequirement,
    ) -> tuple[str | None, CatalogProductRecord] | None:
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
            tuple(authorized)
            if authorized is not None
            else tuple((None, product) for product in snapshot.products)
        )
        matches = tuple(
            (node_id, product)
            for node_id, product in candidates
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
            version_matches = tuple(item for item in matches if item[1].schema_version == version)
            if len(version_matches) > 1:
                raise ValueError(
                    f"required product is ambiguous for {self._scope_key}: "
                    f"{requirement.kind} v{version}"
                )
            if version_matches:
                return version_matches[0]
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
                    outcome=StageOutcome(selected.status),
                    product_digest=selected.digest,
                    document=document,
                    membership=cast(dict[str, JsonValue], selected.summary),
                )
            )
        return tuple(output)
