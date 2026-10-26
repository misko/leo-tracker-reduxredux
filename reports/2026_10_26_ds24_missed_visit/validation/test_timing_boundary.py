"""Independent source-boundary tests; mocked scores, no RF control outcomes."""

import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pytest

HERE=Path(__file__).resolve().parent
TIMING=HERE.parent/'timing'
RUNTIME=Path('/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src')
sys.path.insert(0,str(RUNTIME))


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod


t=load('independent_timing_boundary',TIMING/'timing_search.py')
adapter=load('independent_timing_adapter_boundary',TIMING/'adapter.py')


def test_same_modes_point_and_search_are_durably_sealed_before_confirmation(monkeypatch,tmp_path):
    events=[];path=tmp_path/'selection.json'
    def score(samples,rate,edge,mode,offsets,ownership,group,cache=None):
        events.append(group)
        if group=='confirmation':
            assert path.exists()
            receipt=json.loads(path.read_text())
            assert receipt['selected']['mode_index']==0
            assert receipt['point_selected']['mode_index']==1
        out=[]
        for offset in offsets:
            margin=.3 if mode['mode_id']=='mode0' and offset==8 else .2 if mode['mode_id']=='mode1' and offset==0 else .1
            out.append(dict(status='complete',margin=margin,offset_samples=int(offset),
                epoch_samples=1000.+int(offset),tracking_cfo_hz=100.,frames=3))
        return out
    monkeypatch.setattr(t,'scores',score)
    def seal(receipt):
        assert 'confirmation' not in events
        events.append('durable_seal')
        path.write_text(json.dumps(receipt))
    modes=[dict(mode_id=f'mode{i}',epoch_samples=1000.,cfo_hz=100.,cfo_half_width_hz=500.,
        donors=[dict(support=dict(stop_counter=0))]) for i in range(2)]
    packet=dict(owner_id='test-only-owner',target_support=dict(start_counter=1000000,stop_counter=1200000),modes=modes)
    out=t.score_target(np.zeros(200000),10000000,'lower',packet,on_selected=seal)
    assert out['point']['selected']['mode_index']==1
    assert out['search']['selected']['mode_index']==0
    assert events.index('durable_seal')<events.index('confirmation')
    assert len(out['exposure'])==2*65+17


def test_whole_bank_partition_disjoint_including_wrap_and_interpolation_guards():
    ownership=t.partition(200000,10000000,3.25,'test-metadata-owner')
    search=[];confirmation=[]
    for epoch in (3.25,13000.1,6500.75):
        for offset in range(-256,257):
            effective=(epoch+offset)%(10000000/750.)
            for group,destination in [('search',search),('confirmation',confirmation)]:
                rows=t.geometry(200000,10000000,effective,ownership,group)
                destination.extend((r['sample_start'],r['sample_stop']) for r in rows)
    # All envelopes lie within fixed disjoint group intervals; one interval check
    # per generated block proves bank-wide separation without quadratic pairing.
    for group,blocks in [('search',search),('confirmation',confirmation)]:
        for a,b in blocks:
            assert any(i['group']==group and i['start']<=a<b<=i['stop'] for i in ownership['intervals'])
    assert search and confirmation
    assert not any(max(a['start'],b['start'])<min(a['stop'],b['stop'])
        for a in ownership['intervals'] if a['group']=='search'
        for b in ownership['intervals'] if b['group']=='confirmation')


def test_search_gate_is_diagnostic_and_far_CFO_is_not_continuity():
    score=dict(status='complete',margin=.04,tracking_cfo_hz=150.)
    search=dict(margin=-.01,tracking_cfo_hz=100.)
    result=t.confirmed(score,dict(cfo_hz=100.,cfo_half_width_hz=500.),search)
    assert result['admitted'] and not result['search_passed_gate']
    score['tracking_cfo_hz']=10000.
    result=t.confirmed(score,dict(cfo_hz=100.,cfo_half_width_hz=500.),search)
    assert result['pilot_confirmed'] and not result['continuity_compatible'] and not result['admitted']


def test_enriched_native_generation_and_stream_label_are_distinct():
    row=dict(header=dict(case='test',prediction_id='test/RX0',source_id='source',generation=9,
        stream_generation='stream-label',sample_rate_hz=10000000,start_counter=4000000,
        stop_counter=4200000,receiver_id=0),target_support=dict(start_counter=4000000,stop_counter=4200000,generation=9),
        forecast=dict(status='available',modes=[dict(hypothesis_id='mode',status='one_donor_fallback',
            missed_visits_after_latest=0,missed_visits_between_donors=0,
            donors=[dict(source_id='source',generation=9,stream_generation='stream-label',visit_index=1,
                start_counter=0,stop_counter=200000,support=dict(start_counter=0,stop_counter=200000,generation=9))],
            full=dict(epoch_samples=100.,timing_rate_samples_per_s=100.,reference_counter=4100000,
                CFO_hz=1000.,CFO_rate_hz_per_s=2000.,CFO_half_width_hz=500.,timing_half_width_samples=20.))]))
    packet=adapter.adapt(row)
    assert packet['target_support']['stream_generation']=='stream-label'
    assert packet['target_support']['native_generation']==9
    donor=packet['modes'][0]['donors'][0]['support']
    assert donor['stream_generation']=='stream-label' and donor['native_generation']==9
    assert packet['modes'][0]['epoch_samples']==101.
    assert packet['modes'][0]['reference_offset_s']==.01
