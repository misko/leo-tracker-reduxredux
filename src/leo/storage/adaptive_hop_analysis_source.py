"""Pinned read-only adaptive analysis source with explicit bounded reader lifetime."""

from collections.abc import Iterator
from contextlib import contextmanager

import numpy as np
import numpy.typing as npt

from leo.scanner.adaptive_hop import (
    AdaptiveHopReceiptV1,
    AdaptiveHopReceiptV2,
    AdaptiveHopReceiptV3,
    AdaptiveHopVisitV1,
)
from leo.scanner.adaptive_hop_analysis import (
    AdaptiveHopAnalysisSource,
    DualRx10mAdaptiveHopAnalysisSourceV3,
    EdgeAdaptiveHopAnalysisSourceV2,
)
from leo.scanner.host_adaptive import (
    HostAdaptiveHopReceiptV2,
    HostAdaptiveHopReceiptV3,
    HostAdaptiveHopReceiptV4,
    HostAdaptiveHopReceiptV5,
)
from leo.scanner.host_adaptive_analysis import (
    HostAdaptiveAnalysisSource,
    HostAdaptiveAnalysisSourceV3,
    HostAdaptiveAnalysisSourceV4,
    HostAdaptiveAnalysisSourceV5,
)
from leo.storage.adaptive_hop import AdaptiveHopIqReader, AdaptiveHopIqStore


class _BoundReader:
    def __init__(self, reader: AdaptiveHopIqReader):
        self._reader = reader

    @property
    def session_id(self) -> str:
        return self._reader.session.session_id

    @property
    def input_manifest_sha256(self) -> str:
        return self._reader.session.manifest_sha256

    @property
    def receipt(self) -> AdaptiveHopReceiptV1 | AdaptiveHopReceiptV2 | AdaptiveHopReceiptV3:
        return self._reader.session.manifest.receipt

    def read_visit_ci16(self, index: int) -> tuple[AdaptiveHopVisitV1, npt.NDArray[np.int16]]:
        return self._reader.read_visit_ci16(index)


class AdaptiveHopAnalysisInputStore:
    def __init__(self, store: AdaptiveHopIqStore):
        self._store = store

    def session_ids(self) -> tuple[str, ...]:
        return self._store.session_ids()

    @contextmanager
    def source(self, session_id: str) -> Iterator[AdaptiveHopAnalysisSource]:
        with self._store.reader(session_id) as reader:
            model = (
                HostAdaptiveAnalysisSourceV5
                if isinstance(reader.session.manifest.receipt, HostAdaptiveHopReceiptV5)
                else HostAdaptiveAnalysisSourceV4
                if isinstance(reader.session.manifest.receipt, HostAdaptiveHopReceiptV4)
                else HostAdaptiveAnalysisSourceV3
                if isinstance(reader.session.manifest.receipt, HostAdaptiveHopReceiptV3)
                else HostAdaptiveAnalysisSource
                if isinstance(reader.session.manifest.receipt, HostAdaptiveHopReceiptV2)
                else DualRx10mAdaptiveHopAnalysisSourceV3
                if isinstance(reader.session.manifest.receipt, AdaptiveHopReceiptV3)
                else EdgeAdaptiveHopAnalysisSourceV2
                if isinstance(reader.session.manifest.receipt, AdaptiveHopReceiptV2)
                else AdaptiveHopAnalysisSource
            )
            yield model(_BoundReader(reader))
