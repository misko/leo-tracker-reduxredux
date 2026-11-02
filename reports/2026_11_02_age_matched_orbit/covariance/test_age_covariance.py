import hashlib
import numpy as np
import pytest
from age_covariance import POLICY,base,physical_bank,project_pair,select_pairs

LINES=['1 60148U 24120P   26302.50005787  .00033666  00000-0  10921-2 0  9992',
       '2 60148  53.1593 302.0362 0001439  74.6408 174.9013 15.31689158  5804']


def fake_history(monkeypatch,hours,collections=None):
    monkeypatch.setattr(base,'validate_and_select',lambda *a:([],{}))
    monkeypatch.setattr(base,'tle_epoch',lambda lines:int(lines[0]))
    monkeypatch.setattr(base,'element_sha',lambda lines:hashlib.sha256(str(lines).encode()).hexdigest())
    rows=[dict(epoch=round(h*3.6e12),collected_utc_ns=round(c*3.6e12),lines=[str(round(h*3.6e12))],snapshot_sha256='a'*64)
          for h,c in zip(hours,hours if collections is None else collections)]
    return dict(past_versions={'60148':rows}),dict(lines=[str(round(100*3.6e12))])


def test_maximum_matching_not_greedy(monkeypatch):
    raw,nominal=fake_history(monkeypatch,[80,81,82,83])
    monkeypatch.setitem(POLICY,'horizon_tolerance_hours',.01);monkeypatch.setitem(POLICY,'horizon_relative_tolerance',0.)
    pairs,info=select_pairs(raw,nominal,int(100*3.6e12),int(100*3.6e12),60148,1.)
    assert info['pair_count']==2
    assert [(p['older']['epoch'],p['newer']['epoch']) for p in pairs]==[(int(80*3.6e12),int(81*3.6e12)),(int(82*3.6e12),int(83*3.6e12))]


def test_minimum_mismatch_then_stable_tie(monkeypatch):
    raw,nominal=fake_history(monkeypatch,[80,81,82,83])
    pairs,info=select_pairs(raw,nominal,int(100*3.6e12),int(100*3.6e12),60148,2.)
    assert info['pair_count']==2 and sum(p['absolute_horizon_error_hours'] for p in pairs)==0
    assert len({p[k]['epoch'] for p in pairs for k in ['older','newer']})==4


def test_actual_forecast_requires_older_availability_by_target(monkeypatch):
    raw,nominal=fake_history(monkeypatch,[80,81],[82,83])
    args=(raw,nominal,int(100*3.6e12),int(100*3.6e12),60148,1.)
    assert select_pairs(*args)[1]['pair_count']==0
    assert select_pairs(*args,require_forecast=False)[1]['pair_count']==1


def test_horizon_tolerance_is_fixed_and_chronology_not_nominal_epoch_only(monkeypatch):
    raw,nominal=fake_history(monkeypatch,[80,83,88,89])
    pairs,info=select_pairs(raw,nominal,int(100*3.6e12),int(100*3.6e12),60148,20.)
    assert not pairs and info['horizon_tolerance_hours']==5


def test_physical_revision_recovery_and_SD_coordinate_transport():
    from sgp4.api import Satrec
    from sgp4.exporter import export_tle
    from fit_s01_69333_tle_parameter import perturb
    newer=Satrec.twoline2rv(*LINES)
    physical=np.array([.0001,.002,-.003])
    older=newer
    for parameter,delta in zip(['mean_motion_rev_day','inclination_deg','raan_deg'],physical):older=perturb(older,parameter,delta)
    epoch=base.tle_epoch(LINES)
    pair=dict(older=dict(lines=list(export_tle(older)),epoch=epoch,collected_utc_ns=epoch,snapshot_sha256='a'*64),
        newer=dict(lines=LINES,epoch=epoch,collected_utc_ns=epoch,snapshot_sha256='b'*64),horizon_hours=1.,absolute_horizon_error_hours=0.)
    scales=np.array([.001,.01,.01])
    a,receipt=project_pair(pair,300.,scales)
    doubled,second=project_pair(pair,300.,2*scales)
    assert np.allclose(a*scales,physical,atol=2e-6,rtol=.01)
    assert np.allclose(a,2*doubled,atol=1e-10)
    assert receipt['alignment_converged'] and receipt['historical_derivative_anchor_utc_ns']==epoch
    assert np.allclose(receipt['physical_parameter_revision'],second['physical_parameter_revision'],atol=1e-12)
    assert min(receipt['column_normalized_singular_values'])>1e-3


def test_physical_derivative_phase_anchor_changes_only_removed_phase_to_first_order():
    from sgp4.api import Satrec
    sat=Satrec.twoline2rv(*LINES);epoch=base.tle_epoch(LINES);times=np.array([-150.,0.,150.])
    scales=[.001,.01,.01]
    central=physical_bank(sat,epoch,times,0.,scales)
    changed=physical_bank(sat,epoch,times,150.,scales)
    # The i and RAAN physical directions never inherit the mean-motion gauge.
    for key in ['position_km','velocity_km_s']:assert np.array_equal(central[key][1:],changed[key][1:])
    assert np.max(abs(central['position_km'][0]-changed['position_km'][0]))>0


def test_Gaussian_normalization_and_covariance_floor_retained():
    from dsx01_joint_marginal import integrated_gaussian
    rng=np.random.default_rng(61102);u=rng.normal(size=(9,3));y=rng.normal(size=9)
    c,receipt=base.shrunk_covariance(rng.normal(size=(3,3))*5)
    answer=integrated_gaussian(y,u@np.linalg.cholesky(c),1.)
    dense=np.eye(9)+u@c@u.T
    assert answer['quadratic']+answer['logvolume']==pytest.approx(y@np.linalg.solve(dense,y)+np.linalg.slogdet(dense)[1],abs=1e-10)
    assert min(receipt['bounded_eigenvalues'])>=1 and max(receipt['bounded_eigenvalues'])<=16
