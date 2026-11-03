from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_same_probe_covariance import disjoint_peak_paths,residual_pair,compare_paths


def scene(common=True,image=False):
    t=np.arange(80,dtype=float);rng=np.random.default_rng(1703)
    shared=rng.normal(0,70,len(t));e1=rng.normal(0,5,len(t));e2=rng.normal(0,5,len(t))
    a=2*t*t+500*t+10000+shared+e1
    b=(-t*t+700*t+80000 if not image else 1.1*(2*t*t+500*t+10000)+50000)
    b=b+(shared if common else rng.normal(0,70,len(t)))+e2
    fields=dict(lane=[1,2,10.9e9],times=t,probes=list(range(len(t))),degree=2)
    return dict(fields,key='one',values=a,epochs=np.ones(len(t))*100),dict(fields,key='two',values=b,epochs=np.ones(len(t))*400)


def test_peak_ownership_allows_simultaneous_distinct_paths():
    models=[dict(indices=[0,2,4],gain=10),dict(indices=[1,3,5],gain=9),dict(indices=[2,6],gain=8)]
    assert disjoint_peak_paths(models)==models[:2]


def test_shared_noise_is_visible_in_different_curved_paths():
    one,two=scene();r=compare_paths(one,two,2500000.,seed=31)
    assert all(r['geometry_checks'].values())
    assert r['correlation']>.98 and r['difference_sigma_hz']<10
    assert r['shuffled_correlation_rank']<.01
    assert min(r['interleaved_residual_correlations'])>.98


def test_independent_noise_does_not_pass_common_error_claim():
    one,two=scene(common=False);r=compare_paths(one,two,2500000.)
    assert not r['checks']['positive_covariance']
    assert not r['common_noise_candidate']


def test_affine_frequency_images_cannot_calibrate_common_error():
    one,two=scene(image=True);r=compare_paths(one,two,2500000.)
    assert not r['geometry_checks']['not_affine_frequency_image']
    assert not r['common_noise_candidate']


def test_same_epoch_components_are_not_counted_as_independent_emitters():
    one,two=scene();two['epochs']=one['epochs'];r=compare_paths(one,two,2500000.)
    assert not r['geometry_checks']['distinct_epoch']


def test_residual_projection_preserves_known_common_component():
    t=np.arange(40,dtype=float);a=np.random.default_rng(17).normal(size=40)
    r=residual_pair(t,t*t+a,-t*t+a,2)
    assert r['correlation']==pytest.approx(1.)
    assert r['difference_sigma_hz']<1e-10
