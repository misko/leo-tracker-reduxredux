"""Prepared scalar synthetic tests; no recording/optimizer/integration trial."""
import math

import pytest
from scipy.special import ndtr

from adaptive import ENVELOPE, integrate, log_gap


def zero_seams(left, right):
    return -math.inf


def test_affine_target_and_all_support_one_call():
    row=integrate(lambda x:(2+3*x,3),-1,2,h_bound=0,u_bound=0,seam_bound=zero_seams)
    exact=2+math.log((math.exp(6)-math.exp(-3))/3)
    assert row['status']=='target_met' and row['actual_calls']==1
    assert row['full_support_covered'] and row['bounds']['log_lower']<=exact<=row['bounds']['log_upper']


def test_gaussian_full_interval_and_deterministic_repeat():
    options=dict(h_bound=1,u_bound=-1,seam_bound=zero_seams,target_log_width=.01)
    callback=lambda x:(-.5*x*x,-x)
    first=integrate(callback,-3,3,**options)
    second=integrate(callback,-3,3,**options)
    assert first==second and first['target_met']
    exact=.5*math.log(2*math.pi)+math.log(ndtr(3)-ndtr(-3))
    assert first['bounds']['log_lower']<=exact<=first['bounds']['log_upper']
    assert first['actual_calls']==len(first['ledger'])==1+2*len(first['splits'])


def test_budget_includes_discarded_parents_and_coordinate_ties():
    row=integrate(lambda x:(0.,0.),-1,1,h_bound=1,u_bound=1,
                  seam_bound=zero_seams,target_log_width=1e-12,maximum_calls=6)
    assert row['status']=='budget_exhausted' and row['actual_calls']==5
    assert row['full_support_covered'] and len(row['active_partition_ids'])==3
    assert row['splits'][1]['parent']==1  # Equal children: left coordinate first.
    assert len(row['ledger'])==5 and 0 not in row['active_partition_ids']


def test_failed_child_preserves_parent_support_and_consumed_call():
    calls=[]
    def callback(x):
        calls.append(x)
        if len(calls)==3:raise ValueError('synthetic failure')
        return 0.,0.
    row=integrate(callback,-1,1,h_bound=1,u_bound=1,seam_bound=zero_seams)
    assert row['status']=='callback_failed' and row['actual_calls']==3
    assert row['active_partition_ids']==[0] and row['full_support_covered']
    assert row['splits'][0]['accepted'] is False and row['ledger'][2]['error']


def test_remote_narrow_mode_cannot_be_declared_resolved_from_midpoint():
    sigma,peak,clutter,mu=.05,100.,.01,3.
    def callback(x):
        s=peak*math.exp(-.5*((mu-x)/sigma)**2)
        return math.log(clutter+s)-.5e-12*x*x,s/(clutter+s)*(mu-x)/sigma**2-1e-12*x
    h,u=ENVELOPE.curvature_bounds([1.],[peak/clutter],sigma,1e-12)
    row=integrate(callback,-5,5,h_bound=h,u_bound=u,seam_bound=zero_seams,maximum_calls=3)
    exact_upper=math.log(10*clutter+peak*sigma*math.sqrt(2*math.pi)*(ndtr((5-mu)/sigma)-ndtr((-5-mu)/sigma)))
    assert row['status']=='budget_exhausted' and row['full_support_covered']
    assert row['bounds']['log_upper']>=exact_upper
    assert row['bounds']['log_lower']<=exact_upper-.5e-12*25


def test_seam_bound_is_requested_for_every_sampled_cell():
    calls=[]
    def seams(left,right):
        calls.append((left,right));return math.log(2)
    row=integrate(lambda x:(abs(x),1. if x>=0 else -1.),-1,1,
                  h_bound=0,u_bound=0,seam_bound=seams,maximum_calls=3)
    assert len(calls)==row['actual_calls']==3
    assert row['bounds']['log_upper']>=math.log(2*(math.e-1))


@pytest.mark.parametrize('limits',[dict(maximum_calls=513),dict(maximum_calls=True),dict(target_log_width=0),dict(h_bound=-1)])
def test_invalid_budget_or_bounds_precede_calls(limits):
    args=dict(h_bound=1,u_bound=1,seam_bound=zero_seams);args.update(limits)
    with pytest.raises(ValueError):integrate(lambda x:pytest.fail('called'),-1,1,**args)


def test_stable_gap_handles_small_and_large_log_mass():
    assert log_gap(-10000,-9999)==pytest.approx(log_gap(10000,10001)-20000)
    assert log_gap(1,1)==-math.inf


@pytest.mark.parametrize('bad', [math.nan, math.inf, -math.inf])
def test_nonfinite_root_cannot_report_coverage_or_success(bad):
    row=integrate(lambda x:(bad,0.),-1,1,h_bound=1,u_bound=1,seam_bound=zero_seams)
    assert row['status']=='callback_failed' and row['actual_calls']==1
    assert not row['target_met'] and not row['full_support_covered']
    assert row['bounds'] is None
