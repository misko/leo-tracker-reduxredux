"""Opt-in LIBIIO metadata envelope; not an extension of legacy HOPS/ABI layouts.

The legacy metadata blob is opaque and byte-preserved. Completed results can
refer to earlier dwells. Drain frames contain metadata only, after RF stops.
This codec does not negotiate the transport or turn candidate scores into a
qualified classifier. The native/host integrations must do those separately.
"""

from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass
from typing import Annotated, Literal, Self

from pydantic import BeforeValidator, ConfigDict, Field, PlainSerializer, model_validator

from leo.contracts.base import ContractModel

MAGIC = b"LGC1"
HEADER_BYTES = 128
RECORD_BYTES = 144
MAX_RECORDS = 4
MAX_METADATA_BYTES = 65536
DRAIN = 1
FINAL = 2
DETECTOR_FAILED = 4
_HEADER = struct.Struct("<4sHHIIHHI5Q32s32s")
_RECORD = struct.Struct("<8QI4BII4dQ3d")
VERDICTS: tuple[Literal["unavailable", "starlink", "no_signal"], ...] = (
    "unavailable",
    "starlink",
    "no_signal",
)
REASONS: tuple[
    Literal[
        "complete",
        "worker_busy",
        "worker_failed",
        "invalid_input",
        "incomplete_search",
        "unqualified_classifier",
        "cancelled",
    ],
    ...,
] = (
    "complete",
    "worker_busy",
    "worker_failed",
    "invalid_input",
    "incomplete_search",
    "unqualified_classifier",
    "cancelled",
)


def _counter(value):
    if isinstance(value, str):
        if not re.fullmatch(r"0|[1-9][0-9]{0,19}", value):
            raise ValueError("counter must be a canonical unsigned decimal string")
        return int(value)
    return value


U64 = Annotated[
    int,
    BeforeValidator(_counter),
    Field(strict=True, ge=0, le=2**64 - 1),
    PlainSerializer(str, return_type=str, when_used="json"),
]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Finite = Annotated[float, Field(strict=True, allow_inf_nan=False)]


class ScannerGlrtClassificationV1(ContractModel):
    """One completed classification; absence requires all six temporal slices.

    search_window_mask describes six equal subdivisions of the valid dwell;
    it is temporal search coverage, not a count of statistically independent
    measurements. A positive detection may finish early. A negative may not.
    The digest-pinned classifier defines thresholds and statistical meaning.
    """

    sequence: U64
    visit: U64
    valid_start: U64
    valid_end: U64
    search_start: U64
    search_end: U64
    confirmation_start: U64
    confirmation_end: U64
    rate_hz: Annotated[int, Field(strict=True, gt=0, le=2**32 - 1)]
    channel: Annotated[int, Field(strict=True, ge=1, le=4)]
    edge: Literal["lower", "upper"]
    rx: Annotated[int, Field(strict=True, ge=0, le=1)]
    verdict: Literal["unavailable", "starlink", "no_signal"]
    reason: Literal[
        "complete",
        "worker_busy",
        "worker_failed",
        "invalid_input",
        "incomplete_search",
        "unqualified_classifier",
        "cancelled",
    ]
    search_window_mask: Annotated[int, Field(strict=True, ge=0, le=63)]
    exact_score: Annotated[Finite, Field(ge=0)] = 0
    control_score: Annotated[Finite, Field(ge=0)] = 0
    margin: Finite = 0
    cfo_hz: Finite = 0
    epoch_sample_counter: U64 = 0
    fractional_offset_samples: Annotated[Finite, Field(ge=-2, le=2)] = 0
    cpu_ms: Annotated[Finite, Field(ge=0)] = 0
    wall_ms: Annotated[Finite, Field(ge=0)] = 0

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (
            self.valid_end <= self.valid_start
            or self.valid_end - self.valid_start != self.rate_hz * 120 // 1000
            or not self.valid_start <= self.search_start <= self.search_end <= self.valid_end
            or not self.search_start
            <= self.confirmation_start
            <= self.confirmation_end
            <= self.search_end
        ):
            raise ValueError("classification intervals do not describe a valid 120 ms dwell")
        span = self.valid_end - self.valid_start
        for bit in range(6):
            if self.search_window_mask & (1 << bit) and (
                self.search_start > self.valid_start + span * bit // 6
                or self.search_end < self.valid_start + span * (bit + 1) // 6
            ):
                raise ValueError("search mask lies outside the searched interval")
        if (self.verdict == "unavailable") != (self.reason != "complete"):
            raise ValueError(
                "unavailable evidence requires a reason; classification requires completion"
            )
        if self.verdict == "no_signal" and self.search_window_mask != 63:
            raise ValueError("partial temporal coverage cannot assert dwell absence")
        if self.verdict == "starlink" and (
            not self.search_window_mask
            or self.confirmation_end == self.confirmation_start
            or self.margin <= 0
        ):
            raise ValueError("positive classification requires searched and confirmed evidence")
        if not math.isclose(
            self.margin, self.exact_score - self.control_score, rel_tol=1e-12, abs_tol=1e-12
        ):
            raise ValueError("GLRT margin differs from exact minus control score")
        if self.confirmation_end > self.confirmation_start:
            if not self.confirmation_start <= self.epoch_sample_counter < self.confirmation_end:
                raise ValueError("fractional epoch anchor lies outside its confirmation interval")
        elif any(
            (
                self.exact_score,
                self.control_score,
                self.margin,
                self.cfo_hz,
                self.epoch_sample_counter,
                self.fractional_offset_samples,
            )
        ):
            raise ValueError("unconfirmed records must not carry fabricated candidate measurements")
        return self


