"""Bounded chunk writer and verified reader for short-window IQ recordings."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import zstandard as zstd

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.contracts.short_window_recording import (
    ShortWindowChunkV1,
    ShortWindowIndexV1,
    ShortWindowManifestV1,
)
from leo.contracts.multirate_window_recording import (
    ShortWindowChunkV2, ShortWindowIndexV2, ShortWindowManifestV2,
)
from leo.storage.errors import BundleCorruptionError
from leo.storage.scanner import ScannerIqStore
from leo.storage.uri import confined_path
from leo.storage.writer import _CompressedFileWriter, _fsync_directory

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True)
class ShortWindowRead:
    index: ShortWindowIndexV1
    samples: np.ndarray


class ShortWindowWriter:
    """One writer owner; queue/thread policy belongs to the capture application."""

    def __init__(
        self,
        root: Path,
        session_id: str,
        *,
        configuration: dict[str, Any],
        radio: dict[str, Any],
        receiver_ids: tuple[int, ...],
        chunk_windows: int = 64,
        compression_level: int = 1,
        schema_version: int = 1,
    ) -> None:
        resolved = root.resolve()
        if resolved == Path("/mnt/qnap01") or Path("/mnt/qnap01") in resolved.parents:
            raise ValueError("short-window recordings cannot be written beneath QNAP")
        if not _IDENTIFIER.fullmatch(session_id):
            raise ValueError("invalid recording session identifier")
        if not 1 <= chunk_windows <= 256:
            raise ValueError("chunk window bound must be between 1 and 256")
        if len(receiver_ids) not in (1, 2) or len(set(receiver_ids)) != len(receiver_ids):
            raise ValueError("one or two distinct receivers are required")
        if any(receiver < 0 for receiver in receiver_ids):
            raise ValueError("receiver identifiers must be nonnegative")
        # Accept dataclass-shaped mappings while persisting only canonical JSON.
        # Freeze caller-owned dictionaries before the asynchronous writer uses them.
        configuration = json.loads(canonical_json_bytes(configuration))
        radio = json.loads(canonical_json_bytes(radio))
        if schema_version not in (1, 2):
            raise ValueError("unsupported window recording schema")
        self.schema_version = schema_version
        self.rate = configuration.get("sample_rate_hz", 2_500_000)
        if schema_version == 2 and self.rate not in (1_250_000, 2_500_000, 5_000_000, 7_500_000, 10_000_000):
            raise ValueError("unsupported native window rate")
        self.root = resolved
        self.root.mkdir(parents=True, exist_ok=True)
        self.destination = resolved / session_id
        self.partial = resolved / f".{session_id}.partial"
        if self.destination.exists():
            raise FileExistsError(self.destination)
        self.partial.mkdir(exist_ok=False)
        _fsync_directory(self.root)
        self.session_id = session_id
        self.configuration = configuration
        self.radio = radio
        self.receiver_ids = receiver_ids
        self.chunk_windows = chunk_windows
        self.compression_level = compression_level
        self.created_utc_ns = time.time_ns()
        self.chunks: list[ShortWindowChunkV1] = []
        self.window_count = 0
        self._rows: list[ShortWindowIndexV1] = []
        self._payload: _CompressedFileWriter | None = None
        self._raw_bytes = 0
        self._raw_hash = hashlib.sha256()
        self._closed = False

    def append(
        self,
        *,
        sequence: int,
        target_id: str,
        samples: np.ndarray,
        acquisition: dict[str, Any],
        powers: tuple[dict[str, Any], ...],
    ) -> None:
        if self._closed:
            raise RuntimeError("recording writer is closed")
        if sequence != self.window_count:
            raise ValueError("window sequence must be consecutive")
        values = np.asarray(samples)
        if (
            values.dtype != np.dtype("<i2")
            or values.ndim != 3
            or values.shape[1:] != (len(self.receiver_ids), 2)
            or len(values) > (50_000 if self.schema_version == 1 else self.rate // 50)
            or not values.flags.c_contiguous
        ):
            raise ValueError("window exceeds native CI16 sample/receiver/IQ geometry")
        payload = memoryview(values.reshape(-1)).cast("B")
        row = (ShortWindowIndexV1 if self.schema_version == 1 else ShortWindowIndexV2)(
            sequence=sequence,
            target_id=target_id,
            sample_count=len(values),
            receiver_count=len(self.receiver_ids),
            payload_offset_bytes=self._raw_bytes,
            payload_bytes=payload.nbytes,
            iq_sha256=sha256_digest(payload),
            acquisition=json.loads(canonical_json_bytes(acquisition)),
            powers=tuple(json.loads(canonical_json_bytes(powers))),
        )
        if self._payload is None:
            self._payload = _CompressedFileWriter(
                self.partial / f"iq-{len(self.chunks):06d}.ci16.zst.partial",
                level=self.compression_level,
            )
        self._payload.write(payload)
        self._raw_hash.update(payload)
        self._raw_bytes += payload.nbytes
        self._rows.append(row)
        self.window_count += 1
        if len(self._rows) == self.chunk_windows:
            self._finish_chunk()

    def _finish_chunk(self) -> None:
        if self._payload is None:
            return
        path, compressed_bytes, compressed_hash = self._payload.finish()
        index_path = self.partial / f"windows-{len(self.chunks):06d}.jsonl"
        index_bytes = b"".join(
            canonical_json_bytes(row.model_dump(mode="json")) + b"\n" for row in self._rows
        )
        with index_path.open("xb") as stream:
            stream.write(index_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        chunk = (ShortWindowChunkV1 if self.schema_version == 1 else ShortWindowChunkV2)(
            chunk_index=len(self.chunks),
            first_sequence=self._rows[0].sequence,
            window_count=len(self._rows),
            payload_relative_path=path.name,
            index_relative_path=index_path.name,
            uncompressed_bytes=self._raw_bytes,
            compressed_bytes=compressed_bytes,
            index_bytes=len(index_bytes),
            uncompressed_sha256=f"sha256:{self._raw_hash.hexdigest()}",
            compressed_sha256=compressed_hash,
            index_sha256=sha256_digest(index_bytes),
        )
        self.chunks.append(chunk)
        self._payload = None
        self._rows = []
        self._raw_bytes = 0
        self._raw_hash = hashlib.sha256()
        _fsync_directory(self.partial)

    def finish(self, *, stop_reason: str, failure: str | None = None) -> Path:
        if self._closed:
            raise RuntimeError("recording writer is closed")
        self._finish_chunk()
        manifest_type = ShortWindowManifestV1 if self.schema_version == 1 else ShortWindowManifestV2
        manifest = manifest_type(
            **({"sample_rate_hz": self.rate} if self.schema_version == 2 else {}),
            session_id=self.session_id,
            configuration=self.configuration,
            radio=self.radio,
            receiver_ids=self.receiver_ids,
            created_utc_ns=self.created_utc_ns,
            finalized_utc_ns=max(self.created_utc_ns, time.time_ns()),
            status="complete" if failure is None else "incomplete",
            stop_reason=stop_reason,
            failure=failure,
            window_count=self.window_count,
            chunks=tuple(self.chunks),
        )
        with (self.partial / "manifest.json.partial").open("xb") as stream:
            stream.write(canonical_json_bytes(manifest.model_dump(mode="json")))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(self.partial / "manifest.json.partial", self.partial / "manifest.json")
        _fsync_directory(self.partial)
        if self.destination.exists():
            raise FileExistsError(self.destination)
        os.rename(self.partial, self.destination)
        _fsync_directory(self.root)
        self._closed = True
        return self.destination

    def abort(self) -> None:
        """Keep partial evidence for diagnosis; never publish a failed write as complete."""
        if self._payload is not None:
            self._payload.abort()
        self._closed = True


class ShortWindowReader:
    def __init__(self, path: Path):
        self.path = path.resolve(strict=True)
        payload = ScannerIqStore._read_regular(self.path / "manifest.json", 16 * 1024**2)
        try:
            document = json.loads(payload)
            manifest_type = ShortWindowManifestV2 if document.get("schema_version") == 2 else ShortWindowManifestV1
            self.manifest = manifest_type.model_validate(document)
        except ValueError as error:
            raise BundleCorruptionError(f"invalid short-window manifest: {error}") from error
        if self.path.name != self.manifest.session_id:
            raise BundleCorruptionError("session identity differs from recording directory")
        self.manifest_sha256 = sha256_digest(payload)

    def _member(self, name: str, size: int, digest: str) -> bytes:
        path = confined_path(self.path, self.path / name, must_exist=True)
        payload = ScannerIqStore._read_regular(path, size)
        if len(payload) != size or sha256_digest(payload) != digest:
            raise BundleCorruptionError(f"short-window member changed: {name}")
        return payload

    def windows(self, *, start_sequence: int = 0, stop_sequence: int | None = None) -> Iterator[ShortWindowRead]:
        stop_sequence = self.manifest.window_count if stop_sequence is None else stop_sequence
        if (type(start_sequence) is not int or type(stop_sequence) is not int
                or not 0 <= start_sequence <= stop_sequence <= self.manifest.window_count):
            raise ValueError("window range must be inside the sealed inventory")
        if start_sequence == stop_sequence:
            return
        for chunk in self.manifest.chunks:
            if (chunk.first_sequence + chunk.window_count <= start_sequence
                    or chunk.first_sequence >= stop_sequence):
                continue
            index_bytes = self._member(
                chunk.index_relative_path, chunk.index_bytes, chunk.index_sha256
            )
            try:
                rows = [
                    (ShortWindowIndexV1 if self.manifest.schema_version == 1 else ShortWindowIndexV2).model_validate_json(line)
                    for line in index_bytes.splitlines()
                ]
            except (ValueError, json.JSONDecodeError) as error:
                raise BundleCorruptionError("invalid short-window index") from error
            if len(rows) != chunk.window_count:
                raise BundleCorruptionError("window index count differs from manifest")
            compressed = self._member(
                chunk.payload_relative_path, chunk.compressed_bytes, chunk.compressed_sha256
            )
            raw_hash = hashlib.sha256()
            offset = 0
            try:
                with zstd.ZstdDecompressor().stream_reader(compressed) as stream:
                    for number, row in enumerate(rows):
                        if (
                            row.sequence != chunk.first_sequence + number
                            or row.payload_offset_bytes != offset
                            or row.receiver_count != len(self.manifest.receiver_ids)
                            or row.sample_count > self.manifest.sample_rate_hz // 50
                        ):
                            raise BundleCorruptionError("window index geometry is not consecutive")
                        raw = stream.read(row.payload_bytes)
                        if len(raw) != row.payload_bytes or sha256_digest(raw) != row.iq_sha256:
                            raise BundleCorruptionError("window IQ length or digest changed")
                        raw_hash.update(raw)
                        offset += len(raw)
                        values = np.frombuffer(raw, dtype="<i2").reshape(
                            row.sample_count, row.receiver_count, 2
                        )
                        if start_sequence <= row.sequence < stop_sequence:
                            yield ShortWindowRead(row, values)
                    if stream.read(1):
                        raise BundleCorruptionError("unexpected trailing IQ bytes")
            except zstd.ZstdError as error:
                raise BundleCorruptionError("invalid short-window compressed IQ") from error
            if offset != chunk.uncompressed_bytes or (
                f"sha256:{raw_hash.hexdigest()}" != chunk.uncompressed_sha256
            ):
                raise BundleCorruptionError("short-window chunk geometry or digest changed")
