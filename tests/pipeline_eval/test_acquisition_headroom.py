import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from acquisition_headroom import report, wall_budget


def test_negative_wait_allowance_exposes_a_cpu_floor():
    assert wall_budget(100, 20, 6, 10) == dict(
        target_wall_s=5, wait_allowance_s=-1,
        required_cpu_saving_at_observed_wait_s=5, observed_non_cpu_s=4,
    )
    with pytest.raises(ValueError):
        wall_budget(100, 20, 6, 5)


def test_repair_charge_increases_both_rates_on_each_enrolled_panel():
    for scenarios in report()["panels"].values():
        for base, charged in zip(scenarios[::2], scenarios[1::2], strict=True):
            assert base["required_MB_s"] == max(base["rates_MB_s"])
            assert charged["required_MB_s"] == max(charged["rates_MB_s"])
            assert all(a < b for a, b in zip(base["rates_MB_s"], charged["rates_MB_s"], strict=True))
