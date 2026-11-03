import copy
import hashlib
import json

import pytest

from audit_ds23_counter_time_semantics import audit_rows


def fixture():
    anchor=dict(sample_counter=1_000_000,before=dict(realtime_ns=10,monotonic_ns=1),
                after=dict(realtime_ns=20,monotonic_ns=11))
    rows=[];probes=[];clocks=[];observations=[]
    for visit,start in enumerate((1_000_000,1_100_000)):
        delivery=dict(realtime_ns=30+visit,monotonic_ns=21+visit);clocks.append(delivery)
        receipt=dict(source_rate_hz=2_500_000,valid_start=start,valid_end=start+50_000,
            visit=visit,session=42,generation=9,host_delivery_clock=delivery)
        if visit==0:receipt['utc_clock_bracket']=anchor
        rows.append(dict(acquisition=dict(global_visit=visit,sample_start=start,sample_end=start+50_000,
            counter_authority='hardware',device_session=42,generation=9,retune_receipt=json.dumps(receipt))))
        probes.append(dict(visit_index=visit,receiver_id=0,valid_start_counter=start,payload_start_sample=visit*50000))
        oid='sha256:'+hashlib.sha256(f'session:0:{start}'.encode()).hexdigest()
        observations.append(dict(observation_id=oid,time_s=(start-1_000_000)/2_500_000+.010))
    document=dict(source=dict(sample_rate_hz=2_500_000,probe_ms=20,session_id='session',probes=probes),
        clock_anchor=anchor,delivery_clocks=clocks)
    return rows,document,observations


def test_retune_gap_is_preserved_and_delivery_latency_does_not_warp_time():
    rows,document,observations=fixture()
    result=audit_rows(rows,document,observations)
    assert result['smallest_interwindow_counter_gap_samples']==50_000
    assert result['maximum_timestamp_difference_s']==0


def test_payload_index_substitution_and_changed_midpoint_are_detected():
    rows,document,observations=fixture()
    changed=copy.deepcopy(document);changed['source']['probes'][1]['valid_start_counter']=50_000
    with pytest.raises(ValueError,match='payload indexing'):audit_rows(rows,changed,observations)
    observations[1]['time_s']-=.010
    with pytest.raises(ValueError,match='midpoint'):audit_rows(rows,document,observations)


def test_unannounced_counter_restart_or_provider_mismatch_is_detected():
    rows,document,observations=fixture()
    rows[1]['acquisition']['sample_start']=900_000
    receipt=json.loads(rows[1]['acquisition']['retune_receipt'])
    receipt['valid_start']=900_000
    rows[1]['acquisition']['retune_receipt']=json.dumps(receipt)
    with pytest.raises(ValueError,match='regressed'):audit_rows(rows,document,observations)
