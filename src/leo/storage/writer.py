"""Streaming, crash-safe construction of immutable recording bundles."""

from __future__ import annotations

import hashlib
import os
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, cast

import zstandard as zstd

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.contracts.radio import IqBlockMetadataV1, IqBlockMetadataV2, RadioIdentityV1
from leo.contracts.recording import (
    CompressionSettingsV1,
    ContinuitySummaryV1,
    ContinuitySummaryV2,
    RecordingChunkV1,
    RecordingManifestV1,
    RecordingStreamV1,
    RecordingStreamV2,
    TerminalGapEvidenceV1,
)
from leo.contracts.states import ContinuityStatus, StreamState
from leo.domain.continuity import ContinuityChainValidator
from leo.domain.gap_map import build_iq_gap_map
from leo.domain.iq import IqBlock
from leo.storage.errors import BundleStateError
from leo.storage.uri import BulkUriResolver

FailureInjector = Callable[[str], None]
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True, slots=True)
class StreamWriteReceipt:
    stream_id: str
    radio_id: str
    receiver_ids: tuple[int, ...]
    captured_sample_count: int
    chunks: tuple[RecordingChunkV1, ...]
    timeline_relative_path: str
    timeline_sha256: str
    gap_map_relative_path: str | None
    gap_map_sha256: str | None
    continuity: ContinuitySummaryV1 | ContinuitySummaryV2


@dataclass(frozen=True, slots=True)
class StreamQueueTelemetry:
    capacity_refills: int
    high_water_refills: int
    enqueue_failure_count: int = 0
    maximum_refill_service_interval_ns: int = 0

    def __post_init__(self) -> None:
        if self.capacity_refills <= 0:
            raise ValueError("queue capacity must be positive")
        if not 0 <= self.high_water_refills <= self.capacity_refills:
            raise ValueError("queue high-water is outside its capacity")
        if self.enqueue_failure_count < 0 or self.maximum_refill_service_interval_ns < 0:
            raise ValueError("queue telemetry cannot be negative")


@dataclass(frozen=True, slots=True)
class PublishedBundle:
    session_id: str
    path: Path
    uri: str
    manifest: RecordingManifestV1
    manifest_sha256: str


class _DigestingSink:
    def __init__(self, stream: object) -> None:
        self._stream = stream
        self._digest = hashlib.sha256()
        self.byte_count = 0

    @property
    def digest(self) -> str:
        return f"sha256:{self._digest.hexdigest()}"

    def write(self, payload: bytes | bytearray | memoryview) -> int:
        written = self._stream.write(payload)  # type: ignore[attr-defined]
        if written is None:
            written = len(payload)
        self._digest.update(memoryview(payload)[:written])
        self.byte_count += written
        return written

    def flush(self) -> None:
        self._stream.flush()  # type: ignore[attr-defined]


class _CompressedFileWriter:
    def __init__(self, partial_path: Path, *, level: int) -> None:
        self.partial_path = partial_path
        self.final_path = partial_path.with_suffix("")
        self._raw = partial_path.open("xb")
        self._sink = _DigestingSink(self._raw)
        self._zstd = zstd.ZstdCompressor(
            level=level,
            write_checksum=True,
            write_content_size=False,
        ).stream_writer(cast(BinaryIO, self._sink), closefd=False)
        self._closed = False

    def write(self, payload: bytes | bytearray | memoryview) -> None:
        if self._closed:
            raise BundleStateError("compressed file writer is closed")
        self._zstd.write(payload)

    def finish(self) -> tuple[Path, int, str]:
        if self._closed:
            raise BundleStateError("compressed file writer is closed")
        self._zstd.close()
        self._raw.flush()
        os.fsync(self._raw.fileno())
        self._raw.close()
        self._closed = True
        os.replace(self.partial_path, self.final_path)
        _fsync_directory(self.final_path.parent)
        return self.final_path, self._sink.byte_count, self._sink.digest

    def abort(self) -> None:
        if self._closed:
            return
        try:
            self._zstd.close()
        finally:
            self._raw.close()
            self._closed = True