class ScannerGlrtFrameV1(ContractModel):
    model_config = ConfigDict(ser_json_bytes="hex", val_json_bytes="hex")

    session: U64
    generation: U64
    frame_sequence: U64
    result_sequence_limit: U64
    dropped_results: U64
    algorithm_sha256: Digest
    configuration_sha256: Digest
    flags: Annotated[int, Field(strict=True, ge=0, le=7)] = 0
    legacy_metadata: bytes = b""
    results: tuple[ScannerGlrtClassificationV1, ...] = ()

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if not self.session or not self.generation:
            raise ValueError("session and generation must be nonzero")
        if self.algorithm_sha256 == "0" * 64 or self.configuration_sha256 == "0" * 64:
            raise ValueError("algorithm and configuration identities must be explicit")
        if bool(self.flags & DRAIN) != (not self.legacy_metadata) or (
            self.flags & FINAL and not self.flags & DRAIN
        ):
            raise ValueError("only negotiated drain frames may omit legacy metadata")
        size = HEADER_BYTES + len(self.legacy_metadata) + RECORD_BYTES * len(self.results)
        if len(self.results) > MAX_RECORDS or size > MAX_METADATA_BYTES:
            raise ValueError("classification frame exceeds its fixed bound")
        if self.dropped_results > self.result_sequence_limit:
            raise ValueError("dropped result count exceeds generated results")
        previous = -1
        for result in self.results:
            if not previous < result.sequence < self.result_sequence_limit:
                raise ValueError("result sequences must be ordered and below the generated limit")
            previous = result.sequence
        return self


def encode_frame(frame: ScannerGlrtFrameV1) -> bytes:
    frame = ScannerGlrtFrameV1.model_validate(frame.model_dump())
    payload = bytearray(
        _HEADER.pack(
            MAGIC,
            1,
            HEADER_BYTES,
            HEADER_BYTES + len(frame.legacy_metadata) + RECORD_BYTES * len(frame.results),
            len(frame.legacy_metadata),
            len(frame.results),
            RECORD_BYTES,
            frame.flags,
            frame.session,
            frame.generation,
            frame.frame_sequence,
            frame.result_sequence_limit,
            frame.dropped_results,
            bytes.fromhex(frame.algorithm_sha256),
            bytes.fromhex(frame.configuration_sha256),
        )
    )
    payload.extend(frame.legacy_metadata)
    for r in frame.results:
        payload.extend(
            _RECORD.pack(
                r.sequence,
                r.visit,
                r.valid_start,
                r.valid_end,
                r.search_start,
                r.search_end,
                r.confirmation_start,
                r.confirmation_end,
                r.rate_hz,
                r.channel,
                int(r.edge == "upper"),
                r.rx,
                VERDICTS.index(r.verdict),
                REASONS.index(r.reason),
                r.search_window_mask,
                r.exact_score,
                r.control_score,
                r.margin,
                r.cfo_hz,
                r.epoch_sample_counter,
                r.fractional_offset_samples,
                r.cpu_ms,
                r.wall_ms,
            )
        )
    return bytes(payload)


