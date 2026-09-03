"""Narrow receiver port for persistent, device-counter-authoritative hopping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from leo.scanner.persistent_hop import (
    PersistentHopPlanV1,
    PersistentHopSessionReceiptV1,
    PersistentHopVisitV1,
)
from leo.scanner.ports import ScanRadioIdentity


@dataclass(frozen=True, slots=True)
class PersistentHopVisitBlock:
    """Only the valid IQ for one visit, bound to its counter evidence."""

    samples: np.ndarray
    receiver_ids: tuple[int, ...]
    evidence: PersistentHopVisitV1

    def __post_init__(self) -> None:
        values = np.asarray(self.samples)
        expected_shape = (self.evidence.valid_sample_count, len(self.receiver_ids))
        if values.dtype != np.dtype(np.complex64) or values.shape != expected_shape:
            raise ValueError(f"persistent-hop IQ must be complex64 with shape {expected_shape}")
        if not values.flags.c_contiguous:
            raise ValueError("persistent-hop IQ must be C-contiguous")
        if not np.all(np.isfinite(values)):
            raise ValueError("persistent-hop IQ contains non-finite values")
        if not self.receiver_ids or tuple(sorted(set(self.receiver_ids))) != self.receiver_ids:
            raise ValueError("persistent-hop receiver IDs must be nonempty, unique, and sorted")
        values.setflags(write=False)
        object.__setattr__(self, "samples", values)


class PersistentHopSession(Protocol):
    """One armed session; finish requires an attested server terminal status.

    ``read_visit`` raises ``StopIteration`` only after the server is terminal.
    Cancellation is requested in-band so the transport remains open for HOPT.
    """

    @property
    def plan(self) -> PersistentHopPlanV1: ...

    @property
    def complete(self) -> bool: ...

    def read_visit(self) -> PersistentHopVisitBlock: ...

    def request_cancel(self) -> None: ...

    def finish(self) -> PersistentHopSessionReceiptV1: ...


class PersistentHopRadio(Protocol):
    @property
    def identity(self) -> ScanRadioIdentity: ...

    def open(self) -> ScanRadioIdentity: ...

    def begin_session(
        self, plan: PersistentHopPlanV1, *, session_id: str
    ) -> PersistentHopSession: ...

    def close(self) -> None: ...
