import json
from types import SimpleNamespace

import pytest

from leo.acquisition.authority import LocalCaptureAuthority, RadioResource
from tools.run_shared_scan_cycle import run_cycle


@pytest.mark.parametrize("seconds,edges", [(0, ["lower"]), (1801, ["lower"]),
                                         (601, ["lower", "upper", "lower"]), (300, [])])
def test_fast_campaign_bounds_before_radio_access(seconds, edges):
    from tools.record_fast_scan_campaign import required_reserve
    with pytest.raises(ValueError):
        required_reserve(seconds, edges)


def test_fast_single_capture_reserves_space_for_full_payload():
    from tools.record_fast_scan_campaign import required_reserve
    assert required_reserve(300, ["lower"]) == 6_200_000_000


def setup_cycle(tmp_path):
    config = {"serial": "radio", "fast": {"command": ["fast", "{edge}", "{campaign}"]},
              "adaptive": {"command": ["adaptive"]}}
    authority = LocalCaptureAuthority(tmp_path / "control", (
        RadioResource("radio", "serial", "ip:example"),))
    return config, tmp_path / "schedule.json", authority


def test_shared_cycle_serializes_modes_and_alternates_fast_edges(tmp_path):
    config, state, authority = setup_cycle(tmp_path)
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        current = json.loads(state.read_text())
        assert current["finished_utc_ns"] is None and current["failure"] is None
        # A second scheduler cannot acquire the same live radio lease.
        assert run_cycle(config, tmp_path / "other.json", authority)["state"] == "deferred"
        return SimpleNamespace(returncode=0)
    for _ in range(5):
        run_cycle(config, state, authority, run=run)
    assert [(c[0], c[1] if c[0] == "fast" else None) for c in commands] == [
        ("fast", "lower"), ("adaptive", None), ("fast", "upper"),
        ("adaptive", None), ("fast", "lower")]
    assert len({c[2] for c in commands if c[0] == "fast"}) == 3
    assert json.loads(state.read_text())["completed"] == 5


def test_pause_and_backpressure_do_not_advance_or_launch(tmp_path):
    config, state, authority = setup_cycle(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError("must not acquire RF")
    authority.pause(operator_id="test", reason="pause", wait=False)
    assert run_cycle(config, state, authority, run=forbidden)["state"] == "deferred"
    authority.resume(operator_id="test", reason="resume")
    assert run_cycle(config, state, authority, run=forbidden, pending_fast=3)["state"] == "deferred"
    assert not state.exists()


def test_failure_preserves_slot_and_releases_radio(tmp_path):
    config, state, authority = setup_cycle(tmp_path)
    with pytest.raises(RuntimeError, match="exited 1"):
        run_cycle(config, state, authority, run=lambda *a, **k: SimpleNamespace(returncode=1))
    assert json.loads(state.read_text())["completed"] == 0
    assert json.loads(state.read_text())["state"] == "failed"
    result = run_cycle(config, state, authority, run=lambda *a, **k: SimpleNamespace(returncode=0))
    assert result["mode"] == "fast" and result["edge"] == "lower"


def test_pause_during_capture_drains_and_fences_next_claim(tmp_path):
    config, state, authority = setup_cycle(tmp_path)
    def run(*args, **kwargs):
        status = authority.pause(operator_id="test", reason="stop", wait=False)
        assert status.observed_state.value == "pausing"
        return SimpleNamespace(returncode=0)
    assert run_cycle(config, state, authority, run=run)["state"] == "complete"
    assert authority.snapshot().observed_state.value == "paused"
    assert run_cycle(config, state, authority)["state"] == "deferred"


def test_verification_limit_counts_failed_attempts_too(tmp_path):
    config, state, authority = setup_cycle(tmp_path)
    config["maximum_attempts"] = 1
    with pytest.raises(RuntimeError):
        run_cycle(config, state, authority, run=lambda *a, **k: SimpleNamespace(returncode=1))
    result = run_cycle(config, state, authority)
    assert result["reason"] == "bounded verification capture limit reached"