class _ChunkWriter:
    def __init__(
        self,
        stream_directory: Path,
        *,
        chunk_index: int,
        segment_index: int,
        sample_start: int,
        level: int,
    ) -> None:
        name = f"iq-{chunk_index:06d}.ci16.zst"
        self._compressed = _CompressedFileWriter(stream_directory / f"{name}.partial", level=level)
        self.chunk_index = chunk_index
        self.segment_index = segment_index
        self.sample_start = sample_start
        self.sample_count = 0
        self.uncompressed_bytes = 0
        self._uncompressed_digest = hashlib.sha256()

    def append(self, block: IqBlock) -> None:
        payload = block.wire_bytes
        self._compressed.write(payload)
        self._uncompressed_digest.update(payload)
        self.uncompressed_bytes += payload.nbytes
        self.sample_count += block.metadata.sample_count

    def finish(self, session_directory: Path) -> RecordingChunkV1:
        final_path, compressed_bytes, compressed_digest = self._compressed.finish()
        return RecordingChunkV1(
            chunk_index=self.chunk_index,
            segment_index=self.segment_index,
            relative_path=final_path.relative_to(session_directory).as_posix(),
            sample_start=self.sample_start,
            sample_count=self.sample_count,
            uncompressed_bytes=self.uncompressed_bytes,
            compressed_bytes=compressed_bytes,
            uncompressed_sha256=f"sha256:{self._uncompressed_digest.hexdigest()}",
            compressed_sha256=compressed_digest,
        )

    def abort(self) -> None:
        self._compressed.abort()


