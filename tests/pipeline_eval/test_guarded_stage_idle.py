import fcntl
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
import guarded_cfo_0016_stage as stage
from guarded_stage_idle import IdleAdmission, IdleWindowExpired, Load, QuietInterval
from guarded_stage_checkpoint import Extent, verified_extents


class Clock:
    def __init__(self):
        self.time = 0.

    def now(self):
        return self.time

    def wait(self, seconds):
        self.time += seconds


def state(when, *, pressure=2., queued=0, weighted=0, full_us=0):
    return Load(when, pressure, full_us, queued, weighted)


def test_needs_one_quiet_second_and_rejects_both_instantaneous_signals():
    gate = QuietInterval()
    assert not gate.observe(state(0, pressure=20.))
    assert not gate.observe(state(1, queued=3))
    assert not gate.observe(state(2))
    assert not gate.observe(state(2.75))
    assert gate.observe(state(3))
    assert not gate.observe(state(3.001, queued=3))
    assert not gate.observe(state(3.002))


@pytest.mark.parametrize("spike", [{"weighted": 750}, {"full_us": 100_000}])
def test_queue_and_pressure_deltas_restart_the_quiet_interval(spike):
    gate = QuietInterval()
    assert not gate.observe(state(0))
    assert not gate.observe(state(.25, **spike))
    assert not gate.observe(state(1, **spike))
    assert gate.observe(state(1.25, **spike))


def test_gate_rechecks_after_taking_the_lock_and_yields_it_between_waits(tmp_path):
    clock = Clock()
    named = tmp_path / "gauss"
    named.touch()
    events = []
    checked_under_lock = []

    def owns_slot():
        with named.open("rb") as independent:
            try:
                fcntl.flock(independent, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
        return False

    def observe(device, now):
        del device
        if owns_slot():
            checked_under_lock.append(now())
            if len(checked_under_lock) == 1:
                return state(now(), queued=4)
        return state(now())

    def wait(seconds):
        assert not owns_slot()
        clock.wait(seconds)

    gate = IdleAdmission(named, 5., lambda **event: events.append(event),
                         now=clock.now, wait=wait, observe=observe)
    with named.open("rb") as lock, gate.slot(lock):
        assert owns_slot()
    assert not owns_slot()
    assert checked_under_lock == [1., 2.25]
    assert [entry["event"] for entry in events] == ["idle_wait", "idle_admitted"]
    assert gate.reads == 1


def test_gauss_busy_leaves_original_unopened_until_deadline(tmp_path):
    named = tmp_path / "gauss"
    named.touch()
    clock = Clock()
    gate = IdleAdmission(named, 3., lambda **event: None, now=clock.now, wait=clock.wait,
                         observe=lambda device, now: state(now()))
    original = tmp_path / "missing-source"
    output, journal = tmp_path / "staged", tmp_path / "checkpoint"
    with named.open("rb") as independent, named.open("rb") as lock:
        fcntl.flock(independent, fcntl.LOCK_EX)
        with pytest.raises(IdleWindowExpired):
            stage.copy_member(original, output, 4, sha256(b"data").hexdigest(), lock,
                              SimpleNamespace(), journal=journal, admission=gate)
    assert not output.exists() and not journal.exists()
    assert gate.reads == 0


def test_busy_storage_times_out_with_no_member_or_checkpoint_mutation(tmp_path):
    named = tmp_path / "gauss"
    named.touch()
    clock = Clock()
    gate = IdleAdmission(named, 3., lambda **event: None, now=clock.now, wait=clock.wait,
                         observe=lambda device, now: state(now(), pressure=37., queued=100))
    original = tmp_path / "missing-source"
    output, journal = tmp_path / "staged", tmp_path / "checkpoint"
    with named.open("rb") as lock, pytest.raises(IdleWindowExpired):
        stage.copy_member(original, output, 4, sha256(b"data").hexdigest(), lock,
                          SimpleNamespace(), journal=journal, admission=gate)
    assert not output.exists() and not journal.exists()
    assert gate.reads == 0


def test_between_read_pressure_preserves_the_newly_sealed_prefix(tmp_path, monkeypatch):
    named = tmp_path / "gauss"
    named.touch()
    clock = Clock()
    stage_root = tmp_path / "staged"
    (stage_root / "segment").mkdir(parents=True)
    original = tmp_path / "source"
    original.write_bytes(b"abcdefgh")
    extent = Extent(Path("segment/payload"), 8, "sha256:" + sha256(b"abcdefgh").hexdigest())
    output = stage_root / extent.relative
    journal = stage_root / "checkpoint"
    paid = []
    gate = IdleAdmission(named, 5., lambda **event: None, now=clock.now, wait=clock.wait,
                         observe=lambda device, now: state(now(), queued=7 if paid else 0))
    monkeypatch.setattr(stage, "BLOCK", 3)
    monkeypatch.setattr(stage, "sleep", clock.wait)
    with named.open("rb") as lock, pytest.raises(IdleWindowExpired):
        stage.copy_member(original, output, extent.size, extent.sha256, lock,
                          SimpleNamespace(progress=lambda _, n: paid.append(n)), journal=journal, admission=gate)
    assert paid == [3] and gate.reads == 1
    completed, partial = verified_extents(stage_root, [extent], json.loads(journal.read_text()))
    assert not completed and partial.offset == 3
    assert output.read_bytes() == b"abc"
