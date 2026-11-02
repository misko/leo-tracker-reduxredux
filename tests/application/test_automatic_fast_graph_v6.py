from contextlib import contextmanager

import pytest

from leo.application.automatic_fast_graph_v6 import process


class Store:
    def __init__(self, path):
        self.folder = path
        self.saved = None
        self.verified = False
        self.terminal_value = dict(state="complete", decision="ALGO06_fallback")

    @contextmanager
    def owner(self, _):
        yield True

    def path(self, _):
        return self.folder

    def status(self, _):
        return self.saved

    def verify_input(self, _):
        self.verified = True

    def update(self, job, **changes):
        self.saved = dict(job, **changes)
        return self.saved

    def terminal(self, _):
        return self.terminal_value, dict(sha256="receipt")


@pytest.mark.parametrize("decision", ["ALGO07_reassociation", "ALGO06_fallback"])
def test_bounded_attempt_publishes_terminal_once(tmp_path, decision):
    store = Store(tmp_path)
    store.terminal_value["decision"] = decision
    job = dict(job_id="new", source_job=dict(job_id="old"))
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs["timeout"]))
        return 0

    result = process(job, store=store, command=["worker"], maximum_seconds=20, runner=run)
    assert result["result"]["decision"] == decision
    assert store.verified
    assert calls == [
        (["worker", "--job", "old", "--output", str(tmp_path / "output"),
          "--maximum-seconds", "20"], 35)
    ]
    assert process(job, store=store, command=["worker"], runner=run) == result
    assert len(calls) == 1


def test_interrupted_attempt_recovers_validated_terminal_without_rerun(tmp_path):
    store = Store(tmp_path)
    job = dict(job_id="new", source_job=dict(job_id="old"))
    store.saved = dict(job, state="running")

    def forbidden(*args, **kwargs):
        raise AssertionError("Interrupted numerical attempt cannot run again")

    assert process(job, store=store, command=["worker"], runner=forbidden)["state"] == "complete"


def test_contradictory_worker_exit_fails_closed(tmp_path):
    store = Store(tmp_path)
    with pytest.raises(ValueError, match="exit status contradicts"):
        process(dict(job_id="new", source_job=dict(job_id="old")), store=store,
                command=["worker"], runner=lambda *args, **kwargs: 1)
    assert store.saved["state"] == "failed"


@pytest.mark.parametrize("budget", [0, 1201, True, 1.5])
def test_bad_budget_rejected(tmp_path, budget):
    with pytest.raises(ValueError):
        process({}, store=Store(tmp_path), command=["worker"], maximum_seconds=budget)
