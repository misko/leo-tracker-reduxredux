"""Deterministic one/two-receiver source for contract and coordinator tests."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from leo.contracts.radio import (
    IqBlockMetadataV1,
    IqBlockMetadataV2,
    NanosecondIntervalV1,
    RadioCapabilitiesV1,
    RadioIdentityV1,
    RadioSettingsV1,
)
from leo.contracts.states import ContinuityStatus, RadioTransport, TimingMethod
from leo.domain.iq import IqBlock


class FakeRadioError(RuntimeError):
    pass


class FakeRadioSource:
    """A bounded fake whose samples and timing depend only on constructor inputs."""

    def __init__(
        self,
        radio_id: str,
        *,
        receiver_count: int = 2,
        seed: int = 0,
        fail_after_blocks: int | None = None,
        gaps_before_blocks: Mapping[int, int] | None = None,
        utc_origin_ns: int = 1_700_000_000_000_000_000,
        monotonic_origin_ns: int = 1_000_000_000,
        block_latency_ns: int = 1_000_000,
    ) -> None:
        if receiver_count not in (1, 2):
            raise ValueError("fake radio supports one or two receivers")
        if fail_after_blocks is not None and fail_after_blocks < 0:
            raise ValueError("fail_after_blocks cannot be negative")
        if utc_origin_ns <= 0 or monotonic_origin_ns < 0 or block_latency_ns <= 0:
            raise ValueError("fake clock values are invalid")
        gaps = dict(gaps_before_blocks or {})
        if any(block < 0 or samples <= 0 for block, samples in gaps.items()):
            raise ValueError("fake gaps require non-negative blocks and positive sample counts")
        self._identity = RadioIdentityV1(
            radio_id=radio_id,
            serial=radio_id,
            uri=f"fake://{radio_id}",
            transport=RadioTransport.FAKE,
            model="Deterministic Fake Pluto+",
            firmware_version="fake-v1",
        )
        self._capabilities = RadioCapabilitiesV1(
            receiver_ids=tuple(range(receiver_count)),
            minimum_sample_rate_hz=1,
            maximum_sample_rate_hz=100_000_000,
            supports_device_sample_counter=True,
            supports_continuity_sequence=True,
        )
        self._seed = seed
        self._fail_after_blocks = fail_after_blocks
        self._gaps_before_blocks = gaps
        self._utc_origin_ns = utc_origin_ns
        self._monotonic_origin_ns = monotonic_origin_ns
        self._block_latency_ns = block_latency_ns
        self._settings: RadioSettingsV1 | None = None
        self._is_open = False
        self._block_index = 0
        self._device_sample_counter = 0
        self._session_sample_cursor = 0
        self._metadata_capture = False
        self._metadata_generation = 0
        self._metadata_sequence = 0
        self._kernel_buffers: int | None = None
        self._metadata_refill_samples: int | None = None
        self.lifecycle: list[str] = []

    @property
    def identity(self) -> RadioIdentityV1:
        return self._identity

    @property
    def capabilities(self) -> RadioCapabilitiesV1:
        return self._capabilities

    def open(self) -> RadioIdentityV1:
        if self._is_open:
            raise FakeRadioError("fake radio is already open")
        self._is_open = True
        self.lifecycle.append("open")
        return self.identity

    def configure(self, settings: RadioSettingsV1) -> RadioSettingsV1:
        self._require_open()
        if any(
            receiver not in self.capabilities.receiver_ids for receiver in settings.receiver_ids
        ):
            raise FakeRadioError("settings request an unsupported receiver")
        if not (
            self.capabilities.minimum_sample_rate_hz
            <= settings.sample_rate_hz
            <= self.capabilities.maximum_sample_rate_hz
        ):
            raise FakeRadioError("settings request an unsupported sample rate")
        self._settings = settings
        self._block_index = 0
        self._device_sample_counter = 0
        self._session_sample_cursor = 0
        self._metadata_capture = False
        self._kernel_buffers = None
        self._metadata_refill_samples = None
        self.lifecycle.append("configure")
        return settings

    def reset_receive_buffer(self) -> None:
        self._require_open()
        self._metadata_capture = False
        self._kernel_buffers = None
        self._metadata_refill_samples = None
        self.lifecycle.append("reset_receive_buffer")

    def begin_metadata_capture(self, sample_count: int, *, kernel_buffers: int) -> int:
        self._require_open()
        if self._settings is None:
            raise FakeRadioError("fake radio must be configured before metadata capture")
        if sample_count <= 0 or kernel_buffers < 2:
            raise ValueError("invalid fake metadata-capture geometry")
        self._metadata_capture = True
        self._metadata_generation += 1
        self._metadata_sequence = 0
        self._kernel_buffers = kernel_buffers
        self._metadata_refill_samples = sample_count
        self._session_sample_cursor = 0
        self.lifecycle.append(f"begin_metadata_capture:{sample_count}:{kernel_buffers}")
        return kernel_buffers

    def read_block(self, sample_count: int) -> IqBlock:
        self._require_open()
        settings = self._settings
        if settings is None:
            raise FakeRadioError("fake radio must be configured before capture")
        if sample_count <= 0:
            raise ValueError("sample_count must be positive")
        if self._fail_after_blocks is not None and self._block_index >= self._fail_after_blocks:
            raise FakeRadioError(f"injected failure before block {self._block_index}")

        missing = self._gaps_before_blocks.get(self._block_index, 0)
        self._device_sample_counter += missing
        if self._metadata_capture and missing:
            assert self._metadata_refill_samples is not None
            if missing % self._metadata_refill_samples:
                raise FakeRadioError(
                    "counter-authoritative fake gaps must contain whole fixed refills"
                )
            self._metadata_sequence += missing // self._metadata_refill_samples
        continuity = (
            ContinuityStatus.GAP_BEFORE
            if missing
            else (
                ContinuityStatus.UNKNOWN if self._block_index == 0 else ContinuityStatus.CONTIGUOUS
            )
        )
        samples = self._samples(sample_count, settings.receiver_ids)
        request_start = self._block_index * self._block_latency_ns * 2
        utc_interval = NanosecondIntervalV1(
            lower_ns=self._utc_origin_ns + request_start,
            upper_ns=self._utc_origin_ns + request_start + self._block_latency_ns,
        )
        monotonic_interval = NanosecondIntervalV1(
            lower_ns=self._monotonic_origin_ns + request_start,
            upper_ns=self._monotonic_origin_ns + request_start + self._block_latency_ns,
        )
        common = dict(
            radio_id=self.identity.radio_id,
            receiver_ids=settings.receiver_ids,
            sample_count=sample_count,
            session_sample_start=self._session_sample_cursor,
            host_request_utc_ns=utc_interval,
            host_request_monotonic_ns=monotonic_interval,
            device_sample_counter=self._device_sample_counter,
            source_sequence=(
                self._metadata_sequence if self._metadata_capture else self._block_index
            ),
            continuity=continuity,
            missing_samples_before=missing,
        )
        if self._metadata_capture:
            assert self._kernel_buffers is not None
            sample_start_offset_ns = (
                self._device_sample_counter * 1_000_000_000 // settings.sample_rate_hz
            )
            sample_duration_ns = sample_count * 1_000_000_000 // settings.sample_rate_hz
            metadata: IqBlockMetadataV1 = IqBlockMetadataV2(
                **common,
                timing_method=TimingMethod.DEVICE_COUNTER_ANCHORED,
                stream_generation=f"fake-generation-{self._metadata_generation}",
                metadata_abi_version=1,
                metadata_flags=0,
                kernel_buffers=self._kernel_buffers,
                sample_time_realtime_ns=NanosecondIntervalV1(
                    lower_ns=self._utc_origin_ns + sample_start_offset_ns,
                    upper_ns=self._utc_origin_ns + sample_start_offset_ns + sample_duration_ns,
                ),
                sample_time_monotonic_ns=NanosecondIntervalV1(
                    lower_ns=self._monotonic_origin_ns + sample_start_offset_ns,
                    upper_ns=self._monotonic_origin_ns
                    + sample_start_offset_ns
                    + sample_duration_ns,
                ),
                sample_time_uncertainty_ns=11,
                hardware_metadata={
                    "fake_seed": self._seed,
                    "fake_metadata": True,
                },
            )
        else:
            metadata = IqBlockMetadataV1(
                **common,
                timing_method=TimingMethod.DEVICE_COUNTER_ANCHORED,
                hardware_metadata={"fake_seed": self._seed},
            )
        result = IqBlock(samples=samples, metadata=metadata)
        self._block_index += 1
        self._metadata_sequence += 1
        self._device_sample_counter += sample_count
        self._session_sample_cursor += sample_count
        return result

    def close(self) -> None:
        self._settings = None
        self._is_open = False
        self._metadata_capture = False
        self._kernel_buffers = None
        self._metadata_refill_samples = None
        self.lifecycle.append("close")

    def _samples(self, sample_count: int, receiver_ids: tuple[int, ...]) -> np.ndarray:
        positions = np.arange(sample_count, dtype=np.int64) + self._device_sample_counter
        output = np.empty((sample_count, len(receiver_ids), 2), dtype="<i2")
        for column, receiver_id in enumerate(receiver_ids):
            i_values = (positions + self._seed + receiver_id * 1_009) % 65_536 - 32_768
            q_values = (positions * 3 + self._seed * 7 + receiver_id * 2_003) % 65_536 - 32_768
            output[:, column, 0] = i_values.astype("<i2")
            output[:, column, 1] = q_values.astype("<i2")
        return output

    def _require_open(self) -> None:
        if not self._is_open:
            raise FakeRadioError("fake radio is not open")
