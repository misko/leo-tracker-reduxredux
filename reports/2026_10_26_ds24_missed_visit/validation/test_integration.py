"""Owned tests for practical RF screens and exact native observation staging."""

import copy

import pytest

from baseline_scope import native_row
from integration import (Blocked,bank_reuse_audit,graph_inputs_changed,screen_controls,
                         stage_observations,upper95)


def controls():
    strong=[dict(independent_target_id=f'strong{i}',admitted=True,cfo_error_hz=(-1)**i*200.,
        edge='lower' if i%2 else 'upper',true_rate_hz_s=(-1)**i*2000.,
        donor_error_hz=(-1)**i*500.,timing_error_samples=(-1)**i*64.) for i in range(24)]
    nulls={'full_bank':[dict(independent_target_id=f'null{i}',complete_selection_repeated=True,
        confirmed=False) for i in range(32)]}
    return strong,nulls


def test_practical_screen_measurable_without_global_FAR_claim():
    out=screen_controls(*controls())
    assert out['exploratory_RF_screen_passed']
    assert out['nulls']['full_bank']['upper95']==pytest.approx(.0893681989862648)
    assert not out['global_familywise_FAR_qualified']
    assert not out['promotion_authorized']


def test_strong_failures_and_nonindependence_not_hidden():
    strong,nulls=controls();strong[0]['admitted']=False;strong[1]['cfo_error_hz']=1500.
    assert not screen_controls(strong,nulls)['exploratory_RF_screen_passed']
    strong[1]=strong[0]
    with pytest.raises(Blocked,match='independent trials'):
        screen_controls(strong,nulls)


def test_full_null_exposure_and_trial_precision_required():
    strong,nulls=controls();nulls['full_bank']=nulls['full_bank'][:10]
    assert not screen_controls(strong,nulls)['exploratory_RF_screen_passed']
    strong,nulls=controls();nulls['full_bank'][0]['complete_selection_repeated']=False
    with pytest.raises(Blocked,match='exposure'):
        screen_controls(strong,nulls)
    assert upper95(0,1)==pytest.approx(.95)
    assert upper95(1,2)==pytest.approx(.9746794344808963)


@pytest.fixture
def fixture():
    first=10**12
    probes=[dict(receiver_id=0,channel=5,edge='lower',actual_rf_hz=11709687500.,
        valid_start_counter=first+3540000*i,visit_index=i,probe_index=0) for i in range(3)]
    document=dict(clock_anchor=dict(sample_counter=first),source=dict(probes=probes,
        session_id='session',stream_generation='generation',sample_rate_hz=10000000,
        raw_recording_authority_digest='raw',input_manifest_sha256='input',probe_ms=20))
    native=[native_row(document,p) for p in probes]
    original=[]
    for n in native[:2]:
        row={k:n[k] for k in ('observation_id','receiver','native_receiver_id','channel','time_s','actual_rf_hz')}
        row.update(measured_cfo_hz=123456.123456789,fractional_margin=.1);original.append(row)
    return document,native,original


def candidate(fixture,index=2):
    _,native,_=fixture;n=native[index];start=n['start_counter']
    return dict(target_observation_id=n['observation_id'],native=copy.deepcopy(n),
        measurement_source='unchanged_later_sample_scorer',uses_donor_posterior_penalty=False,
        original_target_used_for_selection=False,confirmation_retuned=False,
        selection_sealed_utc_ns=1,confirmation_started_utc_ns=2,
        reference_counter=start+100000,scope='development',
        support_partition=dict(covers_entire_proposal_bank=True,includes_interpolation_guards=True,
            all_search_envelopes=[[start+100,start+500],[start+1000,start+2000]],
            confirmation_envelopes=[[start+5000,start+6000]]),
        confirmation=dict(cfo_hz=123457.123456789,margin=.05),
        donors=[dict(native_observation_id=native[0]['observation_id'])],
        prediction_at_reference=dict(cfo_hz=123400.,frozen_half_width_hz=1000.),
        association_claim='donor_continuation',proposal_exposure=dict(modes=8,coarse=65,refine=17))


def stage(fixture,candidates):
    document,_,original=fixture
    return stage_observations(document,original,candidates,screen_controls(*controls()))