class StreamBundleWriter:
    """Write complete refills into independently compressed, bounded shards."""

    def __init__(
        self,
        session_directory: Path,
        stream_directory: Path,
        *,
        stream_id: str,
        radio: RadioIdentityV1,
        receiver_ids: tuple[int, ...],
        compression: CompressionSettingsV1,
        on_finalize: Callable[[StreamWriteReceipt], None],
        counter_authoritative: bool = False,
        kernel_buffers: int | None = None,
    ) -> None:
        self._session_directory = session_directory
        self._stream_directory = stream_directory
        self._stream_id = stream_id
        self._radio = radio
        self._receiver_ids = receiver_ids
        self._compression = compression
        self._on_finalize = on_finalize
        self._counter_authoritative = counter_authoritative
        self._kernel_buffers = kernel_buffers
        if counter_authoritative and (kernel_buffers is None or kernel_buffers < 2):
            raise ValueError("counter-authoritative writer requires verified kernel buffers")
        self._continuity_validator = ContinuityChainValidator(
            require_metadata=counter_authoritative,
            require_generation=counter_authoritative,
            validate_declared=True,
        )
        self._timeline = _CompressedFileWriter(
            stream_directory / "timeline.jsonl.zst.partial",
            level=compression.level,
        )
        self._current_chunk: _ChunkWriter | None = None
        self._chunks: list[RecordingChunkV1] = []
        self._captured_samples = 0
        self._refill_count = 0
        self._segment_index = 0
        self._gap_count = 0
        self._missing_samples = 0
        self._overflow_count = 0
        self._first_sequence: int | None = None
        self._last_sequence: int | None = None
        self._all_sequences_present = True
        self._first_counter: int | None = None
        self._last_counter: int | None = None
        self._all_counters_present = True
        self._metadata_abi_version: int | None = None
        self._timeline_records: list[IqBlockMetadataV1] = []
        self._closed = False

    def append(self, block: IqBlock) -> None:
        self._require_open()
        metadata = self._continuity_validator.observe(block.metadata)
        if metadata is not block.metadata:
            block = IqBlock(samples=block.samples, metadata=metadata)
        if metadata.radio_id != self._radio.radio_id:
            raise ValueError("IQ block radio does not match its stream writer")
        if metadata.receiver_ids != self._receiver_ids:
            raise ValueError("IQ block receivers changed within a stream")
        if metadata.session_sample_start != self._captured_samples:
            raise ValueError("IQ block session sample coordinate is not contiguous")
        if self._counter_authoritative:
            if not isinstance(metadata, IqBlockMetadataV2):
                raise ValueError("counter-authoritative writer requires V2 IQ metadata")
            if metadata.kernel_buffers != self._kernel_buffers:
                raise ValueError("IQ metadata kernel-buffer readback changed")
            if self._metadata_abi_version is None:
                self._metadata_abi_version = metadata.metadata_abi_version
            elif metadata.metadata_abi_version != self._metadata_abi_version:
                raise ValueError("IQ metadata ABI changed within a stream")

        starts_new_segment = self._refill_count > 0 and metadata.continuity in {
            ContinuityStatus.GAP_BEFORE,
            ContinuityStatus.OVERFLOW,
        }
        if starts_new_segment:
            self._finish_current_chunk()
            self._segment_index += 1
        if metadata.continuity is ContinuityStatus.GAP_BEFORE:
            self._gap_count += 1
            self._missing_samples += metadata.missing_samples_before
        if metadata.overflow_observed or metadata.continuity is ContinuityStatus.OVERFLOW:
            self._overflow_count += 1

        payload_bytes = block.wire_bytes.nbytes
        if (
            self._current_chunk is not None
            and self._current_chunk.uncompressed_bytes
            and self._current_chunk.uncompressed_bytes + payload_bytes
            > self._compression.target_uncompressed_bytes
        ):
            self._finish_current_chunk()
        if self._current_chunk is None:
            self._current_chunk = _ChunkWriter(
                self._stream_directory,
                chunk_index=len(self._chunks),
                segment_index=self._segment_index,
                sample_start=self._captured_samples,
                level=self._compression.level,
            )

        self._current_chunk.append(block)
        timeline_line = canonical_json_bytes(metadata.model_dump(mode="json")) + b"\n"
        self._timeline.write(timeline_line)
        self._timeline_records.append(metadata)
        self._observe_sequence(metadata.source_sequence)
        self._observe_counter(metadata.device_sample_counter, metadata.sample_count)
        self._captured_samples += metadata.sample_count
        self._refill_count += 1

    def finalize(
        self,
        *,
        queue_telemetry: StreamQueueTelemetry | None = None,
        terminal_gap_metadata: IqBlockMetadataV2 | None = None,
        terminal_enqueue_failure_metadata: IqBlockMetadataV2 | None = None,
        requested_device_span: int | None = None,
    ) -> StreamWriteReceipt:
        self._require_open()
        if self._refill_count == 0:
            self.abort()
            raise BundleStateError("cannot finalize an empty IQ stream")
        terminal_gap = None
        terminal_enqueue_failure = None
        summary_gap_count = self._gap_count
        summary_missing_samples = self._missing_samples
        summary_overflow_count = self._overflow_count
        device_span = (
            0
            if self._first_counter is None or self._last_counter is None
            else self._last_counter - self._first_counter + 1
        )
        if terminal_gap_metadata is not None:
            if not self._counter_authoritative or requested_device_span is None:
                raise BundleStateError("terminal gap evidence requires a V2 device-span request")
            validated_terminal = self._continuity_validator.observe(terminal_gap_metadata)
            if (
                not isinstance(validated_terminal, IqBlockMetadataV2)
                or validated_terminal.continuity is not ContinuityStatus.GAP_BEFORE
                or self._last_counter is None
                or self._first_counter is None
            ):
                raise BundleStateError("terminal metadata is not one validated positive gap")
            assert validated_terminal.device_sample_counter is not None
            assert validated_terminal.source_sequence is not None
            in_span_missing = requested_device_span - device_span
            if not 0 < in_span_missing <= validated_terminal.missing_samples_before:
                raise BundleStateError("terminal gap does not close the requested device span")
            expected_counter = (
                validated_terminal.device_sample_counter - validated_terminal.missing_samples_before
            )
            if expected_counter != self._last_counter + 1:
                raise BundleStateError("terminal gap does not begin after stored IQ")
            terminal_gap = TerminalGapEvidenceV1(
                expected_device_sample_counter=expected_counter,
                actual_device_sample_counter=validated_terminal.device_sample_counter,
                actual_missing_sample_count=validated_terminal.missing_samples_before,
                in_span_missing_sample_count=in_span_missing,
                source_sequence=validated_terminal.source_sequence,
                returned_sample_count=validated_terminal.sample_count,
                stream_generation=validated_terminal.stream_generation,
                metadata_abi_version=validated_terminal.metadata_abi_version,
                metadata_flags=validated_terminal.metadata_flags,
                overflow_observed=validated_terminal.overflow_observed,
                hardware_metadata=validated_terminal.hardware_metadata,
            )
            summary_gap_count += 1
            summary_missing_samples += in_span_missing
            summary_overflow_count += int(validated_terminal.overflow_observed)
            device_span = requested_device_span
        if terminal_enqueue_failure_metadata is not None:
            if not self._counter_authoritative:
                raise BundleStateError("terminal enqueue evidence requires a V2 stream")
            validated_enqueue_failure = self._continuity_validator.observe(
                terminal_enqueue_failure_metadata
            )
            if not isinstance(validated_enqueue_failure, IqBlockMetadataV2):
                raise BundleStateError("terminal enqueue evidence is not V2 IQ metadata")
            terminal_enqueue_failure = validated_enqueue_failure
        common = dict(
            refill_count=self._refill_count,
            segment_count=self._segment_index + 1,
            gap_count=summary_gap_count,
            missing_sample_count=summary_missing_samples,
            overflow_count=summary_overflow_count,
            sample_loss_observable=self._continuity_validator.validated,
            first_source_sequence=(self._first_sequence if self._all_sequences_present else None),
            last_source_sequence=(self._last_sequence if self._all_sequences_present else None),
            first_device_sample_counter=(
                self._first_counter if self._all_counters_present else None
            ),
            last_device_sample_counter=(self._last_counter if self._all_counters_present else None),
        )
        if self._counter_authoritative:
            if queue_telemetry is None:
                raise BundleStateError("V2 stream finalization requires queue telemetry")
            assert self._kernel_buffers is not None
            assert self._first_counter is not None and self._last_counter is not None
            assert self._metadata_abi_version is not None
            continuity: ContinuitySummaryV1 | ContinuitySummaryV2 = (
                ContinuitySummaryV2.model_validate(
                    {
                        **common,
                        "observed_sample_count": self._captured_samples,
                        "device_span_sample_count": device_span,
                        "kernel_buffers": self._kernel_buffers,
                        "metadata_abi_version": self._metadata_abi_version,
                        "validated_stream_generation": (
                            self._continuity_validator.stream_generation
                        ),
                        "queue_capacity_refills": queue_telemetry.capacity_refills,
                        "queue_high_water_refills": queue_telemetry.high_water_refills,
                        "enqueue_failure_count": queue_telemetry.enqueue_failure_count,
                        "maximum_refill_service_interval_ns": (
                            queue_telemetry.maximum_refill_service_interval_ns
                        ),
                        "terminal_gap": terminal_gap,
                        "terminal_enqueue_failure": terminal_enqueue_failure,
                    }
                )
            )
        else:
            continuity = ContinuitySummaryV1.model_validate(common)
        self._finish_current_chunk()
        timeline_path, _timeline_bytes, timeline_digest = self._timeline.finish()
        gap_map_relative_path = None
        gap_map_digest = None
        if self._counter_authoritative:
            assert isinstance(continuity, ContinuitySummaryV2)
            gap_map = build_iq_gap_map(
                stream_id=self._stream_id,
                timeline_sha256=timeline_digest,
                timeline=self._timeline_records,
                continuity=continuity,
            )
            gap_map_payload = canonical_json_bytes(gap_map.model_dump(mode="json"))
            gap_map_path = _write_immutable_file(
                self._stream_directory / "gap-map.json",
                gap_map_payload,
            )
            gap_map_relative_path = gap_map_path.relative_to(self._session_directory).as_posix()
            gap_map_digest = sha256_digest(gap_map_payload)
        self._closed = True
        receipt = StreamWriteReceipt(
            stream_id=self._stream_id,
            radio_id=self._radio.radio_id,
            receiver_ids=self._receiver_ids,
            captured_sample_count=self._captured_samples,
            chunks=tuple(self._chunks),
            timeline_relative_path=timeline_path.relative_to(self._session_directory).as_posix(),
            timeline_sha256=timeline_digest,
            gap_map_relative_path=gap_map_relative_path,
            gap_map_sha256=gap_map_digest,
            continuity=continuity,
        )
        self._on_finalize(receipt)
        return receipt

    def abort(self) -> None:
        if self._closed:
            return
        if self._current_chunk is not None:
            self._current_chunk.abort()
            self._current_chunk = None
        self._timeline.abort()
        self._closed = True

    def _finish_current_chunk(self) -> None:
        if self._current_chunk is None:
            return
        self._chunks.append(self._current_chunk.finish(self._session_directory))
        self._current_chunk = None

    def _observe_sequence(self, value: int | None) -> None:
        if value is None:
            self._all_sequences_present = False
            return
        if self._first_sequence is None:
            self._first_sequence = value
        self._last_sequence = value

    def _observe_counter(self, value: int | None, sample_count: int) -> None:
        if value is None:
            self._all_counters_present = False
            return
        if self._first_counter is None:
            self._first_counter = value
        self._last_counter = value + sample_count - 1

    def _require_open(self) -> None:
        if self._closed:
            raise BundleStateError("IQ stream writer is closed")


