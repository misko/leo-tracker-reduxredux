import pytest
from ds23_delivery_clock_bounds import delivery_interval


def document():
    return dict(source=dict(sample_rate_hz=1000,probe_ms=10,
        probes=[dict(visit_index=0,probe_start_ms=0,valid_start_counter=100)]),
        clock_anchor=dict(sample_counter=0,before=dict(realtime_ns=1000000000,monotonic_ns=1000000000),
                          after=dict(realtime_ns=1250000000,monotonic_ns=1250000000)),
        delivery_clocks=[dict(realtime_ns=1169000000,monotonic_ns=1169000000)])


def test_delivered_samples_impose_an_upper_bound_not_an_exact_clock():
    result=delivery_interval(document(),1125000000)
    assert result['lower_s']==-.125
    assert result['upper_s']==pytest.approx(-.065)
    assert result['witness']['last_sample_counter']==109
    assert result['width_s']==pytest.approx(.06)
    assert result['no_minimum_network_latency_assumed']


def test_probe_to_delivery_mapping_must_be_explicit():
    d=document();d['source']['probes'][0]['visit_index']=2
    with pytest.raises(ValueError,match='matching delivery'):delivery_interval(d,1125000000)


def test_impossible_counter_clock_chronology_is_rejected():
    d=document();d['delivery_clocks'][0]=dict(realtime_ns=1000000000,monotonic_ns=1000000000)
    with pytest.raises(ValueError,match='no feasible'):delivery_interval(d,1125000000)


def test_adaptive_contract_keeps_original_interval_without_invented_delivery():
    d=dict(timing=dict(qualified=True,first_sample_earliest_utc_ns=1000000000,first_sample_latest_utc_ns=1360000000))
    r=delivery_interval(d,1180000000)
    assert not r['delivery_bound_used']
    assert r['lower_s']==-.18 and r['upper_s']==.18
