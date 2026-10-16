"""Production extraction against the immutable research numerical oracle."""

import importlib.util
from pathlib import Path

import model_a_detectability_cohort_port as oracle
import numpy as np
import pytest

from leo.analysis import shared_scan_model as module
from leo.analysis.channel_group_calibration import GroupCalibrationObjective

spec = importlib.util.spec_from_file_location(
    "shared_scan_public_fixture",
    Path(__file__).parents[1] / "tools/model_a_folded_propensity_compatibility_test.py",
)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
actual_case, family = fixture.actual_case, fixture.family


@pytest.mark.parametrize("view", ["all", "low", "high"])
@pytest.mark.parametrize("nonzero", [False, True])
def test_exact_research_objective_full_gradients_posteriors_and_prior(family, view, nonzero):
    raw, v, n, shift = family
    mask = oracle.mask_for(raw, view)
    model = module.SharedScanObjective(raw, shift, mask)
    expected = oracle.ViewModel(raw, shift, "shared", view)
    tail = np.zeros(model.observation_parameter_count)
    if nonzero:
        tail = 0.13 * np.cos(np.arange(len(tail)))
    nuisance = np.r_[n, tail]
    a, details = model.evaluate_details(v, nuisance)
    b, original_details = expected.evaluate_details(v, nuisance)
    for k in range(3):
        np.testing.assert_array_equal(a[k], b[k])
    np.testing.assert_array_equal(a[3].responsibilities, b[3].responsibilities)
    assert details["prior_penalty"] == original_details["prior_penalty"]
    assert details["fixed_contrast_prior"] == pytest.approx(
        0.5 * np.sum(np.asarray(shift.offsets_hz) ** 2) / 50000**2
    )
    assert model.original is raw and model.clock_count == raw.clock_count


def test_donor_transport_exact_every_native_row_and_original_prior(family):
    raw, v, n, _ = family
    joint = GroupCalibrationObjective(raw.base, raw.observations.channel >= 5)
    delta = np.array([-12700.0, 24800.0])
    donor = dict(vector=v, nuisance=np.r_[n, delta])
    target, shift, moved, clock, error = module.donor_state(joint, donor)
    np.testing.assert_allclose(
        target.correction(moved, clock),
        joint.correction(v, donor["nuisance"]),
        atol=1e-9,
        rtol=0,
    )
    np.testing.assert_array_equal(moved[7:], v[7:])
    model = module.SharedScanObjective(target, shift)
    assert error < 1e-8
    assert model.fixed_contrast_prior_penalty == pytest.approx(
        0.5 * delta @ joint.group_precision @ delta
    )


def test_real_native_fitter_uses_shared_density_and_independent_audit(family):
    raw, v, n, shift = family
    model = module.SharedScanObjective(raw, shift)
    nuisance = np.r_[n, np.zeros(model.observation_parameter_count)]
    result = module.bounded_fit(model, v, nuisance, local_center=v[:2], fixed_position=True)
    assert result["actual_objective_calls_exact"] and 0 < result["actual_objective_calls"] <= 2000
    assert result["elapsed_seconds"] <= 20
    if result["phase"] == "audited":
        fit = result["fit"]
        expected = oracle.ViewModel(raw, shift, "shared", "all")
        assert expected.evaluate_joint(fit["vector"], fit["nuisance"])[0] == pytest.approx(
            fit["objective"], abs=1e-8
        )
        np.testing.assert_array_equal(fit["vector"][:2], v[:2])
        assert len(fit["observation_parameters"]) == model.observation_parameter_count
        assert result["audit"]["replay_maximum_error"] <= 1e-7


def test_counted_actual_cap_and_own_solver_deadline_allow_audit(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(module.time, "monotonic", lambda: 0.0)
    counted = module.CountedObjective(SimpleNamespace(evaluate_joint=lambda *_: 42), maximum=1)
    assert counted.evaluate_joint(None, None) == 42
    with pytest.raises(TimeoutError):
        counted.evaluate_joint(None, None)
    assert counted.calls == 1


def test_probability_boundaries_are_valid():
    w, derivative = module.horizon_weight(np.linspace(-1e-5, 1e-5, 1_000_001))
    assert w.min() >= 0 and w.max() <= 1 and derivative.min() >= 0
