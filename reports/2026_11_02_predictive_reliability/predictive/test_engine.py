from types import SimpleNamespace
import numpy as np
import engine as m


def inventory():
    tracks=[];rows=[];slices=[];times=[];begin=0
    for rx in [1,2]:
        for family in [11,22,33]:
            t=np.arange(300.)+.1;n=len(t)
            tracks.append(dict(times=t,observation_ids=[f'{rx}:{family}:{k}'for k in range(n)],receiver=rx,channel=1 if family==11 else 2))
            rows.append(dict(candidate_norad=family));slices.append(slice(begin,begin+n));begin+=n;times.extend(t)
    return SimpleNamespace(scan=SimpleNamespace(tracks=tracks),members=list(range(len(tracks))),rows=rows,slices=slices,
        flat_times=np.array(times),keep=np.ones(begin,bool))


def test_group_splits_synchronize_all_channels_and_exact_guard():
    p=inventory();a=m.native(p);plans=m.plans(p,11,2026110210)
    assert len(plans)==5
    for part in plans[:3]:
        train=np.isin(a['ids'],part['train_ids']);held=np.isin(a['ids'],part['held_ids']);block=np.floor(a['times']/5).astype(int)
        assert not np.any(train&held)
        assert not np.isin(block[train],part['guard_blocks']).any()
        assert np.array_equal(held[:300],held[-300:])
    assert all(np.array_equal(x['held_ids'],y['held_ids'])for x,y in zip(plans,m.plans(p,11,2026110210)))


def test_transfer_holds_entire_target_receiver_cell_and_keeps_other_calibration():
    p=inventory();a=m.native(p)
    for part in m.plans(p,11,1)[3:]:
        assert part['eligible']
        held=np.isin(a['ids'],part['held_ids']);train=np.isin(a['ids'],part['train_ids'])
        assert np.array_equal(held,(a['family']==11)&(a['receiver']==part['held_receiver']))
        assert np.all(train[(a['receiver']==part['held_receiver'])&(a['family']!=11)])
        assert len(part['other_receiver_calibration_families_by_band']['0'])==2


def test_transfer_support_does_not_borrow_opposite_band_calibration():
    p=inventory()
    for t in p.scan.tracks:
        if ':11:' not in t['observation_ids'][0]:t['channel']=6
    for part in m.plans(p,11,1)[3:]:
        assert not part['eligible']
        assert 'fewer_than2_same_band_overlapping_other_calibration_families'in part['ineligible_reasons']


def test_gamma_predictive_inverse_moment_includes_unseen_prior():
    sigma,meta=m.predictive_noise(np.array([2.,0.]),np.array([0,0,0,1]),np.array([True,True,False,False]))
    # n=2 =>alpha3; beta=alpha/E[tau]=1.5; E[1/tau]=beta/(alpha-1)=.75.
    assert np.allclose(sigma[:3],150*np.sqrt(.75))
    assert np.isclose(sigma[-1],150*np.sqrt(2))
    assert meta['unseen_groups'].tolist()==[1]


def test_normalized_joint_density_matches_dense_covariance():
    rng=np.random.default_rng(31);r=rng.normal(size=15);s=rng.uniform(.4,2,15);u=rng.normal(size=(15,5));cov=np.diag(s*s)+u@u.T
    expected=r@np.linalg.solve(cov,r)+np.linalg.slogdet(cov)[1]+len(r)*np.log(2*np.pi)
    assert np.isclose(m.gaussian(r,s,u)['negative_twice_log_density'],expected)


def test_residual_lag_does_not_bridge_large_held_gaps():
    d=m.residual_diagnostics(np.array([1.,2.,3.,4.]),np.array([0.,1.,20.,21.]),np.zeros(4,int))
    assert d['adjacent_pairs']==2
