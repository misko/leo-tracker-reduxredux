"""Transactional composition of persistent hopping and its queued IQ store."""

from __future__ import annotations

from threading import Event

from leo.scanner.persistent_hop import PersistentHopPlanV1
from leo.scanner.persistent_hop_application import capture_persistent_hop_session
from leo.scanner.persistent_hop_ports import PersistentHopRadio
from leo.storage.persistent_hop import (
    PersistentHopIqStore,
    PublishedPersistentHopIqSession,
)


def capture_persistent_hop_to_store(
    radio: PersistentHopRadio,
    plan: PersistentHopPlanV1,
    *,
    session_id: str,
    store: PersistentHopIqStore,
    cancel: Event,
    queue_capacity_visits: int = 16,
) -> PublishedPersistentHopIqSession:
    """Publish only after terminal evidence and all valid IQ are durable."""

    writer = store.begin_queued(
        session_id,
        plan,
        capacity_visits=queue_capacity_visits,
    )
    try:
        receipt = capture_persistent_hop_session(
            radio,
            plan,
            session_id=session_id,
            visit_sink=writer.append,
            cancel=cancel,
        )
        return writer.finish(receipt)
    except BaseException:
        writer.abort()
        raise
