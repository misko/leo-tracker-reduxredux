"""Private bounded raw-IQ staging; final public recording formats stay unchanged."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from pathlib import Path

import numpy as np

from leo.contracts.digests import canonical_json_bytes
from leo.contracts.radio import parse_iq_block_metadata_json
from leo.domain.iq import IqBlock
from leo.storage.errors import BundleStateError


class RawIqStage:
    """Sequential writes on the live path, replay/compression only after RF drain.

    Failure leaves both private files in the unpublished session for diagnosis.
    Removal is allowed only after complete replay and durable final shards.
    """

    def __init__(self, directory: Path, *, maximum_bytes: int) -> None:
        if maximum_bytes <= 0:
            raise ValueError("raw stage requires a positive byte bound")
        directory.mkdir(exist_ok=False)
        self._directory = directory
        self._iq_path = directory / "iq.ci16"
        self._timeline_path = directory / "timeline.jsonl"
        self._iq = self._iq_path.open("xb")
        self._timeline = self._timeline_path.open("xb")
        self._maximum_bytes = maximum_bytes
        self._digest = hashlib.sha256()
        self.byte_count = 0
        self.frame_count = 0
        self._sealed = False
        self._replayed = False

    def append(self, block: IqBlock) -> None:
        if self._sealed:
            raise BundleStateError("raw stage is sealed")
        payload = block.wire_bytes
        if self.byte_count + len(payload) > self._maximum_bytes:
            raise BundleStateError("raw stage exceeded its admitted byte bound")
        self._write_all(self._iq, payload)
        self._write_all(
            self._timeline,
            memoryview(canonical_json_bytes(block.metadata.model_dump(mode="json")) + b"\n"),
        )
        self._digest.update(payload)
        self.byte_count += len(payload)
        self.frame_count += 1

    @staticmethod
    def _write_all(stream, payload: memoryview) -> None:
        while payload:
            written = stream.write(payload)
            if written is None or written <= 0:
                raise OSError("raw-stage write made no progress")
            payload = payload[written:]

    def seal(self) -> None:
        if self._sealed:
            return
        for stream in (self._iq, self._timeline):
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
        self._sealed = True

    def blocks(self) -> Iterator[IqBlock]:
        if not self._sealed:
            raise BundleStateError("raw stage must be sealed before replay")
        digest = hashlib.sha256()
        frames = 0
        byte_count = 0
        with self._iq_path.open("rb") as iq, self._timeline_path.open("rb") as timeline:
            for line in timeline:
                if len(line) > 1_048_576:
                    raise BundleStateError("raw-stage metadata record is oversized")
                metadata = parse_iq_block_metadata_json(line)
                count = metadata.sample_count * len(metadata.receiver_ids) * 4
                if count > self._maximum_bytes - byte_count:
                    raise BundleStateError("raw-stage timeline exceeds its byte bound")
                payload = iq.read(count)
                if len(payload) != count:
                    raise BundleStateError("raw-stage IQ is truncated")
                digest.update(payload)
                byte_count += count
                frames += 1
                samples = np.frombuffer(payload, dtype="<i2").reshape(
                    metadata.sample_count, len(metadata.receiver_ids), 2
                )
                yield IqBlock(samples=samples, metadata=metadata)
            if iq.read(1):
                raise BundleStateError("raw-stage IQ has an unreferenced tail")
        if (
            digest.digest() != self._digest.digest()
            or byte_count != self.byte_count
            or frames != self.frame_count
        ):
            raise BundleStateError("raw-stage replay differs from accepted IQ")
        self._replayed = True

    def discard_after_finalize(self) -> None:
        if not self._replayed:
            raise BundleStateError("raw stage cannot be removed before complete verified replay")
        self._iq_path.unlink()
        self._timeline_path.unlink()
        self._directory.rmdir()

    def close(self) -> None:
        """Close descriptors but preserve incomplete data on every failure."""
        self._iq.close()
        self._timeline.close()
