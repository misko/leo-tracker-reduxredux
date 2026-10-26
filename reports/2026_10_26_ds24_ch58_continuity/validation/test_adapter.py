"""Owned scientific boundary tests; fabricated receipts are test fixtures only."""

import copy
import json
from pathlib import Path

import pytest

from adapter import (Blocked, GATES, MATCHED_FIELDS, digest, file_sha, null_upper,
                     stage, validate_nulls, validate_position_pair)


def support(start, *, receiver=1, native_receiver_id=0, channel=5, rf=12040312500.):
    return dict(recording_id='test-recording',stream_generation='test-generation',
        raw_authority_digest='test-authority',native_receiver_id=native_receiver_id,
        receiver=receiver,channel=channel,edge='upper',start_counter=start,
        end_counter=start+200000,sample_rate_hz=10000000,actual_rf_hz=rf)


@pytest.fixture
def panel(tmp_path):
    inventory=[dict(observation_id=f'oid{i}',support=support(i*3540000),
        time_s=i*.354+.01,existing_winner=i<2) for i in range(3)]
    observations=[dict(observation_id=r['observation_id'],
        receiver=r['support']['receiver'],native_receiver_id=r['support']['native_receiver_id'],
        channel=5,time_s=r['time_s'],measured_cfo_hz=12345.123456789+i,
        actual_rf_hz=r['support']['actual_rf_hz'],fractional_margin=.125)
        for i,r in enumerate(inventory[:2])]
    evidence=tmp_path/'fabricated_TEST_ONLY_evidence.json'
    evidence.write_text(json.dumps({'test_only':True}))
    receipt=dict(protocol_sha256='protocol',baseline_receipt_sha256='baseline',
        independent_review=True,development_only=True,gates={g:'pass' for g in GATES},
        evidence_artifacts={str(evidence):file_sha(evidence)},qualified_proposal_digests=[],
        null_exposure=dict(conditional_on_same_donor_state=True,same_full_proposal_search=True,
            family_exposure=96,independent_grouping_documented=True,
            false_confirmations=0,independent_trials=6000))
    return observations,inventory,receipt


def proposal(panel, *, index=1, kind='correct_existing'):
    observations,inventory,receipt=panel
    p=dict(target_observation_id=f'oid{index}',kind=kind,
        measurement_support=copy.deepcopy(inventory[index]['support']),
        measured_cfo_hz=13000.987654321,sigma_hz=73.,
        measurement_kind='target_only_likelihood',
        uncertainty_kind='calibrated_target_likelihood_sd_hz',mode_count=1,
        full_scan_track_prediction_used=False,
        donors=[dict(observation_id='oid0',support=inventory[0]['support'],role='conditioning_only')])
    if index<len(observations):
        p['expected_existing_cfo_hz']=observations[index]['measured_cfo_hz']
    return p


def reviewed(panel,p):
    p=copy.deepcopy(p)
    p['proposal_digest']=digest(p)
    panel[2]['qualified_proposal_digests'].append(p['proposal_digest'])
    return p


def run(panel,proposals):
    return stage(*panel[:2],proposals,panel[2],'protocol','baseline')


def test_unchanged_baseline_exact(panel):
    before=copy.deepcopy(panel[0])
    out=run(panel,[])
    assert out['observations']==before==panel[0]
    assert out['observations'] is not panel[0]
    assert out['status']=='baseline_unchanged'
    assert not out['geographic_evaluation_permitted']


def test_correction_replaces_owner_preserves_precision_rf_and_metadata(panel):
    before=copy.deepcopy(panel[0])
    p=reviewed(panel,proposal(panel))
    out=run(panel,[p])
    assert len(out['observations'])==len(before)
    assert out['corrected_existing']==1 and out['new_native_detections']==0
    assert out['observations'][0]==before[0]
    changed={k:v for k,v in out['observations'][1].items() if before[1][k]!=v}
    assert changed=={'measured_cfo_hz':p['measured_cfo_hz']}
    assert out['changes'][0]['actual_rf_scale']==12040312500./11.5e9
    assert out['changes'][0]['calibration_group']==1
    assert panel[0]==before
    assert not out['position_execution_authorized']


def test_new_native_detection_increases_count_once(panel):
    p=reviewed(panel,proposal(panel,index=2,kind='new_native_detection'))
    out=run(panel,[p])
    assert out['new_native_detections']==1 and out['corrected_existing']==0
    assert len(out['observations'])==3
    assert out['observations'][-1]['time_s']==panel[1][2]['time_s']


