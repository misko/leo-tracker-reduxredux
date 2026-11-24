from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from signed_state_ceiling import Census, coordinate, exact, operands


def test_projection_key_allows_only_exact_equivalent_sky_and_phases():
    scan = object()
    census = Census(scan)
    bank = dict(time_s=np.array([0., 1.]), position_km=np.zeros((3, 2, 3)), velocity_km_s=np.ones((3, 2, 3)))
    first = SimpleNamespace(scan=scan, sky=bank, mode_bank=bank, flat_times=np.array([.3, .4]),
                            flat_labels=np.array([0, 2]), reference=np.array([.2, .1, .4]))
    second = SimpleNamespace(**vars(first))
    second.sky = {key: value.copy() for key, value in bank.items()}
    second.reference = np.array([.2, .9, .4])
    point = np.zeros(2)
    assert census.phase_projection(first, point) == census.phase_projection(second, point)
    second.reference[0] = np.nextafter(.2, 1.)
    assert census.phase_projection(first, point) != census.phase_projection(second, point)
    assert census.phase_projection(first, point) != census.phase_projection(first, np.array([0., .001]))
    census.validate()
    second.sky["time_s"][0] = -.01
    with pytest.raises(ValueError, match="modified in place"):
        census.validate()


def test_bytes_and_layout_are_distinct_for_actual_posterior_operands():
    x = np.arange(12., dtype=float).reshape(3, 4)
    np.testing.assert_equal(x, np.asfortranarray(x))
    assert operands(x, powers=np.ones(3)) != operands(np.asfortranarray(x), powers=np.ones(3))
    assert exact(x, layout=False) == exact(np.asfortranarray(x), layout=False)
    assert operands(x, prior_nu=3) != operands(x, prior_nu=4)
    assert coordinate(-0., 1.) != coordinate(0., 1.)


def test_same_refresh_and_cross_arm_donors_are_reported_once():
    census = Census(object())
    census.arm = "c0"
    census.epoch = 0
    run = census.watch("geometry", lambda value: value + 1, lambda value: value)
    assert run(7) == 8
    assert run(7) == 8
    census.epoch = 1
    assert run(7) == 8
    census.arm = "fitted_c"
    assert run(7) == 8
    result = census.scopes()["geometry"]
    assert result["calls"] == 4
    assert result["lookup_cpu_ns"] <= result["key_cpu_ns"]
    assert {key: result[key]["calls"] for key in ("same_refresh", "later_refresh", "across_arms")} == {
        "same_refresh": 1, "later_refresh": 1, "across_arms": 1,
    }
