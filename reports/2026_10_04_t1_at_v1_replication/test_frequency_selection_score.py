import numpy as np
import pytest
from frequency_associations import FrequencySearch,compile_mode
from regularized_associations import TimingSearch


def records(number,offset,rows,error):
    rows=list(rows)
    return dict(catalog_number=number,offset_s=offset,eligible_rows=rows,residual_hz=[error]*len(rows))


def fixture():
    raw=[records(10,0.,range(100),0.),records(20,6.14,range(100,170),88.),records(30,-3.77,range(100,170),156.)]
    g=np.arange(170);t=g*.6
    modes=[compile_mode(m,np.zeros(len(g),int),np.ones(len(g),int)) for m in raw]
    return modes,g,t


def test_zero_frequency_weight_exactly_reproduces_timing_only():
    args=fixture();old=TimingSearch(*args).run(3);new=FrequencySearch(*args,frequency_weight=0.).run(3)
    for stage in ('initial','final'):
        for k in ('objective','assigned','satellites','assignments','selected'):assert old[stage][k]==new[stage][k]
    assert old['passes']==new['passes']


def test_frequency_evidence_can_overrule_smaller_timing_shift():
    args=fixture();old=TimingSearch(*args).run(3);new=FrequencySearch(*args).run(3)
    assert {s['catalog_number'] for s in old['final']['selected']}=={10,30}
    assert {s['catalog_number'] for s in new['final']['selected']}=={10,20}
    r=new['final']
    assert r['frequency_cost']==pytest.approx(.5*70*(88/200)**2)
    assert r['objective']==pytest.approx(r['assigned']-10*r['satellites']-r['timing_prior_nll']-r['frequency_cost'])


def test_invalid_weight_or_sigma_rejected():
    for options in ({'frequency_weight':-1},{'sigma_hz':0},{'sigma_hz':float('nan')}):
        with pytest.raises(ValueError):FrequencySearch(*fixture(),**options)
