"""Transactional composition of persistent hopping and its queued IQ store."""

from __future__ import annotations

from collections.abc import Callable
from threading import Event

from leo.scanner.persistent_hop import (
    PersistentHopPlanV1,
    PersistentHopUtcTimingAuthorityV1,
)
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
    before_publish: Callable[[], None] | None = None,
) -> PublishedPersistentHopIqSession:
    """Publish only after terminal evidence and the external safety barrier."""

    writer = store.begin_queued(
        session_id,
        plan,
        capacity_visits=queue_capacity_visits,
    )
    timings: list[PersistentHopUtcTimingAuthorityV1] = []
    try:
        receipt = capture_persistent_hop_session(
            radio,
            plan,
            session_id=session_id,
            visit_sink=writer.append,
            cancel=cancel,
            timing_sink=timings.append,
        )
        if before_publish is not None:
            before_publish()
        if len(timings) != 1:
            raise RuntimeError("persistent-hop capture did not produce one timing authority")
        return writer.finish(receipt, timing=timings[0])
    except BaseException:
        writer.abort()
        raise
