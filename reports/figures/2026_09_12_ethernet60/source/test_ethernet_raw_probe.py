import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "ethernet_raw_probe", Path(__file__).parents[1] / "tools" / "ethernet_raw_probe.py"
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_counter_cadence_handles_one_boundary_crossing():
    advance, rate = probe.counter_cadence((1 << 32) - 20, 80, 0.5, 200)
    assert advance == 100
    assert rate == 200


@pytest.mark.parametrize("elapsed", [0, -1, (1 << 32) / 60_000_000])
def test_refuses_ambiguous_counter_brackets(elapsed):
    with pytest.raises(ValueError):
        probe.counter_cadence(0, 100, elapsed, 60_000_000)
