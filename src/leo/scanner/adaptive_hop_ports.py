"""Application-facing adaptive capture ports, with no PPU or storage types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import numpy.typing as npt

from leo.scanner.adaptive_hop import (
    AdaptiveHopPlanV1,
    AdaptiveHopReceiptV1,
    AdaptiveHopVisitV1,
)
from leo.scanner.persistent_hop_ports import PersistentHopStartClockBracketV1
from leo.scanner.ports import ScanRadioIdentity


@dataclass(frozen=True, slots=True)
class AdaptiveHopVisitBlock:
    """Valid dual-RX IQ in sample/receiver order, bound to one actual visit.

    Construction transfers ownership. As with other capture ports, callers
    must not modify aliased samples after handing the block to a consumer.
    """

    samples: npt.NDArray[np.complex64]
    receiver_ids: tuple[int, int]
    evidence: AdaptiveHopVisitV1

    def __post_init__(self) -> None:
        AdaptiveHopVisitV1.model_validate(self.evidence)
        values = np.asarray(self.samples)
        if (
            self.receiver_ids != (0, 1)
            or any(type(value) is not int for value in self.receiver_ids)
            or values.dtype != np.dtype(np.complex64)
            or values.shape != (self.evidence.valid_sample_count, 2)
            or not values.flags.c_contiguous
            or not np.all(np.isfinite(values))
        ):
            raise ValueError("adaptive IQ must be finite contiguous complex64 for RX0 and RX1")
        values.setflags(write=False)
        object.__setattr__(self, "samples", values)


class AdaptiveHopSession(Protocol):
    @property
    def plan(self) -> AdaptiveHopPlanV1: ...

    @property
    def complete(self) -> bool: ...

    @property
    def start_clock_bracket(self) -> PersistentHopStartClockBracketV1 | None: ...

    def read_visit(self) -> AdaptiveHopVisitBlock: ...

    def request_cancel(self) -> None: ...

    def finish(self) -> AdaptiveHopReceiptV1: ...


class AdaptiveHopRadio(Protocol):
    @property
    def identity(self) -> ScanRadioIdentity: ...

    def open(self) -> ScanRadioIdentity: ...

    def begin_session(self, plan: AdaptiveHopPlanV1, *, session_id: str) -> AdaptiveHopSession: ...

    def close(self) -> None: ...
