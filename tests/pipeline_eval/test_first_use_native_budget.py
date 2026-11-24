import json

import pytest

from reports.ALGO08.v3.first_use_native_budget import M, budget, partition, scenario


def test_native_calls_are_subtracted_only_from_enclosing_acquisition():
    phases = {key: {"elapsed_s": value} for key, value in (
        ("authenticated_raw_acquisition", 6), ("decision_and_publication", 3))}
    native = dict(native_wall_ns=dict(full=10**9, short_primary=2*10**9), native_calls={})
    row = partition(12, 10, phases, native)
    assert row["other_input_s"] == 3 and row["outside_s"] == 1
    assert scenario([row], short_fraction=.5)["total_s"] == 9
    with pytest.raises(ValueError):
        partition(12, 8, phases, native)


def test_model_meets_both_gates_at_the_reported_input_boundary():
    data = json.loads((M/"first-use-native-budget.json").read_bytes())
    rows = [v for k, v in data["cases"].items() if k.startswith("DS30")]
    result = budget(rows)
    assert result == data["physical"]
    rate = result["joint_required_other_input_speedup"]
    args = dict(short_fraction=.5, publication_fraction=2/3)
    assert scenario(rows, input_fraction=1/rate, **args)["sum_speedup"] == pytest.approx(2.)
    assert scenario(rows, input_fraction=1/(rate-.001), **args)["sum_speedup"] < 2.
    assert result["free_native"]["sum_speedup"] < 2 < result["free_native"]["median_speedup"]
    assert budget([data["cases"]["North"]]) == data["north"]
