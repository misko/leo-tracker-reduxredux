"""Skip finished work without weakening validation of work that will be consumed."""

import importlib

import pytest


@pytest.mark.parametrize("version", [3, 4, 5, 6])
@pytest.mark.parametrize("state", [None, "running", "complete", "failed", "unavailable"])
def test_pending_discovery_matches_legacy_eligibility_and_validates_consumed_inputs(
    tmp_path, monkeypatch, version, state
):
    previous_version = version - 1
    previous_module = importlib.import_module(
        f"leo.storage.fast_graph_position_v{previous_version}"
        + ("_export" if previous_version > 2 else "")
    )
    previous_class = getattr(
        previous_module,
        f"FastGraphPositionStoreV{previous_version}" + ("Export" if previous_version > 2 else ""),
    )
    previous = previous_class(tmp_path)
    current_module = importlib.import_module(f"leo.storage.fast_graph_position_v{version}")
    current = getattr(current_module, f"FastGraphPositionStoreV{version}")(
        tmp_path, incumbent=previous
    )
    source = dict(
        job_id="source",
        model_version=previous_module.MODEL_VERSION,
        input_sha256="sha256:fixed-input",
        input_path="input.json",
        run_id="run",
        session_id="session",
        source_job={},
        fast_acquisition={},
        baseline_terminal_sha256="sha256:baseline",
        incumbent_terminal_sha256="sha256:incumbent",
    )
    previous.update(source, state="complete")
    calls = []

    def validate(job):
        calls.append(job["job_id"])
        return dict(state="complete", session_id="session"), {"sha256": "sha256:terminal"}

    monkeypatch.setattr(previous, "terminal", validate)
    job = current.job(source)
    if state is not None:
        current.update(job, state=state)
    legacy = []
    for candidate in current.inputs(minimum_completed_utc_ns=1):
        status = current.status(candidate["job_id"])
        if status is None or status["state"] == "running":
            legacy.append(candidate)
    calls.clear()
    optimized = list(current.inputs(minimum_completed_utc_ns=1, pending_only=True))
    assert optimized == legacy
    if state in (None, "running"):
        assert calls  # Included work retains full validation.

        def corrupt(_):
            raise ValueError("upstream evidence changed")

        monkeypatch.setattr(previous, "terminal", corrupt)
        assert list(current.inputs(minimum_completed_utc_ns=1, pending_only=True)) == []
    else:
        assert calls == []  # Already-finished work does not reopen its evidence.
        current.update(job, state="running")
        assert list(current.inputs(minimum_completed_utc_ns=1, pending_only=True)) == [job]
        assert calls  # Retry eligibility is re-read, never permanently cached.


def test_source_status_identity_checked_before_optional_selection(tmp_path, monkeypatch):
    from leo.storage.fast_graph_position_v5_export import FastGraphPositionStoreV5Export

    store = FastGraphPositionStoreV5Export(tmp_path)
    store.update(dict(job_id="source", model_version="wrong-version"), state="complete")
    called = []
    assert (
        list(
            store.completed_inputs(
                minimum_completed_utc_ns=1, include_status=lambda _: called.append(True)
            )
        )
        == []
    )
    assert called == []
