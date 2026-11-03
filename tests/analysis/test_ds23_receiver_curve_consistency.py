import numpy as np
import pytest

from ds23_receiver_curve_consistency import shared_shape


def tracks(different=False):
    rng=np.random.default_rng(20);result=[]
    for k in [0,1]:
        t=np.linspace(0,30,50)+k*.05;q=1.+.05*k
        curve=4*t*t+.02*t**3+(8*t*t if different and k else 0)
        y=q*(curve+1000*k+30*k*t+rng.normal(0,8,len(t)))
        result.append(dict(times=t,values=y,receiver=2,rf_hz=q*11.5e9,observation_ids=[f'{k}-{i}' for i in range(len(t))]))
    return result


def test_shared_curvature_accepts_arbitrary_frequency_scale_offset_and_linear_drift():
    result=shared_shape(tracks())
    assert result['independent_active_curvature_gain']>100
    assert result['BIC_shared_minus_independent']<10


def test_inconsistent_curvature_is_visible_after_affine_terms_have_been_removed():
    result=shared_shape(tracks(True))
    assert result['BIC_shared_minus_independent']>100


def test_curvature_diagnostic_is_invariant_to_native_alias_and_linear_offsets():
    pair=tracks(True);before=shared_shape(pair)
    for k,t in enumerate(pair):t['values']=t['values']+(k+1)*227272.727+25*t['times']
    after=shared_shape(pair)
    assert after['BIC_shared_minus_independent']==pytest.approx(before['BIC_shared_minus_independent'],abs=1e-6)


def test_receiver_or_physical_id_mismatch_is_rejected():
    pair=tracks();pair[1]['receiver']=1
    with pytest.raises(ValueError,match='same receiver'):shared_shape(pair)
    pair=tracks();pair[1]['observation_ids']=pair[0]['observation_ids']
    with pytest.raises(ValueError,match='reuse'):shared_shape(pair,overlap_only=False)
