"""Single physical receiver capture ports; the payload always has one column."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import numpy.typing as npt

from leo.scanner.adaptive_hop import AdaptiveHopVisitV1
from leo.scanner.host_adaptive import HostAdaptiveHopPlanV2, HostAdaptiveHopReceiptV2
from leo.scanner.persistent_hop_ports import PersistentHopStartClockBracketV1
from leo.scanner.ports import ScanRadioIdentity


@dataclass(frozen=True, slots=True)
class HostAdaptiveHopVisitBlock:
    """Ownership transfers at construction, as for the other capture ports."""

    samples: npt.NDArray[np.complex64]
    receiver_ids: tuple[int]
    evidence: AdaptiveHopVisitV1

    def __post_init__(self) -> None:
        AdaptiveHopVisitV1.model_validate(self.evidence)
        values = np.asarray(self.samples)
        if (
            not isinstance(self.receiver_ids, tuple)
            or len(self.receiver_ids) != 1
            or type(self.receiver_ids[0]) is not int
            or self.receiver_ids[0] not in (0, 1)
            or self.evidence.valid_sample_count != 1_200_000
            or values.dtype != np.complex64
            or values.shape != (1_200_000, 1)
            or not values.flags.c_contiguous
            or not np.isfinite(values).all()
        ):
            raise ValueError("host adaptive IQ requires a native-10M visit and one physical RX")
        values.setflags(write=False)
        object.__setattr__(self, "samples", values)


class HostAdaptiveHopSession(Protocol):
    @property
    def plan(self) -> HostAdaptiveHopPlanV2: ...
    @property
    def complete(self) -> bool: ...
    @property
    def start_clock_bracket(self) -> PersistentHopStartClockBracketV1 | None: ...
    def read_visit(self) -> HostAdaptiveHopVisitBlock: ...
    def request_cancel(self) -> None: ...
    def finish(self) -> HostAdaptiveHopReceiptV2: ...


class HostAdaptiveHopRadio(Protocol):
    @property
    def identity(self) -> ScanRadioIdentity: ...
    def open(self) -> ScanRadioIdentity: ...
    def begin_session(
        self, plan: HostAdaptiveHopPlanV2, *, session_id: str
    ) -> HostAdaptiveHopSession: ...
    def close(self) -> None: ...
