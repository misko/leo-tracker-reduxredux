import numpy as np
import pytest
from cross_curve_residual_witnesses import rate,summarize


def track(name,sat,rx,ch,slope,rf=11.5e9,t=None):
    t=np.arange(0.,41.,2.) if t is None else np.asarray(t)
    return dict(component=name,norad=sat,receiver=rx,channel=ch,rf_hz=rf,times_s=t,residual_hz=30+slope*(t-t.mean()))


def test_witnesses_exclude_target_family_and_balance_duplicate_channels():
    rows=[track('target',1,1,8,4),track('sibling',1,1,7,100),track('a',2,1,7,2),
        track('a2',2,1,8,2),track('b',3,1,1,6),track('other',4,2,8,100),track('short',5,1,8,100,t=[1,2,3,4])]
    r=summarize(rows,'target');g=next(x for x in r['groups'] if x['group']=='same_receiver' and x['scaling']=='hz')
    assert g['distinct_families']==2 and g['witness_curves']==3
    assert g['predicted_target_rate_hz_s']==pytest.approx(4)
    assert g['target_RMS_after_hz']==pytest.approx(30)
    band=next(x for x in r['groups'] if x['group']=='same_receiver_band' and x['scaling']=='hz')
    assert band['predicted_target_rate_hz_s']==pytest.approx(2)
    assert not r['independent_predictive_validation'] and not r['acceptance_authorized']


def test_fractional_rate_scaling_and_missing_witnesses_are_explicit():
    rows=[track('target',1,1,8,4,rf=23e9),track('a',2,1,7,2)]
    r=summarize(rows,'target');g=next(x for x in r['groups'] if x['group']=='same_receiver' and x['scaling']=='fractional')
    assert g['predicted_target_rate_hz_s']==pytest.approx(4)
    absent=next(x for x in r['groups'] if x['group']=='same_satellite_other_curve')
    assert absent['witness_curves']==0 and absent['target_noise_after'] is None
    assert rate(rows[0]['times_s'],rows[0]['residual_hz'])['affine_RMS_hz']<1e-10
