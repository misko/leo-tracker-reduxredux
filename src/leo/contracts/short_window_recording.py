"""Additive persistence envelope for bounded, repeated short-window recordings."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest
from leo.contracts.recording import Identifier, _relative_bundle_path


class ShortWindowIndexV1(ContractModel):
    schema_version: Literal[1] = 1
    sequence: Annotated[int, Field(ge=0)]
    target_id: str
    sample_count: Annotated[int, Field(ge=0, le=50_000)]
    receiver_count: Annotated[int, Field(ge=1, le=2)]
    payload_offset_bytes: Annotated[int, Field(ge=0)]
    payload_bytes: Annotated[int, Field(ge=0, le=400_000)]
    iq_sha256: Sha256Digest
    acquisition: dict[str, JsonValue]
    powers: tuple[dict[str, JsonValue], ...]

    @model_validator(mode="after")
    def _geometry(self) -> Self:
        if self.payload_bytes != self.sample_count * self.receiver_count * 4:
            raise ValueError("window byte count disagrees with CI16 geometry")
        if len(self.powers) != self.receiver_count:
            raise ValueError("one power result is required per receiver")
        return self


class ShortWindowChunkV1(ContractModel):
    chunk_index: Annotated[int, Field(ge=0)]
    first_sequence: Annotated[int, Field(ge=0)]
    window_count: Annotated[int, Field(gt=0, le=256)]
    payload_relative_path: str
    index_relative_path: str
    uncompressed_bytes: Annotated[int, Field(ge=0, le=102_400_000)]
    compressed_bytes: Annotated[int, Field(gt=0, le=104_857_600)]
    index_bytes: Annotated[int, Field(gt=0, le=16_777_216)]
    uncompressed_sha256: Sha256Digest
    compressed_sha256: Sha256Digest
    index_sha256: Sha256Digest

    @field_validator("payload_relative_path", "index_relative_path")
    @classmethod
    def _relative(cls, value: str) -> str:
        return _relative_bundle_path(value)


class ShortWindowManifestV1(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["short_window_iq_recording"] = "short_window_iq_recording"
    session_id: Identifier
    configuration: dict[str, JsonValue]
    radio: dict[str, JsonValue]
    sample_rate_hz: Literal[2_500_000] = 2_500_000
    window_ms: Literal[20] = 20
    sample_format: Literal["ci16_le"] = "ci16_le"
    sample_layout: Literal["sample_receiver_iq"] = "sample_receiver_iq"
    receiver_ids: tuple[int, ...]
    created_utc_ns: Annotated[int, Field(ge=0)]
    finalized_utc_ns: Annotated[int, Field(ge=0)]
    status: Literal["complete", "incomplete"]
    stop_reason: str
    failure: str | None = None
    window_count: Annotated[int, Field(ge=0)]
    chunks: tuple[ShortWindowChunkV1, ...]

    @model_validator(mode="after")
    def _coverage(self) -> Self:
        if len(self.receiver_ids) not in (1, 2) or len(set(self.receiver_ids)) != len(
            self.receiver_ids
        ):
            raise ValueError("recording requires one or two distinct receivers")
        if any(receiver < 0 for receiver in self.receiver_ids):
            raise ValueError("receiver identifiers must be nonnegative")
        if self.finalized_utc_ns < self.created_utc_ns:
            raise ValueError("finalization precedes creation")
        if self.status == "complete" and self.failure is not None:
            raise ValueError("complete recording cannot contain a failure")
        sequence = 0
        paths: set[str] = set()
        for index, chunk in enumerate(self.chunks):
            if chunk.chunk_index != index or chunk.first_sequence != sequence:
                raise ValueError("recording chunks must cover consecutive windows")
            sequence += chunk.window_count
            for path in (chunk.payload_relative_path, chunk.index_relative_path):
                if path in paths:
                    raise ValueError("recording chunk paths must be unique")
                paths.add(path)
        if sequence != self.window_count:
            raise ValueError("manifest window count disagrees with chunks")
        return self
