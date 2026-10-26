"""Owned exact native-counter/public-winner binding tests with local fixtures."""

import json
from pathlib import Path

import pytest

import baseline


def inventory_fixture(tmp_path,monkeypatch):
    case='fixture';folder=tmp_path/case;folder.mkdir()
    anchor=10**12
    probes=[dict(valid_start_counter=anchor+10700003,receiver_id=rx,channel=5,
        edge='lower',actual_rf_hz=11709687500.,visit_index=4,probe_index=0,
        payload_start_sample=100000,candidates=[]) for rx in (0,1)]
    source=dict(sample_rate_hz=10000000,probe_ms=20,session_id='native-session',
        stream_generation='native-generation',raw_recording_authority_digest='raw-digest',probes=probes)
    document=dict(source=source,clock_anchor=dict(sample_counter=anchor))
    saved=[]
    for p in probes:
        import hashlib
        oid='sha256:'+hashlib.sha256(f"native-session:{p['receiver_id']}:{p['valid_start_counter']}".encode()).hexdigest()
        saved.append(dict(observation_id=oid,native_receiver_id=p['receiver_id'],
            receiver=p['receiver_id']+1,channel=5,actual_rf_hz=11709687500.,
            measured_cfo_hz=123.123456789,time_s=1.0800003,fractional_margin=.1))
    (folder/'tracking.json').write_text(json.dumps(document))
    (folder/'observations.json').write_text(json.dumps(saved))
    monkeypatch.setattr(baseline,'SOURCE',tmp_path)
    return case,saved


def test_exact_native_support_retune_gap_receiver_and_rf(tmp_path,monkeypatch):
    case,saved=inventory_fixture(tmp_path,monkeypatch)
    rows,_=baseline.native_inventory(case,lambda _: (saved,{}))
    assert len(rows)==2
    for rx,row in enumerate(rows):
        assert row['support']['start_counter']==10**12+10700003
        assert row['support']['end_counter']==10**12+10900003
        assert row['support']['native_receiver_id']==rx
        assert row['support']['receiver']==rx+1
        assert row['support']['actual_rf_hz']==11709687500.
        assert row['time_s']==1.0800003
        assert row['payload_start_sample']==100000


def test_original_public_winner_drift_rejected(tmp_path,monkeypatch):
    case,saved=inventory_fixture(tmp_path,monkeypatch)
    changed=[dict(row,measured_cfo_hz=123.) for row in saved]
    with pytest.raises(ValueError,match='winning row replay differs'):
        baseline.native_inventory(case,lambda _: (changed,{}))


def test_rounded_time_cannot_replace_native_midpoint(tmp_path,monkeypatch):
    case,saved=inventory_fixture(tmp_path,monkeypatch)
    changed=[dict(row,time_s=1.08) for row in saved]
    (tmp_path/case/'observations.json').write_text(json.dumps(changed))
    with pytest.raises(ValueError,match='timestamp precision'):
        baseline.native_inventory(case,lambda _: (changed,{}))
