from pathlib import Path
import sys
from types import SimpleNamespace
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_synthetic_precision import measurement_noise,add_noise


def scan_fixture():
    return SimpleNamespace(tracks=[dict(values=np.zeros(2),observation_ids=['a','b']),
        dict(values=np.zeros(2),observation_ids=['b','c'])],radio_sigma_hz=80.,
        fixed_window_noise=dict(extra_parameter_BIC_gain=1.,per_observation_noise_sigma_hz={'a':40.,'b':60.,'c':80.}))


def test_common_normal_draws_are_preserved_and_shared_ids_are_identical():
    scan=scan_fixture()
    sigma,base=measurement_noise(scan,[0,1],1.,17)
    low_sigma,low=measurement_noise(scan,[0,1],.1,17)
    for key in sigma:
        assert low_sigma[key]==sigma[key]*.1
        assert low[key]/low_sigma[key]==pytest.approx(base[key]/sigma[key])
    add_noise(scan,[0,1],low)
    assert scan.tracks[0]['values'][1]==scan.tracks[1]['values'][0]
    assert scan.fixed_window_noise['per_observation_noise_sigma_hz']=={'a':40.,'b':60.,'c':80.}


def test_one_hz_floor_is_explicit_in_both_generation_and_declared_noise():
    scan=scan_fixture(); sigma,noise=measurement_noise(scan,[0,1],.001,17)
    assert set(sigma.values())=={1.}
    np.testing.assert_array_equal([noise[k] for k in sorted(noise)],np.random.default_rng(17).normal(size=3))


@pytest.mark.parametrize('value',[0.,-1.,2.,np.nan])
def test_invalid_precision_hypotheses_fail(value):
    with pytest.raises(ValueError): measurement_noise(scan_fixture(),[0,1],value,17)