class RecordingBundleWriter:
    """Own one spool directory and publish its manifest and directory atomically."""

    def __init__(
        self,
        root: Path,
        *,
        session_id: str,
        compression: CompressionSettingsV1,
        resolver: BulkUriResolver,
        spool_root: Path | None = None,
        recordings_root: Path | None = None,
        failure_injector: FailureInjector | None = None,
    ) -> None:
        if not _IDENTIFIER.fullmatch(session_id):
            raise ValueError("session ID is not one safe persisted identifier")
        self.root = root
        self.session_id = session_id
        self.compression = compression
        self._resolver = resolver
        self._failure_injector = failure_injector
        self._recordings_root = root / "recordings" if recordings_root is None else recordings_root
        spool = root / "spool" if spool_root is None else spool_root
        self._spool_path = spool / f"{session_id}.partial"
        self._spool_path.mkdir(parents=False, exist_ok=False)
        _fsync_directory(self._spool_path.parent)
        self._lock = threading.Lock()
        self._publication_forbidden = threading.Event()
        self._writers: dict[str, StreamBundleWriter] = {}
        self._receipts: dict[str, StreamWriteReceipt] = {}
        self._published_path: Path | None = None
        self._closed = False

    @property
    def spool_path(self) -> Path:
        return self._spool_path

    @property
    def published_path(self) -> Path | None:
        return self._published_path

    @property
    def quarantined(self) -> bool:
        return self._publication_forbidden.is_set()

    def quarantine(self) -> None:
        """Permanently forbid publication without racing an active stream writer.

        A bounded coordinator shutdown can return while a stuck storage thread is
        still inside compression or fsync.  Aborting that writer concurrently would
        corrupt its file objects, so quarantine only closes the bundle's publication
        gate.  The unpublished ``.partial`` spool remains as failure evidence, and a
        late finalize callback is rejected by :meth:`_register_receipt`.
        """

        if self._published_path is not None:
            raise BundleStateError("cannot quarantine an already-published bundle")
        # This fence must not wait for ``_lock``: a storage syscall may be hung
        # inside ``open_stream`` while holding it.  Publication belongs to the
        # coordinator thread, which can only run after its capture workers have
        # returned, so setting this monotonic event before returning is enough
        # to reject every subsequent open, receipt callback, close, or publish.
        self._publication_forbidden.set()
        self._closed = True

    def open_stream(
        self,
        stream_id: str,
        radio: RadioIdentityV1,
        receiver_ids: tuple[int, ...],
        *,
        counter_authoritative: bool = False,
        kernel_buffers: int | None = None,
    ) -> StreamBundleWriter:
        if not _IDENTIFIER.fullmatch(stream_id):
            raise ValueError("stream ID is not one safe persisted identifier")
        if not receiver_ids or tuple(sorted(set(receiver_ids))) != receiver_ids:
            raise ValueError("stream receivers must be non-empty, unique, and sorted")
        self._require_open()
        with self._lock:
            self._require_open()
            if stream_id in self._writers or stream_id in self._receipts:
                raise BundleStateError(f"stream already exists: {stream_id}")
            directory_name = _radio_directory_name(radio.serial)
            if any(
                writer._stream_directory.name == directory_name for writer in self._writers.values()
            ):
                raise BundleStateError("radio serial maps to an existing stream directory")
            stream_directory = self._spool_path / directory_name
            stream_directory.mkdir(exist_ok=False)
            _fsync_directory(self._spool_path)
            # Quarantine is deliberately lock-free and may have been declared
            # while the directory fsync above was stalled.
            self._require_open()
            writer = StreamBundleWriter(
                self._spool_path,
                stream_directory,
                stream_id=stream_id,
                radio=radio,
                receiver_ids=receiver_ids,
                compression=self.compression,
                on_finalize=self._register_receipt,
                counter_authoritative=counter_authoritative,
                kernel_buffers=kernel_buffers,
            )
            self._writers[stream_id] = writer
            return writer

    def publish(self, manifest: RecordingManifestV1) -> PublishedBundle:
        with self._lock:
            self._require_open()
            if any(stream_id not in self._receipts for stream_id in self._writers):
                raise BundleStateError("all opened stream writers must be finalized")
            self._validate_manifest(manifest)
            manifest_payload = canonical_json_bytes(manifest.model_dump(mode="json"))
            partial_manifest = self._spool_path / "manifest.json.partial"
            with partial_manifest.open("xb") as stream:
                stream.write(manifest_payload)
                stream.flush()
                os.fsync(stream.fileno())
            self._inject("after_manifest_fsync")
            manifest_path = self._spool_path / "manifest.json"
            os.replace(partial_manifest, manifest_path)
            _fsync_directory(self._spool_path)
            self._inject("after_manifest_rename")

            created = datetime.fromtimestamp(
                manifest.created_utc_ns // 1_000_000_000,
                tz=UTC,
            )
            parent = (
                self._recordings_root
                / f"{created.year:04d}"
                / f"{created.month:02d}"
                / f"{created.day:02d}"
            )
            _mkdir_durable(parent, stop=self._recordings_root)
            final_path = parent / self.session_id
            if final_path.exists():
                raise FileExistsError(f"recording bundle already exists: {final_path}")
            os.rename(self._spool_path, final_path)
            self._published_path = final_path
            self._closed = True
            self._inject("after_session_rename")
            _fsync_directory(parent)
            self._inject("after_recordings_parent_fsync")
            return PublishedBundle(
                session_id=self.session_id,
                path=final_path,
                uri=self._resolver.uri_for(final_path),
                manifest=manifest,
                manifest_sha256=sha256_digest(manifest_payload),
            )

    def close(self) -> None:
        if self._publication_forbidden.is_set():
            # A quarantined writer may still have a daemon consumer blocked in
            # storage while holding ``_lock``.  Preserve that spool as evidence
            # and never defeat the coordinator's bounded shutdown by waiting.
            self._closed = True
            return
        with self._lock:
            if self._closed:
                return
            for writer in self._writers.values():
                writer.abort()
            self._closed = True

    def _register_receipt(self, receipt: StreamWriteReceipt) -> None:
        # Reject a late consumer before attempting the potentially occupied
        # bundle lock.  It can finalize files in the quarantined spool, but it
        # can never make them eligible for publication.
        self._require_open()
        with self._lock:
            self._require_open()
            if receipt.stream_id in self._receipts:
                raise BundleStateError(f"stream already finalized: {receipt.stream_id}")
            self._receipts[receipt.stream_id] = receipt

    def _validate_manifest(self, manifest: RecordingManifestV1) -> None:
        if manifest.session_id != self.session_id:
            raise BundleStateError("manifest session ID does not match its spool directory")
        if manifest.compression != self.compression:
            raise BundleStateError("manifest compression settings changed during capture")
        manifest_stream_ids = {stream.stream_id for stream in manifest.streams}
        if set(self._receipts) - manifest_stream_ids:
            raise BundleStateError("manifest omits a finalized IQ stream")
        for stream in manifest.streams:
            receipt = self._receipts.get(stream.stream_id)
            if stream.state is StreamState.FAILED:
                if receipt is not None:
                    raise BundleStateError("failed manifest stream has a finalized IQ receipt")
                continue
            if receipt is None:
                raise BundleStateError("manifest data stream has no finalized IQ receipt")
            self._validate_stream_receipt(stream, receipt)

    @staticmethod
    def _validate_stream_receipt(
        stream: RecordingStreamV1,
        receipt: StreamWriteReceipt,
    ) -> None:
        if stream.applied_settings is None:
            raise BundleStateError("stored IQ stream has no applied radio settings")
        if (
            stream.radio.radio_id != receipt.radio_id
            or stream.applied_settings.receiver_ids != receipt.receiver_ids
            or stream.captured_sample_count != receipt.captured_sample_count
            or stream.chunks != receipt.chunks
            or stream.timeline_relative_path != receipt.timeline_relative_path
            or stream.timeline_sha256 != receipt.timeline_sha256
        ):
            raise BundleStateError("manifest stream inventory disagrees with written IQ")
        if isinstance(stream, RecordingStreamV2) and (
            stream.gap_map_relative_path != receipt.gap_map_relative_path
            or stream.gap_map_sha256 != receipt.gap_map_sha256
        ):
            raise BundleStateError("manifest gap map disagrees with written continuity evidence")
        stored = receipt.continuity
        declared = stream.continuity
        storage_fields: tuple[str, ...] = (
            "refill_count",
            "segment_count",
            "gap_count",
            "missing_sample_count",
            "overflow_count",
            "sample_loss_observable",
            "first_source_sequence",
            "last_source_sequence",
            "first_device_sample_counter",
            "last_device_sample_counter",
        )
        if isinstance(stored, ContinuitySummaryV2):
            storage_fields += (
                "observed_sample_count",
                "device_span_sample_count",
                "kernel_buffers",
                "metadata_abi_version",
                "validated_stream_generation",
                "queue_capacity_refills",
                "queue_high_water_refills",
                "enqueue_failure_count",
                "maximum_refill_service_interval_ns",
                "terminal_gap",
                "terminal_enqueue_failure",
            )
        if any(getattr(stored, field) != getattr(declared, field) for field in storage_fields):
            raise BundleStateError("manifest continuity disagrees with written timeline")

    def _inject(self, point: str) -> None:
        if self._failure_injector is not None:
            self._failure_injector(point)

    def _require_open(self) -> None:
        if self._publication_forbidden.is_set():
            raise BundleStateError("recording bundle writer is quarantined")
        if self._closed:
            raise BundleStateError("recording bundle writer is closed")


def _radio_directory_name(serial: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", serial).strip("._-") or "radio"
    if safe == serial and len(safe) <= 80:
        return f"radio-{safe}"
    suffix = hashlib.sha256(serial.encode("utf-8")).hexdigest()[:12]
    return f"radio-{safe[:64]}-{suffix}"


def _write_immutable_file(path: Path, payload: bytes) -> Path:
    partial = path.with_suffix(path.suffix + ".partial")
    with partial.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(partial, path)
    _fsync_directory(path.parent)
    return path


def _mkdir_durable(path: Path, *, stop: Path) -> None:
    if stop.parts[:4] != ("/", "proc", "self", "fd"):
        stop = stop.resolve(strict=True)
    relative = path.relative_to(stop)
    current = stop
    for part in relative.parts:
        child = current / part
        try:
            child.mkdir()
        except FileExistsError:
            if not child.is_dir():
                raise
        else:
            _fsync_directory(current)
        current = child


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
