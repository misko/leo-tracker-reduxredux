from contextlib import contextmanager

import pytest

import ds30_0280_moment_position_extended as extended


def test_extended_admission_checks_original_event_and_new_retry(monkeypatch):
    checked = []
    def verify(event, pid):
        checked.append((event, pid))
        assert extended.capsule.TIMEOUT == 21
    monkeypatch.setattr(extended, "BASE_LIVE", verify)
    monkeypatch.setattr(extended.capsule, "TIMEOUT", 40)
    event = {"unix_ns": 100}
    extended.fresh_window(event, 7, 99)
    with pytest.raises(ValueError, match="has not retried"):
        extended.fresh_window(event, 7, 100)
    assert checked == [(event, 7), (event, 7)]
    assert extended.capsule.TIMEOUT == 40


def test_observed_lease_records_release_on_child_failure(monkeypatch):
    released = False

    @contextmanager
    def lease():
        nonlocal released
        try:
            yield 29
        finally:
            released = True

    def stamp():
        return 20 if released else 10

    monkeypatch.setattr(extended, "time_ns", stamp)
    monkeypatch.setattr(extended, "BASE_LEASE", lease)
    reads = {}
    with pytest.raises(RuntimeError, match="child"):
        with extended.observed_lease(reads) as fd:
            assert fd == 29
            assert reads == {"acquired_ns": 10}
            raise RuntimeError("child failure")
    assert reads == {"acquired_ns": 10, "released_ns": 20}


def test_retry_events_only_for_the_exact_lease_window(tmp_path):
    events = tmp_path/"cases/DS30-0001/events"
    events.mkdir(parents=True)
    for stamp, state in [(8, "deferred_shared_lease"), (14, "deferred_shared_lease"),
                         (25, "deferred_storage_busy"), (30, "deferred_shared_lease")]:
        extended.saved.write(events/f"{stamp:020d}-a.json", {"state": state})
    result = extended.retry_readout(tmp_path, {"case": "DS30-0001"},
        {"acquired_ns": 10, "released_ns": 20})
    assert [row["unix_ns"] for row in result["retries_deferred_by_shared_lease"]] == [14]
    assert result["next_official_event"]["unix_ns"] == 25
