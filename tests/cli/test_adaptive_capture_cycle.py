"""Scheduling/identity checks only; these tests never open a radio."""

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def runner():
    path = Path(__file__).resolve().parents[2] / "tools/run_adaptive_capture_cycle.py"
    spec = importlib.util.spec_from_file_location("adaptive_capture_cycle", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seven_minute_slots_advance_across_hour_and_day_boundaries(runner):
    for epoch in (1790467200, 1790470680, 1790553300):
        first = runner.slot_configuration(epoch, "radio")
        second = runner.slot_configuration(epoch + 420, "radio")
        assert second[0] == first[0] + 1


@pytest.mark.parametrize("branch", [0, 1])
@pytest.mark.parametrize("rate_choice", range(2))
def test_rate_probability_preserves_edge_selection(runner, monkeypatch, branch, rate_choice):
    def choice(serial, ordinal, domain, size):
        if domain == "rate-2p5-10-half-v1":
            assert size == 2
            return rate_choice
        assert domain == "edge" and size == 2
        return branch

    monkeypatch.setattr(runner, "deterministic_uniform_choice", choice)
    _, rate, edge, frequencies = runner.slot_configuration(1790467200, "radio")
    assert rate == (2_500_000, 10_000_000)[rate_choice]
    assert edge == ("upper" if branch else "lower")
    expected = runner.FREQUENCIES_10M if rate == 10_000_000 else runner.FREQUENCIES_2P5
    assert frequencies == expected[branch::2]


def test_rate_distribution_across_reproducible_slots(runner):
    count = 12000
    rates = Counter(
        runner.slot_configuration(i * runner.SLOT_SECONDS, "rate-test")[1] for i in range(count)
    )
    assert set(rates) == {2_500_000, 10_000_000}
    assert rates[2_500_000] / count == pytest.approx(0.50, abs=0.015)
    assert rates[10_000_000] / count == pytest.approx(0.50, abs=0.015)


def test_same_slot_activations_cannot_reuse_recording_identity(runner):
    first = runner.campaign_configuration(1790467200, "radio", None, capture_token="one")
    second = runner.campaign_configuration(1790467201, "radio", None, capture_token="two")
    assert first[:4] == second[:4]
    assert first[4] != second[4]
    assert first == runner.campaign_configuration(1790467200, "radio", None, capture_token="one")


@pytest.mark.parametrize("rate", [2_500_000, 10_000_000])
def test_spool_budget_covers_uncompressed_dual_rx(runner, rate):
    assert runner.minimum_capture_free_bytes(rate, 300000) == rate * 300 * 8 + 2 * 1024**3
    with pytest.raises(ValueError):
        runner.minimum_capture_free_bytes(rate, 0)


@pytest.mark.parametrize("rate", [2_500_000, 10_000_000])
def test_rate_override_preserved(runner, rate):
    _, actual, edge, frequencies, _ = runner.campaign_configuration(
        1790467200, "radio", rate, capture_token="test"
    )
    assert actual == rate
    assert frequencies == runner.FREQUENCIES_BY_RATE[rate][0 if edge == "lower" else 1 :: 2]


@pytest.mark.parametrize("rate", [1_250_000, 5_000_000, 7_500_000])
def test_other_rate_overrides_rejected(runner, rate):
    with pytest.raises(ValueError, match="require 2.5 or 10 MS/s"):
        runner.campaign_configuration(1790467200, "radio", rate, capture_token="test")


@pytest.mark.hardware  # Requires the optional acquisition package; never opens RF.
def test_manual_gain_preserved(runner):
    for slot in range(100):
        dwell, gain = runner.slot_capture_settings(1790467200 + slot * 420, "radio")
        assert dwell == 120
        assert gain.value == "manual"


def test_timer_waits_three_minutes_after_completion():
    root = Path(__file__).resolve().parents[2]
    timer = (root / "deploy/systemd/leo-adaptive-seven-minute.timer.conf").read_text()
    assert "OnCalendar=\n" in timer
    assert "OnUnitInactiveSec=\nOnUnitInactiveSec=3min\n" in timer
    assert "RandomizedDelaySec=0\n" in timer


@pytest.mark.hardware  # Requires the deployed acquisition runtime; never opens RF.
@pytest.mark.parametrize("rate", [2_500_000, 10_000_000])
def test_dry_run_keeps_five_minute_dual_receiver_capture(runner, monkeypatch, capsys, tmp_path, rate):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capture",
            "--epoch",
            "1790467200",
            "--sample-rate",
            str(rate),
            "--evidence-root",
            str(tmp_path / "evidence"),
            "--iq-spool-root",
            str(tmp_path / "iq"),
            "--dry-run",
        ],
    )
    assert runner.main() == 0
    resolved = json.loads(capsys.readouterr().out)
    assert resolved["rate_hz"] == rate
    assert resolved["setup"]["source_rate_hz"] == rate
    assert resolved["setup"]["analog_bandwidth_hz"] == rate
    assert resolved["setup"]["protocol_version"] == 3
    assert resolved["setup"]["duration_ms"] == 300_000
    assert resolved["setup"]["rx_mask"] == 3
    assert resolved["gain_mode"] == "manual"
    assert resolved["active_dwell_ms"] == resolved["quiet_dwell_ms"] == 120
    assert resolved["setup"]["dwell_ms"] == 120
    assert not list(tmp_path.iterdir())


@pytest.mark.hardware  # Optional acquisition runtime; the guard prevents all RF access.
def test_full_spool_defers_before_opening_radio(runner, monkeypatch, capsys, tmp_path):
    from types import SimpleNamespace
    monkeypatch.setattr(sys, "argv", [
        "capture", "--evidence-root", str(tmp_path), "--iq-spool-root", str(tmp_path),
    ])
    monkeypatch.setattr(runner.shutil, "disk_usage", lambda path: SimpleNamespace(free=0))
    assert runner.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "deferred_insufficient_spool_space"
    assert result["required_bytes"] > 0
    assert not list(tmp_path.iterdir())
