import numpy as np
from archive_export import select_first
from investigate import random_groups, polynomial_audit
from leo.analysis.research.track_recovery_diagnostics import profile_rate
from leo.analysis.research.retained_track_likelihood import PERIOD


def test_post_selection_never_falls_back_and_is_not_fit_selected():
    records=[dict(norad=1,epoch_utc_ns=90,collected_utc_ns=110,hash='old'),
             dict(norad=1,epoch_utc_ns=105,collected_utc_ns=120,hash='first'),
             dict(norad=1,epoch_utc_ns=115,collected_utc_ns=130,hash='later'),
             dict(norad=2,epoch_utc_ns=90,collected_utc_ns=125,hash='not-post'),
             dict(norad=3,epoch_utc_ns=110,collected_utc_ns=250,hash='outside')]
    assert select_first(records,100,200)=={'1':records[1]}


def test_group_split_is_reproducible_and_guarded():
    t=np.arange(90.)
    tr,he,groups=random_groups(t,42)
    assert np.array_equal(tr,random_groups(t,42)[0])
    assert not np.any(tr&he)
    for g in groups:
        assert not np.any(tr & (t>=g*12-2)&(t<(g+1)*12+2))
    assert tr.sum()>=8 and he.sum()>=4


def test_alias_and_rate_recovered_without_duplicate_samples():
    t=np.arange(100.);pred=3000-120*t-.3*t*t
    y=pred-PERIOD+20+.4*(t-t.mean())
    r=profile_rate(y,pred,t,bias_sigma_hz=1000,rate_sigma_hz_s=2.)
    assert r['alias'][0]==1
    assert abs(r['rate_hz_s'][0]-.4)<.03
    assert r['residual_hz'].shape==(1,len(t))


def test_polynomial_does_not_bend_to_isolated_endpoint():
    t=np.arange(50.);y=500-100*t;y[-1]+=4000
    r=polynomial_audit(t,y)
    assert r['robust_orders'][0]['degree']==1
    assert r['robust_orders'][0]['inlier_probabilities'][-1]<.01
