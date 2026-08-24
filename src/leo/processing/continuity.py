"""Gap-map construction and explicit masked device-time IQ reconstruction."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from leo.contracts.continuity import IqGapMapV1
from leo.domain.gap_map import IqContinuityEvidenceError
from leo.domain.gap_map import build_iq_gap_map as build_iq_gap_map
from leo.pipeline.contracts import IqReader


@dataclass(frozen=True, slots=True)
class MaskedDeviceIqBlock:
    """A bounded device-time block; false mask elements are logical zero fill."""

    samples: npt.NDArray[np.int16]
    valid_samples: npt.NDArray[np.bool_]
    device_sample_start: int
    continuity_segment_index: int
    stored_sample_start: int | None

    def __post_init__(self) -> None:
        values = np.asarray(self.samples)
        validity = np.asarray(self.valid_samples)
        if values.dtype != np.dtype("<i2") or values.ndim != 3 or values.shape[2] != 2:
            raise ValueError("masked IQ samples must have CI16 sample/receiver/IQ geometry")
        if validity.dtype != np.dtype(np.bool_) or validity.shape != (values.shape[0],):
            raise ValueError("validity mask must contain one boolean per sample time")
        if values.shape[0] == 0:
            raise ValueError("masked IQ block cannot be empty")
        if self.device_sample_start < 0 or self.continuity_segment_index < 0:
            raise ValueError("masked IQ coordinates must be non-negative")
        if self.stored_sample_start is not None and self.stored_sample_start < 0:
            raise ValueError("stored IQ coordinate must be non-negative")
        if self.stored_sample_start is None:
            if np.any(validity) or np.any(values):
                raise ValueError("logical gap blocks must contain only invalid zeros")
        elif not np.all(validity):
            raise ValueError("observed IQ blocks must be wholly valid")
        if not values.flags.c_contiguous or not validity.flags.c_contiguous:
            raise ValueError("masked IQ arrays must be C-contiguous")
        values.setflags(write=False)
        validity.setflags(write=False)
        object.__setattr__(self, "samples", values)
        object.__setattr__(self, "valid_samples", validity)

    @property
    def sample_count(self) -> int:
        return int(self.samples.shape[0])

    @property
    def is_zero_fill(self) -> bool:
        return self.stored_sample_start is None


def iter_masked_device_iq(
    reader: IqReader,
    gap_map: IqGapMapV1,
    *,
    block_samples: int,
) -> Iterator[MaskedDeviceIqBlock]:
    """Stitch observed IQ on the FPGA axis and yield explicit masked zero spans."""

    if block_samples <= 0:
        raise ValueError("block_samples must be positive")
    if reader.sample_count != gap_map.observed_sample_count:
        raise IqContinuityEvidenceError("reader sample count disagrees with the gap map")

    receiver_count = len(reader.receiver_ids)
    if receiver_count <= 0:
        raise IqContinuityEvidenceError("reader has no receiver channels")
    device_cursor = 0
    observed_cursor = 0
    segment_index = 0
    boundary_index = 0
    boundaries = gap_map.boundaries

    for block in reader.iter_blocks(block_samples=block_samples):
        metadata = block.metadata
        if metadata.session_sample_start != observed_cursor:
            raise IqContinuityEvidenceError("reader did not preserve stored sample coordinates")
        counter = metadata.device_sample_counter
        if counter is None:
            raise IqContinuityEvidenceError("reader block lacks its FPGA sample counter")
        device_start = counter - gap_map.first_device_sample_counter
        if device_start < device_cursor:
            raise IqContinuityEvidenceError("reader device coordinates overlapped or regressed")

        while boundary_index < len(boundaries) and (
            boundaries[boundary_index].stored_sample_offset == observed_cursor
        ):
            boundary = boundaries[boundary_index]
            if boundary.device_sample_offset != device_cursor:
                raise IqContinuityEvidenceError("gap-map boundary does not meet prior IQ")
            gap_end = boundary.device_sample_offset + boundary.missing_sample_count
            while device_cursor < gap_end:
                count = min(block_samples, gap_end - device_cursor)
                zeros = np.zeros((count, receiver_count, 2), dtype="<i2")
                invalid = np.zeros(count, dtype=np.bool_)
                yield MaskedDeviceIqBlock(
                    samples=zeros,
                    valid_samples=invalid,
                    device_sample_start=device_cursor,
                    continuity_segment_index=boundary.segment_index,
                    stored_sample_start=None,
                )
                device_cursor += count
            segment_index = boundary.segment_index
            boundary_index += 1

        if device_start != device_cursor:
            raise IqContinuityEvidenceError("reader device gap is absent from the gap map")
        validity = np.ones(metadata.sample_count, dtype=np.bool_)
        yield MaskedDeviceIqBlock(
            samples=block.samples,
            valid_samples=validity,
            device_sample_start=device_start,
            continuity_segment_index=segment_index,
            stored_sample_start=observed_cursor,
        )
        observed_cursor += metadata.sample_count
        device_cursor += metadata.sample_count

    while boundary_index < len(boundaries) and (
        boundaries[boundary_index].stored_sample_offset == observed_cursor
    ):
        boundary = boundaries[boundary_index]
        if boundary.device_sample_offset != device_cursor:
            raise IqContinuityEvidenceError("terminal gap-map boundary does not meet prior IQ")
        gap_end = boundary.device_sample_offset + boundary.missing_sample_count
        while device_cursor < gap_end:
            count = min(block_samples, gap_end - device_cursor)
            zeros = np.zeros((count, receiver_count, 2), dtype="<i2")
            invalid = np.zeros(count, dtype=np.bool_)
            yield MaskedDeviceIqBlock(
                samples=zeros,
                valid_samples=invalid,
                device_sample_start=device_cursor,
                continuity_segment_index=boundary.segment_index,
                stored_sample_start=None,
            )
            device_cursor += count
        boundary_index += 1

    if boundary_index != len(boundaries):
        raise IqContinuityEvidenceError("gap map contains boundaries beyond returned IQ")
    if observed_cursor != gap_map.observed_sample_count:
        raise IqContinuityEvidenceError("reader ended before its observed sample inventory")
    if device_cursor != gap_map.device_span_sample_count:
        raise IqContinuityEvidenceError("masked IQ does not cover the declared device span")