def _validated_header(payload: bytes):
    if not HEADER_BYTES <= len(payload) <= MAX_METADATA_BYTES:
        raise ValueError("classification metadata length is out of bounds")
    (
        magic,
        version,
        header,
        total,
        legacy,
        count,
        record_size,
        flags,
        session,
        generation,
        sequence,
        limit,
        dropped,
        algorithm,
        configuration,
    ) = _HEADER.unpack_from(payload)
    if (
        magic != MAGIC
        or version != 1
        or header != HEADER_BYTES
        or total != len(payload)
        or record_size != RECORD_BYTES
        or count > MAX_RECORDS
        or HEADER_BYTES + legacy + count * RECORD_BYTES != total
    ):
        raise ValueError("invalid or unsupported classification envelope")
    return (
        legacy,
        count,
        flags,
        session,
        generation,
        sequence,
        limit,
        dropped,
        algorithm,
        configuration,
    )


@dataclass(frozen=True, slots=True)
class ScannerGlrtEnvelopeViewV1:
    """Structurally bounded view, before classification semantic validation."""

    flags: int
    legacy_metadata: bytes
    result_count: int


def inspect_envelope(payload: bytes) -> ScannerGlrtEnvelopeViewV1:
    legacy, count, flags, *_ = _validated_header(payload)
    return ScannerGlrtEnvelopeViewV1(
        flags=flags,
        legacy_metadata=payload[HEADER_BYTES : HEADER_BYTES + legacy],
        result_count=count,
    )


def extract_legacy_metadata(payload: bytes) -> bytes:
    """Preserve recording metadata even if a classification record is invalid.

    Only the negotiated envelope's structural bounds are used here. The owner
    must still validate the returned legacy metadata using its existing codec.
    Unknown envelope versions are not guessed or passed off as old metadata.
    """
    return inspect_envelope(payload).legacy_metadata


def decode_frame(payload: bytes) -> ScannerGlrtFrameV1:
    (
        legacy,
        count,
        flags,
        session,
        generation,
        sequence,
        limit,
        dropped,
        algorithm,
        configuration,
    ) = _validated_header(payload)
    results = []
    for index in range(count):
        values = _RECORD.unpack_from(payload, HEADER_BYTES + legacy + index * RECORD_BYTES)
        if values[10] > 1 or values[12] >= len(VERDICTS) or values[13] >= len(REASONS):
            raise ValueError("unknown classification enum")
        results.append(
            ScannerGlrtClassificationV1(
                **dict(
                    zip(
                        (
                            "sequence",
                            "visit",
                            "valid_start",
                            "valid_end",
                            "search_start",
                            "search_end",
                            "confirmation_start",
                            "confirmation_end",
                        ),
                        values[:8],
                        strict=True,
                    )
                ),
                rate_hz=values[8],
                channel=values[9],
                edge=("lower", "upper")[values[10]],
                rx=values[11],
                verdict=VERDICTS[values[12]],
                reason=REASONS[values[13]],
                search_window_mask=values[14],
                exact_score=values[15],
                control_score=values[16],
                margin=values[17],
                cfo_hz=values[18],
                epoch_sample_counter=values[19],
                fractional_offset_samples=values[20],
                cpu_ms=values[21],
                wall_ms=values[22],
            )
        )
    return ScannerGlrtFrameV1(
        session=session,
        generation=generation,
        frame_sequence=sequence,
        result_sequence_limit=limit,
        dropped_results=dropped,
        algorithm_sha256=algorithm.hex(),
        configuration_sha256=configuration.hex(),
        flags=flags,
        legacy_metadata=payload[HEADER_BYTES : HEADER_BYTES + legacy],
        results=tuple(results),
    )
