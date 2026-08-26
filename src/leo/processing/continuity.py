"""Gap-map construction and explicit masked device-time IQ reconstruction."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Protocol, cast

import numpy as np
import numpy.typing as npt

from leo.contracts.continuity import IqGapMapV1
from leo.contracts.radio import IqBlockMetadataV1
from leo.contracts.rate_analysis import VerifiedIqGapMapEvidenceV1
from leo.contracts.states import ContinuityStatus
from leo.contracts.validity import (
    ContinuitySegmentV1,
    DeviceAxisContentKind,
    ValidityInventoryV1,
)
from leo.domain.gap_map import IqContinuityEvidenceError
from leo.domain.gap_map import build_iq_gap_map as build_iq_gap_map
from leo.domain.iq import IqBlock
from leo.domain.validity import build_validity_inventory_v1
from leo.pipeline.contracts import GapAwareIqReader, IqReader
from leo.pipeline.validity import (
    ContinuitySegmentIqReader,
    DeviceIqSpan,
    WindowClassification,
    WindowValidity,
)

_MAX_BOUNDED_DEVICE_READ_SAMPLES = 1_048_576


class _StoredRangeIqReader(Protocol):
    """Optional packed-observed range primitive implemented by retained storage."""

    def iter_stored_blocks(
        self,
        *,
        stored_sample_start: int,
        sample_count: int,
        block_samples: int,
    ) -> Iterable[IqBlock]: ...


@dataclass(frozen=True, slots=True)
class PhysicalDeviceIqBlock:
    """Internal physical V3 block whose observation meaning cannot be omitted."""

    samples: npt.NDArray[np.int16]
    device_sample_start: int
    receiver_ids: tuple[int, ...]
    content_kind: DeviceAxisContentKind
    continuity_segment_index: int | None

    def __post_init__(self) -> None:
        values = np.asarray(self.samples)
        if values.dtype != np.dtype("<i2") or values.ndim != 3 or values.shape[2] != 2:
            raise ValueError("physical device IQ must have native CI16 geometry")
        if (
            values.shape[0] == 0
            or values.shape[1] != len(self.receiver_ids)
            or not self.receiver_ids
            or tuple(sorted(set(self.receiver_ids))) != self.receiver_ids
            or self.device_sample_start < 0
            or not values.flags.c_contiguous
        ):
            raise ValueError("physical device IQ coordinates and geometry are not canonical")
        observed = self.content_kind is DeviceAxisContentKind.OBSERVED
        if observed != (self.continuity_segment_index is not None):
            raise ValueError("physical observed IQ requires a segment; zero fill forbids one")
        if not observed and np.any(values):
            raise ValueError("physical zero-fill IQ contains nonzero bytes")
        values.setflags(write=False)
        object.__setattr__(self, "samples", values)

    @property
    def sample_count(self) -> int:
        return int(self.samples.shape[0])

    @property
    def device_sample_stop(self) -> int:
        return self.device_sample_start + self.sample_count


class VerifiedPhysicalDeviceAxisIqSource(Protocol):
    """Narrow retained-byte source used only behind the mandatory-validity adapter."""

    @property
    def sample_rate_hz(self) -> int: ...

    @property
    def center_frequency_hz(self) -> int: ...

    @property
    def receiver_ids(self) -> tuple[int, ...]: ...

    @property
    def validity_inventory(self) -> ValidityInventoryV1: ...

    @property
    def verified_gap_map_evidence(self) -> VerifiedIqGapMapEvidenceV1: ...

    def iter_physical_device_blocks(
        self,
        *,
        device_sample_start: int,
        sample_count: int,
        block_samples: int,
    ) -> Iterable[PhysicalDeviceIqBlock]: ...

    def iter_observed_segment_blocks(
        self,
        segment: ContinuitySegmentV1,
        *,
        block_samples: int,
    ) -> Iterable[IqBlock]: ...

    def close(self) -> None: ...


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


class V2ValidityAwareIqReader:
    """Expose packed V2 observed IQ through one verified logical device-axis view.

    This adapter is deliberately distinct from an ordinary ``IqReader``: its
    logical span includes synthetic zeros, and those bytes are available only
    together with mandatory validity and segment arrays.  A future physical
    zero-fill V3 adapter implements the same storage-neutral pipeline port.
    """

    def __init__(self, source: GapAwareIqReader) -> None:
        self._source = source
        evidence = cast(VerifiedIqGapMapEvidenceV1, source.gap_map_evidence())
        gap_map = evidence.gap_map
        if source.sample_count != gap_map.observed_sample_count:
            raise IqContinuityEvidenceError(
                "V2 source sample count disagrees with its verified gap map"
            )
        if source.sample_rate_hz <= 0 or not source.receiver_ids:
            raise IqContinuityEvidenceError("V2 validity source has invalid IQ geometry")
        self._gap_map = gap_map
        self._gap_map_evidence = evidence
        self._inventory = build_validity_inventory_v1(gap_map)
        self._closed = False

    @property
    def sample_rate_hz(self) -> int:
        self._assert_open()
        return self._source.sample_rate_hz

    @property
    def center_frequency_hz(self) -> int:
        self._assert_open()
        return self._source.center_frequency_hz

    @property
    def sample_count(self) -> int:
        self._assert_open()
        return self._inventory.logical_sample_count

    @property
    def observed_sample_count(self) -> int:
        self._assert_open()
        return self._inventory.observed_sample_count

    @property
    def missing_sample_count(self) -> int:
        self._assert_open()
        return self._inventory.missing_sample_count

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        self._assert_open()
        return self._source.receiver_ids

    @property
    def validity_inventory(self) -> ValidityInventoryV1:
        self._assert_open()
        return self._inventory

    @property
    def verified_gap_map_evidence(self) -> VerifiedIqGapMapEvidenceV1:
        """Return the already verified evidence bound to this immutable view."""

        self._assert_open()
        return self._gap_map_evidence

    def iter_masked_blocks(self, *, block_samples: int) -> Iterable[DeviceIqSpan]:
        self._assert_open()
        if not 0 < block_samples <= _MAX_BOUNDED_DEVICE_READ_SAMPLES:
            raise ValueError(f"block_samples must be in [1, {_MAX_BOUNDED_DEVICE_READ_SAMPLES}]")
        for block in iter_masked_device_iq(
            self._source,
            self._gap_map,
            block_samples=block_samples,
        ):
            segment_ids = np.full(block.sample_count, -1, dtype=np.int32)
            if not block.is_zero_fill:
                segment_ids.fill(block.continuity_segment_index)
            yield DeviceIqSpan(
                samples=block.samples,
                valid_samples=block.valid_samples,
                continuity_segment_ids=segment_ids,
                device_sample_start=block.device_sample_start,
                receiver_ids=self.receiver_ids,
            )

    def iter_valid_blocks(self, *, block_samples: int) -> Iterable[DeviceIqSpan]:
        """Yield observed IQ on global coordinates without allocating gap buffers."""

        self._assert_open()
        if not 0 < block_samples <= _MAX_BOUNDED_DEVICE_READ_SAMPLES:
            raise ValueError(f"block_samples must be in [1, {_MAX_BOUNDED_DEVICE_READ_SAMPLES}]")
        observed_runs = tuple(
            run
            for run in self._inventory.runs
            if run.content_kind is DeviceAxisContentKind.OBSERVED
        )
        run_index = 0
        stored_cursor = 0
        for block in self._source.iter_blocks(block_samples=block_samples):
            metadata = block.metadata
            stored_start = metadata.session_sample_start
            stored_stop = stored_start + metadata.sample_count
            if stored_start != stored_cursor:
                raise IqContinuityEvidenceError(
                    "V2 source did not preserve packed observed coordinates"
                )
            if run_index >= len(observed_runs):
                raise IqContinuityEvidenceError("V2 source exceeds the validity inventory")
            run = observed_runs[run_index]
            assert run.stored_sample_start is not None
            assert run.continuity_segment_index is not None
            run_stored_stop = run.stored_sample_start + run.sample_count
            if stored_start < run.stored_sample_start or stored_stop > run_stored_stop:
                raise IqContinuityEvidenceError(
                    "V2 source block crosses a canonical continuity segment"
                )
            device_start = run.device_sample_start + stored_start - run.stored_sample_start
            counter = metadata.device_sample_counter
            expected_counter = self._inventory.first_device_sample_counter + device_start
            if counter is None or counter != expected_counter:
                raise IqContinuityEvidenceError(
                    "V2 source counter disagrees with canonical device coordinates"
                )
            validity = np.ones(metadata.sample_count, dtype=np.bool_)
            segment_ids = np.full(
                metadata.sample_count,
                run.continuity_segment_index,
                dtype=np.int32,
            )
            yield DeviceIqSpan(
                samples=block.samples,
                valid_samples=validity,
                continuity_segment_ids=segment_ids,
                device_sample_start=device_start,
                receiver_ids=self.receiver_ids,
            )
            stored_cursor = stored_stop
            if stored_stop == run_stored_stop:
                run_index += 1

        if stored_cursor != self._inventory.observed_sample_count or run_index != len(
            observed_runs
        ):
            raise IqContinuityEvidenceError("V2 source ended before the validity inventory")

    def read_device_span(self, device_sample_start: int, sample_count: int) -> DeviceIqSpan:
        self._assert_open()
        if device_sample_start < 0 or sample_count <= 0:
            raise ValueError("device read requires a non-negative start and positive count")
        if sample_count > _MAX_BOUNDED_DEVICE_READ_SAMPLES:
            raise ValueError(
                f"device read cannot exceed {_MAX_BOUNDED_DEVICE_READ_SAMPLES} samples"
            )
        device_sample_stop = device_sample_start + sample_count
        if device_sample_stop > self.sample_count:
            raise ValueError("device read exceeds the logical device-time span")

        samples = np.zeros((sample_count, len(self.receiver_ids), 2), dtype="<i2")
        validity = np.zeros(sample_count, dtype=np.bool_)
        segment_ids = np.full(sample_count, -1, dtype=np.int32)
        for run in self._inventory.runs:
            if run.content_kind is not DeviceAxisContentKind.OBSERVED:
                continue
            overlap_start = max(device_sample_start, run.device_sample_start)
            overlap_stop = min(device_sample_stop, run.device_sample_stop)
            if overlap_start >= overlap_stop:
                continue
            assert run.stored_sample_start is not None
            assert run.continuity_segment_index is not None
            stored_start = run.stored_sample_start + overlap_start - run.device_sample_start
            overlap_count = overlap_stop - overlap_start
            output_start = overlap_start - device_sample_start
            copied = 0
            for block in _iter_stored_range(
                self._source,
                stored_sample_start=stored_start,
                sample_count=overlap_count,
                block_samples=_MAX_BOUNDED_DEVICE_READ_SAMPLES,
            ):
                if block.metadata.session_sample_start != stored_start + copied:
                    raise IqContinuityEvidenceError(
                        "bounded stored IQ read did not preserve packed coordinates"
                    )
                expected_counter = (
                    self._inventory.first_device_sample_counter + overlap_start + copied
                )
                if block.metadata.device_sample_counter != expected_counter:
                    raise IqContinuityEvidenceError(
                        "bounded stored IQ read disagrees with device coordinates"
                    )
                count = block.metadata.sample_count
                if copied + count > overlap_count:
                    raise IqContinuityEvidenceError("bounded stored IQ read exceeded its range")
                selected = slice(output_start + copied, output_start + copied + count)
                samples[selected] = block.samples
                validity[selected] = True
                segment_ids[selected] = run.continuity_segment_index
                copied += count
            if copied != overlap_count:
                raise IqContinuityEvidenceError("bounded stored IQ read ended early")

        expected_valid = sum(
            _overlap_count(
                device_sample_start,
                device_sample_stop,
                run.device_sample_start,
                run.device_sample_stop,
            )
            for run in self._inventory.runs
            if run.content_kind is DeviceAxisContentKind.OBSERVED
        )
        if int(np.count_nonzero(validity)) != expected_valid:
            raise IqContinuityEvidenceError("bounded V2 device read lost observed IQ")
        return DeviceIqSpan(
            samples=samples,
            valid_samples=validity,
            continuity_segment_ids=segment_ids,
            device_sample_start=device_sample_start,
            receiver_ids=self.receiver_ids,
        )

    def classify_window(self, device_sample_start: int, sample_count: int) -> WindowClassification:
        self._assert_open()
        return _classify_inventory_window(
            self._inventory,
            device_sample_start=device_sample_start,
            sample_count=sample_count,
        )

    def segment_readers(self) -> tuple[ContinuitySegmentIqReader, ...]:
        self._assert_open()
        return tuple(
            _V2ContinuitySegmentIqReader(self._source, segment)
            for segment in self._inventory.segments
            if segment.observed_sample_count
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        close = getattr(self._source, "close", None)
        if callable(close):
            close()

    def _assert_open(self) -> None:
        if self._closed:
            raise RuntimeError("V2 validity-aware IQ reader is closed")


class V3ValidityAwareIqReader:
    """Expose verified physical V3 device-axis IQ only with mandatory validity."""

    def __init__(self, source: VerifiedPhysicalDeviceAxisIqSource) -> None:
        inventory = source.validity_inventory
        if (
            source.sample_rate_hz <= 0
            or not source.receiver_ids
            or inventory.logical_sample_count
            != inventory.observed_sample_count + inventory.missing_sample_count
        ):
            raise IqContinuityEvidenceError("V3 validity source has invalid IQ authority")
        self._source = source
        self._inventory = inventory
        self._closed = False

    @property
    def sample_rate_hz(self) -> int:
        self._assert_open()
        return self._source.sample_rate_hz

    @property
    def center_frequency_hz(self) -> int:
        self._assert_open()
        return self._source.center_frequency_hz

    @property
    def sample_count(self) -> int:
        self._assert_open()
        return self._inventory.logical_sample_count

    @property
    def observed_sample_count(self) -> int:
        self._assert_open()
        return self._inventory.observed_sample_count

    @property
    def missing_sample_count(self) -> int:
        self._assert_open()
        return self._inventory.missing_sample_count

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        self._assert_open()
        return self._source.receiver_ids

    @property
    def validity_inventory(self) -> ValidityInventoryV1:
        self._assert_open()
        return self._inventory

    @property
    def verified_gap_map_evidence(self) -> VerifiedIqGapMapEvidenceV1:
        self._assert_open()
        return self._source.verified_gap_map_evidence

    def read_device_span(self, device_sample_start: int, sample_count: int) -> DeviceIqSpan:
        self._assert_open()
        if device_sample_start < 0 or sample_count <= 0:
            raise ValueError("device read requires a non-negative start and positive count")
        if sample_count > _MAX_BOUNDED_DEVICE_READ_SAMPLES:
            raise ValueError(
                f"device read cannot exceed {_MAX_BOUNDED_DEVICE_READ_SAMPLES} samples"
            )
        device_sample_stop = device_sample_start + sample_count
        if device_sample_stop > self.sample_count:
            raise ValueError("device read exceeds the logical device-time span")

        samples = np.empty((sample_count, len(self.receiver_ids), 2), dtype="<i2")
        validity = np.empty(sample_count, dtype=np.bool_)
        segment_ids = np.empty(sample_count, dtype=np.int32)
        cursor = device_sample_start
        for physical in self._source.iter_physical_device_blocks(
            device_sample_start=device_sample_start,
            sample_count=sample_count,
            block_samples=_MAX_BOUNDED_DEVICE_READ_SAMPLES,
        ):
            if physical.device_sample_start != cursor:
                raise IqContinuityEvidenceError("physical V3 bounded read is not contiguous")
            span = self._masked_physical_span(physical)
            output_start = cursor - device_sample_start
            output_stop = output_start + span.sample_count
            samples[output_start:output_stop] = span.samples
            validity[output_start:output_stop] = span.valid_samples
            segment_ids[output_start:output_stop] = span.continuity_segment_ids
            cursor = physical.device_sample_stop
        if cursor != device_sample_stop:
            raise IqContinuityEvidenceError("physical V3 bounded read ended early")
        return DeviceIqSpan(
            samples=samples,
            valid_samples=validity,
            continuity_segment_ids=segment_ids,
            device_sample_start=device_sample_start,
            receiver_ids=self.receiver_ids,
        )

    def iter_masked_blocks(self, *, block_samples: int) -> Iterable[DeviceIqSpan]:
        self._assert_open()
        _validate_block_samples(block_samples)
        cursor = 0
        for physical in self._source.iter_physical_device_blocks(
            device_sample_start=0,
            sample_count=self.sample_count,
            block_samples=block_samples,
        ):
            if physical.device_sample_start != cursor:
                raise IqContinuityEvidenceError("physical V3 iteration is not contiguous")
            yield self._masked_physical_span(physical)
            cursor = physical.device_sample_stop
        if cursor != self.sample_count:
            raise IqContinuityEvidenceError("physical V3 iteration ended early")

    def iter_valid_blocks(self, *, block_samples: int) -> Iterable[DeviceIqSpan]:
        self._assert_open()
        _validate_block_samples(block_samples)
        observed = 0
        for segment_reader in self.segment_readers():
            for block in segment_reader.iter_blocks(block_samples=block_samples):
                local_start = block.metadata.session_sample_start
                device_start = segment_reader.to_global_device_sample(local_start)
                expected_counter = self._inventory.first_device_sample_counter + device_start
                if block.metadata.device_sample_counter != expected_counter:
                    raise IqContinuityEvidenceError(
                        "physical V3 observed IQ disagrees with device coordinates"
                    )
                count = block.metadata.sample_count
                validity = np.ones(count, dtype=np.bool_)
                segment_ids = np.full(
                    count,
                    segment_reader.continuity_segment_index,
                    dtype=np.int32,
                )
                yield DeviceIqSpan(
                    samples=block.samples,
                    valid_samples=validity,
                    continuity_segment_ids=segment_ids,
                    device_sample_start=device_start,
                    receiver_ids=self.receiver_ids,
                )
                observed += count
        if observed != self.observed_sample_count:
            raise IqContinuityEvidenceError("physical V3 observed iteration ended early")

    def segment_readers(self) -> tuple[ContinuitySegmentIqReader, ...]:
        self._assert_open()
        return tuple(
            _V3ContinuitySegmentIqReader(self._source, segment)
            for segment in self._inventory.segments
            if segment.observed_sample_count
        )

    def classify_window(self, device_sample_start: int, sample_count: int) -> WindowClassification:
        self._assert_open()
        return _classify_inventory_window(
            self._inventory,
            device_sample_start=device_sample_start,
            sample_count=sample_count,
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._source.close()

    def _masked_physical_span(self, physical: PhysicalDeviceIqBlock) -> DeviceIqSpan:
        if physical.receiver_ids != self.receiver_ids:
            raise IqContinuityEvidenceError("physical V3 receiver inventory changed")
        run = next(
            (
                item
                for item in self._inventory.runs
                if item.device_sample_start <= physical.device_sample_start
                and physical.device_sample_stop <= item.device_sample_stop
            ),
            None,
        )
        if (
            run is None
            or physical.content_kind is not run.content_kind
            or physical.continuity_segment_index != run.continuity_segment_index
        ):
            raise IqContinuityEvidenceError("physical V3 block disagrees with canonical validity")
        observed = physical.content_kind is DeviceAxisContentKind.OBSERVED
        validity = np.full(physical.sample_count, observed, dtype=np.bool_)
        segment_ids = np.full(
            physical.sample_count,
            physical.continuity_segment_index if observed else -1,
            dtype=np.int32,
        )
        return DeviceIqSpan(
            samples=physical.samples,
            valid_samples=validity,
            continuity_segment_ids=segment_ids,
            device_sample_start=physical.device_sample_start,
            receiver_ids=physical.receiver_ids,
        )

    def _assert_open(self) -> None:
        if self._closed:
            raise RuntimeError("V3 validity-aware IQ reader is closed")


class _V2ContinuitySegmentIqReader:
    """Lazy packed-IQ slice with local coordinates and explicit global mapping."""

    def __init__(self, source: IqReader, segment: ContinuitySegmentV1) -> None:
        if segment.observed_sample_count <= 0:
            raise ValueError("empty continuity segments cannot create analysis readers")
        self._source = source
        self._segment = segment

    @property
    def segment(self) -> ContinuitySegmentV1:
        return self._segment

    @property
    def continuity_segment_index(self) -> int:
        return self._segment.segment_index

    @property
    def global_device_sample_start(self) -> int:
        return self._segment.device_sample_start

    @property
    def sample_rate_hz(self) -> int:
        return self._source.sample_rate_hz

    @property
    def center_frequency_hz(self) -> int:
        return self._source.center_frequency_hz

    @property
    def sample_count(self) -> int:
        return self._segment.observed_sample_count

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        return self._source.receiver_ids

    def to_global_device_sample(self, local_sample: int) -> int:
        if not 0 <= local_sample <= self.sample_count:
            raise ValueError("local sample lies outside the continuity segment")
        return self.global_device_sample_start + local_sample

    def iter_blocks(self, *, block_samples: int) -> Iterable[IqBlock]:
        if not 0 < block_samples <= _MAX_BOUNDED_DEVICE_READ_SAMPLES:
            raise ValueError(f"block_samples must be in [1, {_MAX_BOUNDED_DEVICE_READ_SAMPLES}]")
        stored_start = self._segment.stored_sample_start
        local_cursor = 0
        for block in _iter_stored_range(
            self._source,
            stored_sample_start=stored_start,
            sample_count=self.sample_count,
            block_samples=block_samples,
        ):
            expected_stored_start = stored_start + local_cursor
            if block.metadata.session_sample_start != expected_stored_start:
                raise IqContinuityEvidenceError("segment reader lost packed IQ continuity")
            count = block.metadata.sample_count
            samples = np.ascontiguousarray(block.samples)
            metadata = _local_segment_metadata(
                block.metadata,
                source_offset=0,
                sample_count=count,
                local_sample_start=local_cursor,
                segment=self._segment,
            )
            yield IqBlock(samples=samples, metadata=metadata)
            local_cursor += count
        if local_cursor != self.sample_count:
            raise IqContinuityEvidenceError("segment reader ended before its declared IQ span")


class _V3ContinuitySegmentIqReader:
    """Local contiguous V3 reader backed only by verified observed physical IQ."""

    def __init__(
        self,
        source: VerifiedPhysicalDeviceAxisIqSource,
        segment: ContinuitySegmentV1,
    ) -> None:
        if segment.observed_sample_count <= 0:
            raise ValueError("empty continuity segments cannot create analysis readers")
        self._source = source
        self._segment = segment

    @property
    def segment(self) -> ContinuitySegmentV1:
        return self._segment

    @property
    def continuity_segment_index(self) -> int:
        return self._segment.segment_index

    @property
    def global_device_sample_start(self) -> int:
        return self._segment.device_sample_start

    @property
    def sample_rate_hz(self) -> int:
        return self._source.sample_rate_hz

    @property
    def center_frequency_hz(self) -> int:
        return self._source.center_frequency_hz

    @property
    def sample_count(self) -> int:
        return self._segment.observed_sample_count

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        return self._source.receiver_ids

    def to_global_device_sample(self, local_sample: int) -> int:
        if not 0 <= local_sample <= self.sample_count:
            raise ValueError("local sample lies outside the continuity segment")
        return self.global_device_sample_start + local_sample

    def iter_blocks(self, *, block_samples: int) -> Iterable[IqBlock]:
        _validate_block_samples(block_samples)
        local_cursor = 0
        for block in self._source.iter_observed_segment_blocks(
            self._segment,
            block_samples=block_samples,
        ):
            expected_stored_start = self._segment.stored_sample_start + local_cursor
            if block.metadata.session_sample_start != expected_stored_start:
                raise IqContinuityEvidenceError("V3 segment reader lost packed IQ continuity")
            count = block.metadata.sample_count
            metadata = _local_segment_metadata(
                block.metadata,
                source_offset=0,
                sample_count=count,
                local_sample_start=local_cursor,
                segment=self._segment,
            )
            yield IqBlock(samples=np.ascontiguousarray(block.samples), metadata=metadata)
            local_cursor += count
        if local_cursor != self.sample_count:
            raise IqContinuityEvidenceError("V3 segment reader ended before its declared IQ span")


def _local_segment_metadata(
    metadata: IqBlockMetadataV1,
    *,
    source_offset: int,
    sample_count: int,
    local_sample_start: int,
    segment: ContinuitySegmentV1,
) -> IqBlockMetadataV1:
    document = metadata.model_dump(mode="json")
    document.update(
        {
            "sample_count": sample_count,
            "session_sample_start": local_sample_start,
            "device_sample_counter": (
                None
                if metadata.device_sample_counter is None
                else metadata.device_sample_counter + source_offset
            ),
            "continuity": (
                ContinuityStatus.UNKNOWN.value
                if local_sample_start == 0
                else ContinuityStatus.CONTIGUOUS.value
            ),
            "missing_samples_before": 0,
            "overflow_observed": False,
            "hardware_metadata": {
                **metadata.hardware_metadata,
                "source_stored_sample_start": metadata.session_sample_start + source_offset,
                "global_device_sample_start": segment.device_sample_start + local_sample_start,
                "continuity_segment_index": segment.segment_index,
            },
        }
    )
    return type(metadata).model_validate(document)


def _overlap_count(left_start: int, left_stop: int, right_start: int, right_stop: int) -> int:
    return max(0, min(left_stop, right_stop) - max(left_start, right_start))


def _validate_block_samples(block_samples: int) -> None:
    if not 0 < block_samples <= _MAX_BOUNDED_DEVICE_READ_SAMPLES:
        raise ValueError(f"block_samples must be in [1, {_MAX_BOUNDED_DEVICE_READ_SAMPLES}]")


def _classify_inventory_window(
    inventory: ValidityInventoryV1,
    *,
    device_sample_start: int,
    sample_count: int,
) -> WindowClassification:
    if sample_count <= 0:
        raise ValueError("window sample count must be positive")
    device_sample_stop = device_sample_start + sample_count
    if device_sample_start < 0 or device_sample_stop > inventory.logical_sample_count:
        return WindowClassification(
            device_sample_start=device_sample_start,
            sample_count=sample_count,
            status=WindowValidity.OUTSIDE_SPAN,
        )

    missing = sum(
        _overlap_count(
            device_sample_start,
            device_sample_stop,
            run.device_sample_start,
            run.device_sample_stop,
        )
        for run in inventory.runs
        if run.content_kind is DeviceAxisContentKind.ZERO_FILL
    )
    crossed = tuple(
        segment.segment_index
        for segment in inventory.segments[1:]
        if device_sample_start < segment.device_sample_start < device_sample_stop
    )
    if missing:
        return WindowClassification(
            device_sample_start=device_sample_start,
            sample_count=sample_count,
            status=WindowValidity.GAP_OVERLAP,
            missing_sample_count=missing,
            crossed_segment_indexes=crossed,
        )
    if crossed:
        return WindowClassification(
            device_sample_start=device_sample_start,
            sample_count=sample_count,
            status=WindowValidity.CONTINUITY_BOUNDARY,
            crossed_segment_indexes=crossed,
        )
    segment = next(
        (
            item
            for item in inventory.segments
            if item.device_sample_start <= device_sample_start
            and device_sample_stop <= item.device_sample_stop
        ),
        None,
    )
    if segment is None:
        raise IqContinuityEvidenceError(
            "window lies inside the logical span but outside its validity inventory"
        )
    return WindowClassification(
        device_sample_start=device_sample_start,
        sample_count=sample_count,
        status=WindowValidity.VALID,
        continuity_segment_index=segment.segment_index,
    )


def _iter_stored_range(
    source: IqReader,
    *,
    stored_sample_start: int,
    sample_count: int,
    block_samples: int,
) -> Iterable[IqBlock]:
    """Use bounded retained storage when available, with a compatibility fallback."""

    method = getattr(source, "iter_stored_blocks", None)
    if callable(method):
        yield from cast(_StoredRangeIqReader, source).iter_stored_blocks(
            stored_sample_start=stored_sample_start,
            sample_count=sample_count,
            block_samples=block_samples,
        )
        return

    stored_sample_stop = stored_sample_start + sample_count
    selected_cursor = stored_sample_start
    for block in source.iter_blocks(block_samples=block_samples):
        block_start = block.metadata.session_sample_start
        block_stop = block_start + block.metadata.sample_count
        overlap_start = max(stored_sample_start, block_start)
        overlap_stop = min(stored_sample_stop, block_stop)
        if overlap_start >= overlap_stop:
            continue
        if overlap_start != selected_cursor:
            raise IqContinuityEvidenceError("fallback stored IQ range is not contiguous")
        offset = overlap_start - block_start
        count = overlap_stop - overlap_start
        samples = np.ascontiguousarray(block.samples[offset : offset + count])
        yield IqBlock(
            samples=samples,
            metadata=_slice_packed_metadata(
                block.metadata,
                source_offset=offset,
                sample_count=count,
            ),
        )
        selected_cursor = overlap_stop
        if selected_cursor == stored_sample_stop:
            break
    if selected_cursor != stored_sample_stop:
        raise IqContinuityEvidenceError("fallback stored IQ range ended early")


def _slice_packed_metadata(
    metadata: IqBlockMetadataV1,
    *,
    source_offset: int,
    sample_count: int,
) -> IqBlockMetadataV1:
    document = metadata.model_dump(mode="json")
    document.update(
        {
            "sample_count": sample_count,
            "session_sample_start": metadata.session_sample_start + source_offset,
            "device_sample_counter": (
                None
                if metadata.device_sample_counter is None
                else metadata.device_sample_counter + source_offset
            ),
        }
    )
    if source_offset:
        document.update(
            {
                "continuity": ContinuityStatus.CONTIGUOUS.value,
                "missing_samples_before": 0,
                "overflow_observed": False,
            }
        )
    return type(metadata).model_validate(document)
