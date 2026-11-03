from pathlib import Path
import sys
from types import SimpleNamespace
import copy
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from probe_ds23_synthetic_noise import perturb_tracks


def fixture():
    return SimpleNamespace(tracks=[dict(values=np.zeros(2),observation_ids=['a','b']),dict(values=np.zeros(2),observation_ids=['b','c'])],
        fixed_window_noise=dict(extra_parameter_BIC_gain=1.,per_observation_noise_sigma_hz={'a':10.,'b':20.,'c':30.}),radio_sigma_hz=50.)


def test_same_physical_observation_reuses_noise_and_seed_is_reproducible():
    one=fixture();two=fixture();perturb_tracks(one,[0,1],17);perturb_tracks(two,[0,1],17)
    assert one.tracks[0]['values'][1]==one.tracks[1]['values'][0]
    for a,b in zip(one.tracks,two.tracks):np.testing.assert_array_equal(a['values'],b['values'])


def test_missing_or_invalid_declared_noise_is_not_silently_replaced():
    scan=fixture();scan.fixed_window_noise['per_observation_noise_sigma_hz']['a']=-1
    with pytest.raises(ValueError):perturb_tracks(scan,[0],17)
    scan=fixture();del scan.fixed_window_noise['per_observation_noise_sigma_hz']['a']
    with pytest.raises(KeyError):perturb_tracks(scan,[0],17)