def test_new_native_and_no_change_semantics(fixture):
    assert stage(fixture,[])['observations']==fixture[2]
    p=candidate(fixture);out=stage(fixture,[p])
    assert out['new_native_detections']==1 and out['corrections']==0
    assert len(out['observations'])==3
    assert out['staged'][0]['actual_RF_scale']==11709687500./11.5e9
    assert out['staged'][0]['receiver_band_offset_group']==1
    assert not out['position_execution_authorized'] and not out['qualified_promotion']
    assert len(fixture[2])==2


def test_correction_preserves_owner_and_every_other_field(fixture):
    p=candidate(fixture,1);before=copy.deepcopy(fixture[2])
    p['expected_existing_cfo_hz']=before[1]['measured_cfo_hz']
    out=stage(fixture,[p]);assert len(out['observations'])==2
    assert out['corrections']==1 and out['new_native_detections']==0
    assert out['observations'][0]==before[0]
    assert {k:v for k,v in out['observations'][1].items() if before[1][k]!=v}=={'measured_cfo_hz':p['confirmation']['cfo_hz']}


def test_entire_mode_bank_and_interpolation_guards_own_support(fixture):
    p=candidate(fixture);s=p['native']['start_counter']
    # The selected mode could be clean while another tested mode consumes confirmation.
    p['support_partition']['all_search_envelopes'].append([s+5900,s+6200])
    with pytest.raises(Blocked,match='not disjoint'):
        stage(fixture,[p])
    p=candidate(fixture);p['support_partition']['includes_interpolation_guards']=False
    with pytest.raises(Blocked,match='every mode'):
        stage(fixture,[p])


@pytest.mark.parametrize('field,value,message',[
    ('measurement_source','donor_carry','not a new measurement'),
    ('uses_donor_posterior_penalty',True,'posterior information'),
    ('original_target_used_for_selection',True,'archived oracle'),
    ('confirmation_retuned',True,'cannot retune'),
    ('selection_sealed_utc_ns',3,'sealed before'),
    ('reference_counter',0,'baseline midpoint'),
    ('scope','validation','held-validation'),
])
def test_causal_information_and_selection_boundaries(fixture,field,value,message):
    p=candidate(fixture);p[field]=value
    with pytest.raises(Blocked,match=message):stage(fixture,[p])


def test_far_FFT_pilot_support_does_not_prove_donor_continuity(fixture):
    p=candidate(fixture);p['confirmation']['cfo_hz']+=10000
    with pytest.raises(Blocked,match='not donor continuity'):stage(fixture,[p])
    p['association_claim']='independent_pilot_discovery'
    out=stage(fixture,[p])
    assert out['staged'][0]['pilot_confirmed']
    assert not out['staged'][0]['frequency_prediction_compatible']
    assert not out['position_execution_authorized']


def test_alias_alternatives_and_receivers_do_not_duplicate_native_owner(fixture):
    p=candidate(fixture)
    with pytest.raises(Blocked,match='duplicate target'):stage(fixture,[p,p])
    p['native']['receiver']=2
    with pytest.raises(Blocked,match='mapping drift'):stage(fixture,[p])


def test_changed_observations_require_graph_and_bank_support_audit(fixture):
    original=fixture[2];new=stage(fixture,[candidate(fixture)])['observations']
    audit=graph_inputs_changed(original,new,[],[])
    assert audit['bank_full_catalogue_and_time_support_audit_required']
    assert audit['fresh_radio_noise_and_graph_receipts_required']
    assert not audit['old_bank_receipt_valid_for_new_inputs']


def test_complete_regional_causal_bank_reuse_requires_time_and_phase_margins():
    receipt=dict(reference_position_used=False,search_center=[37.906,-122.545],
        search_box_width_km=25.,cutoff_utc_ns=100)
    elements={'1':dict(provenance=dict(element_epoch_utc_ns=99,collected_utc_ns=99))}
    tracks=[dict(times=[1.,299.])]
    assert bank_reuse_audit([-17.,318.],[1],elements,receipt,tracks,tracks)['reuse_allowed']
    changed=[dict(times=[1.,304.])]
    assert not bank_reuse_audit([-17.,318.],[1],elements,receipt,tracks,changed)['reuse_allowed']
    with pytest.raises(Blocked,match='complete declared'):bank_reuse_audit([-17.,318.],[1,2],elements,receipt,tracks,tracks)
    elements['1']['provenance']['collected_utc_ns']=101
    with pytest.raises(Blocked,match='noncausal'):bank_reuse_audit([-17.,318.],[1],elements,receipt,tracks,tracks)
