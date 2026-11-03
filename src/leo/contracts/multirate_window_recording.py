"""Version two native-rate windows; published version-one geometry is unchanged."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from leo.contracts.short_window_recording import (
    ShortWindowChunkV1,
    ShortWindowIndexV1,
    ShortWindowManifestV1,
)


class ShortWindowIndexV2(ShortWindowIndexV1):
    schema_version: Literal[2] = 2
    sample_count: Annotated[int, Field(ge=0, le=200_000)]
    payload_bytes: Annotated[int, Field(ge=0, le=1_600_000)]


class ShortWindowChunkV2(ShortWindowChunkV1):
    uncompressed_bytes: Annotated[int, Field(ge=0, le=409_600_000)]
    compressed_bytes: Annotated[int, Field(gt=0, le=419_430_400)]


class ShortWindowManifestV2(ShortWindowManifestV1):
    schema_version: Literal[2] = 2
    sample_rate_hz: Literal[1_250_000, 2_500_000, 5_000_000, 7_500_000, 10_000_000]
    chunks: tuple[ShortWindowChunkV2, ...]

    @model_validator(mode="after")
    def _native_geometry(self) -> Self:
        if self.configuration.get("sample_rate_hz") != self.sample_rate_hz:
            raise ValueError("native window manifest and configuration rates differ")
        if self.configuration.get("window_ms") != self.window_ms:
            raise ValueError("native window duration differs from configuration")
        return self
