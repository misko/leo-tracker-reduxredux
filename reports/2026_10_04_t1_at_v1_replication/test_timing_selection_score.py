import numpy as np
import pytest
from timing_selection_score import timing_cost
from regularized_associations import TimingSearch,Search,compile_mode


def mode(number,offset,rows,errors=None):
    rows=np.asarray(rows)
    return dict(catalog_number=number,offset_s=offset,eligible_rows=rows.tolist(),
                residual_hz=np.zeros(len(rows)).tolist() if errors is None else list(errors))


def run(records,weight=1.):
    groups=np.arange(40);times=np.arange(40)*.6
    modes=[compile_mode(r,np.zeros(40,int),np.ones(40,int)) for r in records]
    return TimingSearch(modes,groups,times,timing_weight=weight).run(3),modes,groups,times


def test_cost_matches_zero_sum_localization_prior():
    timing=np.array([1.,-2.,3.,4.]);mean=timing.mean()
    assert timing_cost(len(timing),timing.sum(),timing@timing)==pytest.approx(.5*sum((timing-mean)**2)+.5*(mean/10)**2)
    assert timing_cost(0,0.,0.)==0
    assert np.isinf(timing_cost(1,11.,121.))
    assert timing_cost(2,4.,8.)==pytest.approx(.02)


def test_zero_weight_reproduces_original_assignments_and_repair():
    records=[mode(1,8.,range(25)),mode(2,0.,range(15)),mode(3,-1.,range(15,40))]
    result,modes,g,t=run(records,0.)
    old=Search(modes,g,t).run(3)
    for stage in ('initial','final'):
        for key in ('assigned','satellites','objective','assignments','selected'):
            assert result[stage][key]==old[stage][key]
    assert result['passes']==old['passes']


def test_main_score_can_choose_lower_count_lower_timing_cost():
    # First common near-zero track anchors the timing gauge. The remaining
    # overlapping alternatives have different relative timing costs.
    records=[mode(10,0.,range(20)),mode(20,8.,range(20,35)),mode(30,0.,range(20,34))]
    old,*_=run(records,0.);new,*_=run(records,1.)
    assert {r['catalog_number'] for r in old['final']['selected']}=={10,20}
    assert {r['catalog_number'] for r in new['final']['selected']}=={10,30}
    assert new['final']['assigned']==34
    assert all(p['objective']>=new['initial']['objective'] for p in new['passes'])


def test_primary_regularizer_can_reject_unpaid_satellite():
    records=[mode(10,0.,range(20)),mode(20,9.,range(20,31))]
    result,*_=run(records,1.)
    assert result['final']['satellites']==1
    assert result['final']['assigned']==20
