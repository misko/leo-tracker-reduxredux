"""Adaptive recording publication after radio close and external safety checks."""

from __future__ import annotations

from collections.abc import Callable
from threading import Event

from leo.scanner.adaptive_hop import AdaptiveHopPlanV1
from leo.scanner.adaptive_hop_application import capture_adaptive_hop_session
from leo.scanner.adaptive_hop_ports import AdaptiveHopRadio
from leo.storage.adaptive_hop import AdaptiveHopIqStore, PublishedAdaptiveHopIqSession


def capture_adaptive_hop_to_store(
    radio: AdaptiveHopRadio,
    plan: AdaptiveHopPlanV1,
    *,
    session_id: str,
    store: AdaptiveHopIqStore,
    cancel: Event,
    queue_capacity_visits: int = 8,
    before_publish: Callable[[], None] | None = None,
) -> PublishedAdaptiveHopIqSession:
    writer = store.begin_queued(session_id, plan, capacity_visits=queue_capacity_visits)
    try:
        capture = capture_adaptive_hop_session(
            radio,
            plan,
            session_id=session_id,
            visit_sink=writer.append,
            cancel=cancel,
        )
        if before_publish is not None:
            before_publish()
        return writer.finish(capture.receipt, timing=capture.timing)
    except BaseException as primary:
        try:
            writer.abort()
        except BaseException as cleanup:
            primary.add_note(f"adaptive storage abort also failed: {cleanup!r}")
        raise
