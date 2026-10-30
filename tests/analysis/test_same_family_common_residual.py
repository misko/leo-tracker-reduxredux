import numpy as np
import pytest
from audit_same_family_common_residual import common_screen
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen


def fixture():
    rng=np.random.default_rng(2);t=np.arange(40.);z=np.linspace(-1,1,40);tracks=[];diags=[]
    for k in range(2):
        times=t+.2*k;r=180*(z*z-np.mean(z*z))+rng.normal(0,70,40)
        tracks.append(dict(receiver=1,rf_hz=11.5e9,times=times,observation_ids=[f'{k}-{i}' for i in range(40)]))
        diags.append(dict(times_s=times,raw_residual_hz=r,profile_bias_hz=0))
    return tracks,diags


def test_shared_curve_can_fail_even_when_both_members_pass():
    tracks,diags=fixture()
    assert all(batch_noise_screen(d['raw_residual_hz'][None],d['times_s'])['noise_screen_pass'][0] for d in diags)
    pooled=common_screen(diags,tracks)
    assert all(not r['passed'] and r['noise']['quadratic_bic_gain']>10 for r in pooled)


def test_common_audit_rejects_duplicate_points_and_mixed_receivers():
    tracks,diags=fixture();tracks[1]['observation_ids'][0]=tracks[0]['observation_ids'][0]
    with pytest.raises(ValueError,match='duplicate'):common_screen(diags,tracks)
    tracks,diags=fixture();tracks[1]['receiver']=2
    with pytest.raises(ValueError,match='one receiver'):common_screen(diags,tracks)
