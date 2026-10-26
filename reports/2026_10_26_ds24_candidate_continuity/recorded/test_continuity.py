import numpy as np
from continuity import global_phase, linear_path, CFO_PERIOD


def test_counter_phase_uses_exact_rational_period_and_origin():
    origin = 1613490476683
    assert global_phase(origin, origin, 127.25, 10_000_000) == 127.25
    assert abs(global_phase(origin+40_000, origin, 127.25, 10_000_000)-127.25) < 1e-9
    assert abs(global_phase(origin+13_333, origin, 127.25, 10_000_000)-(127.25-1/3)) < 1e-9
    assert global_phase(origin+13_333, origin, 127.25, 10_000_000) != 127.25


def fixture():
    return [dict(candidate_id=str(i), window_id=str(i), time_s=float(i), cfo_hz=1000+100*i,
                 global_epoch_samples=(13332+2*i)%(10_000_000/750), margin=.1, candidate_rank=1) for i in range(6)]


def test_known_path_wrap_and_permutation():
    rows=fixture(); r=linear_path(rows,10_000_000)
    assert r['points']==6 and r['span_s']==5
    assert abs(r['epoch_rate_samples_s']-2)<1e-9
    assert linear_path(list(reversed(rows)),10_000_000)==r
    shifted=[dict(x,cfo_hz=x['cfo_hz']+2*CFO_PERIOD) for x in rows]
    assert linear_path(shifted,10_000_000)['candidate_ids']==r['candidate_ids']


def test_repeated_candidate_same_window_cannot_supply_persistence():
    rows=fixture()
    for r in rows:r['window_id']='one'
    assert linear_path(rows,10_000_000) is None


def test_epoch_drift_and_gap_fail_without_rule_relaxation():
    rows=fixture()
    for r in rows:r['global_epoch_samples']=(r['time_s']*900)%(10_000_000/750)
    assert linear_path(rows,10_000_000) is None


def test_window_port_preserves_historical_native_id_separately():
    from inventory import window
    probe=dict(valid_start_counter=100,probe_start_ms=0,actual_rf_hz=10e9,
        receiver_id=0,channel=1,visit_index=0,probe_index=0,candidates=[dict(
        candidate_rank=0,passed_fractional_margin_gate=True,integer_epoch_sample=100,
        fractional_epoch_offset_samples=.25,fractional_tracking_cfo_hz=1000.,
        fractional_margin=.1,fractional_exact_score=.2,fractional_control_score=.1)])
    source=dict(sample_rate_hz=10_000_000,probe_ms=20,session_id='fixture',
        input_manifest_sha256='fixture',stream_generation='fixture')
    native=dict(observation_id='historical-native-id',measured_cfo_hz=1000.,fractional_margin=.1)
    w,rows=window(probe,source,100,native,'fixture-owner')
    assert w['observation_id']==rows[0]['observation_id']=='historical-native-id'
    assert w['window_id']!=w['observation_id']
    assert rows[0]['acquired_cfo_hz'] is None and rows[0]['global_epoch_samples']==100.25
    rows=fixture()
    for r in rows:r['time_s']*=4
    assert linear_path(rows,10_000_000) is None
