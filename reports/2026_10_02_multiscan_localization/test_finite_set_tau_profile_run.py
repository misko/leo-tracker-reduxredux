from types import SimpleNamespace

import numpy as np
import pytest
from finite_set_tau_profile_run import fit_profile_branches


def test_profile_branch_keeps_frozen_mass_priors_and_marks_incomplete_search():
    data = SimpleNamespace(times=np.arange(2.), measured=np.arange(2.), group=np.arange(2),
                           rf=np.ones(2), receiver=np.array([0, 1]), channel=np.ones(2))
    calls = []

    def profiler(data, parameters, satellites, prepared, **options):
        calls.append(options)
        return {"parameters": np.zeros(8), "initial_objective": 10.,
                "objective": 9., "complete": len(satellites) == 1}

    def refiner(data, parameters, satellites, weights, likelihood, **options):
        assert likelihood.detection_probability == 0.4
        return {"initial_objective": 9., "objective": 8., "selection_score": 9.,
                "success": True, "parameters": parameters}

    source = {"full_bank": [0, 1], "trials": [
        {"satellite_indices": [0], "parameters": np.zeros(8), "objective": 10.},
        {"satellite_indices": [0, 1], "parameters": np.zeros(8), "objective": 10.},
    ]}
    fitted = fit_profile_branches(data, source, cavity_factory=None,
                                 profiler=profiler, refiner=refiner)
    assert len(fitted["trials"]) == 2
    assert fitted["local_refinements_resolved"]
    assert not fitted["selection"]["selection_resolved"]
    assert not fitted["all_timing_profiles_complete"]
    assert calls[0]["tau_sigma_s"] == 1.
    assert calls[0]["tau_bound_s"] == 3.
    assert calls[0]["step_s"] == 0.1
    assert source["trials"][0]["objective"] == 10.


def test_profile_source_reproduction_is_required():
    data = SimpleNamespace(times=np.arange(2.), measured=np.arange(2.), group=np.arange(2),
                           rf=np.ones(2), receiver=np.array([0, 1]), channel=np.ones(2))

    def profiler(*args, **options):
        return {"initial_objective": 11.}

    with pytest.raises(ValueError, match="reproduce sealed"):
        fit_profile_branches(data, {
            "full_bank": [0], "trials": [{"satellite_indices": [0],
                                          "parameters": np.zeros(7), "objective": 10.}],
        }, cavity_factory=None, profiler=profiler)
