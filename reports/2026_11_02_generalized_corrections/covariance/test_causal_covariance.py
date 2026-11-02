"""Component-owned numerical/provenance checks for the report-local prototype."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from causal_covariance import (POLICY,_phase_states,element_sha,shrunk_covariance,
    tle_epoch,transform_mode_bank,validate_and_select)

LINES=['1 60148U 24120P   26302.50005787  .00033666  00000-0  10921-2 0  9992',
       '2 60148  53.1593 302.0362 0001439  74.6408 174.9013 15.31689158  5804']


def history_fixture():
    epoch=tle_epoch(LINES)
    cutoff=epoch+int(24*3.6e12)
    nominal=dict(lines=LINES,provenance=dict(collected_utc_ns=cutoff-1,
        element_epoch_utc_ns=epoch,snapshot_digest='sha256:'+'a'*64))
    raw=dict(cutoff_utc_ns=cutoff,origin_utc_ns=cutoff+1,sources=[dict(collected_utc_ns=cutoff-1,sha256='a'*64)],past_versions={'60148':[]})
    return raw,nominal,cutoff


def test_dense_normalized_gaussian_equivalence():
    from dsx01_joint_marginal import integrated_gaussian
    rng=np.random.default_rng(41027)
    y=rng.normal(size=11);u=rng.normal(size=(11,3));sigma=np.linspace(.4,1.2,11)
    c,_=shrunk_covariance(rng.normal(size=(8,3))*3)
    transformed=u@np.linalg.cholesky(c)
    result=integrated_gaussian(y,transformed,sigma)
    dense=np.diag(sigma**2)+u@c@u.T
    expected=y@np.linalg.solve(dense,y)+np.linalg.slogdet(dense)[1]-2*np.log(sigma).sum()
    assert result['quadratic']+result['logvolume']==pytest.approx(expected,abs=2e-12)


def test_shrinkage_psd_floor_cap_and_no_false_precision():
    assert np.allclose(shrunk_covariance(np.zeros((3,3)))[0],np.eye(3))
    a=np.array([[100.,2.,3.],[-20.,5.,6.],[7.,-8.,9.]])
    c,info=shrunk_covariance(a)
    eig=np.linalg.eigvalsh(c)
    assert np.min(eig)>=1-1e-10 and np.max(eig)<=16+1e-10
    # Repeating the same correlated history never increases its precision.
    assert np.allclose(c,shrunk_covariance(np.repeat(a,30,axis=0))[0])
    assert np.allclose(c,c.T)
    assert info['eigenvalue_clipped_count']>0


def test_mode_transform_orientation_and_unrelated_modes_unchanged():
    rng=np.random.default_rng(19)
    bank=dict(time_s=np.arange(5.),position_km=rng.normal(size=(9,5,3)),velocity_km_s=rng.normal(size=(9,5,3)))
    before={k:v.copy() for k,v in bank.items()}
    c=np.array([[4.,1.,0.],[1.,2.,.2],[0.,.2,1.5]])
    changed=transform_mode_bank(bank,1,c)
    for key in ['position_km','velocity_km_s']:
        assert np.array_equal(bank[key],before[key])
        assert np.array_equal(changed[key][[0,1,2,6,7,8]],bank[key][[0,1,2,6,7,8]])
        original=bank[key][3:6].reshape(3,-1).T
        altered=changed[key][3:6].reshape(3,-1).T
        assert np.allclose(altered@altered.T,original@c@original.T)


def test_epoch_only_does_not_prove_availability():
    raw,nominal,cutoff=history_fixture()
    raw['past_versions']['60148']=[dict(lines=LINES,epoch=tle_epoch(LINES),collected_utc_ns=cutoff+1,snapshot_sha256='a'*64)]
    with pytest.raises(ValueError,match='post-cutoff'):
        validate_and_select(raw,nominal,cutoff,cutoff+1,60148)


def test_source_receipt_binds_collection_and_digest():
    raw,nominal,cutoff=history_fixture()
    nominal['provenance']['snapshot_digest']='sha256:'+'b'*64
    with pytest.raises(ValueError,match='source ledger'):
        validate_and_select(raw,nominal,cutoff,cutoff+1,60148)


def test_duplicate_snapshot_earlier_collection_proves_availability():
    raw,nominal,cutoff=history_fixture()
    raw['sources'][0]['collected_utc_ns']-=int(2*3.6e12)
    rows,info=validate_and_select(raw,nominal,cutoff,cutoff+1,60148)
    assert info['nominal_snapshot_first_verified_collection_utc_ns']<info['nominal_collected_utc_ns']
    assert rows==[]


def test_tle_identity_not_just_dictionary_key():
    raw,nominal,cutoff=history_fixture()
    with pytest.raises(ValueError,match='satellite number'):
        validate_and_select(raw,nominal,cutoff,cutoff+1,60149)
    historical=copy.deepcopy(nominal['lines'])
    historical[0]=historical[0].replace('60148','60149')
    historical[1]=historical[1].replace('60148','60149')
    raw['past_versions']['60148']=[dict(lines=historical,epoch=tle_epoch(historical),collected_utc_ns=cutoff-1,snapshot_sha256='a'*64)]
    with pytest.raises(ValueError,match='satellite number'):
        validate_and_select(raw,nominal,cutoff,cutoff+1,60148)


def test_phase_state_rotation_matches_engine_convention():
    from analyze_dsx01_fixed_site import ecef_states
    from sgp4.api import Satrec
    from leo.sky.propagation import ElementSetCatalogue
    from leo.analysis.research.orbit_phase_geometry import phase_shifted_states
    sat=Satrec.twoline2rv(*LINES);origin=tle_epoch(LINES)+int(5*3.6e12)
    knots=np.arange(-10.,321.)
    cat=ElementSetCatalogue(('60148',),(60148,),(sat,))
    p,v,valid=ecef_states(cat,origin,knots)
    assert valid.all()
    times=np.array([0.,150.,300.]);phase=2.
    expected=phase_shifted_states(dict(time_s=knots,position_km=p,velocity_km_s=v),times,phase)
    actual=_phase_states(sat,origin,times,phase)
    for a,b in zip(actual,expected):assert np.allclose(a,b[0],atol=1e-10,rtol=0)


def test_insufficient_history_is_explicit():
    raw,nominal,cutoff=history_fixture()
    rows,info=validate_and_select(raw,nominal,cutoff,cutoff+1,60148)
    assert rows==[] and 'insufficient' in info['unsupported_reason']


def test_fallback_context_is_exact_same_object():
    from causal_covariance import candidate_context
    d=dict(scan=SimpleNamespace(norads=np.array([60148])),problems={'fitted_c':(SimpleNamespace(labels=[0],supported=[]),np.zeros(2))})
    changed,receipt=candidate_context(d,{},dict(selected_family=60148))
    assert changed is d and not receipt['applied'] and receipt['status']=='fallback'
