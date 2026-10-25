"""Owned narrow-port tests; synthetic arrays only, no corpus propagation."""
import copy
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pytest
import witness as w


def fake_context():
    tracks = []
    for i in range(3):
        tracks.append(dict(key='t'+str(i), times=np.arange(3.)+i*5, rf_hz=(11.4+i*.1)*1e9,
            receiver=2 if i<2 else 1, channel=i+3, values=np.arange(3.)*10+i,
            observation_ids=['id'+str(i)+str(j) for j in range(3)]))
    scan = SimpleNamespace(tracks=tracks, rx_basis=[np.ones((3,1)) for _ in tracks], radio_sigma_hz=2.,
        fixed_window_noise=dict(extra_parameter_BIC_gain=0, per_observation_noise_sigma_hz={}))
    features = np.arange(44.).reshape(4,11)/30
    parent = dict(features=features, coefficient=np.arange(11.)/10,
        coefficient_prior_precision=np.ones(11), noise_precision=np.array([1.2]))
    p = SimpleNamespace(scan=scan, labels=[0,1], hardware=np.zeros((4,9)), smooth=np.zeros((4,2)),
        members=[0], noise_groups=np.zeros(4,int), keep=np.ones(4,bool), point_noise=np.ones(4)*2,
        fitted_c=False, calculate=lambda x:parent, curved_calculate=lambda x:parent)
    d = dict(scan=scan, base=p, powers=np.ones(1), entries=[], arms={'c0':dict(phase_reference=[0,0])})
    entries = [dict(track_index=i, component='t'+str(i), candidate_index=i%2, alias=i+2,
        observation_ids=tracks[i]['observation_ids']) for i in range(2)]
    return d, p, parent, entries


def test_radio_label_and_alias_are_not_screen_inputs():
    d,p,parent,entries = fake_context()
    with patch.object(w.k.owners.m.r, 'build', return_value=p):
        first = w.background(d,'c0',np.zeros(2),entries)
        relabeled = [dict(e,candidate_index=9000,alias=-99) for e in entries]
        second = w.background(d,'c0',np.zeros(2),relabeled)
    for key in ('raw','covariance','parent_coefficients','parent_noise'):
        np.testing.assert_array_equal(first[key],second[key])
    assert [e['alias'] for e in entries] == [2,3]
    assert w.clean_entries(d,entries)[0]['alias'] == 0


def test_joint_marginal_equals_independent_and_other_CFO_redaction():
    d,p,parent,entries = fake_context()
    before = copy.deepcopy(parent)
    with patch.object(w.k.owners.m.r, 'build', return_value=p):
        joint = w.background(d,'c0',np.zeros(2),entries)
        single = w.background(d,'c0',np.zeros(2),entries[:1])
        p.scan.tracks[1]['values'] = np.array([1e7,-1e8,1e9])
        redacted = w.background(d,'c0',np.zeros(2),entries)
    own = w.marginal(joint,joint['slices'][0])
    for key in ('raw','covariance'):
        np.testing.assert_allclose(own[key],single[key],atol=0,rtol=0)
        np.testing.assert_array_equal(own[key],w.marginal(redacted,redacted['slices'][0])[key])
    for key in before:
        np.testing.assert_array_equal(before[key],parent[key])
    assert np.max(abs(joint['covariance'][:3,3:])) > 0  # shared radio uncertainty retained


def test_target_CFO_never_calibrates_parent_or_covariance():
    d,p,parent,entries = fake_context()
    with patch.object(w.k.owners.m.r,'build',return_value=p):
        first = w.background(d,'c0',np.zeros(2),entries)
        p.scan.tracks[0]['values'] = p.scan.tracks[0]['values']+1234
        second = w.background(d,'c0',np.zeros(2),entries)
    for key in ('covariance','parent_coefficients','parent_noise'):
        np.testing.assert_array_equal(first[key],second[key])
    np.testing.assert_allclose(second['raw'][:3]-first['raw'][:3],1234)
    np.testing.assert_array_equal(second['raw'][3:],first['raw'][3:])


def toy_catalogue():
    return dict(norads=np.arange(100,112),frequency_hz=np.arange(12.)[:,None]*np.ones((12,3)),
        derivative_hz_per_s=np.ones((12,3))*.1,phase_sd_s=np.ones(12),
        minimum_mean_elevation_deg=np.ones(12),phase_means_s=np.zeros(12))


def test_ordinary_screen_has_no_truth_backfill_and_rejects_extra_fields():
    cat = toy_catalogue()
    obs = dict(raw_hz=np.array([2.,2.2,1.9]),covariance_hz2=np.eye(3))
    a = w.sr.previous.ordinary_screen(obs,cat)
    assert a['candidate_norads'][0] == 102 and len(a['candidate_norads']) == 8
    assert a['forced_or_reserved_candidate'] is False
    with pytest.raises(ValueError):
        w.sr.previous.ordinary_screen(dict(obs,true_norad=111),cat)


def test_radio_only_relabeling_preserves_actual_ordinary_shortlist():
    d,p,parent,entries = fake_context()
    with patch.object(w.k.owners.m.r,'build',return_value=p):
        first = w.background(d,'c0',np.zeros(2),entries[:1])
        second = w.background(d,'c0',np.zeros(2),[dict(entries[0],candidate_index=999,alias=999)])
    cat = toy_catalogue()
    a = w.sr.previous.ordinary_screen(dict(raw_hz=first['raw'],covariance_hz2=first['covariance']),cat)
    b = w.sr.previous.ordinary_screen(dict(raw_hz=second['raw'],covariance_hz2=second['covariance']),cat)
    for key in a:
        np.testing.assert_equal(a[key],b[key])


def test_common_position_does_not_mutate_old_arm_endpoints():
    d = dict(arms={a:dict(endpoint_east_north_km=np.array([i,i+1]),phase_reference=[1]) for i,a in enumerate(w.ARMS)})
    changed = w.at_common_position(d,np.array([7.,9.]))
    for arm in w.ARMS:
        np.testing.assert_array_equal(changed['arms'][arm]['endpoint_east_north_km'],[7,9])
    np.testing.assert_array_equal(d['arms']['c0']['endpoint_east_north_km'],[0,1])


def test_native_coverage_duplicates_or_owner_overlap_fail_shut():
    d,p,parent,entries = fake_context()
    selected = [dict(component=t['key'],observation_ids=t['observation_ids']) for t in p.scan.tracks]
    coverage = {a:dict(accepted_observation_ids=['id00']) for a in w.ARMS}
    with pytest.raises(ValueError,match='overlaps'):
        w.native_entries(d,selected,coverage)


def test_order_certificate_precision_and_null_guard_are_separate():
    row = dict(status='complete',norad=10,certified_visibility=True,
        full_support_lower_log_integral=-10.,full_support_upper_log_integral=-9.,numerically_qualified=False)
    null = dict(objective=100.,independent_dense_passed=True)
    proof = w.sr.certified_order([row],null)
    assert proof['proved'] and proof['winner_norad']==10
    assert not proof['absolute_score_precision_implied'] and not proof['operational_identity_assignment']
    assert not w.sr.certified_order([row],dict(null,independent_dense_passed=False))['proved']


def test_expired_budget_and_missing_parent_guard_fail_shut():
    with pytest.raises(TimeoutError):w.sr.alarm(0.)
    assert not w.hard_parent(dict(phase_qualified=True,precision_qualified=False,support_qualified=True))
