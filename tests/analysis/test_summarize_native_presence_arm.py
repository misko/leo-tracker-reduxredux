import json

import pytest

from tools.summarize_native_presence_arm import summarize, verify_replay


def fixture():
    inputs = [
        {
            "file": "a.probe",
            "sha256": "a" * 64,
            "device_counter": str(10**16 + 19),
            "rate_hz": 2500000,
            "edge": "lower",
        }
    ]
    candidate = {"epoch": 12, "fractional_complete": 1, "margin": 0.3}
    row = {
        "schema": "native-presence-replay-profile-v1",
        "iteration": 0,
        "format": 2,
        "device_counter": inputs[0]["device_counter"],
        "rate_hz": 2500000,
        "edge": 0,
        "candidates": [candidate],
        "total_cpu_ms": 40,
        "total_wall_ms": 42,
    }
    desktop = [{"probe": "a.probe", "variant": "test", "result": row}]
    raw = "a" * 64 + "  /tmp/a.probe\n" + json.dumps(row) + "\n"
    raw += json.dumps({**row, "iteration": 1}) + "\n"
    return raw, inputs, desktop


def test_complete_replay_and_timing_summary():
    raw, inputs, desktop = fixture()
    rows = verify_replay(raw, inputs, desktop, "test", 2, 2)
    assert len(rows) == 2
    assert summarize(rows)["2500000"]["warmed"]["total_wall_ms"]["max"] == 42


@pytest.mark.parametrize(
    "replacement",
    [
        ("a" * 64, "b" * 64),
        ('"iteration": 1', '"iteration": 0'),
        ('"format": 2', '"format": 1'),
        ('"margin": 0.3', '"margin": 0.2'),
        ('"margin": 0.3', '"margin": NaN'),
        ('"edge": 0', '"edge": 1'),
        ('"total_cpu_ms": 40', '"total_cpu_ms": -1'),
    ],
)
def test_rejects_changed_or_untrustworthy_results(replacement):
    raw, inputs, desktop = fixture()
    with pytest.raises(ValueError):
        verify_replay(raw.replace(*replacement), inputs, desktop, "test", 2, 2)


def test_rejects_partial_or_unbound_replay():
    raw, inputs, desktop = fixture()
    for lines in (raw.splitlines()[:-1], raw.splitlines()[1:]):
        with pytest.raises(ValueError):
            verify_replay("\n".join(lines), inputs, desktop, "test", 2, 2)


def nuisance_fixture():
    _, inputs, desktop = fixture()
    row = desktop[0]["result"]
    row["schema"] = "native-presence-nuisance-replay-v1"
    row["nuisance"] = {
        "enabled": 1,
        "applied": 1,
        "frequency_hz": -73123,
        "spectral_fraction": 0.3,
        "fitted_power_fraction": 0.2,
        "cpu_ms": 10,
    }
    raw = "a" * 64 + "  /tmp/a.probe\n" + json.dumps(row) + "\n"
    raw += json.dumps({**row, "iteration": 1}) + "\n"
    return raw, inputs, desktop


def test_nuisance_parity_allows_only_execution_time_to_differ():
    raw, inputs, desktop = nuisance_fixture()
    rows = verify_replay(raw.replace('"cpu_ms": 10', '"cpu_ms": 15'), inputs, desktop, "test", 2, 2)
    assert len(rows) == 2


@pytest.mark.parametrize(
    "replacement",
    [
        ('"cpu_ms": 10', '"cpu_ms": NaN'),
        ('"cpu_ms": 10', '"cpu_ms": -1'),
        ('"applied": 1', '"applied": 0'),
        ('"frequency_hz": -73123', '"frequency_hz": -73120'),
        ('"fitted_power_fraction": 0.2', '"fitted_power_fraction": 0.3'),
    ],
)
def test_rejects_changed_nuisance_or_invalid_duration(replacement):
    raw, inputs, desktop = nuisance_fixture()
    with pytest.raises(ValueError):
        verify_replay(raw.replace(*replacement), inputs, desktop, "test", 2, 2)