@pytest.mark.parametrize('field,value,message',[
    ('measurement_kind','donor_conditioned_posterior','joint covariance'),
    ('kind','donor_carry','only corrections'),
    ('uncertainty_kind','GLRT_margin','calibrated target'),
    ('mode_count',2,'multiple same-target'),
    ('full_scan_track_prediction_used',True,'earlier-only'),
    ('expected_existing_cfo_hz',12345,'exact existing'),
])
def test_information_source_and_authority_rejections(panel,field,value,message):
    p=proposal(panel);p[field]=value
    with pytest.raises(Blocked,match=message):
        run(panel,[reviewed(panel,p)])


def test_unreviewed_or_modified_candidate_blocked(panel):
    p=reviewed(panel,proposal(panel))
    p['sigma_hz']=1.
    with pytest.raises(Blocked,match='changed after RF review'):
        run(panel,[p])


def test_modes_aliases_and_repeated_targets_not_independent(panel):
    p=reviewed(panel,proposal(panel))
    with pytest.raises(Blocked,match='duplicate target/mode'):
        run(panel,[p,p])
    p=reviewed(panel,proposal(panel,index=1,kind='new_native_detection'))
    with pytest.raises(Blocked,match='already has'):
        run(panel,[p])


@pytest.mark.parametrize('field,value',[
    ('native_receiver_id',1),('receiver',2),('channel',8),('edge','lower'),
    ('actual_rf_hz',11500000000.),('start_counter',0),
])
def test_native_raw_and_actual_rf_mapping_cannot_drift(panel,field,value):
    p=proposal(panel);p['measurement_support'][field]=value
    with pytest.raises(Blocked,match='identity|support interval'):
        run(panel,[reviewed(panel,p)])


def test_target_cannot_serve_as_donor(panel):
    p=proposal(panel)
    p['donors']=[dict(observation_id='oid1',support=panel[1][1]['support'],role='conditioning_only')]
    with pytest.raises(Blocked,match='overlaps target'):
        run(panel,[reviewed(panel,p)])


def test_existing_alias_labels_cannot_make_overlapping_iq_independent(panel):
    extra=copy.deepcopy(panel[1][0]);extra['observation_id']='alias'
    extra['support']['channel']=8;extra['support']['actual_rf_hz']=12700000000.
    panel[1].append(extra)
    with pytest.raises(Blocked,match='overlaps independently owned'):
        run(panel,[])


def test_small_zero_false_alarm_experiment_is_insufficient(panel):
    r=panel[2]['null_exposure'];r['independent_trials']=100
    with pytest.raises(Blocked,match='cannot certify'):
        validate_nulls(r)
    r['independent_trials']=6000
    assert validate_nulls(r)['family_upper_95']<.05
    assert null_upper(0,1)==pytest.approx(.95)
    assert null_upper(1,2)==pytest.approx(.9746794344808963)


def test_correlated_null_repeats_not_independent(panel):
    r=panel[2]['null_exposure'];r['independent_grouping_documented']=False
    with pytest.raises(Blocked,match='correlated null'):
        validate_nulls(r)


def test_rf_evidence_hash_and_all_gates_required(panel):
    p=reviewed(panel,proposal(panel))
    panel[2]['gates']['natural_target_support']='unknown'
    with pytest.raises(Blocked,match='all independent RF gates'):
        run(panel,[p])
    panel[2]['gates']['natural_target_support']='pass'
    path=next(iter(panel[2]['evidence_artifacts']))
    Path(path).write_text('changed')
    with pytest.raises(Blocked,match='artifact missing or changed'):
        run(panel,[p])


def position_pair():
    common={f:'sealed-'+f for f in MATCHED_FIELDS}
    common.update(search_budget=dict(phase_rounds=5,iterations=48),
        region_center=[37.906,-122.545],box_width_km=25.,start_east_north_km=[0.,0.],
        GPS_used=False,post_scan_TLE_used=False,causal_graph_review_passed=True,
        primary_execution_approval=True)
    return dict(common,arm='c0'),dict(common,arm='fitted_c')


def test_c_ablation_is_matched_and_regional():
    c0,fc=position_pair()
    assert validate_position_pair(c0,fc)
    fc['candidate_catalog_sha256']='different'
    with pytest.raises(Blocked,match='candidate_catalog'):
        validate_position_pair(c0,fc)


@pytest.mark.parametrize('field,value',[
    ('GPS_used',True),('post_scan_TLE_used',True),
    ('primary_execution_approval',False),('causal_graph_review_passed',False),
])
def test_position_dependency_gates(field,value):
    c0,fc=position_pair();fc[field]=value
    with pytest.raises(Blocked):
        validate_position_pair(c0,fc)
