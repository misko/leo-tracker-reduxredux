from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3.position import NormalPosition
from leo.analysis.localization_v3.region import SearchRegion
from tools.pipeline_eval.variants.algo08_cold_start import ARRAYS, ColdStarts, cold_model_key


def fixture(scan):
    problem = NormalPosition.__new__(NormalPosition)
    problem.scan = scan
    for name in ARRAYS:
        setattr(problem, name, np.zeros(2))
    problem.keep = np.array([True, True])
    bank = dict(time_s=np.zeros(2), position_km=np.zeros((2, 2, 3)),
                velocity_km_s=np.zeros((2, 2, 3)))
    problem.sky = bank
    problem.mode_bank = {k: v.copy() for k, v in bank.items()}
    problem.members = [0, 1]
    problem.labels = [0, 1]
    problem.supported = [1]
    problem.supported_local = [1]
    problem.alias = [0, 1]
    problem.fitted_c = False
    problem.sigma = 150.
    problem.noise_volume = 2.0
    problem.variant = "radio_noise"
    return problem


@pytest.mark.parametrize("changed", (
    "mask", "alias", "phase", "width", "prior", "region", "layout", "provider", "signed_center",
))
def test_exact_cold_start_uses_only_ranked_center_and_complete_model(changed, monkeypatch):
    scan = SimpleNamespace(
        search_region=SearchRegion((34., 19.)), origin_utc_ns=1,
        previous_tle_sha256="prior", previous_tle="catalogue", bound=object(),
    )
    ranked, refit = fixture(scan), fixture(scan)
    calls = []

    def residual(model, x):
        calls.append((model, tuple(x)))
        return np.array(x) + 3.

    monkeypatch.setattr(NormalPosition, "residual", residual)
    cache = ColdStarts(True)
    cache.record(ranked)
    key = cold_model_key(ranked)
    assert key is not None
    initial = np.zeros(2)
    if changed == "mask":
        refit.keep[0] = False
    elif changed == "alias":
        refit.alias[0] += 1
    elif changed == "phase":
        refit.reference[0] = 2.
    elif changed == "width":
        refit.phase_sigma[1] = 1.
    elif changed == "prior":
        scan.previous_tle_sha256 = "different"
    elif changed == "region":
        scan.search_region = SearchRegion((20., 48.))
    elif changed == "layout":
        refit.hardware[0] = 2.
    elif changed == "provider":
        scan.bound = object()
    elif changed == "signed_center":
        initial[0] = -0.

    def fit(evaluate, start, lower, upper):
        return evaluate(start), evaluate(np.array([0.001, 0.]))

    cache.stage = "initial_refit"
    cache.optimize(fit, refit.residual, initial, [-12.5, -12.5], [12.5, 12.5])
    assert cache.counts["start_hits"] == 0
    assert len(calls) == 3


def test_exact_contiguous_model_skips_only_first_residual(monkeypatch):
    scan = SimpleNamespace(
        search_region=SearchRegion((34., 19.)), origin_utc_ns=1,
        previous_tle_sha256="prior", previous_tle="catalogue", bound=object(),
    )
    ranked, refit = fixture(scan), fixture(scan)
    calls = []

    def residual(model, x):
        calls.append((model, tuple(x)))
        return np.array(x) + 3

    monkeypatch.setattr(NormalPosition, "residual", residual)
    cache = ColdStarts(True)
    cache.record(ranked)
    cache.stage = "initial_refit"

    def fit(evaluate, start, lower, upper):
        assert evaluate(start).tolist() == [3., 3.]
        assert evaluate(start).tolist() == [3., 3.]

    cache.optimize(fit, refit.residual, np.zeros(2), [-12.5, -12.5], [12.5, 12.5])
    assert cache.counts["start_hits"] == 1
    assert [model for model, _ in calls] == [ranked, refit]
