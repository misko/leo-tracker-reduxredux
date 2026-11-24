import pytest

from leo.analysis.localization_v3.history_policy import ARMS, pair_passes
from reports.ALGO08.v3.early_lean_refusal import fitted_first, gate_record, load


def arm(*, curved=(True,), linear=(True,), endpoint=(12.5, -12.5), phase=0.01):
    return dict(gates={"tracks": [{"compatible": flag} for flag in curved]},
                linear_gates=[{"compatible": flag} for flag in linear],
                endpoint_east_north_km=endpoint, final_phase_change_s=phase)


@pytest.mark.parametrize(("fitted", "include_linear", "reject"), [
    (arm(), True, False),
    (arm(curved=(False,)), True, True),
    (arm(linear=(False,)), True, True),
    (arm(linear=(False,)), False, False),
    (arm(phase=0.01001), True, True),
    (arm(endpoint=(12.500000001, 0.)), True, False),
    (arm(endpoint=(12.500001, 0.)), True, True),
    (arm(endpoint=(float("nan"), 0.)), True, True),
    (arm(curved=(), linear=()), False, True),
])
def test_only_the_completed_fitted_veto_skips_c0(fitted, include_linear, reject):
    original = {"c0": arm(), "fitted_c": fitted}
    calls = []

    def fit(which):
        calls.append(which)
        return original[which]

    options = dict(include_linear=include_linear, half_width_km=12.5)
    records, passes = fitted_first(fit, **options)
    assert passes == pair_passes(original, **options) == (not reject)
    assert calls == (["fitted_c"] if reject else ["fitted_c", "c0"])
    assert records["fitted_c"] is fitted
    if passes:
        assert tuple(records) == ARMS
        assert records["c0"] is original["c0"]


def test_c0_is_still_a_mandatory_gate_after_the_fitted_arm_passes():
    original = {"c0": arm(curved=(False,)), "fitted_c": arm()}
    records, passes = fitted_first(original.__getitem__, include_linear=True, half_width_km=12.5)
    assert records == original
    assert not passes


def test_readout_preserves_inactive_tracks_and_predictive_failures():
    archived = dict(curved_points=0, compatible_curved_points=0, failed_curved=[],
                    linear_points=17, compatible_linear_points=0, failed_linear=["track"],
                    east_north_km=[0, 0], final_phase_change_s=0.)
    record = gate_record(archived)
    assert record["gates"]["tracks"] == []
    assert record["linear_gates"] == [{"compatible": False}]
    archived["failed_linear"].clear()
    with pytest.raises(ValueError, match="Invalid linear gate"):
        gate_record(archived)


def test_replay_rejects_unsealed_inputs(tmp_path):
    trace = tmp_path / "trace.json"
    trace.write_text("{}")
    with pytest.raises(ValueError, match="Unreviewed saved receipt"):
        load(trace, "0" * 64)
