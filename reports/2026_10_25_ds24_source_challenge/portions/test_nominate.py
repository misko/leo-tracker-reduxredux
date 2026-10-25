"""Owned nomination, native-gauge, marginal-background and eligibility checks."""
import inspect
import numpy as np
import pytest
from scipy.linalg import solve_triangular
from localize_merged_track_catalogue import raw_curvature
import nominate as n


def fixture():
    rng=np.random.default_rng(2026102575);count=18;points=12
    frequency=rng.normal(size=(count,points))*80
    derivative=rng.normal(size=(count,points))*10
    covariance=np.eye(points)*100+np.ones((points,points))*80
    catalogue=dict(norads=np.arange(70000,70000+count),frequency_hz=frequency,derivative_hz_per_s=derivative,
        phase_means_s=np.linspace(-2,2,count),phase_sd_s=np.linspace(.2,2,count),minimum_mean_elevation_deg=np.ones(count))
    raw=frequency[3]+derivative[3]*.2+rng.normal(size=points)
    return raw,covariance,catalogue


def test_actual_both_arm_input_smoke_and_all_frozen_ID_partitions():
    receipt=n.r.read(n.HERE/'load_smoke.json')
    assert receipt['all_passed'] and receipt['ordinary_screens']==0 and receipt['source_sha256']==n.r.sha(n.__file__)
    assert {row['arm'] for row in receipt['checks']}==set(n.ARMS)
    selections=dict(n.selections());assert len(selections)==7
    for cut in n.CUTS:
        prefix,suffix=selections[f'cut{cut}_prefix'],selections[f'cut{cut}_suffix']
        assert not set(prefix)&set(suffix)
        np.testing.assert_array_equal(np.r_[prefix,suffix],np.arange(43))
    cat=n.arrays(n.HERE/'inputs/catalogue.npz')
    assert cat['frequency_hz'].shape==cat['mean_elevation_deg'].shape==(1487,43)
    for arm in n.ARMS:
        obs=n.arrays(n.HERE/'inputs'/(arm+'.npz'))
        assert len(set(obs['native_ids']))==43
        np.testing.assert_allclose(obs['native_values_hz']-obs['graph_values_hz'],2*n.k.PERIOD,atol=1e-7,rtol=0)


def test_original_ordinary_screen_is_exact_and_no_privileged_label_port():
    raw,covariance,cat=fixture();actual=n.screen(raw,covariance,cat)
    reference=n.sr.previous.ordinary_screen(dict(raw_hz=raw,covariance_hz2=covariance),cat)
    for key in ['candidate_indices','candidate_norads','coarse_scores','ranked_visible_indices']:
        assert actual[key]==reference[key]
    assert list(inspect.signature(n.screen).parameters)==['raw','covariance','catalogue']
    assert not actual['forced_or_reserved_candidate'] and not actual['accepted'] and not actual['exact_identity_evidence']


def test_gaussian_phase_posterior_matches_dense_rank_one_conditioning():
    raw,covariance,cat=fixture();actual=n.screen(raw,covariance,cat)
    for j in range(len(cat['norads'])):
        alias=np.asarray(actual['coarse_aliases'])[j,0]
        a=cat['derivative_hz_per_s'][j]*cat['phase_sd_s'][j]
        residual=raw+alias*n.k.PERIOD-cat['frequency_hz'][j]
        z=float(a@np.linalg.solve(covariance+np.outer(a,a),residual))
        assert actual['phase_z'][j]==pytest.approx(z,abs=1e-11)
        expected=cat['phase_means_s'][j]+cat['phase_sd_s'][j]*z
        assert actual['linear_phase_mean_s'][j]==pytest.approx(expected,abs=1e-11)


def test_portion_visibility_is_not_whole_owner_visibility():
    raw,covariance,cat=fixture()
    cat['mean_elevation_deg']=np.ones_like(cat['frequency_hz']);cat['mean_elevation_deg'][3,-1]=-2.
    short=n.select_catalogue(cat,np.arange(6));whole=n.select_catalogue(cat,np.arange(12))
    assert short['minimum_mean_elevation_deg'][3]>0 and whole['minimum_mean_elevation_deg'][3]<0
    assert 3 in n.screen(raw[:6],covariance[:6,:6],short)['ranked_visible_indices']
    assert 3 not in n.screen(raw,covariance,whole)['ranked_visible_indices']


def test_unrestricted_original_alias_and_phase_are_never_clipped():
    raw,covariance,cat=fixture();raw=raw+7*n.k.PERIOD
    cat['phase_means_s'][:]=20.
    result=n.screen(raw,covariance,cat)
    assert np.all(np.asarray(result['coarse_aliases'])==-7)
    assert not np.asarray(result['nearest_alias_in_finite_exact_support']).any()
    assert not np.asarray(result['phase_mean_in_operational_domain']).all()


def test_integer_graph_gauge_changes_alias_only_not_score_or_phase():
    raw,covariance,cat=fixture();first=n.screen(raw,covariance,cat);second=n.screen(raw+n.k.PERIOD,covariance,cat)
    np.testing.assert_array_equal(np.asarray(second['coarse_aliases']),np.asarray(first['coarse_aliases'])-1)
    np.testing.assert_allclose(first['coarse_scores'],second['coarse_scores'],atol=1e-7,rtol=0)
    np.testing.assert_allclose(first['phase_z'],second['phase_z'],atol=1e-10,rtol=0)


def test_overlay_native_gauge_has_same_radio_conditioned_residual():
    raw,covariance,cat=fixture();result=n.screen(raw,covariance,cat)
    radio=np.linspace(12,18,len(raw));graph=raw+radio;native=graph+2*n.k.PERIOD
    j=result['candidate_indices'][0];alias=np.asarray(result['coarse_aliases'])[j,0]
    linear=cat['frequency_hz'][j]+cat['derivative_hz_per_s'][j]*cat['phase_sd_s'][j]*result['phase_z'][j]
    prediction=linear+radio-alias*n.k.PERIOD+2*n.k.PERIOD
    np.testing.assert_allclose(native-prediction,raw+alias*n.k.PERIOD-linear,atol=1e-9,rtol=0)


def test_original_duration_curvature_predicate_and_no_gate_waiver():
    for duration in [10.,20.,30.]:
        t=np.linspace(0,duration,40)
        for scale in [1.,1000.]:
            y=50*t+scale*np.sin(t)
            flags=n.eligibility(t,y)
            assert flags['original_duration_and_curvature_eligible']==raw_curvature(dict(times=t,values=y))
            assert not flags['portion_adopted'] and not flags['fresh_original_residual_gates_tested']


def test_archived_background_marginals_and_response_redaction_immutable():
    cat=n.arrays(n.HERE/'inputs/catalogue.npz');original=cat['frequency_hz'].copy()
    for arm in n.ARMS:
        obs=n.arrays(n.HERE/'inputs'/(arm+'.npz'))
        for name,use in n.selections():
            covariance=obs['covariance_hz2'][np.ix_(use,use)]
            np.linalg.cholesky(covariance)
            assert len(use)==len(obs['native_ids'][use])
    np.testing.assert_array_equal(cat['frequency_hz'],original)
