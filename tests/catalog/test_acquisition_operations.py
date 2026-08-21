from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from leo.catalog import InvalidStateError, LeaseLostError


def _enqueue(harness, key: str, kind: str = "scheduled_recording"):
    due = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)
    return harness.repository.enqueue_acquisition_operation(
        operation_key=key,
        kind=kind,
        payload={"profile_name": "live-60s", "radio_ids": ["radio-a", "radio-b"]},
        scheduled_for=due,
    )


def test_cadence_enqueue_is_idempotent_and_conflicts_fail_closed(catalog_harness) -> None:
    first = _enqueue(catalog_harness, "dwell:20260821T080000Z")
    repeated = _enqueue(catalog_harness, "dwell:20260821T080000Z")

    assert repeated.operation_id == first.operation_id
    assert repeated.state == "pending"
    with pytest.raises(InvalidStateError, match="different intent"):
        catalog_harness.repository.enqueue_acquisition_operation(
            operation_key="dwell:20260821T080000Z",
            kind="scanner_sweep",
            payload={},
            scheduled_for=first.scheduled_for,
        )


def test_two_workers_can_never_claim_radio_operations_concurrently(catalog_harness) -> None:
    _enqueue(catalog_harness, "dwell:one")
    _enqueue(catalog_harness, "scan:one", "scanner_sweep")

    with ThreadPoolExecutor(max_workers=2) as pool:
        leases = tuple(
            pool.map(
                lambda worker: catalog_harness.repository.claim_acquisition_operation(
                    worker_id=worker,
                    lease_for=timedelta(minutes=2),
                ),
                ("worker-a", "worker-b"),
            )
        )

    assert sum(lease is not None for lease in leases) == 1
    assert len(catalog_harness.repository.active_acquisition_operations()) == 2


def test_expired_lease_is_recovered_without_dropping_the_intent(catalog_harness) -> None:
    operation = _enqueue(catalog_harness, "dwell:recover")
    lease = catalog_harness.repository.claim_acquisition_operation(
        worker_id="dead-worker", lease_for=timedelta(microseconds=1)
    )
    assert lease is not None

    reclaimed = catalog_harness.repository.reclaim_expired_acquisition_operations(
        as_of=datetime.now(UTC) + timedelta(seconds=1)
    )
    replacement = catalog_harness.repository.claim_acquisition_operation(
        worker_id="replacement", lease_for=timedelta(minutes=1)
    )

    assert reclaimed == (operation.operation_id,)
    assert replacement is not None
    assert replacement.operation_id == operation.operation_id
    assert replacement.attempt_number == 2


def test_completion_releases_global_owner_and_preserves_fifo_alternation(
    catalog_harness,
) -> None:
    dwell = _enqueue(catalog_harness, "dwell:alternate")
    scan = _enqueue(catalog_harness, "scan:alternate", "scanner_sweep")
    first = catalog_harness.repository.claim_acquisition_operation(
        worker_id="supervisor", lease_for=timedelta(minutes=1)
    )
    assert first is not None and first.operation_id == dwell.operation_id

    catalog_harness.repository.complete_acquisition_operation(
        operation_id=first.operation_id,
        worker_id="supervisor",
        outcome="capture committed",
    )
    second = catalog_harness.repository.claim_acquisition_operation(
        worker_id="supervisor", lease_for=timedelta(minutes=1)
    )
    assert second is not None and second.operation_id == scan.operation_id


def test_stale_worker_cannot_complete_recovered_operation(catalog_harness) -> None:
    _enqueue(catalog_harness, "dwell:fence")
    stale = catalog_harness.repository.claim_acquisition_operation(
        worker_id="stale", lease_for=timedelta(microseconds=1)
    )
    assert stale is not None
    catalog_harness.repository.reclaim_expired_acquisition_operations(
        as_of=datetime.now(UTC) + timedelta(seconds=1)
    )
    with pytest.raises(LeaseLostError):
        catalog_harness.repository.complete_acquisition_operation(
            operation_id=stale.operation_id,
            worker_id="stale",
            outcome="must not publish",
        )
