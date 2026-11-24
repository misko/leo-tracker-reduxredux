from contextlib import contextmanager

import pytest

import joint_recovery_0049_wait as waiter


def test_wait_releases_before_sleep_and_starts_only_one_worker(monkeypatch):
    clock, held, lock_attempts = 0, False, 0
    started = []
    monkeypatch.setattr(waiter, "monotonic", lambda: clock)
    loads = iter((False, True, True, True, False, True, True, True))
    official = iter((False, True, True, True, True, True))

    def sample():
        return next(loads), {"quiet_stats": "sampled"}

    @contextmanager
    def use_lease():
        nonlocal held, lock_attempts
        assert not held
        lock_attempts += 1
        if lock_attempts == 1:
            raise BlockingIOError
        held = True
        try:
            yield 7
        finally:
            held = False

    def pause(until):
        assert not held
        assert clock < until
        nonlocal_clock_advance()

    def nonlocal_clock_advance():
        nonlocal clock
        clock += 1

    def cached():
        assert held
        return {"tle_files": 48}

    def launch(fd, summary):
        assert held and fd == 7
        started.append(summary)
        return {"exit_code": 0}

    done, counts, _ = waiter.wait_for_slot(
        deadline=10, sleep_until=pause, sample=sample, driver_idle=lambda: next(official),
        use_lease=use_lease, cached=cached, launch=launch,
    )
    assert done == {"exit_code": 0}
    assert counts == dict(nonquiet=1, official_busy=1, lease_busy=1, lost_quiet_on_lease=1)
    assert started == [dict(quiet={"quiet_stats": "sampled"}, cache={"tle_files": 48},
                            rejected_polls=dict(counts))]
    assert clock == 4 and lock_attempts == 3 and not held


def test_timeout_never_acquires_a_lease_on_nonquiet_host(monkeypatch):
    clock = 0
    monkeypatch.setattr(waiter, "monotonic", lambda: clock)

    def pause(until):
        nonlocal clock
        clock += 1

    def unavailable(*args):
        pytest.fail("A busy host may only sample and wait")

    done, counts, last = waiter.wait_for_slot(
        deadline=3, sleep_until=pause, sample=lambda: (False, {"busy": True}),
        driver_idle=unavailable, use_lease=unavailable, cached=unavailable, launch=unavailable,
    )
    assert done is None and counts == {"nonquiet": 3} and last == {"busy": True}


def test_error_after_launch_is_not_treated_as_retryable_lock_contention(monkeypatch):
    monkeypatch.setattr(waiter, "monotonic", lambda: 0)
    starts = []

    @contextmanager
    def acquired():
        yield 7

    def launch(fd, summary):
        starts.append(fd)
        raise BlockingIOError("after starting")

    def no_retry(*args):
        pytest.fail("Possible started child must never be retried")

    with pytest.raises(BlockingIOError, match="after starting"):
        waiter.wait_for_slot(
            deadline=2, sleep_until=no_retry, sample=lambda: (True, {}), driver_idle=lambda: True,
            use_lease=acquired, cached=dict, launch=launch,
        )
    assert starts == [7]


def test_resident_native_override_still_requires_exact_signed_bytes(tmp_path):
    import json
    from hashlib import sha256

    import signed_cfo_time_readout as signed

    source = dict(sample_rate_hz=signed.SAMPLE_RATE, probes=[], raw_recording_authority_digest="raw")
    detector = "sha256:"+("8"*64)
    source["analysis_manifest_sha256"] = signed.canonical(
        ["cancellation", "raw", detector[7:], source["probes"]],
    )
    packet = dict(source=source, provenance=dict(detector_sha256=detector))
    resident = tmp_path/"native.json"
    resident.write_text(json.dumps(packet))
    pin = sha256(resident.read_bytes()).hexdigest()
    assert signed.read_native(tmp_path/"absent", pin, path=resident) == packet
    with pytest.raises(ValueError, match="Sealed input differs"):
        signed.read_native(tmp_path/"absent", "0"*64, path=resident)
