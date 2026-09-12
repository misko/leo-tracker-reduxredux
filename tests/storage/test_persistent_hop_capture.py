from __future__ import annotations

from threading import Event

import pytest

from leo.scanner.fake_persistent_hop import FakePersistentHopRadio
from leo.scanner.persistent_hop import compile_persistent_hop_plan_v1
from leo.storage.persistent_hop import PersistentHopIqStore
from leo.storage.persistent_hop_capture import capture_persistent_hop_to_store


class _OneVisitSession:
    def __init__(self, plan, block, receipt) -> None:
        self.plan = plan
        self._block = block
        self._receipt = receipt
        self._read = False

    @property
    def complete(self) -> bool:
        return self._read

    def read_visit(self):
        if self._read:
            raise StopIteration
        self._read = True
        return self._block

    def request_cancel(self) -> None:
        raise AssertionError("completed stub must not be cancelled")

    def finish(self):
        return self._receipt


class _OneVisitRadio:
    def __init__(self, source: FakePersistentHopRadio, session: _OneVisitSession) -> None:
        self.identity = source.identity
        self._session = session
        self.opened = False

    def open(self):
        self.opened = True
        return self.identity

    def begin_session(self, plan, *, session_id: str):
        assert plan == self._session.plan
        assert session_id == self._session._receipt.session_id
        return self._session

    def close(self) -> None:
        self.opened = False


class _FailingRadio:
    def __init__(self, identity) -> None:
        self.identity = identity

    def open(self):
        raise RuntimeError("injected provider admission failure")

    def begin_session(self, plan, *, session_id: str):
        raise AssertionError("failed open cannot begin a session")

    def close(self) -> None:
        raise AssertionError("failed open cannot close an unopened radio")


@pytest.mark.parametrize("receiver_id", [None, 0, 1])
def test_capture_publishes_only_after_receipt_and_iq_are_closed(tmp_path, receiver_id) -> None:
    if receiver_id is None:
        plan = compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000)
    else:
        from leo.scanner.models import scheduled_low_band_targets
        from leo.scanner.persistent_hop import PersistentHopProfileV1
        from leo.scanner.single_rx import SingleRxPersistentHopPlanV2

        plan = SingleRxPersistentHopPlanV2(
            receiver_ids=(receiver_id,),
            transition_guard_samples=10_000,
            profiles=tuple(
                PersistentHopProfileV1(target_index=i, fastlock_profile_index=i, target=target)
                for i, target in enumerate(scheduled_low_band_targets(bandwidth_hz=5_000_000))
            ),
        )
    source = FakePersistentHopRadio()
    source.open()
    source_session = source.begin_session(plan, session_id="stored-session")
    block = source_session.read_visit()
    source_session.request_cancel()
    receipt = source_session.finish()
    source.close()
    radio = _OneVisitRadio(source, _OneVisitSession(plan, block, receipt))
    store = PersistentHopIqStore(tmp_path / "bulk")

    published = capture_persistent_hop_to_store(
        radio,
        plan,
        session_id="stored-session",
        store=store,
        cancel=Event(),
        queue_capacity_visits=2,
    )

    assert published.manifest.receipt == receipt
    assert published.manifest.schema_version == (2 if receiver_id is None else 3)
    assert published.manifest.timing.session_id == receipt.session_id
    assert (
        published.manifest.timing.session_start_device_sample_counter
        == receipt.session_start_device_sample_counter
    )
    assert published.manifest.timing.qualified
    assert published.manifest.total_sample_count == plan.valid_visit_samples
    assert published.manifest.queue_telemetry is not None
    reopened = store.verify(published.session_id)
    assert reopened.manifest == published.manifest
    reader = store.valid_ci16_reader(reopened)
    assert reader.receiver_ids == plan.receiver_ids
    assert reader.read_valid_ci16(0, 10).shape == (10, len(plan.receiver_ids), 2)
    if receiver_id is not None:
        assert store.page(cursor=0, limit=20).total == 0
        history = store.page(cursor=0, limit=20, include_single_rx=True)
        assert history.items[0].receiver_ids == (receiver_id,)
        assert history.items[0].sample_rate_hz == 10_000_000
    assert published.manifest.queue_telemetry.enqueue_failure_count == 0
    assert store.inspect("stored-session").manifest_sha256 == published.manifest_sha256
    assert radio.opened is False


def test_aborted_spool_is_forensic_but_does_not_block_a_retry(tmp_path) -> None:
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000)
    identity = FakePersistentHopRadio().identity
    store = PersistentHopIqStore(tmp_path / "bulk")

    for _attempt in range(2):
        with pytest.raises(RuntimeError, match="provider admission"):
            capture_persistent_hop_to_store(
                _FailingRadio(identity),
                plan,
                session_id="retryable-session",
                store=store,
                cancel=Event(),
                queue_capacity_visits=2,
            )

    assert len(tuple(store.spool_root.glob("retryable-session.*.partial"))) == 2
