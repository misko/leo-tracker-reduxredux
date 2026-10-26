"""Additions-only and honest structural-order tests; no waveform outcomes."""

import copy
import json
from types import SimpleNamespace

import pytest

import candidate_ledger as ledger


@pytest.fixture
def native_case(monkeypatch):
    common=dict(recording_id='source',stream_generation='stream',raw_authority_digest='raw',
        native_receiver_id=0,receiver=1,channel=5,edge='lower',actual_rf_hz=11709687500.,sample_rate_hz=10000000)
    donor=dict(common,observation_id='donor',start_counter=0,stop_counter=200000,time_s=.01)
    target=dict(common,observation_id='target',start_counter=1000000,stop_counter=1200000,time_s=.11)
    original=[dict(observation_id='donor',receiver=1,native_receiver_id=0,channel=5,time_s=.01,
        actual_rf_hz=11709687500.,measured_cfo_hz=100.,fractional_margin=.1)]
    monkeypatch.setattr(ledger,'metadata_inventory',lambda _: ({},[donor,target],original))
    monkeypatch.setattr(ledger,'ordering_and_support',lambda *_:dict(kind='audited_source_order_and_durable_callback'))
    mode=dict(cfo_hz=100.,cfo_half_width_hz=4500.,cfo_reference_counter=1100000,mode_id='mode',
        donors=[dict(observation_id='old-candidate',support=dict(start_counter=0,stop_counter=200000,
            native_generation_verified=True,stream_generation='stream'))])
    selected=dict(mode_index=0)
    item=dict(selected=selected,confirmation=dict(status='complete',margin=.05,tracking_cfo_hz=150.,offset_samples=8),
        evaluation=dict(pilot_confirmed=True,continuity_compatible=True,admitted=True))
    result=dict(status='complete',owner_id='source/rx0/1000000:1200000',mode_provenance=[mode],
        target_support=dict(stream_generation='stream'),search=item,point=copy.deepcopy(item),exposure=[{}])
    header=dict(case='test',receiver_id=0,start_counter=1000000,channel=5,edge='lower',actual_rf_hz=11709687500.,
        sample_rate_hz=10000000,source_id='source')
    cell=dict(prediction_id='test/RX0',packet=dict(header=header,target_support=dict(stream_generation='stream')),
        result=result,original_fullwindow=dict(candidates=[]))
    window=dict(request_id='test',status='complete',public_source_parity=dict(full_reader_exhausted=True,
        parity={'0':dict(all_passed=True),'1':dict(all_passed=True)}),cells=[cell])
    return dict(rows=[window]),original,target


def test_only_new_owner_is_added_existing_values_are_preserved(native_case):
    doc,original,_=native_case
    out=ledger.build_ledger('test',doc,None)
    assert out['corrections']==0 and out['new_native_detections']==1
    assert out['observations'][:len(original)]==original
    assert out['staged'][0]['ordering_evidence']['kind']=='audited_source_order_and_durable_callback'
    assert not out['position_execution_authorized']


def test_existing_confirmation_never_automatically_replaces_original(native_case):
    doc,original,target=native_case
    original.append(dict(observation_id='target',receiver=1,native_receiver_id=0,channel=5,time_s=.11,
        actual_rf_hz=11709687500.,measured_cfo_hz=50.,fractional_margin=.4))
    out=ledger.build_ledger('test',doc,None)
    assert out['observations']==original
    assert out['corrections']==out['new_native_detections']==0
    assert out['counts']['admitted_existing_preserved']==1


def test_far_CFO_and_failed_native_replay_remain_visible(native_case):
    doc,_,_=native_case
    item=doc['rows'][0]['cells'][0]['result']['search']
    item['confirmation']['tracking_cfo_hz']=10000.
    item['evaluation'].update(continuity_compatible=False,admitted=False)
    out=ledger.build_ledger('test',doc,None)
    assert out['new_native_detections']==0
    assert out['all_target_outcomes'][0]['status']=='far_CFO_pilot_discovery_unresolved'
    doc['rows'][0].pop('public_source_parity');doc['rows'][0].update(status='failed',error='read failed')
    out=ledger.build_ledger('test',doc,None)
    assert out['counts']['windows_failed']==1 and out['missing_receiver_cells']==48


def test_recorded_callback_filename_uses_prediction_tag_not_owner(monkeypatch,tmp_path):
    original_order=ledger.ordering_and_support
    monkeypatch.setattr(ledger,'TIMING',tmp_path);(tmp_path/'selections').mkdir()
    receipt=dict(selected={'mode_index':0},point_selected={'mode_index':0},confirmation_accessed=False)
    from integration import digest
    receipt['selection_sha256']=digest(receipt)
    (tmp_path/'selections/test_RX0.json').write_text(json.dumps(receipt))
    for name in ('timing_search.py','study.py'):(tmp_path/name).write_text('test-only source')
    ownership=dict(intervals=[])
    result=dict(owner_id='different/raw-owner',selection_receipt=receipt,ownership=ownership,
        point=dict(selected={'mode_index':0},confirmation=dict(status='unavailable')),
        search=dict(selected={'mode_index':0},confirmation=dict(status='unavailable')),exposure=[])
    out=original_order(result,SimpleNamespace(digest=digest),'test/RX0')
    assert out['no_wall_clock_confirmation_start_claim']
    assert out['selection_path'].endswith('test_RX0.json')
