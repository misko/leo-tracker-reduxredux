"""Pinned read-only adaptive analysis source with explicit bounded reader lifetime."""

from collections.abc import Iterator
from contextlib import contextmanager

import numpy as np
import numpy.typing as npt

from leo.scanner.adaptive_hop import AdaptiveHopReceiptV1, AdaptiveHopVisitV1
from leo.scanner.adaptive_hop_analysis import AdaptiveHopAnalysisSource
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
    def receipt(self) -> AdaptiveHopReceiptV1:
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
            yield AdaptiveHopAnalysisSource(_BoundReader(reader))
