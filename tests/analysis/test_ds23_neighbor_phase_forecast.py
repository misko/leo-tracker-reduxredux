from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_neighbor_phase_forecast import features


def row(number, time_s, target):
    return dict(norad=number, validation_time_ns=int(time_s*1e9), next_innovation_s=target,
        predicted_sigma_s=1., unit_forecast_s=0., age_s=1., target_orbit=[53., 10., 15.], available_orbit=[53., 10., 15.])


def test_neighbor_predictor_excludes_own_family_same_batch_and_future_targets():
    model = dict(shrinkage=0., multiplier=1., nu=None)
    past = [row(i, 0, 1.) for i in range(1, 13)]
    query = row(0, 1000, 8.)
    noisy = past+[row(0, 0, -1000.), row(100, 900, -1000.), row(101, 1000, -1000.), row(102, 2000, -1000.)]
    a, _ = features(past, model, {}, [query]); b, _ = features(noisy, model, {}, [query])
    np.testing.assert_allclose(a, np.ones((1, 2)), atol=1e-15)
    np.testing.assert_allclose(a, b, atol=1e-15)


def test_each_neighbor_votes_only_its_latest_causally_available_innovation():
    model = dict(shrinkage=0., multiplier=1., nu=None)
    past = [row(i, 0, -3.) for i in range(1, 13)]+[row(i, 1000, 2.) for i in range(1, 13)]
    result, counts = features(past, model, {}, [row(0, 2000, 0.)])
    np.testing.assert_allclose(result, np.full((1, 2), 2.), atol=1e-15)
    np.testing.assert_allclose(counts, np.full((1, 2), 12.), atol=1e-12)
