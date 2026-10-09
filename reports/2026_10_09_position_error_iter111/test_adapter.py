import runpy
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

api = runpy.run_path(str(Path(__file__).with_name("adapter.py")))


def fixture():
    model = NS(
        size=9,
        initial_clock=np.zeros(5),
        basis=np.array([[1], [-1]]),
        bank=None,
        observations=None,
        prior=None,
        baseline=np.zeros(3),
        design=np.arange(15).reshape(3, 5) / 7,
        clock_design=np.zeros((3, 5)),
        satellite_basis=np.array([[1], [-1]]),
        offset_slice=slice(1, 2),
        slope_slice=slice(2, 3),
        delta_time=np.array([[0, 1], [1, 2], [2, 3]]) / 100,
        precision=np.eye(5),
        score=NS(sigma_hz=125, common_sigma_s=2, relative_sigma_s=2),
    )
    model.clock_design[:, [0, 3, 4]] = np.array([[1, 2, 3], [2, 3, 4], [3, 4, 5]])

    def predictor(bank, observations, prior, point, shifts):
        spatial = np.tile([[1, 2], [3, 4]], (3, 1, 1))
        timing = np.tile(shifts, (3, 1))
        prediction = np.einsum("nki,i->nk", spatial, point) + 0.5 * shifts[None, :] ** 2
        return prediction, np.ones((3, 2), bool), spatial, timing

    model.evaluate_joint = lambda v, c: (
        7,
        None,
        None,
        NS(responsibilities=np.array([[0.3, 0.2], [0.1, 0.6], [0, 0.5]])),
    )
    endpoint = dict(
        vector=np.arange(9) / 10, clock_coefficients=np.arange(5) / 10, objective=7, converged=True
    )
    return model, endpoint, predictor


def test_all_frequency_derivatives_match_finite_difference():
    model, endpoint, predictor = fixture()
    v, c = np.asarray(endpoint["vector"]), np.asarray(endpoint["clock_coefficients"])
    _, jac = api["frequency_design"](model, v, c, predictor=predictor)
    combined = np.r_[v, c]
    for i in range(len(combined)):
        plus, minus = combined.copy(), combined.copy()
        plus[i] += 1e-5
        minus[i] -= 1e-5
        a = api["frequency_design"](model, plus[:9], plus[9:], predictor=predictor)[0]
        b = api["frequency_design"](model, minus[:9], minus[9:], predictor=predictor)[0]
        np.testing.assert_allclose(jac[:, :, i], (a - b) / 2e-5, atol=1e-9)


def test_soft_rows_and_c0_locks():
    model, endpoint, predictor = fixture()
    fitted = api["construct"](model, endpoint, "fitted-c", predictor=predictor)
    assert fitted["spatial"].shape == (6, 2)
    assert fitted["model_parameter_scales"][11] == 100
    np.testing.assert_allclose(
        fitted["full_jacobian"][:, :, 11], model.delta_time * model.satellite_basis[:, 0] * 100
    )
    np.testing.assert_allclose(fitted["weights"], np.array([0.3, 0.2, 0.1, 0.6, 0, 0.5]) / 125**2)
    endpoint["vector"][6] = 0
    endpoint["clock_coefficients"][-2:] = 0
    zero = api["construct"](model, endpoint, "zero-c", predictor=predictor)
    assert zero["locked_parameter_indices"] == [6, 12, 13]
    assert zero["nuisance"].shape[1] == fitted["nuisance"].shape[1] - 3
    np.testing.assert_array_equal(zero["weights"], fitted["weights"])


def test_endpoint_binding_required():
    model, endpoint, predictor = fixture()
    with pytest.raises(ValueError):
        api["construct"](model, endpoint, "zero-c", predictor=predictor)
    endpoint["objective"] = 8
    with pytest.raises(ValueError):
        api["construct"](model, endpoint, "fitted-c", predictor=predictor)


def test_fixed_rf_drift_locks_terms_but_retains_static_c():
    model, endpoint, predictor = fixture()
    model.fixed_rf_drift = True
    with pytest.raises(ValueError):
        api["construct"](model, endpoint, "fitted-c", predictor=predictor)
    endpoint["clock_coefficients"][-2:] = 0
    result = api["construct"](model, endpoint, "fitted-c", predictor=predictor)
    assert result["locked_parameter_indices"] == [12, 13]
    assert 6 in result["nuisance_parameter_indices"]


def test_invalid_responsibility_mass_rejected():
    model, endpoint, predictor = fixture()
    model.evaluate_joint = lambda v, c: (7, None, None, NS(responsibilities=np.full((3, 2), 0.6)))
    with pytest.raises(ValueError, match="responsibilities"):
        api["construct"](model, endpoint, "fitted-c", predictor=predictor)
