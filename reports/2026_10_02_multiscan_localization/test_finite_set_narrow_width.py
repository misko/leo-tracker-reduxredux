from types import SimpleNamespace

import numpy as np
import pytest
from finite_set_narrow_width import fit_width_branches


def inputs():
    data = SimpleNamespace(times=np.arange(2.), measured=np.arange(2.), group=np.arange(2),
                           rf=np.ones(2), receiver=np.array([0, 1]), channel=np.ones(2))
    source = {"full_bank": [0, 1], "trials": [
        {"satellite_indices": [0], "parameters": np.zeros(8), "objective": -1000.},
    ]}
    return data, source


def test_width_recomputes_objective_and_preserves_model_settings():
    data, source = inputs()
    calls = []

    def refiner(data, parameters, satellites, weights, likelihood, **options):
        assert likelihood.detection_probability == 0.4
        assert options == dict(sigma_hz=82., tau_sigma_s=1., tau_bound_s=3.,
                               slope_bound=50., budget_s=15.)
        calls.append(options)
        return {"initial_objective": 100. if len(calls) == 1 else 80.,
                "objective": 90. if len(calls) == 1 else 70.,
                "selection_score": 90. if len(calls) == 1 else 70.,
                "success": True, "parameters": parameters.copy()}

    def profiler(data, parameters, satellites, prepared, **options):
        assert options["sigma_hz"] == 82.
        assert options["tau_sigma_s"] == 1.
        assert options["step_s"] == .05
        assert options["detection_probability"] == .4
        return {"initial_objective": 90., "objective": 80.,
                "parameters": parameters.copy(), "complete": False}

    result = fit_width_branches(data, source, cavity_factory=None,
                                refiner=refiner, profiler=profiler)
    assert result["trials"][0]["objective"] == 70.
    assert result["local_refinements_resolved"]
    assert not result["selection"]["selection_resolved"]
    assert source["trials"][0]["objective"] == -1000.


def test_width_profile_must_reproduce_new_objective():
    data, source = inputs()

    def refiner(*args, **options):
        return {"initial_objective": 100., "objective": 90., "parameters": np.zeros(8)}

    def profiler(*args, **options):
        return {"initial_objective": 91.}

    with pytest.raises(ValueError, match="reproduce narrow-width"):
        fit_width_branches(data, source, cavity_factory=None,
                           refiner=refiner, profiler=profiler)


def test_width_refinement_cannot_discard_initial_incumbent():
    data, source = inputs()

    def refiner(*args, **options):
        return {"initial_objective": 100., "objective": 101.}

    with pytest.raises(ValueError, match="lost its starting incumbent"):
        fit_width_branches(data, source, cavity_factory=None, refiner=refiner)
