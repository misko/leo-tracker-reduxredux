import numpy as np

from ds23_supported_curvature import curvature_evidence
from localize_merged_track_catalogue import raw_curvature


def test_short_but_strong_distributed_curvature_can_pass_the_duration_ablation():
    t=np.linspace(0,14,25);rng=np.random.default_rng(12)
    track=dict(times=t,values=30*(t-7)**2+50*t+rng.normal(0,20,len(t)))
    assert not raw_curvature(track)
    r=curvature_evidence(track)
    assert r['qualified'] and r['minimum_linear_RMS_hz']>250


def test_a_single_point_cannot_supply_the_curvature_evidence():
    t=np.linspace(0,14,25);rng=np.random.default_rng(13);y=100*t+rng.normal(0,20,len(t));y[0]+=10000
    assert not curvature_evidence(dict(times=t,values=y))['qualified']


def test_a_clean_line_and_too_short_curve_are_not_curved_calibration():
    t=np.linspace(0,14,25)
    assert not curvature_evidence(dict(times=t,values=200*t))['qualified']
    assert not curvature_evidence(dict(times=t/2,values=300*t*t))['qualified']
