"""Read-only analysis adapter for persisted valid-only hopping IQ."""

from __future__ import annotations

from leo.scanner.persistent_hop_analysis import (
    PersistentHopAnalysisSource,
    build_persistent_hop_analysis_source,
)
from leo.storage.persistent_hop import (
    PersistentHopIqStore,
    PublishedPersistentHopIqSession,
)


class PersistentHopAnalysisInputStore:
    """Narrow read adapter used by the restartable analysis worker."""

    def __init__(self, store: PersistentHopIqStore) -> None:
        self._store = store

    def session_ids(self) -> tuple[str, ...]:
        return self._store.session_ids()

    def source(self, session_id: str) -> PersistentHopAnalysisSource:
        return persisted_persistent_hop_analysis_source(self._store, session_id)


def persisted_persistent_hop_analysis_source(
    store: PersistentHopIqStore,
    session: PublishedPersistentHopIqSession | str,
) -> PersistentHopAnalysisSource:
    """Bind an inspected session and its digest-verified lazy CI16 reader."""

    inspected = store.inspect(session) if isinstance(session, str) else session
    return build_persistent_hop_analysis_source(
        receipt=inspected.manifest.receipt,
        reader=store.valid_ci16_reader(inspected),
        input_uri=inspected.uri,
        input_manifest_sha256=inspected.manifest_sha256,
    )
