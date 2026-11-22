from hashlib import sha256
from pathlib import Path
import runpy
from types import SimpleNamespace

import numpy as np

from leo.analysis.localization_v3 import orbit_modes
from leo.analysis.localization_v3.orbits import ecef_states
from leo.sky.propagation import parse_element_sets
from tests.operations.test_causal_tle_catalogue import at_day
from tools.pipeline_eval.variants import algo08_nominal_angular_bank as overlay


def example(day):
    nominal = at_day(232.6)
    cat = parse_element_sets(nominal)
    origin = int(cat.element_epoch_utc_ns()[0])
    times = np.arange(-17., 318.)
    p, v, ok = ecef_states(cat, origin, times)
    assert ok.all()
    previous = at_day(day)
    number, = cat.satellite_numbers
    return SimpleNamespace(origin_utc_ns=origin, norads=np.array([number]),
        sky=dict(time_s=times, position_km=p, velocity_km_s=v),
        elements={str(number): {"lines": nominal.splitlines()[1:]}},
        previous_tle=previous, previous_tle_sha256=sha256(previous.encode()).hexdigest())


def test_nominal_states_are_reused_across_previous_contexts_but_modes_stay_exact():
    previous_days = [232.45, 232.55]
    exact = [orbit_modes.build_modes(example(day), [0], [0], "physical") for day in previous_days]
    with overlay.nominal_angular_bank(enabled=True) as counts:
        shared = [orbit_modes.build_modes(example(day), [0], [0], "physical") for day in previous_days]
    assert counts["hits"] == 1 and counts["other_prior_hits"] == 1
    assert exact[0][1] != exact[1][1]
    for (ours, metadata), (stock, expected_metadata) in zip(shared, exact, strict=True):
        assert metadata == expected_metadata
        for key in stock:
            assert ours[key].tobytes() == stock[key].tobytes()


def test_state_cache_key_changes_with_elements_epoch_and_grid():
    model = example(232.5)
    other = example(232.4)
    original = overlay.nominal_key(model, 0)
    assert overlay.nominal_key(other, 0) == original
    other.origin_utc_ns += 1
    assert overlay.nominal_key(other, 0) != original
    other.origin_utc_ns -= 1
    other.sky["time_s"][0] += .1
    assert overlay.nominal_key(other, 0) != original
    other.sky["time_s"] = model.sky["time_s"].copy()
    number = str(int(other.norads[0]))
    other.elements[number]["lines"] = at_day(232.61).splitlines()[1:]
    assert overlay.nominal_key(other, 0) != original


def test_numeric_prefix_keys_preserve_signed_zero_shape_and_kwarg_order():
    trial = Path(__file__).resolve().parents[2] / "reports/ALGO08/single-core-2x/solver_initial_prefix_trial.py"
    digest = runpy.run_path(str(trial))["numeric_digest"]
    values = np.array([0., 2.])
    assert digest((values,), {"a": False, "b": None}) == digest((values.copy(),), {"b": None, "a": False})
    assert digest((values,), {}) != digest((values[None],), {})
    assert digest((values,), {}) != digest((np.array([-0., 2.]),), {})
    assert digest((0.,), {}) != digest((-0.,), {})
