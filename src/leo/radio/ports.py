"""Narrow acquisition-owned radio port."""

from __future__ import annotations

from typing import Protocol

from leo.contracts.device_buffer import DdrRingStatusV1, DeviceBufferRequestV1
from leo.contracts.gain_control import GainControllerPolicyV1
from leo.contracts.radio import RadioCapabilitiesV1, RadioIdentityV1, RadioSettingsV1
from leo.domain.iq import IqBlock


class RadioSource(Protocol):
    @property
    def identity(self) -> RadioIdentityV1: ...

    @property
    def capabilities(self) -> RadioCapabilitiesV1: ...

    def open(self) -> RadioIdentityV1: ...

    def configure(self, settings: RadioSettingsV1) -> RadioSettingsV1: ...

    def reset_receive_buffer(self) -> None: ...

    def begin_metadata_capture(
        self,
        sample_count: int,
        *,
        kernel_buffers: int,
        gain_controller: GainControllerPolicyV1 | None = None,
        device_buffer: DeviceBufferRequestV1 | None = None,
    ) -> int: ...

    def ddr_ring_status(self) -> DdrRingStatusV1: ...

    def read_block(self, sample_count: int) -> IqBlock: ...

    def close(self) -> None: ...
